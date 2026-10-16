"""4.1 双引擎并行隐私检测: 离线工作流 (用于标书截图).

    语料输入 ─┬─> 隐私检测·规则引擎 ─┐
              ├─> 隐私检测·NER 模型 ─┼─> 隐私检测结果合并 (节点上红字高亮隐私实体 + 类型·引擎标签)
              └──────────────────────┘
规则引擎: 正则 + 校验 (身份证校验位、手机号、学号、邮箱、详细地址、学校)
NER 模型: spaCy zh_core_web_sm (人名、地名、机构); 输出目录打 .offline_prepared 标记后不再加载模型.

本目录 (example/offline_prepared/privacy_detection/):
    data/模拟_含隐私语料.jsonl    2 条模拟语料 (家校沟通记录、学生档案, 隐私信息均为虚构)
    output/rule|ner|merged/      检测结果 (运行后生成); output/merged/检测报告.md
    privacy_detection.json       工作流 (本脚本生成)
    privacy_detection*.png       截图 (../shoot_workflow.py 生成)
节点代码: Corpus_Cleansing_Pipeline/privacy_detection_node.py

用法 (在 COCLP 目录下):
    python example/offline_prepared/privacy_detection/make_privacy_detection_workflow.py build
    (ComfyUI 里运行一次, 真正跑 NER)
    python example/offline_prepared/privacy_detection/make_privacy_detection_workflow.py mark
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/privacy_detection.json \
        --out example/offline_prepared/privacy_detection/privacy_detection.png
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "privacy_detection.json"
REL = "../example/offline_prepared/privacy_detection"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致


def build_workflow():
    workflow = {"id": "0ff1e5a0-91a0-4b1d-9c3e-5c2e7a1b0d08", "revision": 0, "last_node_id": 0, "last_link_id": 0,
                "nodes": [], "links": [], "groups": [], "config": {},
                "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}

    def add_node(node_type, title, pos, size, inputs, outputs, widgets_values):
        workflow["last_node_id"] += 1
        node = {"id": workflow["last_node_id"], "type": node_type, "title": title,
                "pos": list(pos), "size": list(size), "flags": {}, "order": workflow["last_node_id"], "mode": 0,
                "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
                "outputs": [{"name": n, "type": t, "links": None} for n, t in outputs],
                "properties": {"Node name for S&R": node_type}, "widgets_values": widgets_values}
        workflow["nodes"].append(node)
        return node

    def add_link(src, dst, dst_slot):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], 0, dst["id"], dst_slot, "STRING"])
        src["outputs"][0]["links"] = (src["outputs"][0]["links"] or []) + [link_id]
        dst["inputs"][dst_slot]["link"] = link_id

    corpus = add_node("PassThroughDir", "语料输入 (家校沟通记录、学生档案)", (0, 300), (340, 90), [],
                      [("语料目录", "STRING")], [f"{REL}/data"])
    rule = add_node("PIIRuleEngine", "隐私检测·规则引擎 (正则 + 校验)", (420, 80), (360, 90),
                    [("input_dir", "STRING")], [("规则检测结果", "STRING")], [f"{REL}/output/rule"])
    ner = add_node("PIINerEngine", "隐私检测·NER 模型 (spaCy 中文)", (420, 440), (360, 120),
                   [("input_dir", "STRING")], [("NER 检测结果", "STRING")], [f"{REL}/output/ner", "zh_core_web_sm"])
    # 合并节点自身高亮显示检测结果 (红字标出隐私实体, web/pii_highlight.js)
    merge = add_node("PIIMerge", "隐私检测结果合并 (红字标出隐私信息)", (860, 60), (640, 500),
                     [("corpus_dir", "STRING"), ("rule_dir", "STRING"), ("ner_dir", "STRING")],
                     [("合并检测结果", "STRING")], [f"{REL}/output/merged"])
    add_link(corpus, rule, 0)
    add_link(corpus, ner, 0)
    add_link(corpus, merge, 0)
    add_link(rule, merge, 1)
    add_link(ner, merge, 2)

    workflow["groups"].append({"id": 1, "title": "双引擎并行隐私检测 (规则引擎 + NER 模型)",
                               "bounding": [-40, -60, 1580, 700], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


def mark_offline_prepared():
    ner_dir = HERE / "output" / "ner"
    if not (ner_dir / "entities.jsonl").exists():
        raise SystemExit(f"{ner_dir} 里还没有 NER 结果, 先在 ComfyUI 里运行一次")
    (ner_dir / OFFLINE_MARKER).write_text("结果已离线生成, NER 节点直接复用\n", encoding="utf-8")
    print(f"标记 {ner_dir / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["build", "mark"])
    {"build": build_workflow, "mark": mark_offline_prepared}[parser.parse_args().step]()
