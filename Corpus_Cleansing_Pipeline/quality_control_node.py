"""6.1 质量评估、专家审核与黄金集质控. 三个节点, 阈值都是节点参数, 可调:

    质量评估            规则 5 维 (完整性/可读性/规范性/合规性/标注完备性) + ecnu-plus 评审 4 项
                        (知识准确性/教育价值/适龄性/标注一致性, 1-5 分); 加权总分 -> A / B / C 档;
                        硬规则: 隐私残留直接 C 档, 任一评审项 <=2 分最多 B 档. 节点上显示批次质量报告.
    黄金集质控 (五维)   用五维标注函数标注黄金集, 与专家标准标签逐维比对; 任一维准确率低于合格线 -> 生成退返单.
    专家抽样审核        B 档必审 + A 档按比例抽检; 阻塞等待专家提交审核单 (可改五维标签/质量档, 三项核对,
                        结论: 通过 / 修改后通过 / 退返); 汇总一致率, 修改过的样本作为黄金集候选; 通过率不达标拦截下游.
大模型结果 (评审、黄金集标注) 缓存在输出目录; 放 .offline_prepared 标记后只用缓存, 调阈值可立即重算.
前端: web/pii_highlight.js 渲染前两个节点的 ui.html, web/expert_review.js 渲染专家审核面板.
示例: example/offline_prepared/quality_control/
"""
import html
import json
import random
import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    from .llm_utils import resolve_api_key, is_offline_prepared
    from .five_dim_label_node import load_vocab, build_prompt, label_record, LLM_DIMS
    from .privacy_detection_node import rule_detect
    from .text_normalizer_node import normalize_text
    from . import human_audit_node as audit
except ImportError:  # 直接 python quality_control_node.py 调试时
    from llm_utils import resolve_api_key, is_offline_prepared
    from five_dim_label_node import load_vocab, build_prompt, label_record, LLM_DIMS
    from privacy_detection_node import rule_detect
    from text_normalizer_node import normalize_text
    import human_audit_node as audit

RULE_DIMS = ("完整性", "可读性", "规范性", "合规性", "标注完备性")
JUDGE_DIMS = ("知识准确性", "教育价值", "适龄性", "标注一致性")
LABEL_DIMS = ("学科", "学段", "场景", "难度", "格式")


def read_jsonl(path_or_dir):
    root = Path(path_or_dir)
    files = [root] if root.is_file() else sorted(root.glob("*.jsonl"))
    return [json.loads(l) for f in files for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def make_client(api_key, api_url):
    from openai import OpenAI
    return OpenAI(api_key=resolve_api_key(api_key), base_url=api_url)


# ---------- 质量评估: 规则 5 维 ----------

def rule_scores(rec, vocab):
    text = rec.get("text", "")
    n = max(len(text), 1)
    complete = min(1.0, len(text) / 80) - (0.2 if not re.search(r"[。！？.!?”）)]$", text.strip()) else 0)
    garbled = sum(text.count(c) for c in "�") / n
    repeats = sum(len(m.group()) for m in re.finditer(r"(.)\1{3,}|(..)\2{2,}", text)) / n
    readable = 1 - 8 * garbled - 2 * repeats
    normalized = normalize_text(text, {"fullwidth", "punct"})
    changed = sum(a != b for a, b in zip(text, normalized)) + abs(len(text) - len(normalized))
    standard = 1 - 6 * changed / n
    compliant = 0.0 if rule_detect(text) else 1.0
    ok_labels = sum(1 for d in LLM_DIMS if rec.get(d) in vocab[d]) + (1 if rec.get("格式") else 0)
    clamp = lambda x: round(max(0.0, min(1.0, x)), 2)
    return dict(zip(RULE_DIMS, map(clamp, (complete, readable, standard, compliant, ok_labels / 5))))


# ---------- 质量评估: ecnu-plus 评审 ----------

JUDGE_PROMPT = ("你是教育语料质量评审专家。阅读语料正文和它的五维标签, 从四个方面各打 1-5 分 (5 最好):\n"
                "知识准确性: 学科知识是否正确; 教育价值: 是否适合用于教学或学习; 适龄性: 内容难度与表述是否适合所标学段;\n"
                "标注一致性: 五维标签是否与内容相符.\n"
                '只输出 JSON: {"知识准确性": 0, "教育价值": 0, "适龄性": 0, "标注一致性": 0, "理由": "不超过30字"}')


def judge_record(client, model_name, rec):
    labels = "，".join(f"{d}: {rec.get(d, '缺失')}" for d in LABEL_DIMS)
    try:
        resp = client.chat.completions.create(model=model_name, temperature=0, timeout=60, messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"标题: {rec.get('title', '')}\n五维标签: {labels}\n正文:\n{rec.get('text', '')[:2000]}"}])
        data = json.loads(re.search(r"\{.*\}", resp.choices[0].message.content, re.S).group(0))
        scores = {d: max(1, min(5, int(data.get(d, 3)))) for d in JUDGE_DIMS}
        return {**scores, "理由": str(data.get("理由", ""))[:60]}
    except Exception as e:
        print(f"[质量评估] {rec.get('id')} 评审失败, 记 3 分待人工: {type(e).__name__}: {e}")
        return {**{d: 3 for d in JUDGE_DIMS}, "理由": "模型评审失败, 待人工复核"}


