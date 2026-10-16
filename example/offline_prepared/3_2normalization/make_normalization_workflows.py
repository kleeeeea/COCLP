"""3.2 格式归一化与语言规范化: 两个离线工作流 (用于标书截图, 2 张图), 全部规则处理, 不调模型.

    图 1 归一化对比:  格式归一化 (只开 全半角 / 数学公式 / 中英标点) ──> 清洗前后对比 (高亮差异)
    图 2 简繁/术语:   格式归一化 (只开 简繁统一 / 术语统一) ──> 清洗前后对比
                      └──> 预览: 术语词典
直接点 "运行".

本目录 (example/offline_prepared/normalization/):
    data/format/      模拟样例: 全角字母数字、中英标点混用、Unicode 数学符号
    data/t2s_terms/   模拟样例: 繁体、术语别名; 术语词典.tsv
    output/           归一化结果 (运行后生成)
    normalization_format.json / normalization_t2s_terms.json   工作流 (本脚本生成)
    *.png             截图 (../shoot_workflow.py 生成)
节点代码: Corpus_Cleansing_Pipeline/text_normalizer_node.py (归一化), compare_diff_node.py (对比)

用法 (在 COCLP 目录下):
    python example/offline_prepared/normalization/make_normalization_workflows.py
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/normalization_format.json \
        --out example/offline_prepared/normalization/normalization_format.png
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/normalization_t2s_terms.json \
        --out example/offline_prepared/normalization/normalization_t2s_terms.png
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REL = "../example/offline_prepared/normalization"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
TERM_DICT = f"{REL}/data/t2s_terms/术语词典.tsv"


def new_workflow(workflow_id):
    workflow = {"id": workflow_id, "revision": 0, "last_node_id": 0, "last_link_id": 0, "nodes": [], "links": [],
                "groups": [], "config": {}, "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}

    def add_node(node_type, title, pos, size, inputs, outputs, widgets_values):
        workflow["last_node_id"] += 1
        node = {"id": workflow["last_node_id"], "type": node_type, "title": title,
                "pos": list(pos), "size": list(size), "flags": {}, "order": workflow["last_node_id"], "mode": 0,
                "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
                "outputs": [{"name": n, "type": t, "links": None} for n, t in outputs],
                "properties": {"Node name for S&R": node_type}, "widgets_values": widgets_values}
        workflow["nodes"].append(node)
        return node

    def add_link(src, src_slot, dst, dst_slot, link_type="STRING"):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], src_slot, dst["id"], dst_slot, link_type])
        src["outputs"][src_slot]["links"] = (src["outputs"][src_slot]["links"] or []) + [link_id]
        dst["inputs"][dst_slot]["link"] = link_id

    return workflow, add_node, add_link


def add_normalizer_and_compare(add_node, add_link, title, sub, flags):
    """flags: (全半角, 数学公式, 中英标点, 简繁统一, 术语统一)"""
    # TextNormalizer: [input_dir, output_dir, 全半角, 数学公式, 中英标点, 简繁统一, 术语统一, term_dict]
    normalizer = add_node("TextNormalizer", title, (0, 0), (380, 330), [],
                          [("原始语料目录", "STRING"), ("归一化后目录", "STRING")],
                          [f"{REL}/data/{sub}", f"{REL}/output/{sub}", *flags, TERM_DICT])
    # CompareTextDiff: inputs before_dir / after_dir, widgets [max_records, context_chars]
    compare = add_node("CompareTextDiff", "清洗前后对比 (高亮差异)", (440, 0), (680, 560),
                       [("before_dir", "STRING"), ("after_dir", "STRING")], [("对比摘要", "STRING")], [4, 500])
    add_link(normalizer, 0, compare, 0)
    add_link(normalizer, 1, compare, 1)
    return normalizer


def save(workflow, name, group_title, bounding):
    workflow["groups"].append({"id": 1, "title": group_title, "bounding": bounding,
                               "color": "#3f789e", "font_size": 24, "flags": {}})
    dst = HERE / f"{name}.json"
    dst.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {dst}")


def build_format_workflow():
    workflow, add_node, add_link = new_workflow("0ff1e5a0-a0b1-4b1d-9c3e-5c2e7a1b0d06")
    add_normalizer_and_compare(add_node, add_link, "格式归一化 (全半角 / 数学公式 / 中英标点)", "format",
                               (True, True, True, False, False))
    save(workflow, "normalization_format", "格式归一化: 全半角、中英标点、数学公式", [-40, -80, 1200, 700])


def build_t2s_terms_workflow():
    workflow, add_node, add_link = new_workflow("0ff1e5a0-a0b1-4b1d-9c3e-5c2e7a1b0d07")
    normalizer = add_normalizer_and_compare(add_node, add_link, "语言规范化 (简繁统一 / 术语统一)", "t2s_terms",
                                            (False, False, False, True, True))
    # PreviewOutputDir: [max_files, max_chars, file_pattern]; 术语词典和样例在同一个目录
    terms = add_node("PreviewOutputDir", "预览: 术语词典", (0, 400), (380, 360),
                     [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 1000, "*.tsv"])
    add_link(normalizer, 0, terms, 0)
    save(workflow, "normalization_t2s_terms", "语言规范化: 简繁统一、术语统一", [-40, -80, 1200, 900])


if __name__ == "__main__":
    build_format_workflow()
    build_t2s_terms_workflow()
