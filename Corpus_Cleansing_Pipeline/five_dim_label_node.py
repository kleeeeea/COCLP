"""五维标注与分类 (招标要求第 5 条): 脱敏后语料按 学科 / 学段 / 场景 / 难度 / 格式 五个维度标注.

- 学科、学段、场景、难度: 大模型 (OpenAI 兼容接口) 一次调用返回 JSON, 取值必须在 config/five_dim/<维度>.txt 词表内,
  不在词表的归入兜底值 (其他 / 跨学段 / 中等)
- 格式: 规则判定, 按原始文件扩展名查 config/five_dim/格式.txt, 不调模型
- 另附 "标注依据" 一句话, 便于人工抽检
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

try:
    from .llm_utils import resolve_api_key, is_offline_prepared
except ImportError:  # 直接 python five_dim_label_node.py 调试时
    from llm_utils import resolve_api_key, is_offline_prepared

VOCAB_DIR = Path(__file__).parent / "config" / "five_dim"
LLM_DIMS = ("学科", "学段", "场景", "难度")
FALLBACK = {"学科": "其他", "学段": "跨学段", "场景": "其他", "难度": "中等"}


def load_vocab(vocab_dir=VOCAB_DIR):
    vocab = {dim: [l.strip() for l in (Path(vocab_dir) / f"{dim}.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
             for dim in LLM_DIMS}
    format_map = {}
    for line in (Path(vocab_dir) / "格式.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            ext, label = line.split("\t")
            format_map[ext.strip().lower()] = label.strip()
    return vocab, format_map


def build_prompt(vocab):
    options = "\n".join(f"- {dim}: {' / '.join(vocab[dim])}" for dim in LLM_DIMS)
    return (
        "你是教育语料标注员。阅读给定的教育语料, 按以下四个维度各选一个标签, 只能从给定选项中选:\n"
        f"{options}\n"
        "难度按目标学段学生的理解难度判断。\n"
        '只输出一个 JSON 对象, 不要解释, 格式: {"学科": "", "学段": "", "场景": "", "难度": "", "标注依据": "不超过30字"}'
    )


def parse_labels(answer, vocab):
    """解析模型输出的 JSON, 不在词表内的值换成兜底值"""
    match = re.search(r"\{.*\}", answer or "", flags=re.DOTALL)
    data = json.loads(match.group(0)) if match else {}
    labels = {dim: data.get(dim) if data.get(dim) in vocab[dim] else FALLBACK[dim] for dim in LLM_DIMS}
    labels["标注依据"] = str(data.get("标注依据", ""))[:60]
    return labels


def detect_format(record, source_dir, format_map):
    """格式: 找原始文件 (与 md 同名的源文件, 或记录里的 audio_path 等), 按扩展名查表"""
    for key in ("source_path", "audio_path", "image_path"):
        if record.get(key):
            return format_map.get(Path(record[key]).suffix.lower(), "其他")
    stem = Path(record.get("md_path", "")).stem
    if stem and source_dir and Path(source_dir).is_dir():
        for path in Path(source_dir).rglob(f"{stem}.*"):
            if path.suffix.lower() in format_map:
                return format_map[path.suffix.lower()]
    return "纯文本"


def label_record(record, client, model_name, system_prompt, vocab, format_map, source_dir, max_chars=3000):
    text = record.get("text", "")
    title = Path(record.get("md_path", "")).stem
    try:
        response = client.chat.completions.create(
            model=model_name, temperature=0, timeout=60,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": f"标题: {title}\n正文:\n{text[:max_chars]}"}])
        labels = parse_labels(response.choices[0].message.content, vocab)
    except Exception as e:
        print(f"[五维标注] {title} 调用失败, 使用兜底值: {type(e).__name__}: {e}")
        labels = {**FALLBACK, "标注依据": "模型调用失败, 待人工标注"}
    labels["格式"] = detect_format(record, source_dir, format_map)
    # 标签放在正文前面, 预览时先看到五个维度
    ordered = {k: record[k] for k in ("id",) if k in record}
    ordered.update({dim: labels[dim] for dim in ("学科", "学段", "场景", "难度", "格式", "标注依据")})
    ordered.update({k: v for k, v in record.items() if k not in ordered})
    return ordered


class FiveDimLabelNode:
    """五维标注与分类: 学科 / 学段 / 场景 / 难度 (大模型) + 格式 (规则)"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_folder": ("STRING", {"default": ""}),
                "output_folder": ("STRING", {"default": ""}),
                "api_key": ("STRING", {"default": "None"}),
                "api_url": ("STRING", {"default": ""}),
                "model_name": ("STRING", {"default": "qwen"}),
                "source_dir": ("STRING", {"default": "../example/test_data"}),
                "max_workers": ("INT", {"default": 4, "min": 1, "max": 64}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("out_path",)
    FUNCTION = "label"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Document Processing"

    def label(self, input_folder, output_folder, api_key, api_url, model_name, source_dir, max_workers):
        if is_offline_prepared(output_folder):
            print(f"[离线回放] 五维标注结果已预先生成, 跳过大模型调用: {output_folder}")
            return (output_folder,)

        vocab, format_map = load_vocab()
        system_prompt = build_prompt(vocab)
        client = OpenAI(api_key=resolve_api_key(api_key), base_url=api_url)
        os.makedirs(output_folder, exist_ok=True)

        for in_file in sorted(Path(input_folder).glob("*.jsonl")):
            records = [json.loads(l) for l in in_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                labeled = list(pool.map(
                    lambda r: label_record(r, client, model_name, system_prompt, vocab, format_map, source_dir), records))
            with open(Path(output_folder) / in_file.name, "w", encoding="utf-8") as f:
                for record in labeled:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[五维标注] {in_file.name}: {len(labeled)} 条")
        return (output_folder,)


if __name__ == "__main__":
    # 调试: python five_dim_label_node.py <输入jsonl目录> <输出目录> <api_url> <model_name>
    import sys
    vocab, format_map = load_vocab()
    print(build_prompt(vocab))
    print(parse_labels('```json\n{"学科": "语文", "学段": "小学", "场景": "课外阅读", "难度": "火星", "标注依据": "成语故事"}\n```', vocab))
    if len(sys.argv) == 5:
        FiveDimLabelNode().label(sys.argv[1], sys.argv[2], "None", sys.argv[3], sys.argv[4], "../example/test_data", 2)
