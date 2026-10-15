"""从 pdf_workflow.json 生成 pdf_workflow_test.json:
- Mineru 直接读 example/test_data (原来读的是解压分类工作流的输出 test_out/classify/pdf)
- 在 OCR / jsonl / 清洗 三步后面各接一个 "预览输出目录" 节点, 放在 pdf_pipeline 组里 (GroupExecutor 只执行组内输出节点)
- 关掉需要大模型 API 的 "文档批量分类处理" (trigger=False), 没配 api_key 也能跑通前面几步

用法: python example/make_pdf_test_workflow.py
"""
import copy
import json
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
SRC = EXAMPLE_DIR / "pdf_workflow.json"
DST = EXAMPLE_DIR / "pdf_workflow_test.json"

TEST_INPUT_DIR = "../example/test_data"
PREVIEW_W, PREVIEW_H = 420, 360


def find_node(workflow, node_type):
    return next(n for n in workflow["nodes"] if n["type"] == node_type)


def add_preview_node(workflow, source_node, pos, title):
    node_id = workflow["last_node_id"] + 1
    link_id = workflow["last_link_id"] + 1
    workflow["last_node_id"], workflow["last_link_id"] = node_id, link_id

    workflow["nodes"].append({
        "id": node_id,
        "type": "PreviewOutputDir",
        "title": title,
        "pos": list(pos),
        "size": [PREVIEW_W, PREVIEW_H],
        "flags": {},
        "order": 99,
        "mode": 0,
        "inputs": [{"name": "dir_path", "type": "STRING", "link": link_id}],
        "outputs": [{"name": "preview_text", "type": "STRING", "links": None}],
        "properties": {"Node name for S&R": "PreviewOutputDir"},
        "widgets_values": [3, 2000],
    })
    source_node["outputs"][0].setdefault("links", None)
    source_node["outputs"][0]["links"] = (source_node["outputs"][0]["links"] or []) + [link_id]
    # link 格式: [link_id, from_node, from_slot, to_node, to_slot, type]
    workflow["links"].append([link_id, source_node["id"], 0, node_id, 0, "STRING"])


def main():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))
    workflow = copy.deepcopy(workflow)

    mineru = find_node(workflow, "Mineru_ocr")
    md_to_jsonl = find_node(workflow, "MarkdownInfoNode")
    pruner = find_node(workflow, "MultiPruner")
    labeler = find_node(workflow, "BatchProcessDocuments_Zho")

    mineru["widgets_values"][0] = TEST_INPUT_DIR
    labeler["widgets_values"][-1] = False  # trigger

    group = next(g for g in workflow["groups"] if g["title"] == "pdf_pipeline")
    gx, gy, gw, gh = group["bounding"]
    row_y = gy + gh + 20  # 原组底部下面一排放 3 个预览节点
    add_preview_node(workflow, mineru, (gx + 20, row_y), "预览: MinerU OCR 结果")
    add_preview_node(workflow, md_to_jsonl, (gx + 40 + PREVIEW_W, row_y), "预览: Markdown → JSONL")
    add_preview_node(workflow, pruner, (gx + 60 + 2 * PREVIEW_W, row_y), "预览: 清洗后结果")
    group["bounding"][3] = gh + PREVIEW_H + 80  # 组往下扩, 把预览节点包进来

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
