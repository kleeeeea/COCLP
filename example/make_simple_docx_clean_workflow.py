"""生成最简单的、不调用任何模型的工作流 simple_docx_clean_workflow.json:
    DocxToMarkdown (docx -> md/纯文本)  ->  MarkdownInfoNode (md -> jsonl)  ->  MultiPruner (正则/规则清洗)
每一步后面接一个 "预览输出目录" 节点; 不分组, 不用 GroupExecutor, 直接点 "运行" 即可.

节点定义从 docx_workflow.json 里复制 (保证 widgets_values 格式和前端一致), 只改路径.
用法: python example/make_simple_docx_clean_workflow.py
"""
import copy
import json
from pathlib import Path

from make_pdf_test_workflow import find_node, add_preview_node, PREVIEW_W

EXAMPLE_DIR = Path(__file__).resolve().parent
SRC = EXAMPLE_DIR / "docx_workflow.json"
DST = EXAMPLE_DIR / "simple_docx_clean_workflow.json"

TEST_INPUT_DIR = "../example/test_data"
OUTPUT_ROOT = "../example/test_out/simple_docx"


def main():
    source = json.loads(SRC.read_text(encoding="utf-8"))
    docx_to_md = copy.deepcopy(find_node(source, "DocxToMarkdown"))
    md_to_jsonl = copy.deepcopy(find_node(source, "MarkdownInfoNode"))
    pruner = copy.deepcopy(find_node(source, "MultiPruner"))

    # 只保留这三个节点之间的两条连线: docx_to_md -> md_to_jsonl -> pruner
    link_md, link_jsonl = 1, 2
    docx_to_md["outputs"][0]["links"] = [link_md]
    md_to_jsonl["inputs"][0]["link"] = link_md
    md_to_jsonl["outputs"][0]["links"] = [link_jsonl]
    pruner["inputs"][0]["link"] = link_jsonl
    pruner["outputs"][0]["links"] = None

    # DocxToMarkdown: [input_base, output_base]
    docx_to_md["widgets_values"] = [TEST_INPUT_DIR, f"{OUTPUT_ROOT}/md"]
    # MarkdownInfoNode: [md_root(连线), original_root, output_file, threads]
    md_to_jsonl["widgets_values"][1:3] = [f"{OUTPUT_ROOT}/jsonl", f"{OUTPUT_ROOT}/jsonl/md_info.jsonl"]
    # MultiPruner: [input_dir(连线), output_dir, num_processes, min_text_length, enable_* x12]
    pruner["widgets_values"][1] = f"{OUTPUT_ROOT}/clean"
    pruner["widgets_values"][2] = 1   # 单进程
    pruner["widgets_values"][3] = 10  # 示例 docx 很短, 默认 100 字以下会被整条丢掉

    # 横排: 三个处理节点在上, 预览节点在下
    for i, node in enumerate([docx_to_md, md_to_jsonl, pruner]):
        node["pos"] = [i * (PREVIEW_W + 40), 0]

    workflow = {
        "id": "5f0c3c8e-0d1a-4c55-9a51-3a7e2d1c0b01",
        "revision": 0,
        "last_node_id": max(n["id"] for n in (docx_to_md, md_to_jsonl, pruner)),
        "last_link_id": link_jsonl,
        "nodes": [docx_to_md, md_to_jsonl, pruner],
        "links": [
            [link_md, docx_to_md["id"], 0, md_to_jsonl["id"], 0, "STRING"],
            [link_jsonl, md_to_jsonl["id"], 0, pruner["id"], 0, "STRING"],
        ],
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.8, "offset": [50, 50]}},
        "version": 0.4,
    }
    add_preview_node(workflow, docx_to_md, (0, 480), "预览: docx → markdown")
    add_preview_node(workflow, md_to_jsonl, (PREVIEW_W + 40, 480), "预览: markdown → jsonl")
    add_preview_node(workflow, pruner, (2 * (PREVIEW_W + 40), 480), "预览: 规则清洗后")

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
