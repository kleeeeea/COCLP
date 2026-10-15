"""语料规模看板: 大字号显示一个指标 (文档数 / Token 数 / 学段分布), 用于管道总览截图.

数据来源二选一:
- stats_json 为空: 从 corpus_dir (标注后的 jsonl) 实时统计; Token 数按 "中文 1 字 ≈ 1 token, 英文 1 词 ≈ 1.3 token" 估算
- stats_json 指向统计快照 json: 直接读其中的数字 (用于展示全量语料规模, 例如离线统计好的结果)
前端渲染见 web/stat_card.js.
"""
import html
import json
import re
from collections import Counter
from pathlib import Path

METRICS = ["文档数", "Token 数", "学段分布"]
COCLP_ROOT = Path(__file__).resolve().parent.parent
PATH_ALIASES_FILE = Path(__file__).resolve().parent / "config" / "path_aliases.json"


def resolve_alias(path):
    """本机不存在的生产路径 (如 /data/corpus/production/...) 按 config/path_aliases.json 换成本地目录"""
    if Path(path).exists() or not PATH_ALIASES_FILE.exists():
        return Path(path)
    aliases = json.loads(PATH_ALIASES_FILE.read_text(encoding="utf-8"))
    for prefix, local_dir in aliases.items():
        if not prefix.startswith("_") and str(path).startswith(prefix):
            return COCLP_ROOT / local_dir / str(path)[len(prefix):].lstrip("/")
    return Path(path)
STAGE_ORDER = ["学前", "小学", "初中", "高中", "职业教育", "高等教育", "跨学段"]


def estimate_tokens(text):
    cjk = len(re.findall(r"[一-鿿]", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    return int(cjk + words * 1.3)


def stats_from_corpus(corpus_dir):
    root = Path(corpus_dir)
    files = [root] if root.is_file() else sorted(root.rglob("*.jsonl"))
    docs, tokens, stages = 0, 0, Counter()
    for file_path in files:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                docs += 1
                tokens += estimate_tokens(record.get("text", ""))
                stages[record.get("学段", "未标注")] += 1
    return {"文档数": docs, "Token 数": tokens, "学段分布": dict(stages), "caption": "实时统计 (当前批次)"}


def format_count(value, unit):
    """12345678 -> 1,235 万; 203600000000 -> 2,036 亿"""
    if value >= 1e8:
        return f"{value / 1e8:,.0f}", f"亿{unit}"
    if value >= 1e4:
        return f"{value / 1e4:,.0f}", f"万{unit}"
    return f"{value:,}", unit


def render_number(title, value, unit, caption):
    number, unit_text = format_count(value, unit)
    return (f'<div class="coclp-card"><div class="coclp-card-title">{html.escape(title)}</div>'
            f'<div class="coclp-card-number">{number}<span class="coclp-card-unit">{unit_text}</span></div>'
            f'<div class="coclp-card-caption">{html.escape(caption)}</div></div>')


def render_distribution(title, counts, caption):
    total = sum(counts.values()) or 1
    keys = [k for k in STAGE_ORDER if k in counts] + [k for k in counts if k not in STAGE_ORDER]
    rows = []
    for key in keys:
        pct = counts[key] / total * 100
        rows.append(f'<div class="coclp-bar-row"><span class="coclp-bar-label">{html.escape(key)}</span>'
                    f'<span class="coclp-bar-track"><span class="coclp-bar-fill" style="width:{pct:.1f}%"></span></span>'
                    f'<span class="coclp-bar-pct">{pct:.0f}%</span></div>')
    return (f'<div class="coclp-card"><div class="coclp-card-title">{html.escape(title)}</div>'
            f'{"".join(rows)}<div class="coclp-card-caption">{html.escape(caption)}</div></div>')


def build_card(metric, stats):
    caption = stats.get("caption", "")
    if metric == "文档数":
        return render_number("入库文档数", stats["文档数"], "篇", caption), f"文档数 {stats['文档数']}"
    if metric == "Token 数":
        return render_number("语料规模 (Token)", stats["Token 数"], "", caption), f"Token 数 {stats['Token 数']}"
    return render_distribution("学段分布", stats["学段分布"], caption), f"学段分布 {stats['学段分布']}"


class CorpusStatCard:
    """语料规模看板: 一个节点显示一个大字号指标"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "corpus_dir": ("STRING", {"default": ""}),
                "metric": (METRICS,),
                "stats_json": ("STRING", {"default": ""}),  # 空 = 从 corpus_dir 实时统计
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("指标",)
    FUNCTION = "show"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Preview"

    def show(self, corpus_dir, metric, stats_json):
        if stats_json.strip():
            stats = json.loads(resolve_alias(stats_json.strip()).read_text(encoding="utf-8"))
        else:
            stats = stats_from_corpus(corpus_dir)
        card_html, summary = build_card(metric, stats)
        return {"ui": {"html": [card_html]}, "result": (summary,)}


if __name__ == "__main__":
    import sys
    # python stat_card_node.py <metric> <stats_json>   或   python stat_card_node.py <metric> --corpus <dir>
    metric, source = sys.argv[1], sys.argv[2]
    card = CorpusStatCard()
    result = card.show(sys.argv[3], metric, "") if source == "--corpus" else card.show("", metric, source)
    print(result["result"][0])
