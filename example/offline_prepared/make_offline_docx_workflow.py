"""生成 "离线预先生成结果" 版的 docx 工作流 offline_prepared/docx_workflow_test.json, 用于标书截图.

流程 (example/docx_workflow_test.json 去掉 QA 组):
    Word 文档转换 -> Markdown→JSONL -> 多功能文本清洗 -> 文档批量分类 (ecnu-plus)
所有输出写到 offline_prepared/output/. 分类这一步离线跑一次后, 在输出目录放 .offline_prepared 标记,
之后再点 "运行" 就直接复用已有结果 (见 Corpus_Cleansing_Pipeline/llm_utils.py 的 is_offline_prepared), 一两秒出全部预览.

用法:
    python example/offline_prepared/make_offline_docx_workflow.py          # 生成 workflow json
    (在 ComfyUI 里打开 offline_prepared/docx_workflow_test 运行一次, 真正调用大模型生成结果)
    python example/offline_prepared/make_offline_docx_workflow.py --mark   # 给分类输出目录打上离线标记
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
LLM_OUTPUT_SUBDIRS = ("label",)

GROUP_TITLES = {"docx_pipeline": "文档处理流水线"}
NODE_TITLES = {
    "DocxToMarkdown": "Word 文档转换",
    "MarkdownInfoNode": "Markdown → JSONL",
    "MultiPruner": "多功能文本清洗器",
    "BatchProcessDocuments_Zho": "文档批量分类 (ecnu-plus)",
    "PromptTextEditor": "模型接口地址",
    "GroupExecutorSender": "流水线执行器",
}


def remove_nodes(workflow, node_ids):
    """删节点, 连带删掉相关连线, 并清理其它节点上指向这些连线的引用"""
    dead_links = {l[0] for l in workflow["links"] if l[1] in node_ids or l[3] in node_ids}
    workflow["links"] = [l for l in workflow["links"] if l[0] not in dead_links]
    workflow["nodes"] = [n for n in workflow["nodes"] if n["id"] not in node_ids]
    for node in workflow["nodes"]:
        for inp in node.get("inputs", []):
            if inp.get("link") in dead_links:
                inp["link"] = None
        for out in node.get("outputs", []):
            if out.get("links"):
                out["links"] = [l for l in out["links"] if l not in dead_links] or None


def add_link(workflow, from_node, from_slot, to_node, to_slot, link_type):
    link_id = workflow["last_link_id"] + 1
    workflow["last_link_id"] = link_id
    workflow["links"].append([link_id, from_node["id"], from_slot, to_node["id"], to_slot, link_type])
    from_node["outputs"][from_slot]["links"] = (from_node["outputs"][from_slot].get("links") or []) + [link_id]
    to_node["inputs"][to_slot]["link"] = link_id


def drop_qa_group(workflow):
    """不需要 QA: 删掉 QA 组里的节点 (QA 节点、QA 预览、QA 组执行器), 文档组执行器直接连流水线执行器"""
    qa_group = next(g for g in workflow["groups"] if g["title"] == "QA")
    qa_executor = next(n for n in workflow["nodes"]
                       if n["type"] == "GroupExecutorSingle" and n["widgets_values"][0] == "QA")
    qa_ids = {find_node(workflow, "BatchGenerateQANode")["id"], qa_executor["id"]}
    qa_ids |= {n["id"] for n in workflow["nodes"]
               if n["type"] == "PreviewOutputDir" and n.get("title", "").startswith("预览: QA")}
    remove_nodes(workflow, qa_ids)
    workflow["groups"].remove(qa_group)

    docx_executor = next(n for n in workflow["nodes"] if n["type"] == "GroupExecutorSingle")
    add_link(workflow, docx_executor, 0, find_node(workflow, "GroupExecutorSender"), 0, "SIGNAL")


def use_diff_for_clean_preview(workflow, extra_height=100):
    """把 "预览: 清洗后结果" 换成 "清洗前后对比": before 接 Markdown→JSONL 的输出, after 接清洗器的输出"""
    node = next(n for n in workflow["nodes"]
                if n["type"] == "PreviewOutputDir" and n.get("title") == "预览: 清洗后结果")
    after_link = node["inputs"][0]["link"]
    node.update({
        "type": "CompareTextDiff",
        "title": "清洗前后对比 (高亮差异)",
        "properties": {"Node name for S&R": "CompareTextDiff"},
        "inputs": [{"name": "before_dir", "type": "STRING", "link": None},
                   {"name": "after_dir", "type": "STRING", "link": after_link}],
        "outputs": [{"name": "对比摘要", "type": "STRING", "links": None}],
        "widgets_values": [3, 40],
    })
    node["size"][1] += extra_height
    for link in workflow["links"]:
        if link[0] == after_link:
            link[4] = 1  # 清洗器输出改接到 after_dir (第 2 个输入)
    add_link(workflow, find_node(workflow, "MarkdownInfoNode"), 0, node, 0, "STRING")
    for group in workflow["groups"]:
        group["bounding"][3] += extra_height


def add_doc_first_page_preview(workflow, width=460, height=900, gap=40):
    """在 "Word 文档转换" 左边加 "文档首页预览" (显示原始 docx 第一页), 输出连到它的 input_base; 分组向左扩"""
    docx_to_md = find_node(workflow, "DocxToMarkdown")
    group = next(g for g in workflow["groups"] if g["title"] == GROUP_TITLES["docx_pipeline"])
    gx, gy = group["bounding"][0], group["bounding"][1]
    node_x = gx - width - gap
    group["bounding"][0] = node_x - 20
    group["bounding"][2] += width + gap + 20

    node_id = workflow["last_node_id"] + 1
    workflow["last_node_id"] = node_id
    preview = {
        "id": node_id, "type": "DocFirstPagePreview", "title": "原始文档 (首页预览)",
        "pos": [node_x, gy + 60], "size": [width, height], "flags": {}, "order": 0, "mode": 0,
        "inputs": [], "outputs": [{"name": "文档目录", "type": "STRING", "links": None}],
        "properties": {"Node name for S&R": "DocFirstPagePreview"},
        # [input_dir, file_types, max_docs, width_px, cache_dir]
        "widgets_values": [INPUT_DIR, "docx", 4, 800, f"{OUTPUT_ROOT}/doc_preview_cache"],
    }
    workflow["nodes"].append(preview)
    # input_base 从控件改成连线输入
    docx_to_md.setdefault("inputs", []).append(
        {"name": "input_base", "type": "STRING", "widget": {"name": "input_base"}, "link": None})
    add_link(workflow, preview, 0, docx_to_md, len(docx_to_md["inputs"]) - 1, "STRING")


def build_workflow():
    workflow = json.loads(SRC.read_text(encoding="utf-8"))
    workflow["id"] = "0ff1e5a0-d0c5-4b1d-9c3e-5c2e7a1b0d01"  # 和 docx_workflow_test 区分, 可同时打开
    drop_qa_group(workflow)
    use_diff_for_clean_preview(workflow)

    find_node(workflow, "DocxToMarkdown")["widgets_values"] = [INPUT_DIR, f"{OUTPUT_ROOT}/md"]
    md_to_jsonl = find_node(workflow, "MarkdownInfoNode")
    md_to_jsonl["widgets_values"][1:3] = [f"{OUTPUT_ROOT}/jsonl", f"{OUTPUT_ROOT}/jsonl/md_info.jsonl"]
    find_node(workflow, "MultiPruner")["widgets_values"][1] = f"{OUTPUT_ROOT}/clean"
    find_node(workflow, "BatchProcessDocuments_Zho")["widgets_values"][1] = f"{OUTPUT_ROOT}/label"

    for node in workflow["nodes"]:
        if node["type"] in NODE_TITLES:
            node["title"] = NODE_TITLES[node["type"]]
        if node["type"] == "GroupExecutorSingle":  # 组执行器按组名找节点, 组改名要同步
            old_group = node["widgets_values"][0]
            node["widgets_values"][0] = GROUP_TITLES.get(old_group, old_group)
            node["title"] = f"执行组: {node['widgets_values'][0]}"
    for group in workflow["groups"]:
        group["title"] = GROUP_TITLES.get(group["title"], group["title"])

    add_doc_first_page_preview(workflow)  # 放在组改名之后, 按中文组名找分组

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
