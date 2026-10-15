"""4.1 双引擎并行隐私检测: 规则引擎 + 命名实体识别 (NER) 模型, 结果合并.

    隐私检测·规则引擎  ─┐
                        ├─> 检测结果合并 -> 检测报告.md (原文标注 + 实体清单 + 统计)
    隐私检测·NER 模型  ─┘
规则引擎: 正则 + 校验 (手机号、身份证号含校验位、学号、邮箱、详细地址)
NER 模型: spaCy 中文模型 (默认 zh_core_web_sm, 约 46MB), 识别姓名、地名、机构;
          输出目录放 .offline_prepared 标记后不再加载模型, 直接复用离线结果.
示例: example/offline_prepared/privacy_detection/
"""
import json
import re
from collections import Counter
from pathlib import Path

try:
    from .llm_utils import is_offline_prepared
except ImportError:  # 直接 python privacy_detection_node.py 调试时
    from llm_utils import is_offline_prepared


def read_records(input_dir):
    records = []
    for path in sorted(Path(input_dir).rglob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            records += [json.loads(line) for line in f if line.strip()]
    return records


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------- 规则引擎 ----------

def id_card_valid(num):
    """18 位身份证校验位 (GB 11643)"""
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    checks = "10X98765432"
    return checks[sum(int(d) * w for d, w in zip(num[:17], weights)) % 11] == num[17].upper()


RULES = [  # (类型, 正则, 取第几个分组, 额外校验)
    ("身份证号", re.compile(r"(?<![0-9Xx])(\d{17}[\dXx])(?![0-9Xx])"), 1, id_card_valid),
    ("手机号", re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"), 1, None),
    ("学号", re.compile(r"学号[:：\s]*(\d{6,12})"), 1, None),
    ("邮箱", re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"), 1, None),
    ("地址", re.compile(r"([一-鿿]{2,}(?:省|市)[一-鿿]{1,6}(?:区|县)[一-鿿0-9]{1,12}?"
                      r"(?:路|街|弄|巷)\d+号(?:\d+室)?)"), 1, None),
    ("学校", re.compile(r"([一-鿿]{2,10}?(?:第[一二三四五六七八九十\d]+)?(?:中学|小学|大学|学院|幼儿园))"), 1, None),
]
# 正则会把 "家住上海市..." 的 "家住" 一起匹配进来, 去掉这类引导词
LEAD_WORDS_RE = re.compile(r"^(?:家住|居住在|住在|家庭住址|住址|地址|现就读于|就读于|在)[:：]?")


def rule_detect(text):
    entities = []
    for kind, pattern, group, check in RULES:
        for m in pattern.finditer(text):
            value, start = m.group(group), m.start(group)
            lead = LEAD_WORDS_RE.match(value)
            if lead:
                value, start = value[lead.end():], start + lead.end()
            if check and not check(value):
                continue
            entities.append({"text": value, "type": kind, "start": start, "end": start + len(value), "engine": "规则"})
    return entities


class PIIRuleEngine:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "input_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/privacy_detection/output/rule"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("规则检测结果",)
    FUNCTION = "run"
    CATEGORY = "MY_NODES/隐私"

    def run(self, input_dir, output_dir):
        rows = [{"id": r["id"], "entities": rule_detect(r.get("text", ""))} for r in read_records(input_dir)]
        write_jsonl(Path(output_dir) / "entities.jsonl", rows)
        return (output_dir,)


# ---------- NER 模型 ----------

NER_LABELS = {"PERSON": "姓名", "GPE": "地名", "LOC": "地名", "FAC": "地名", "ORG": "机构"}  # spaCy 标签 -> 隐私类型
PLACE_SUFFIX_RE = re.compile(r"(?:省|市|区|县|镇|乡|街道)$")
ROLE_WORDS = {"班主任", "老师", "校长", "教师", "家长", "同学", "学生"}  # 小模型常把职务/称谓误标成机构


def ner_detect(texts, model_name):
    """spaCy 中文模型 (默认 zh_core_web_sm) 做 NER, 再用两条轻量规则纠正小模型的常见误判"""
    import spacy
    nlp = spacy.load(model_name)
    results = []
    for doc in nlp.pipe(texts):
        found = []
        for e in doc.ents:
            kind = NER_LABELS.get(e.label_)
            if not kind or e.text in ROLE_WORDS:
                continue
            if PLACE_SUFFIX_RE.search(e.text):
                kind = "地名"  # "静安区" 被标成人名、"上海市静安区" 被标成机构 -> 统一为地名
            found.append({"text": e.text, "type": kind, "start": e.start_char, "end": e.end_char, "engine": "NER"})
        results.append(found)
    return results


class PIINerEngine:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "input_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/privacy_detection/output/ner"}),
            "model": ("STRING", {"default": "zh_core_web_sm"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("NER 检测结果",)
    FUNCTION = "run"
    CATEGORY = "MY_NODES/隐私"

    def run(self, input_dir, output_dir, model):
        if is_offline_prepared(output_dir):
            print(f"[离线回放] NER 结果已预先生成, 不加载模型: {output_dir}")
            return (output_dir,)
        records = read_records(input_dir)
        found = ner_detect([r.get("text", "") for r in records], model)
        write_jsonl(Path(output_dir) / "entities.jsonl", [{"id": r["id"], "entities": f} for r, f in zip(records, found)])
        return (output_dir,)


# ---------- 合并 ----------

def merge_entities(rule_ents, ner_ents):
    """重叠片段合并为一个实体: 取最长片段, 两个引擎都命中的标 "双引擎", 类型以规则引擎为准"""
    spans = sorted(rule_ents + ner_ents, key=lambda e: (e["start"], -(e["end"] - e["start"])))
    merged = []
    for e in spans:
        if merged and e["start"] < merged[-1]["end"]:
            m = merged[-1]
            engines = set(m["engines"]) | {e["engine"]}
            if e["end"] - e["start"] > m["end"] - m["start"]:
                m.update(text=e["text"], start=e["start"], end=e["end"])
            if e["engine"] == "规则":
                m["type"] = e["type"]
            m["engines"] = sorted(engines)
        else:
            merged.append({**{k: e[k] for k in ("text", "type", "start", "end")}, "engines": [e["engine"]]})
    for m in merged:
        m["engine"] = "双引擎" if len(m["engines"]) > 1 else m["engines"][0]
        del m["engines"]
    return merged


def mark_text(text, entities):
    """原文里把实体标成 【原文|类型】"""
    out, pos = [], 0
    for e in entities:
        out.append(text[pos:e["start"]])
        out.append(f"【{e['text']}|{e['type']}】")
        pos = e["end"]
    out.append(text[pos:])
    return "".join(out)


def build_report(records, merged_rows):
    lines, by_type, by_engine = [], Counter(), Counter()
    for rec, row in zip(records, merged_rows):
        lines.append(f"── {rec['id']}  {rec.get('source', '')} ──")
        lines.append(mark_text(rec["text"], row["entities"]))
        for e in row["entities"]:
            lines.append(f"  · {e['type']:<6} {e['text']:<28} {e['engine']}")
            by_type[e["type"]] += 1
            by_engine[e["engine"]] += 1
        lines.append("")
    lines.append(f"共检出 {sum(by_type.values())} 处隐私信息: " + "，".join(f"{k} {v}" for k, v in by_type.most_common()))
    lines.append("检出来源: " + "，".join(f"{k} {v}" for k, v in by_engine.most_common()))
    return "\n".join(lines)


def build_report_html(records, merged_rows):
    """节点上的高亮显示 (web/pii_highlight.js 渲染): 隐私实体红字标出, 后面跟 "类型·引擎" 小标签"""
    import html
    by_type, by_engine, blocks = Counter(), Counter(), []
    for rec, row in zip(records, merged_rows):
        text, pos, parts = rec["text"], 0, []
        for e in row["entities"]:
            parts.append(html.escape(text[pos:e["start"]]))
            parts.append(f'<mark class="coclp-pii">{html.escape(e["text"])}</mark>'
                         f'<span class="coclp-pii-tag">{html.escape(e["type"])}·{html.escape(e["engine"])}</span>')
            pos = e["end"]
            by_type[e["type"]] += 1
            by_engine[e["engine"]] += 1
        parts.append(html.escape(text[pos:]))
        blocks.append(f'<div class="coclp-rec"><div class="coclp-rec-head">{html.escape(rec["id"])} '
                      f'<span class="coclp-stat">{html.escape(rec.get("source", ""))} · 检出 {len(row["entities"])} 处</span>'
                      f'</div><div>{"".join(parts)}</div></div>')
    summary = (f'<div class="coclp-summary">共检出 <b class="coclp-pii-num">{sum(by_type.values())}</b> 处隐私信息: '
               + "，".join(f"{html.escape(k)} {v}" for k, v in by_type.most_common())
               + "<br>检出来源: " + "，".join(f"{html.escape(k)} {v}" for k, v in by_engine.most_common()) + "</div>")
    return summary + "".join(blocks)


class PIIMerge:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "corpus_dir": ("STRING", {"forceInput": True}),
            "rule_dir": ("STRING", {"forceInput": True}),
            "ner_dir": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/privacy_detection/output/merged"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("合并检测结果",)
    FUNCTION = "run"
    OUTPUT_NODE = True  # 节点上直接高亮显示检测结果
    CATEGORY = "MY_NODES/隐私"

    def run(self, corpus_dir, rule_dir, ner_dir, output_dir):
        records = read_records(corpus_dir)
        rule = {r["id"]: r["entities"] for r in read_records(rule_dir)}
        ner = {r["id"]: r["entities"] for r in read_records(ner_dir)}
        merged = [{"id": r["id"], "text": r["text"], "entities": merge_entities(rule.get(r["id"], []), ner.get(r["id"], []))}
                  for r in records]
        out = Path(output_dir)
        write_jsonl(out / "pii_detected.jsonl", merged)
        (out / "检测报告.md").write_text(build_report(records, merged) + "\n", encoding="utf-8")
        return {"ui": {"html": [build_report_html(records, merged)]}, "result": (output_dir,)}


class PassThroughDir:
    """把一个目录路径原样输出, 让同一份语料能分发给并行的两个引擎 (画布上更直观)"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"input_dir": ("STRING", {"default": "../example/offline_prepared/privacy_detection/data"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("语料目录",)
    FUNCTION = "run"
    CATEGORY = "MY_NODES/隐私"

    def run(self, input_dir):
        return (input_dir,)


if __name__ == "__main__":
    # python Corpus_Cleansing_Pipeline/privacy_detection_node.py <语料目录> [--ner]
    import sys
    records = read_records(sys.argv[1])
    texts = [r["text"] for r in records]
    ner = ner_detect(texts, "zh_core_web_sm") if "--ner" in sys.argv else [[] for _ in texts]
    merged = [{"id": r["id"], "text": r["text"], "entities": merge_entities(rule_detect(r["text"]), n)}
              for r, n in zip(records, ner)]
    print(build_report(records, merged))
