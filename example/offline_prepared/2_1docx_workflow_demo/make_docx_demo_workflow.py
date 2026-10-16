"""最简 docx 采集工作流 (离线, 用于标书截图): 基于 ../多源多模态教育语料构建总体能力/docx_workflow_test.json,
只保留文档采集部分, 去掉文本清洗、清洗前后对比、五维标注、模型接口地址和组执行器.

    原始文档 (首页预览) -> Word 文档转换 -> Markdown → JSONL
                            └> 预览: docx → markdown   └> 预览: 结构化语料 (JSONL)
全部是本地处理, 不调模型; 不分组执行器, 直接点 "运行".

本目录 (example/offline_prepared/docx_workflow_demo/):
    output/                   转换结果 (md / jsonl / 首页预览缓存)
    docx_workflow_demo.json   工作流 (本脚本生成)
    docx_workflow_demo*.png   截图 (../shoot_workflow.py 生成)

用法 (在 COCLP 目录下):
    python example/offline_prepared/docx_workflow_demo/make_docx_demo_workflow.py
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/docx_workflow_demo.json \
        --out example/offline_prepared/docx_workflow_demo/docx_workflow_demo.png
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
from make_offline_docx_workflow import remove_nodes, find_node  # noqa: E402
from make_pdf_test_workflow import add_preview_node  # noqa: E402

SRC = HERE.parent / "多源多模态教育语料构建总体能力" / "docx_workflow_test.json"
DST = HERE / "docx_workflow_demo.json"
REL = "../example/offline_prepared/docx_workflow_demo/output"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
KEEP_TYPES = ("DocFirstPagePreview", "DocxToMarkdown", "MarkdownInfoNode")
KEEP_PREVIEW_TITLE = "预览: docx → markdown"


def fit_group(workflow, group, pad=40, title_h=60):
    """组框包住所有节点"""
    nodes = workflow["nodes"]
    x0 = min(n["pos"][0] for n in nodes) - pad
    y0 = min(n["pos"][1] for n in nodes) - title_h
    x1 = max(n["pos"][0] + n["size"][0] for n in nodes) + pad
    y1 = max(n["pos"][1] + n["size"][1] for n in nodes) + pad
    group["bounding"] = [x0, y0, x1 - x0, y1 - y0]


def build_workflow():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))
    workflow["id"] = "0ff1e5a0-d0c5-4b1d-9c3e-5c2e7a1b0d04"

    keep = {n["id"] for n in workflow["nodes"]
            if n["type"] in KEEP_TYPES or n.get("title") == KEEP_PREVIEW_TITLE}
    remove_nodes(workflow, {n["id"] for n in workflow["nodes"]} - keep)

    first_page = find_node(workflow, "DocFirstPagePreview")
    # DocFirstPagePreview: [input_dir, file_types, max_docs, width_px, cache_dir]
    first_page["widgets_values"][4] = f"{REL}/doc_preview_cache"
    find_node(workflow, "DocxToMarkdown")["widgets_values"][1] = f"{REL}/md"
    md_to_jsonl = find_node(workflow, "MarkdownInfoNode")
    md_to_jsonl["widgets_values"][1:3] = [f"{REL}/jsonl", f"{REL}/jsonl/md_info.jsonl"]

    md_preview = next(n for n in workflow["nodes"] if n.get("title") == KEEP_PREVIEW_TITLE)
    add_preview_node(workflow, md_to_jsonl,
                     (md_preview["pos"][0] + md_preview["size"][0] + 40, md_preview["pos"][1]),
                     "预览: 结构化语料 (JSONL)")

    workflow["groups"] = [{"id": 1, "title": "Word 文档采集", "bounding": [0, 0, 0, 0],
                           "color": "#3f789e", "font_size": 24, "flags": {}}]
    fit_group(workflow, workflow["groups"][0])
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")
    for n in workflow["nodes"]:
        print(" ", n["id"], n["type"], n.get("title", ""), n.get("widgets_values"))


if __name__ == "__main__":
    build_workflow()