def cached_llm(cache_path, records, offline, compute):
    """按 id 缓存大模型结果; offline=True 时只用缓存, 不调模型"""
    cache = {r["id"]: r["result"] for r in read_jsonl(cache_path)} if cache_path.exists() else {}
    for rec in records:
        if rec["id"] not in cache and not offline:
            cache[rec["id"]] = compute(rec)
    write_jsonl(cache_path, [{"id": k, "result": v} for k, v in cache.items()])
    return cache


def used_dims(with_labels):
    """还没做五维标注的语料 (如 3.3 清洗阶段) 不计 标注完备性 / 标注一致性"""
    if with_labels:
        return RULE_DIMS, JUDGE_DIMS
    return tuple(d for d in RULE_DIMS if d != "标注完备性"), tuple(d for d in JUDGE_DIMS if d != "标注一致性")


def grade_record(rule, judge, a_line, b_line, judge_weight, with_labels=True):
    rule_dims, judge_dims = used_dims(with_labels)
    rule_avg = sum(rule[d] for d in rule_dims) / len(rule_dims)
    judge_avg = sum((judge[d] - 1) / 4 for d in judge_dims) / len(judge_dims)
    total = round((1 - judge_weight) * rule_avg + judge_weight * judge_avg, 3)
    grade = "A" if total >= a_line else "B" if total >= b_line else "C"
    reasons = [f"{d}偏低 ({rule[d]:.2f})" for d in rule_dims if rule[d] < 0.6 and d != "合规性"]
    if rule["合规性"] < 1:
        grade, reasons = "C", reasons + ["隐私残留, 退回脱敏"]
    low = [f"评审·{d} {judge[d]} 分" for d in judge_dims if judge[d] <= 2]
    if low and grade == "A":
        grade = "B"
    return total, grade, reasons + low


def quality_html(rows, a_line, b_line, judge_weight, with_labels=True):
    rule_dims, judge_dims = used_dims(with_labels)
    counts = Counter(r["质量档"] for r in rows)
    dim_avg = {d: sum(r["规则分"][d] for r in rows) / len(rows) for d in rule_dims}
    judge_avg = {d: sum(r["模型评审"][d] for r in rows) / len(rows) for d in judge_dims}
    head = (f'<div class="coclp-summary">批次 {len(rows)} 条: '
            f'<span class="q-a">A 档 {counts["A"]}</span> <span class="q-b">B 档 {counts["B"]}</span> '
            f'<span class="q-c">C 档 {counts["C"]}</span> · 直接入库率 {counts["A"] / len(rows):.0%}<br>'
            f'分档线 A≥{a_line} B≥{b_line} · 模型评审权重 {judge_weight}<br>'
            f'规则均分: {"，".join(f"{d} {v:.2f}" for d, v in dim_avg.items())}<br>'
            f'评审均分: {"，".join(f"{d} {v:.1f}" for d, v in judge_avg.items())}</div>')
    body = "".join(
        f'<tr><td>{html.escape(r["id"])}</td><td>{html.escape(r.get("title", ""))}</td><td>{r["总分"]:.2f}</td>'
        f'<td class="q-{r["质量档"].lower()}">{r["质量档"]}</td>'
        f'<td>{html.escape("; ".join(r["原因"]) or "—")}</td></tr>' for r in rows)
    return head + ('<table class="coclp-table"><tr><th>ID</th><th>语料</th><th>总分</th><th>档</th><th>原因</th></tr>'
                   f"{body}</table>")


