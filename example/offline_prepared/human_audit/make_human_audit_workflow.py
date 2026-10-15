"""4.3 人工抽样审计: 阻塞式审计节点的离线工作流 (用于标书截图).

    人工抽样审计 (阻塞等待) ──(放行目录)──> 语料入库 (审核通过后才执行)
抽样推送审核面板 -> 等待期间每 remind_interval_sec 提醒一次 (节点面板 + 弹窗 + 节点闪烁 + 浏览器通知)
-> 审核人提交结论 -> 通过率 >= 阈值放行入库, 否则用 ExecutionBlocker 拦截下游、退回.

本目录 (example/offline_prepared/human_audit/):
    data/模拟_脱敏后语料.jsonl   8 条模拟脱敏语料, 第 6 条故意漏脱敏 (姓名、手机号), 用来演示 "不达标拦截"
    output/<task_id>/           审计任务、审计结论 audit_result.jsonl、报告 report.md (运行后生成)
    human_audit.json            工作流 (本脚本生成)
    human_audit_审核中*.png / human_audit_审核结果*.png   截图 (shoot_human_audit.py 生成)
节点代码: Corpus_Cleansing_Pipeline/human_audit_node.py, 前端面板 web/human_audit.js

用法 (在 COCLP 目录下):
    python example/offline_prepared/human_audit/make_human_audit_workflow.py
    python example/offline_prepared/human_audit/shoot_human_audit.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "human_audit.json"
REL = "../example/offline_prepared/human_audit"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)


def build_workflow():
    workflow = {"id": "0ff1e5a0-a0d1-4b1d-9c3e-5c2e7a1b0d10", "revision": 0, "last_node_id": 0, "last_link_id": 0,
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

    # HumanSampleAudit: [input_dir, output_dir, sample_size, seed, (seed 的生成后控制), pass_threshold,
    #                    remind_interval_sec, timeout_min, max_chars]
    # 前端会给名为 seed 的控件自动加一个 "生成后控制" 控件, widgets_values 里要占一位; 用 fixed 保证抽样可复现
    # 隐私审计从严: 阈值 0.95, 抽 5 条里只要有 1 条不通过 (80%) 就拦截
    audit = add_node("HumanSampleAudit", "人工抽样审计 (阻塞等待审核)", (0, 0), (620, 960), [],
                     [("放行目录", "STRING"), ("审计报告", "STRING")],
                     [f"{REL}/data", f"{REL}/output", 5, 2026, "fixed", 0.95, 60, 0, 300])
    # PreviewOutputDir: [max_files, max_chars, file_pattern]
    ingest = add_node("PreviewOutputDir", "语料入库 (审核通过后才执行)", (700, 0), (440, 360),
                      [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 600, "*.jsonl"])
    workflow["last_link_id"] = 1
    workflow["links"].append([1, audit["id"], 0, ingest["id"], 0, "STRING"])
    audit["outputs"][0]["links"] = [1]
    ingest["inputs"][0]["link"] = 1

    workflow["groups"].append({"id": 1, "title": "人工抽样审计: 阻塞等待审核 → 定期提醒 → 达标放行 / 不达标拦截退回",
                               "bounding": [-40, -80, 1220, 1100], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    build_workflow()
