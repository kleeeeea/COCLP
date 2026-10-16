"""5 语料标注与分类: 离线工作流 (用于标书截图), 只保留 "五维标注与分类" 这一步.

    语料输入 ─┬─> 预览: 待标注语料
              └─> 五维标注与分类 (ecnu-plus) ──> 预览: 五维标注结果
    模型接口地址 ──┘
学科 / 学段 / 场景 / 难度 由大模型按词表标注, 格式按文件类型规则判定, 另附 "标注依据".
节点和参数取自 ../多源多模态教育语料构建总体能力/docx_workflow_test.json; 标注结果离线跑好后打 .offline_prepared 标记,
再运行时不调大模型, 直接复用.

本目录 (example/offline_prepared/labeling/):
    data/md_info.jsonl      清洗后语料 (复制自 ../output/clean, 《卧薪尝胆》《友爱》两篇)
    output/md_info.jsonl    五维标注结果 (复制自 ../output/label, ecnu-plus 离线标注) + .offline_prepared
    labeling.json           工作流 (本脚本生成)
    labeling*.png           截图 (../shoot_workflow.py 生成)
节点代码: Corpus_Cleansing_Pipeline/five_dim_label_node.py

用法 (在 COCLP 目录下):
    python example/offline_prepared/labeling/make_labeling_workflow.py prepare   # 复制语料和离线标注结果
    python example/offline_prepared/labeling/make_labeling_workflow.py build     # 生成工作流 json
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/labeling.json \
        --out example/offline_prepared/labeling/labeling.png
"""
import argparse
import copy
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OVERVIEW = HERE.parent / "多源多模态教育语料构建总体能力" / "docx_workflow_test.json"
DST = HERE / "labeling.json"
REL = "../example/offline_prepared/labeling"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致


def prepare():
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "output").mkdir(exist_ok=True)
    shutil.copy(HERE.parent / "output" / "clean" / "md_info.jsonl", HERE / "data" / "md_info.jsonl")
    shutil.copy(HERE.parent / "output" / "label" / "md_info.jsonl", HERE / "output" / "md_info.jsonl")
    (HERE / "output" / OFFLINE_MARKER).write_text("结果已离线生成 (ecnu-plus), 标注节点直接复用\n", encoding="utf-8")
    print(f"复制语料与标注结果到 {HERE}, 已打离线标记")


def build_workflow():
    overview = json.loads(OVERVIEW.read_text(encoding="utf-8"))
    label = copy.deepcopy(next(n for n in overview["nodes"] if n["type"] == "FiveDimLabelNode"))
    api = copy.deepcopy(next(n for n in overview["nodes"] if n["type"] == "PromptTextEditor"))

    # 只保留标注这一步: input_folder 原来连清洗节点, 改连 "语料输入" (本目录 data/), 输入语料也单独预览
    def preview_node(node_id, title, pos, size, link, widgets_values):
        return {"id": node_id, "type": "PreviewOutputDir", "title": title, "pos": pos, "size": size,
                "flags": {}, "order": node_id, "mode": 0,
                "inputs": [{"name": "dir_path", "type": "STRING", "link": link}],
                "outputs": [{"name": "preview_text", "type": "STRING", "links": None}],
                "properties": {"Node name for S&R": "PreviewOutputDir"},
                "widgets_values": widgets_values}  # [max_files, max_chars, file_pattern]

    corpus = {"id": 1, "type": "PassThroughDir", "title": "语料输入 (清洗、脱敏后)", "pos": [0, 0], "size": [420, 90],
              "flags": {}, "order": 1, "mode": 0, "inputs": [],
              "outputs": [{"name": "语料目录", "type": "STRING", "links": [1, 2]}],
              "properties": {"Node name for S&R": "PassThroughDir"}, "widgets_values": [f"{REL}/data"]}
    input_preview = preview_node(2, "预览: 待标注语料", [0, 160], [420, 520], 2, [1, 700, "*.jsonl"])

    api["id"], label["id"] = 3, 4
    api["outputs"][0]["links"] = [3]
    api["pos"], api["size"] = [500, 0], [400, 160]
    links_by_input = {"input_folder": 1, "api_url": 3}  # 语料输入 -> input_folder, 模型接口地址 -> api_url
    for inp in label["inputs"]:
        inp["link"] = links_by_input[inp["name"]]
    label["outputs"][0]["links"] = [4]
    # FiveDimLabelNode: [input_folder, output_folder, api_key, api_url, model_name, source_dir, max_workers]
    label["widgets_values"][0:2] = [f"{REL}/data", f"{REL}/output"]
    label["pos"], label["size"] = [500, 240], [400, 260]
    result_preview = preview_node(5, "预览: 五维标注结果 (学科 / 学段 / 场景 / 难度 / 格式)", [980, 0], [560, 680], 4,
                                  [1, 1400, "*.jsonl"])

    slot = {inp["name"]: i for i, inp in enumerate(label["inputs"])}
    workflow = {"id": "0ff1e5a0-1abe-4b1d-9c3e-5c2e7a1b0d11", "revision": 0, "last_node_id": 5, "last_link_id": 4,
                "nodes": [corpus, input_preview, api, label, result_preview],
                "links": [[1, corpus["id"], 0, label["id"], slot["input_folder"], "STRING"],
                          [2, corpus["id"], 0, input_preview["id"], 0, "STRING"],
                          [3, api["id"], 0, label["id"], slot["api_url"], "STRING"],
                          [4, label["id"], 0, result_preview["id"], 0, "STRING"]],
                "groups": [{"id": 1, "title": "语料标注与分类: 学科、学段、场景、难度、格式 五维标注",
                            "bounding": [-40, -80, 1620, 840], "color": "#3f789e", "font_size": 24, "flags": {}}],
                "config": {}, "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["prepare", "build"])
    {"prepare": prepare, "build": build_workflow}[parser.parse_args().step]()