class QualityAssess:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "batch_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/quality_control/output/quality"}),
            "api_key": ("STRING", {"default": "None"}),
            "api_url": ("STRING", {"forceInput": True}),
            "model_name": ("STRING", {"default": "ecnu-plus"}),
            "A档线": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
            "B档线": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05}),
            "模型评审权重": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.05}),
        }, "optional": {
            # 3.3 清洗阶段还没做五维标注时关掉: 不计 标注完备性 / 标注一致性
            "计入标注指标": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("评估结果目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/质量"

    def run(self, batch_dir, output_dir, api_key, api_url, model_name, A档线, B档线, 模型评审权重, 计入标注指标=True):
        records, out = read_jsonl(batch_dir), Path(output_dir)
        offline = is_offline_prepared(output_dir)
        client = None if offline else make_client(api_key, api_url)
        judges = cached_llm(out / "judge_cache.jsonl", records, offline,
                            lambda rec: judge_record(client, model_name, rec))
        vocab, _ = load_vocab()
        rows = []
        for rec in records:
            rule = rule_scores(rec, vocab)
            judge = judges.get(rec["id"], {**{d: 3 for d in JUDGE_DIMS}, "理由": "无缓存"})
            total, grade, reasons = grade_record(rule, judge, A档线, B档线, 模型评审权重, 计入标注指标)
            rows.append({**rec, "规则分": rule, "模型评审": judge, "总分": total, "质量档": grade, "原因": reasons})
        write_jsonl(out / "scored.jsonl", rows)
        html_report = quality_html(rows, A档线, B档线, 模型评审权重, 计入标注指标)
        return {"ui": {"html": [html_report]}, "result": (output_dir,)}


# ---------- 黄金集质控 (五维标注) ----------

def golden_html(acc, line, errors, retour):
    rows = "".join(f'<tr><td>{d}</td><td>{v:.0%}</td><td>{line:.0%}</td>'
                   f'<td class="{"q-a" if v >= line else "q-c"}">{"合格" if v >= line else "不合格"}</td></tr>'
                   for d, v in acc.items())
    table = f'<table class="coclp-table"><tr><th>维度</th><th>准确率</th><th>合格线</th><th>结论</th></tr>{rows}</table>'
    err = "".join(f'<div>· {html.escape(e["id"])} {html.escape(e["title"])}: {e["维度"]} 标准「{html.escape(e["标准"])}」'
                  f' 实际「<span class="q-c">{html.escape(e["实际"])}</span>」</div>' for e in errors)
    verdict = (f'<div class="coclp-retour">{html.escape(retour)}</div>' if retour
               else '<div class="coclp-pass">黄金集质控合格: 五维标注各维度准确率均达到合格线, 本批次标注放行</div>')
    return table + (f'<div class="coclp-rec-head" style="margin-top:6px">不一致样例</div>{err}' if err else "") + verdict


def retour_sheet(acc, line, errors, golden_version):
    failed = [d for d, v in acc.items() if v < line]
    if not failed:
        return ""
    lines = [f"退返单 RT-{datetime.now():%Y%m%d-%H%M}",
             f"质控依据: {golden_version}  合格线: 各维度准确率 ≥ {line:.0%}",
             "问题环节: " + "、".join(f"五维标注·{d} (实际 {acc[d]:.0%})" for d in failed),
             "失败样例: " + "；".join(f'{e["id"]} {e["维度"]} 应为「{e["标准"]}」实为「{e["实际"]}」'
                                    for e in errors if e["维度"] in failed),
             "处理: 退回五维标注环节, 补充该维度的标注规范与示例后重跑本批次, 复检合格后放行"]
    return "\n".join(lines)


class GoldenLabelCheck:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "golden_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/quality_control/output/golden"}),
            "api_key": ("STRING", {"default": "None"}),
            "api_url": ("STRING", {"forceInput": True}),
            "model_name": ("STRING", {"default": "ecnu-plus"}),
            "合格线": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("质控结果目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/质量"

    def run(self, golden_dir, output_dir, api_key, api_url, model_name, 合格线):
        golden, out = read_jsonl(golden_dir), Path(output_dir)
        offline = is_offline_prepared(output_dir)
        vocab, format_map = load_vocab()
        client, prompt = (None, None) if offline else (make_client(api_key, api_url), build_prompt(vocab))
        preds = cached_llm(out / "pred_labels_cache.jsonl", golden, offline,
                           lambda rec: label_record({"text": rec["text"], "md_path": rec["title"]}, client, model_name,
                                                    prompt, vocab, format_map, ""))
        acc, errors = {}, []
        for dim in LLM_DIMS:
            hits = 0
            for g in golden:
                pred = preds.get(g["id"], {}).get(dim, "无缓存")
                if pred == g["gold_labels"][dim]:
                    hits += 1
                else:
                    errors.append({"id": g["id"], "title": g["title"], "维度": dim, "标准": g["gold_labels"][dim], "实际": pred})
            acc[dim] = hits / len(golden)
        version = Path(golden_dir).name if Path(golden_dir).is_file() else next(Path(golden_dir).glob("*.jsonl")).stem
        retour = retour_sheet(acc, 合格线, errors, version)
        out.mkdir(parents=True, exist_ok=True)
        (out / "质控结果.json").write_text(json.dumps({"准确率": acc, "合格线": 合格线, "不一致": errors},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
        if retour:
            (out / "退返单.md").write_text(retour + "\n", encoding="utf-8")
        return {"ui": {"html": [golden_html(acc, 合格线, errors, retour)]}, "result": (output_dir,)}


# ---------- 专家抽样审核 (阻塞) ----------

def draw_review_samples(rows, a_rate, a_min, rng_seed):
    """B 档全部必审; A 档按比例随机抽检 (至少 a_min 条); C 档已退返, 不进专家审核"""
    b_rows = [r for r in rows if r["质量档"] == "B"]
    a_rows = [r for r in rows if r["质量档"] == "A"]
    k = min(len(a_rows), max(a_min, round(len(a_rows) * a_rate)))
    return b_rows + random.Random(rng_seed).sample(a_rows, k)


def summarize_review(samples, result, pass_line):
    verdicts = {v["sample_id"]: v for v in result.get("verdicts", [])}
    rows, n_pass, n_agree, candidates = [], 0, 0, []
    for s in samples:
        v = verdicts.get(s["id"], {})
        conclusion = v.get("conclusion", "退返")
        changed = {d: v.get("labels", {}).get(d) for d in LABEL_DIMS
                   if v.get("labels", {}).get(d) not in (None, s["labels"].get(d))}
        grade_changed = v.get("grade") not in (None, s["质量档"])
        n_pass += conclusion in ("通过", "修改后通过")
        n_agree += conclusion == "通过" and not changed and not grade_changed
        if changed or grade_changed:
            candidates.append({"id": s["id"], "text": s["text"], "gold_labels": {**s["labels"], **changed},
                               "专家": result.get("auditor", ""), "确认日期": datetime.now().strftime("%Y-%m-%d")})
        rows.append({**s, "专家结论": conclusion, "改正标签": changed, "专家质量档": v.get("grade", s["质量档"]),
                     "核对": v.get("checks", {}), "备注": v.get("comment", "")})
    n = max(len(samples), 1)
    passed = n_pass / n >= pass_line
    report = "\n".join([
        f"专家抽样审核: {'通过, 放行入库' if passed else '未通过, 批次退返'}",
        f"审核人: {result.get('auditor') or '未填写'}    提交时间: {result.get('submitted_at', '')}",
        f"审核 {len(samples)} 条: 通过率 {n_pass / n:.0%} (阈值 {pass_line:.0%}) · 与自动评估一致率 {n_agree / n:.0%}",
        *[f"  - {r['id']} {r.get('title', '')}: {r['专家结论']}"
          + (f", 改正 {'、'.join(f'{d}→{t}' for d, t in r['改正标签'].items())}" if r["改正标签"] else "")
          + (f" ({r['备注']})" if r["备注"] else "") for r in rows],
        f"黄金集候选 {len(candidates)} 条 (专家改正过的样本)"])
    return rows, candidates, passed, report


class ExpertSampleReview:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "scored_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/quality_control/output/review"}),
            "A档抽检比例": ("FLOAT", {"default": 0.02, "min": 0.0, "max": 1.0, "step": 0.01}),
            "A档最少抽检": ("INT", {"default": 1, "min": 0, "max": 1000}),
            "通过率阈值": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
            "提醒间隔秒": ("INT", {"default": 60, "min": 5, "max": 86400}),
            "抽样种子": ("INT", {"default": 2026, "min": 0, "max": 2**31 - 1}),
        }, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("放行目录", "审核报告")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/质量"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # 每次运行都要重新人工审核

    def run(self, scored_dir, output_dir, A档抽检比例, A档最少抽检, 通过率阈值, 提醒间隔秒, 抽样种子, unique_id=None):
        rows = read_jsonl(Path(scored_dir) / "scored.jsonl")
        picked = draw_review_samples(rows, A档抽检比例, A档最少抽检, 抽样种子)
        vocab, _ = load_vocab()
        samples = [{"id": r["id"], "sample_id": r["id"], "title": r.get("title", ""), "text": r["text"],
                    "质量档": r["质量档"], "总分": r["总分"], "原因": r["原因"],
                    "抽样原因": "B 档必审" if r["质量档"] == "B" else f"A 档抽检 {A档抽检比例:.0%}",
                    "labels": {d: r.get(d, "") for d in LABEL_DIMS}} for r in picked]
        task_id = f"review-{datetime.now():%Y%m%d-%H%M%S}-{unique_id}"
        payload = {"task_id": task_id, "node_id": unique_id, "pass_threshold": 通过率阈值, "samples": samples,
                   "vocab": vocab, "batch_size": len(rows)}
        with audit.PENDING_LOCK:
            audit.PENDING_AUDITS[task_id] = {"event": threading.Event(), "result": None, "payload": payload}
        audit.send_event("coclp.review.request", payload)
        try:
            result = audit.wait_for_verdict(
                task_id, 提醒间隔秒, 0,
                lambda waited: audit.send_event("coclp.review.remind", {**payload, "waited_sec": waited}),
                audit.raise_if_interrupted)
        finally:
            with audit.PENDING_LOCK:
                audit.PENDING_AUDITS.pop(task_id, None)

        reviewed, candidates, passed, report = summarize_review(samples, result, 通过率阈值)
        out = Path(output_dir) / task_id
        write_jsonl(out / "reviewed.jsonl", reviewed)
        write_jsonl(out / "golden_candidates.jsonl", candidates)
        (out / "report.md").write_text(report + "\n", encoding="utf-8")
        if passed:
            released = scored_dir
        else:
            from comfy_execution.graph_utils import ExecutionBlocker
            released = ExecutionBlocker("专家抽样审核未通过, 批次退返")
        return {"ui": {"text": [report]}, "result": (released, report)}


if __name__ == "__main__":
    # 脱离 ComfyUI 只算规则分 (评审记 3 分): python quality_control_node.py <批次目录>
    import sys
    vocab, _ = load_vocab()
    for rec in read_jsonl(sys.argv[1]):
        rule = rule_scores(rec, vocab)
        print(rec["id"], rule, grade_record(rule, {d: 3 for d in JUDGE_DIMS}, 0.8, 0.6, 0.4))
