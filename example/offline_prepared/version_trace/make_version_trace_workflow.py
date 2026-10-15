"""6.2 版本管理、双向追溯与合规审计: 离线工作流 (用于标书截图), 全部自动, 不含人工环节.

    质控后批次 ─┬─> 批次版本登记 (版本台账) ─┬─> 模型-语料双向追溯 (正向: 样本→版本→任务→模型; 反向: 模型→任务→版本→样本)
                │                            └─> 隐私合规审计 (覆盖率 + 残留复检 + 月度报告)
                └────────────────────────────────┘
版本台账里预先登记 v1 (原始批次 6 条, prepare 步骤), 工作流登记 v2 (6.1 质控后剔除 C 档 Q04/Q05, 4 条).

本目录 (example/offline_prepared/version_trace/):
    data/batch_v1/, data/batch_v2/   两个批次 (复用 6.1 的模拟批次)
    data/隐私处理日志.jsonl           4.1/4.2 隐私检测与脱敏的处理记录 (模拟)
    data/训练任务登记.jsonl           训练/评测任务 -> 模型 -> 使用的语料批次 (模拟)
    registry/versions.jsonl          版本台账;  output/月度审计报告_<月份>.md
    version_trace.json / version_trace*.png
节点代码: Corpus_Cleansing_Pipeline/version_trace_node.py

用法 (在 COCLP 目录下):
    python example/offline_prepared/version_trace/make_version_trace_workflow.py prepare   # 台账登记 v1
    python example/offline_prepared/version_trace/make_version_trace_workflow.py build
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/version_trace.json \
        --out example/offline_prepared/version_trace/version_trace.png
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
COCLP_DIR = HERE.parents[2]
REL = "../example/offline_prepared/version_trace"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
DST = HERE / "version_trace.json"


def prepare():
    sys.path.insert(0, str(COCLP_DIR / "Corpus_Cleansing_Pipeline"))
    from version_trace_node import register_batch
    shutil.rmtree(HERE / "registry", ignore_errors=True)
    _, v1 = register_batch(HERE / "registry", HERE / "data" / "batch_v1", "原始批次 (已五维标注)")
    print(f"台账登记 {v1['版本号']} ({v1['记录数']} 条)")


def build_workflow():
    workflow = {"id": "0ff1e5a0-7e50-4b1d-9c3e-5c2e7a1b0d14", "revision": 0, "last_node_id": 0, "last_link_id": 0,
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

    batch = add_node("PassThroughDir", "质控后批次 (6.1 剔除 C 档)", (0, 0), (400, 90), [],
                     [("语料目录", "STRING")], [f"{REL}/data/batch_v2"])
    # BatchVersionRegister widgets: [registry_dir, 版本说明]
    register = add_node("BatchVersionRegister", "批次版本登记 · 版本台账", (460, 0), (780, 460),
                        [("batch_dir", "STRING")], [("版本台账目录", "STRING")],
                        [f"{REL}/registry", "质控后入库: 剔除 C 档 2 条"])
    # ModelCorpusTrace widgets: [training_jobs, 样本ID, 模型]
    tracer = add_node("ModelCorpusTrace", "模型-语料双向追溯", (460, 540), (780, 520),
                      [("registry_dir", "STRING")], [("追溯结果", "STRING")],
                      [f"{REL}/data/训练任务登记.jsonl", "Q06", "静安教育大模型 v1.2"])
    # ComplianceAudit widgets: [privacy_log, output_dir, 审计月份, 覆盖率要求]
    auditor = add_node("ComplianceAudit", "隐私合规审计 · 月度审计报告", (1300, 0), (620, 560),
                       [("registry_dir", "STRING"), ("batch_dir", "STRING")], [("审计报告目录", "STRING")],
                       [f"{REL}/data/隐私处理日志.jsonl", f"{REL}/output", datetime.now().strftime("%Y-%m"), 1.0])
    add_link(batch, register, 0)
    add_link(register, tracer, 0)
    add_link(register, auditor, 0)
    add_link(batch, auditor, 1)

    workflow["groups"].append({"id": 1, "title": "版本管理、双向追溯与合规审计: 批次版本台账 → 模型语料追溯 → 月度合规审计",
                               "bounding": [-40, -80, 2000, 1180], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["prepare", "build"])
    {"prepare": prepare, "build": build_workflow}[parser.parse_args().step]()
