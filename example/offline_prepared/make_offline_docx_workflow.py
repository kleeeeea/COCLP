"""生成 "离线预先生成结果" 版的 docx 工作流 offline_prepared/docx_workflow_test.json, 用于标书截图.

流程 (和 example/docx_workflow_test.json 一样):
    Word 文档转换 -> Markdown→JSONL -> 多功能文本清洗 -> 文档批量分类 (ecnu-plus) -> 问答对生成 (ecnu-plus)
所有输出写到 offline_prepared/output/. 大模型两步离线跑一次后, 在输出目录放 .offline_prepared 标记,
之后再点 "运行" 就直接复用已有结果 (见 Corpus_Cleansing_Pipeline/llm_utils.py 的 is_offline_prepared), 一两秒出全部预览.

用法:
    python example/offline_prepared/make_offline_docx_workflow.py          # 生成 workflow json
    (在 ComfyUI 里打开 offline_prepared/docx_workflow_test 运行一次, 真正调用大模型生成结果)
    python example/offline_prepared/make_offline_docx_workflow.py --mark   # 给分类/QA 输出目录打上离线标记
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from make_pdf_test_workflow import find_node  # noqa: E402

SRC = HERE.parent / "docx_workflow_test.json"
DST = HERE / "docx_workflow_test.json"
OFFLINE_MARKER = ".offline_prepared"  # 与 llm_utils.OFFLINE_MARKER 一致

OUTPUT_ROOT = "../example/offline_prepared/output"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
OUTPUT_DIR = HERE / "output"
INPUT_DIR = "../example/test_data"
LLM_OUTPUT_SUBDIRS = ("label", "QA")

GROUP_TITLES = {"docx_pipeline": "文档处理流水线", "QA": "问答对生成"}
NODE_TITLES = {
    "DocxToMarkdown": "Word 文档转换",
    "MarkdownInfoNode": "Markdown → JSONL",
    "MultiPruner": "多功能文本清洗器",
    "BatchProcessDocuments_Zho": "文档批量分类 (ecnu-plus)",
    "BatchGenerateQANode": "问答对生成 (ecnu-plus)",
    "PromptTextEditor": "模型接口地址",
    "GroupExecutorSender": "流水线执行器",
}


def build_workflow():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))
    workflow["id"] = "0ff1e5a0-d0c5-4b1d-9c3e-5c2e7a1b0d01"  # 和 docx_workflow_test 区分, 可同时打开

    find_node(workflow, "DocxToMarkdown")["widgets_values"] = [INPUT_DIR, f"{OUTPUT_ROOT}/md"]
    md_to_jsonl = find_node(workflow, "MarkdownInfoNode")
    md_to_jsonl["widgets_values"][1:3] = [f"{OUTPUT_ROOT}/jsonl", f"{OUTPUT_ROOT}/jsonl/md_info.jsonl"]
    find_node(workflow, "MultiPruner")["widgets_values"][1] = f"{OUTPUT_ROOT}/clean"
    find_node(workflow, "BatchProcessDocuments_Zho")["widgets_values"][1] = f"{OUTPUT_ROOT}/label"
    find_node(workflow, "BatchGenerateQANode")["widgets_values"][1] = f"{OUTPUT_ROOT}/QA"

    for node in workflow["nodes"]:
        if node["type"] in NODE_TITLES:
            node["title"] = NODE_TITLES[node["type"]]
        if node["type"] == "GroupExecutorSingle":  # 组执行器按组名找节点, 组改名要同步
            old_group = node["widgets_values"][0]
            node["widgets_values"][0] = GROUP_TITLES.get(old_group, old_group)
            node["title"] = f"执行组: {node['widgets_values'][0]}"
    for group in workflow["groups"]:
        group["title"] = GROUP_TITLES.get(group["title"], group["title"])

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


def mark_offline_prepared():
    for sub in LLM_OUTPUT_SUBDIRS:
        out_dir = OUTPUT_DIR / sub
        if not any(out_dir.glob("*.jsonl")):
            raise SystemExit(f"{out_dir} 里还没有结果, 先在 ComfyUI 里完整运行一次")
        (out_dir / OFFLINE_MARKER).write_text("结果已离线生成, 大模型节点直接复用\n", encoding="utf-8")
        print(f"标记 {out_dir / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mark", action="store_true", help="给分类/QA 输出目录打离线标记")
    args = parser.parse_args()
    mark_offline_prepared() if args.mark else build_workflow()
