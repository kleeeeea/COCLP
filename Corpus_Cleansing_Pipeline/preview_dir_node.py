import os
import json
from pathlib import Path

TEXT_SUFFIXES = (".jsonl", ".json", ".md", ".txt")


LONG_TEXT_KEYS = ("text", "content", "question", "answer")
HIDDEN_KEYS = ("md_path", "audio_path")  # 本地路径不展示


def format_record(index, obj, max_chars):
    """一条 jsonl 记录 -> 易读文本: 短字段一行一个, 长文本字段原样换行展示"""
    lines = [f"── 第 {index} 条 ──"]
    for key, value in obj.items():
        if key in HIDDEN_KEYS or key in LONG_TEXT_KEYS:
            continue
        if key == "id" and isinstance(value, str) and len(value) > 16:
            value = value[:12] + "…"
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {value[:120]}")
    for key in LONG_TEXT_KEYS:
        if isinstance(obj.get(key), str):
            text = obj[key]
            lines.append(f"{key}:\n{text[:max_chars]}{'…' if len(text) > max_chars else ''}")
    return "\n".join(lines)


def read_text_preview(file_path, max_chars):
    """读一个文件的开头; jsonl 逐条展开字段, 正文正常换行 (不显示转义的 JSON)"""
    if file_path.suffix != ".jsonl":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    blocks, used = [], 0
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for index, line in enumerate(f, start=1):
            if used >= max_chars:
                blocks.append("……")
                break
            try:
                block = format_record(index, json.loads(line), max_chars - used)
            except json.JSONDecodeError:
                block = line.strip()
            blocks.append(block)
            used += len(block)
    return "\n\n".join(blocks)


def display_path(path):
    """预览里不出现 /Users/... 这类本机路径: 尽量显示成相对 COCLP 目录的路径"""
    coclp_root = Path(__file__).resolve().parent.parent
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(coclp_root))
    except ValueError:
        return resolved.name


def build_dir_preview(dir_path, max_files, max_chars):
    root = Path(dir_path)
    if not root.exists():
        return f"目录不存在: {display_path(root)}"
    if root.is_file():
        files = [root]
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    if not files:
        return f"目录里没有 {TEXT_SUFFIXES} 文件: {display_path(root)}"

    parts = [f"目录: {display_path(root)}  (共 {len(files)} 个文本文件, 显示前 {min(max_files, len(files))} 个)"]
    for file_path in files[:max_files]:
        size_kb = os.path.getsize(file_path) / 1024
        parts.append(f"\n===== {file_path.relative_to(root) if root.is_dir() else file_path.name}  ({size_kb:.1f} KB) =====")
        parts.append(read_text_preview(file_path, max_chars))
    return "\n".join(parts)


class PreviewOutputDir:
    """接在任意 "输出目录路径" 后面, 把目录里的结果文件内容显示在节点上"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "dir_path": ("STRING", {"forceInput": True}),
                "max_files": ("INT", {"default": 3, "min": 1, "max": 50}),
                "max_chars": ("INT", {"default": 2000, "min": 100, "max": 100000, "step": 100}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("preview_text",)
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Preview"

    def preview(self, dir_path, max_files, max_chars):
        text = build_dir_preview(dir_path, max_files, max_chars)
        # ui.text 由 web/preview_dir.js 渲染成节点上的只读文本框
        return {"ui": {"text": [text]}, "result": (text,)}


if __name__ == "__main__":
    import sys
    print(build_dir_preview(sys.argv[1] if len(sys.argv) > 1 else ".", 3, 2000))
