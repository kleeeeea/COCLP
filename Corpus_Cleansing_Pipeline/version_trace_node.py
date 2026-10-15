"""6.2 版本管理、双向追溯与合规审计 (全部自动, 不含人工环节):

    批次版本登记   语料批次 -> 内容指纹 (SHA-256) + 记录数 + 父版本 + 与父版本的增删, 写入版本台账 versions.jsonl;
                   同一内容重复登记复用原版本号. 节点上显示版本台账.
    双向追溯       正向: 样本 ID -> 所在版本 -> 使用这些版本的训练/评测任务 -> 模型;
                   反向: 模型 -> 训练/评测任务 -> 语料版本 -> 样本. 训练任务登记表按 "语料批次" 名关联版本.
    合规审计       最新版本逐条重跑隐私规则检测 (残留必须为 0) + 对照隐私处理日志算检测/脱敏覆盖率,
                   覆盖率低于要求则判不合规; 生成月度审计报告.
示例: example/offline_prepared/version_trace/
"""
import hashlib
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    from .privacy_detection_node import rule_detect
except ImportError:  # 直接 python version_trace_node.py 调试时
    from privacy_detection_node import rule_detect


def read_jsonl(path_or_dir):
    root = Path(path_or_dir)
    files = [root] if root.is_file() else sorted(root.glob("*.jsonl"))
    return [json.loads(l) for f in files for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def batch_info(batch_dir):
    """一个批次目录 -> 批次名、记录、内容指纹 (按记录排序后整体 SHA-256)"""
    files = sorted(Path(batch_dir).glob("*.jsonl"))
    records = read_jsonl(batch_dir)
    canon = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in sorted(records, key=lambda r: r["id"]))
    return {"批次名": files[0].stem if files else Path(batch_dir).name, "records": records,
            "指纹": hashlib.sha256(canon.encode("utf-8")).hexdigest()}


def load_registry(registry_dir):
    path = Path(registry_dir) / "versions.jsonl"
    return read_jsonl(path) if path.exists() else []


def register_batch(registry_dir, batch_dir, note, now=None):
    """登记一个批次; 内容指纹已登记过则直接返回原版本 (幂等)"""
    registry, info = load_registry(registry_dir), batch_info(batch_dir)
    for v in registry:
        if v["指纹"] == info["指纹"]:
            return registry, v
    parent = registry[-1] if registry else None
    ids = sorted(r["id"] for r in info["records"])
    now = now or datetime.now()
    version = {
        "版本号": f"v{now:%Y%m%d}-{len(registry) + 1:03d}", "批次名": info["批次名"], "父版本": parent["版本号"] if parent else "—",
        "记录数": len(ids), "样本": ids, "指纹": info["指纹"], "登记时间": now.strftime("%Y-%m-%d %H:%M:%S"),
        "新增": sorted(set(ids) - set(parent["样本"])) if parent else ids,
        "移除": sorted(set(parent["样本"]) - set(ids)) if parent else [], "说明": note,
    }
    registry.append(version)
    Path(registry_dir).mkdir(parents=True, exist_ok=True)
    (Path(registry_dir) / "versions.jsonl").write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in registry), encoding="utf-8")
    return registry, version


def registry_html(registry, current):
    highlight = ' class="q-a"'  # 本次登记的版本整行标绿
    rows = "".join(
        f'<tr{highlight if v["版本号"] == current["版本号"] else ""}><td>{v["版本号"]}</td>'
        f'<td>{html.escape(v["批次名"])}</td><td>{v["父版本"]}</td><td>{v["记录数"]}</td>'
        f'<td>{v["指纹"][:12]}…</td><td>{v["登记时间"][5:16]}</td>'
        f'<td>{("+" + "、".join(v["新增"])) if v["父版本"] != "—" and v["新增"] else ""}'
        f'{(" −" + "、".join(v["移除"])) if v["移除"] else ""}{"首次登记" if v["父版本"] == "—" else ""}</td>'
        f'<td>{html.escape(v["说明"])}</td></tr>' for v in registry)
    return (f'<div class="coclp-summary">版本台账共 {len(registry)} 个版本 · 本次登记 <b class="q-a">{current["版本号"]}</b>'
            f' (父版本 {current["父版本"]})</div>'
            '<table class="coclp-table"><tr><th>版本号</th><th>批次</th><th>父版本</th><th>记录</th><th>内容指纹</th>'
            f'<th>登记</th><th>相对父版本</th><th>说明</th></tr>{rows}</table>')


