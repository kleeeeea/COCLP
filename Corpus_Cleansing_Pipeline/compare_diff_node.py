"""清洗前后对比: 两个 jsonl 目录按 id 对齐, 逐字 diff, 在节点上高亮显示 (删除标红划线, 新增标绿).

前端渲染见 web/compare_diff.js (把 ui.html 放进节点上的 DOM 组件).
"""
import difflib
import html
import json
from pathlib import Path

try:
    from .preview_dir_node import display_path
except ImportError:  # 直接 python compare_diff_node.py 调试时
    from preview_dir_node import display_path


def load_records_by_id(dir_path):
    """读取目录 (或单个文件) 下所有 jsonl, 返回 {id: text}, 保持原顺序"""
    root = Path(dir_path)
    files = [root] if root.is_file() else sorted(root.rglob("*.jsonl"))
    records = {}
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    records[obj.get("id", f"{file_path.name}:{len(records)}")] = obj.get("text", "")
    return records


def diff_segments(before, after):
    """逐字 diff -> [(op, text)], op 取 equal / delete / insert"""
    segments = []
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(("equal", before[i1:i2]))
        else:
            if i2 > i1:
                segments.append(("delete", before[i1:i2]))
            if j2 > j1:
                segments.append(("insert", after[j1:j2]))
    return segments


def show_newlines(text):
    """被删/新增的换行看不见, 换成 ↵ 再保留换行"""
    return text.replace("\n", "↵\n")


def collapse(text, keep_head, keep_tail):
    """只保留开头 keep_head 个字和结尾 keep_tail 个字, 中间折叠成 …"""
    if len(text) <= keep_head + keep_tail + 6:
        return text
    tail = text[len(text) - keep_tail:] if keep_tail else ""
    return text[:keep_head] + " … " + tail


def segments_to_html(segments, context_chars):
    """未改动的段落只保留改动处前后 context_chars 个字 (第一段只留结尾, 最后一段只留开头)"""
    parts = []
    for index, (op, text) in enumerate(segments):
        if op == "equal":
            keep_head = 0 if index == 0 else context_chars
            keep_tail = 0 if index == len(segments) - 1 else context_chars
            parts.append(html.escape(collapse(text, keep_head, keep_tail)))
        elif op == "delete":
            parts.append(f'<del class="coclp-del">{html.escape(show_newlines(text))}</del>')
        else:
            parts.append(f'<ins class="coclp-ins">{html.escape(show_newlines(text))}</ins>')
    return "".join(parts)


def build_diff_report(before_dir, after_dir, max_records, context_chars):
    before, after = load_records_by_id(before_dir), load_records_by_id(after_dir)
    common_ids = [rid for rid in before if rid in after]
    dropped = [rid for rid in before if rid not in after]

    diffs = []  # (改动字数, id, segments, 删除数, 新增数)
    for rid in common_ids:
        segments = diff_segments(before[rid], after[rid])
        n_del = sum(len(t) for op, t in segments if op == "delete")
        n_ins = sum(len(t) for op, t in segments if op == "insert")
        diffs.append((n_del + n_ins, rid, segments, n_del, n_ins))
    total_del = sum(d[3] for d in diffs)
    total_ins = sum(d[4] for d in diffs)

    blocks = []
    for _, rid, segments, n_del, n_ins in sorted(diffs, key=lambda d: -d[0])[:max_records]:  # 改动最多的排前面
        title = html.escape(before[rid].strip().split("\n")[0].lstrip("# ")[:30])
        blocks.append(
            f'<div class="coclp-rec"><div class="coclp-rec-head">{title}'
            f'<span class="coclp-stat">删除 {n_del} 字 · 新增 {n_ins} 字 · {len(before[rid])}→{len(after[rid])} 字</span></div>'
            f'<div class="coclp-rec-body">{segments_to_html(segments, context_chars)}</div></div>'
        )

    summary = (f'<div class="coclp-summary">清洗前: {html.escape(display_path(before_dir))} → 清洗后: {html.escape(display_path(after_dir))}<br>'
               f'对齐 {len(common_ids)} 条, 整条过滤 {len(dropped)} 条; 共删除 <del class="coclp-del">{total_del}</del> 字, '
               f'新增 <ins class="coclp-ins">{total_ins}</ins> 字</div>')
    text_report = f"对齐 {len(common_ids)} 条, 整条过滤 {len(dropped)} 条, 删除 {total_del} 字, 新增 {total_ins} 字"
    return summary + "".join(blocks), text_report


class CompareTextDiff:
    """清洗前后对比: 高亮显示每条语料被删掉 / 新增的内容"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "before_dir": ("STRING", {"forceInput": True}),
                "after_dir": ("STRING", {"forceInput": True}),
                "max_records": ("INT", {"default": 3, "min": 1, "max": 50}),
                "context_chars": ("INT", {"default": 40, "min": 0, "max": 500}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("对比摘要",)
    FUNCTION = "compare"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Preview"

    def compare(self, before_dir, after_dir, max_records, context_chars):
        html_report, text_report = build_diff_report(before_dir, after_dir, max_records, context_chars)
        return {"ui": {"html": [html_report]}, "result": (text_report,)}


if __name__ == "__main__":
    import sys
    before_dir, after_dir = sys.argv[1], sys.argv[2]
    print(build_diff_report(before_dir, after_dir, 2, 20)[0][:3000])
