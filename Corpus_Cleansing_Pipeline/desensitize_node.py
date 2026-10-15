"""4.2 脱敏处理: 读取 4.1 隐私检测结果 (pii_detected.jsonl, 每条带 entities), 按实体类型套用三种策略:

    不可逆哈希    身份证号 / 手机号 / 学号 / 邮箱  -> #H:<加盐 SHA-256 前 8 位>
    标记化替换    姓名 / 学校 / 机构               -> [姓名_1] [学校_1] ..., 同一实体在整批语料中编号一致
    地理泛化      地址 / 地名                      -> 保留到 区县 / 城市 / 省份 一级
输出: 脱敏后 jsonl (保持 id, 便于和 "清洗前后对比" 节点对齐)、脱敏策略与统计.md、
      映射表 (标记 -> 原文, 仅授权人员可见, 生产环境应加密单独存放).
示例: example/offline_prepared/desensitization/
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

GEO_RE = re.compile(r"^(?P<province>.*?(?:省|自治区))?(?P<city>.*?市)?(?P<district>.*?(?:区|县))?")
GEO_LEVELS = ["区县", "城市", "省份"]


def split_types(types_str):
    return [t.strip() for t in re.split(r"[,，\s]+", types_str) if t.strip()]


def hash_value(value, salt):
    return "#H:" + hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:8]


def generalize_place(place, level):
    """上海市静安区南京西路1266号 -> 上海市静安区 (区县) / 上海市 (城市)"""
    m = GEO_RE.match(place)
    keep = {"区县": ("province", "city", "district"), "城市": ("province", "city"), "省份": ("province",)}[level]
    parts = [m.group(k) for k in keep if m and m.group(k)]
    if not parts:  # 匹配不到行政区划时整段泛化
        return "[地点]"
    if level == "城市" and not m.group("city"):  # 直辖市下的区/县直接写在省级位置时兜底
        return parts[0]
    return "".join(parts)


def desensitize_records(records, hash_types, token_types, geo_types, geo_level, salt, changes=None):
    """changes: 传入列表时, 按记录追加 [(普通文本, None) | (原文, (替换值, 策略, 类型))], 用于整段高亮对比"""
    token_ids = defaultdict(dict)  # 类型 -> {原文: 编号}
    stats = Counter()
    out = []
    for rec in records:
        text, pieces, pos, segs = rec["text"], [], 0, []
        for e in sorted(rec.get("entities", []), key=lambda e: e["start"]):
            if e["type"] in hash_types:
                repl, strategy = hash_value(e["text"], salt), "不可逆哈希"
            elif e["type"] in token_types:
                ids = token_ids[e["type"]]
                ids.setdefault(e["text"], len(ids) + 1)
                repl, strategy = f"[{e['type']}_{ids[e['text']]}]", "标记化替换"
            elif e["type"] in geo_types:
                repl, strategy = generalize_place(e["text"], geo_level), "地理泛化"
            else:
                continue  # 未配置策略的类型保持原样
            pieces += [text[pos:e["start"]], repl]
            segs += [(text[pos:e["start"]], None), (e["text"], (repl, strategy, e["type"]))]
            pos = e["end"]
            stats[(strategy, e["type"])] += 1
        pieces.append(text[pos:])
        segs.append((text[pos:], None))
        out.append({"id": rec["id"], "text": "".join(pieces)})
        if changes is not None:
            changes.append((rec, segs))
    mapping = {f"[{t}_{i}]": name for t, ids in token_ids.items() for name, i in ids.items()}
    return out, stats, mapping


def strategy_report(stats, hash_types, token_types, geo_types, geo_level):
    lines = ["脱敏策略配置:",
             f"  不可逆哈希 (加盐 SHA-256): {'、'.join(hash_types)}",
             f"  标记化替换 (全批编号一致): {'、'.join(token_types)}",
             f"  地理泛化 (保留到{geo_level}): {'、'.join(geo_types)}",
             "", "本批脱敏统计:"]
    by_strategy = defaultdict(list)
    for (strategy, kind), n in stats.items():
        by_strategy[strategy].append(f"{kind} {n}")
    for strategy in ("不可逆哈希", "标记化替换", "地理泛化"):
        if by_strategy[strategy]:
            lines.append(f"  {strategy}: {'，'.join(by_strategy[strategy])}")
    lines.append(f"  合计 {sum(stats.values())} 处")
    lines += ["", "映射表 (标记 -> 原文) 单独加密存放, 仅授权人员可回溯; 哈希不可逆."]
    return "\n".join(lines)


def changes_to_html(changes, stats):
    """脱敏前后对比 (web/pii_highlight.js 渲染): 每个实体整段显示 原文(红删除线) -> 替换值(绿), 后跟 类型·策略 标签.
    不用逐字 diff: 哈希值和原号码会被拆成交错的碎片, 看不清"""
    import html
    by_strategy = Counter()
    for (strategy, _), n in stats.items():
        by_strategy[strategy] += n
    summary = (f'<div class="coclp-summary">共脱敏 <b class="coclp-pii-num">{sum(stats.values())}</b> 处: '
               + "，".join(f"{k} {v}" for k, v in by_strategy.most_common()) + "</div>")
    blocks = []
    for rec, segs in changes:
        parts = []
        for text, change in segs:
            if change is None:
                parts.append(html.escape(text))
            else:
                repl, strategy, kind = change
                parts.append(f'<del class="coclp-del">{html.escape(text)}</del>'
                             f'<ins class="coclp-ins">{html.escape(repl)}</ins>'
                             f'<span class="coclp-pii-tag">{html.escape(kind)}·{html.escape(strategy)}</span>')
        n = sum(1 for _, c in segs if c)
        blocks.append(f'<div class="coclp-rec"><div class="coclp-rec-head">{html.escape(rec["id"])} '
                      f'<span class="coclp-stat">{html.escape(rec.get("source", ""))} 脱敏 {n} 处</span></div>'
                      f'<div>{"".join(parts)}</div></div>')
    return summary + "".join(blocks)


class Desensitizer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "detection_dir": ("STRING", {"default": "../example/offline_prepared/privacy_detection/output/merged"}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/desensitization/output"}),
            "哈希类型": ("STRING", {"default": "身份证号, 手机号, 学号, 邮箱"}),
            "标记化类型": ("STRING", {"default": "姓名, 学校, 机构"}),
            "泛化类型": ("STRING", {"default": "地址, 地名"}),
            "泛化级别": (GEO_LEVELS, {"default": "区县"}),
            "salt": ("STRING", {"default": "edu-pii-2026"}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("脱敏前目录", "脱敏后目录", "策略报告目录")
    FUNCTION = "run"
    OUTPUT_NODE = True  # 节点上直接显示脱敏前后对比
    CATEGORY = "MY_NODES/隐私"

    def run(self, detection_dir, output_dir, 哈希类型, 标记化类型, 泛化类型, 泛化级别, salt):
        hash_types, token_types, geo_types = split_types(哈希类型), split_types(标记化类型), split_types(泛化类型)
        records = []
        for path in sorted(Path(detection_dir).glob("*.jsonl")):
            with open(path, encoding="utf-8") as f:
                records += [json.loads(line) for line in f if line.strip()]
        changes = []
        out, stats, mapping = desensitize_records(records, hash_types, token_types, geo_types, 泛化级别, salt, changes)

        out_dir = Path(output_dir)
        (out_dir / "data").mkdir(parents=True, exist_ok=True)
        with open(out_dir / "data" / "desensitized.jsonl", "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        (out_dir / "report").mkdir(exist_ok=True)
        (out_dir / "report" / "脱敏策略与统计.md").write_text(
            strategy_report(stats, hash_types, token_types, geo_types, 泛化级别) + "\n", encoding="utf-8")
        (out_dir / "映射表_仅授权可见.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        result = (detection_dir, str(out_dir / "data"), str(out_dir / "report"))
        return {"ui": {"html": [changes_to_html(changes, stats)]}, "result": result}


if __name__ == "__main__":
    # python Corpus_Cleansing_Pipeline/desensitize_node.py <4.1 检测结果目录>
    import sys
    records = [json.loads(l) for p in sorted(Path(sys.argv[1]).glob("*.jsonl"))
               for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    args = (["身份证号", "手机号", "学号", "邮箱"], ["姓名", "学校", "机构"], ["地址", "地名"], "区县")
    out, stats, mapping = desensitize_records(records, *args, "edu-pii-2026")
    for before, after in zip(records, out):
        print("前:", before["text"])
        print("后:", after["text"])
        print()
    print(strategy_report(stats, *args))
    print(mapping)