class BatchVersionRegister:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "batch_dir": ("STRING", {"forceInput": True}),
            "registry_dir": ("STRING", {"default": "../example/offline_prepared/version_trace/registry"}),
            "版本说明": ("STRING", {"default": "质控后入库: 剔除 C 档 2 条"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("版本台账目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/版本"

    def run(self, batch_dir, registry_dir, 版本说明):
        registry, current = register_batch(registry_dir, batch_dir, 版本说明)
        return {"ui": {"html": [registry_html(registry, current)]}, "result": (registry_dir,)}


# ---------- 双向追溯 ----------

def trace(registry, jobs, sample_id, model):
    by_batch = {v["批次名"]: v for v in registry}
    forward_versions = [v for v in registry if sample_id in v["样本"]]
    forward_jobs = [j for j in jobs if any(by_batch.get(b, {}).get("版本号") in {v["版本号"] for v in forward_versions}
                                          for b in j["语料批次"])]
    backward_jobs = [j for j in jobs if j["模型"] == model]
    backward_versions = [by_batch[b] for j in backward_jobs for b in j["语料批次"] if b in by_batch]
    return forward_versions, forward_jobs, backward_jobs, list({v["版本号"]: v for v in backward_versions}.values())


def trace_html(sample_id, model, fwd_v, fwd_j, bwd_j, bwd_v):
    def chain(items):
        return ' <span class="coclp-stat">→</span> '.join(items)

    fwd = chain([f'<b>样本 {html.escape(sample_id)}</b>',
                 "版本 " + ("、".join(f'{v["版本号"]}' for v in fwd_v) or "无"),
                 "任务 " + ("、".join(f'{j["任务"]}({j["类型"]})' for j in fwd_j) or "未被使用"),
                 "模型 " + ("、".join(sorted({j["模型"] for j in fwd_j})) or "—")])
    bwd = chain([f'<b>模型 {html.escape(model)}</b>',
                 "任务 " + ("、".join(f'{j["任务"]}({j["类型"]})' for j in bwd_j) or "无"),
                 "版本 " + ("、".join(f'{v["版本号"]} ({v["批次名"]}, {v["记录数"]} 条)' for v in bwd_v) or "无"),
                 "样本 " + ("、".join(sorted({s for v in bwd_v for s in v["样本"]})) or "—")])
    return (f'<div class="coclp-rec"><div class="coclp-rec-head">正向追溯 (语料 → 模型)</div>{fwd}</div>'
            f'<div class="coclp-rec"><div class="coclp-rec-head">反向追溯 (模型 → 语料)</div>{bwd}</div>')


class ModelCorpusTrace:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "registry_dir": ("STRING", {"forceInput": True}),
            "training_jobs": ("STRING", {"default": "../example/offline_prepared/version_trace/data/训练任务登记.jsonl"}),
            "样本ID": ("STRING", {"default": "Q06"}),
            "模型": ("STRING", {"default": "静安教育大模型 v1.2"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("追溯结果",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/版本"

    def run(self, registry_dir, training_jobs, 样本ID, 模型):
        registry, jobs = load_registry(registry_dir), read_jsonl(training_jobs)
        fwd_v, fwd_j, bwd_j, bwd_v = trace(registry, jobs, 样本ID.strip(), 模型.strip())
        text = json.dumps({"正向": {"版本": [v["版本号"] for v in fwd_v], "任务": [j["任务"] for j in fwd_j]},
                           "反向": {"任务": [j["任务"] for j in bwd_j], "版本": [v["版本号"] for v in bwd_v]}},
                          ensure_ascii=False)
        return {"ui": {"html": [trace_html(样本ID, 模型, fwd_v, fwd_j, bwd_j, bwd_v)]}, "result": (text,)}


# ---------- 合规审计 ----------

def audit_version(version, batch_records, privacy_log):
    logged = {r["id"]: r for r in privacy_log}
    residual = {r["id"]: [e["type"] for e in rule_detect(r.get("text", ""))] for r in batch_records}
    residual = {k: v for k, v in residual.items() if v}
    checked = [i for i in version["样本"] if i in logged]
    desensitized = [i for i in checked if logged[i]["检出"] == 0 or logged[i]["脱敏"] == "完成"]
    n = max(version["记录数"], 1)
    return {"检测覆盖率": len(checked) / n, "脱敏覆盖率": len(desensitized) / n, "残留": residual,
            "未检测": sorted(set(version["样本"]) - set(checked))}


def monthly_report(month, registry, result, required, current):
    ok = result["检测覆盖率"] >= required and result["脱敏覆盖率"] >= required and not result["残留"]
    in_month = [v for v in registry if v["登记时间"].startswith(month)]
    removed = sorted({i for v in in_month for i in v["移除"]})
    lines = [f"月度隐私合规审计报告 {month}  ({'合规' if ok else '不合规'})",
             f"本月登记版本 {len(in_month)} 个: " + "、".join(v["版本号"] for v in in_month),
             f"审计对象: 最新入库版本 {current['版本号']} ({current['记录数']} 条)",
             f"隐私检测覆盖率 {result['检测覆盖率']:.0%} · 脱敏覆盖率 {result['脱敏覆盖率']:.0%} (要求 ≥ {required:.0%})",
             f"入库语料隐私残留复检 (规则引擎): {'0 条' if not result['残留'] else '、'.join(f'{k}:{v}' for k, v in result['残留'].items())}",
             f"本月版本间移除样本: {'、'.join(removed) or '无'} (质量评估判 C 档, 退回清洗/脱敏, 未进入入库版本)"]
    return ok, "\n".join(lines)


class ComplianceAudit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "registry_dir": ("STRING", {"forceInput": True}),
            "batch_dir": ("STRING", {"forceInput": True}),
            "privacy_log": ("STRING", {"default": "../example/offline_prepared/version_trace/data/隐私处理日志.jsonl"}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/version_trace/output"}),
            "审计月份": ("STRING", {"default": datetime.now().strftime("%Y-%m")}),
            "覆盖率要求": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("审计报告目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/版本"

    def run(self, registry_dir, batch_dir, privacy_log, output_dir, 审计月份, 覆盖率要求):
        registry = load_registry(registry_dir)
        info = batch_info(batch_dir)
        current = next((v for v in registry if v["指纹"] == info["指纹"]), registry[-1])
        result = audit_version(current, info["records"], read_jsonl(privacy_log))
        ok, report = monthly_report(审计月份, registry, result, 覆盖率要求, current)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"月度审计报告_{审计月份}.md").write_text(report + "\n", encoding="utf-8")
        lines = report.split("\n")
        body = f'<div class="{"coclp-pass" if ok else "coclp-retour"}"><b>{html.escape(lines[0])}</b><br>' + \
               "<br>".join(html.escape(l) for l in lines[1:]) + "</div>"
        return {"ui": {"html": [body]}, "result": (output_dir,)}


if __name__ == "__main__":
    # python Corpus_Cleansing_Pipeline/version_trace_node.py <registry_dir> <batch_v1> <batch_v2>
    import sys
    reg_dir, v1, v2 = sys.argv[1:4]
    register_batch(reg_dir, v1, "原始批次 (已五维标注)")
    registry, cur = register_batch(reg_dir, v2, "质控后入库: 剔除 C 档 2 条")
    for v in registry:
        print(v["版本号"], v["批次名"], v["父版本"], v["记录数"], v["新增"], v["移除"])
