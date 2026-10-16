"""6.1 质量评估、专家审核与黄金集质控: 两个离线工作流 (用于标书截图, 2 张图). 阈值都是节点参数, 可调.

图 1 quality_golden.json:
    批次语料输入 ──> 质量评估 (规则 5 维 + ecnu-plus 评审) ── 节点上显示批次质量报告 (A/B/C 档)
    模型接口地址 ──┤
    黄金集输入 ────> 黄金集质控 (五维标注) ── 节点上显示各维度准确率 + 退返单
图 2 expert_review.json:
    质量评估结果 ──> 专家抽样审核 (阻塞等待, B 档必审 + A 档抽检) ──(放行目录)──> 入库语料 (审核通过后执行)

本目录 (example/offline_prepared/quality_control/):
    data/batch/      6 条模拟批次 (已五维标注): 优质 2 条、格式不规范、OCR 乱码缺标签、隐私残留、学科标错
    data/golden/     黄金集 v1.0: 4 条专家确认的标准五维标签
    output/quality/  评审缓存 judge_cache.jsonl + scored.jsonl;  output/golden/  标注缓存 + 质控结果/退返单
    output/review/   专家审核结论、黄金集候选
节点代码: Corpus_Cleansing_Pipeline/quality_control_node.py; 前端 web/pii_highlight.js, web/expert_review.js

用法 (在 COCLP 目录下):
    python example/offline_prepared/quality_control/make_quality_workflows.py build
    (ComfyUI 里运行一次图 1, 真正调 ecnu-plus 评审和标注)
    python example/offline_prepared/quality_control/make_quality_workflows.py mark     # 之后只用缓存
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/quality_golden.json \
        --out example/offline_prepared/quality_control/quality_golden.png
    python example/offline_prepared/quality_control/shoot_expert_review.py
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REL = "../example/offline_prepared/quality_control"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
API_URL = "https://chat.ecnu.edu.cn/open/api/v1"
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致


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

    def add_link(src, src_slot, dst, dst_slot):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], src_slot, dst["id"], dst_slot, "STRING"])
        src["outputs"][src_slot]["links"] = (src["outputs"][src_slot]["links"] or []) + [link_id]
        dst["inputs"][dst_slot]["link"] = link_id

    return workflow, add_node, add_link


def save(workflow, name, group_title, bounding):
    workflow["groups"].append({"id": 1, "title": group_title, "bounding": bounding,
                               "color": "#3f789e", "font_size": 24, "flags": {}})
    dst = HERE / f"{name}.json"
    dst.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {dst}")


def build_quality_golden():
    workflow, add_node, add_link = new_workflow("0ff1e5a0-9c01-4b1d-9c3e-5c2e7a1b0d12")
    batch = add_node("PassThroughDir", "批次语料输入 (已五维标注)", (0, 0), (400, 90), [],
                     [("语料目录", "STRING")], [f"{REL}/data/batch"])
    api = add_node("PromptTextEditor", "模型接口地址 (ecnu-plus)", (0, 180), (400, 160), [],
                   [("append_text", "STRING")], [API_URL])
    golden = add_node("PassThroughDir", "黄金集输入 (v1.0, 专家确认)", (0, 420), (400, 90), [],
                      [("语料目录", "STRING")], [f"{REL}/data/golden"])
    # QualityAssess widgets: [output_dir, api_key, model_name, A档线, B档线, 模型评审权重]
    quality = add_node("QualityAssess", "质量评估 (规则 5 维 + ecnu-plus 评审) · 批次质量报告", (480, 0), (720, 760),
                       [("batch_dir", "STRING"), ("api_url", "STRING")], [("评估结果目录", "STRING")],
                       [f"{REL}/output/quality", "None", "ecnu-plus", 0.8, 0.6, 0.4])
    # GoldenLabelCheck widgets: [output_dir, api_key, model_name, 合格线]
    check = add_node("GoldenLabelCheck", "黄金集质控 (五维标注) · 退返单", (1260, 0), (600, 760),
                     [("golden_dir", "STRING"), ("api_url", "STRING")], [("质控结果目录", "STRING")],
                     [f"{REL}/output/golden", "None", "ecnu-plus", 0.9])
    add_link(batch, 0, quality, 0)
    add_link(api, 0, quality, 1)
    add_link(golden, 0, check, 0)
    add_link(api, 0, check, 1)
    save(workflow, "quality_golden", "质量评估与黄金集质控: 自动评估分档 + 黄金集比对退返", [-40, -80, 1940, 880])


def build_expert_review():
    workflow, add_node, add_link = new_workflow("0ff1e5a0-9c01-4b1d-9c3e-5c2e7a1b0d13")
    scored = add_node("PassThroughDir", "质量评估结果 (图 1 输出)", (0, 0), (400, 90), [],
                      [("语料目录", "STRING")], [f"{REL}/output/quality"])
    # ExpertSampleReview widgets: [output_dir, A档抽检比例, A档最少抽检, 通过率阈值, 提醒间隔秒, 抽样种子]
    review = add_node("ExpertSampleReview", "专家抽样审核 (B 档必审 + A 档抽检, 阻塞等待)", (480, 0), (720, 900),
                      [("scored_dir", "STRING")], [("放行目录", "STRING"), ("审核报告", "STRING")],
                      [f"{REL}/output/review", 0.02, 1, 0.8, 60, 2026])
    ingest = add_node("PreviewOutputDir", "入库语料 (专家审核通过后执行)", (1260, 0), (440, 360),
                      [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 600, "scored.jsonl"])
    add_link(scored, 0, review, 0)
    add_link(review, 0, ingest, 0)
    save(workflow, "expert_review", "专家抽样审核: 审核单 (五维标签 / 质量档 / 核对项 / 结论)", [-40, -80, 1780, 1040])


def mark_offline_prepared():
    for sub in ("quality/judge_cache.jsonl", "golden/pred_labels_cache.jsonl"):
        cache = HERE / "output" / sub
        if not cache.exists():
            raise SystemExit(f"{cache} 不存在, 先在 ComfyUI 里运行一次图 1")
        (cache.parent / OFFLINE_MARKER).write_text("ecnu-plus 结果已离线生成, 只用缓存\n", encoding="utf-8")
        print(f"标记 {cache.parent / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["build", "mark"])
    step = parser.parse_args().step
    if step == "build":
        build_quality_golden()
        build_expert_review()
    else:
        mark_offline_prepared()
