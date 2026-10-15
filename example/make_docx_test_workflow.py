"""从 docx_workflow.json 生成 docx_workflow_test.json:
- DocxToMarkdown 直接读 example/test_data 里的 .docx (原来读解压分类工作流的输出 test_out/classify/docx)
- 文档分类 / QA 生成 用 ECNU 的 ecnu-plus; api_key 填 None, 实际 key 由 run.sh start 从 .env 读进 ECNU_API_KEY
- docx→md / 清洗 / 分类 / QA 后面各接一个 "预览输出目录" 节点, 放在各自组里

用法: python example/make_docx_test_workflow.py
"""
import json
from pathlib import Path

from make_pdf_test_workflow import find_node, add_preview_node, PREVIEW_W, PREVIEW_H
from make_anonymization_test_workflow import node_linked_to, API_URL, MODEL_NAME

EXAMPLE_DIR = Path(__file__).resolve().parent
SRC = EXAMPLE_DIR / "docx_workflow.json"
DST = EXAMPLE_DIR / "docx_workflow_test.json"

TEST_INPUT_DIR = "../example/test_data"
OUTPUT_ROOT = "../example/test_out/docx"


def main():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))

    docx_to_md = find_node(workflow, "DocxToMarkdown")
    pruner = find_node(workflow, "MultiPruner")
    labeler = find_node(workflow, "BatchProcessDocuments_Zho")
    qa = find_node(workflow, "BatchGenerateQANode")

    # DocxToMarkdown: [input_base, output_base]
    docx_to_md["widgets_values"] = [TEST_INPUT_DIR, f"{OUTPUT_ROOT}/md"]
    # BatchProcessDocuments_Zho: [input_folder, output_folder, api_key, api_url, model_name, valid_files_folder, max_workers, trigger]
    labeler["widgets_values"][4] = MODEL_NAME
    labeler["widgets_values"][6] = 2
    labeler["widgets_values"][7] = True
    # BatchGenerateQANode: [input_folder, output_folder, api_key, api_url, model_name, max_workers, shard_size]
    qa["widgets_values"][4] = MODEL_NAME
    qa["widgets_values"][5] = 2
    for node in (labeler, qa):
        node_linked_to(workflow, node, "api_url")["widgets_values"] = [API_URL]

    pipeline_group = next(g for g in workflow["groups"] if g["title"] == "docx_pipeline")
    gx, gy, gw, gh = pipeline_group["bounding"]
    row_y = gy + gh + 20
    add_preview_node(workflow, docx_to_md, (gx + 20, row_y), "预览: docx → markdown")
    add_preview_node(workflow, pruner, (gx + 40 + PREVIEW_W, row_y), "预览: 清洗后结果")
    add_preview_node(workflow, labeler, (gx + 60 + 2 * PREVIEW_W, row_y), "预览: 分类结果")
    pipeline_group["bounding"][3] = gh + PREVIEW_H + 80

    qa_group = next(g for g in workflow["groups"] if g["title"] == "QA")
    qx, qy, qw, qh = qa_group["bounding"]
    add_preview_node(workflow, qa, (qx + 20, qy + qh + 20), "预览: QA 结果")
    qa_group["bounding"][2] = max(qw, PREVIEW_W + 40)
    qa_group["bounding"][3] = qh + PREVIEW_H + 80

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
