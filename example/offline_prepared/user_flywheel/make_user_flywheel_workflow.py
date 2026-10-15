"""2.4 用户贡献采集 最简工作流 (用于标书截图): 一条网站反馈接口日志 -> 一条 SFT 训练样本.

    用户反馈日志解析 ─┬─> 预览: 原始网站日志 (data/*.log)
                       └─> 反馈转 SFT 样本 ──> 预览: SFT 训练样本 (output/sft/sft.jsonl)
全部规则处理, 不调模型, 直接点 "运行".

本目录 (example/offline_prepared/user_flywheel/):
    data/feedback_api.log        模拟的一条反馈接口日志 (用户对 "光合作用 教学设计" 提交纠错)
    output/feedback.jsonl        结构化反馈 (运行后生成)
    output/sft/sft.jsonl         SFT 样本, messages 对话格式 (运行后生成)
    user_flywheel.json           工作流 (本脚本生成)
    user_flywheel*.png           截图 (../shoot_workflow.py 生成)
节点代码: Corpus_Cleansing_Pipeline/user_feedback_node.py

用法 (在 COCLP 目录下):
    python example/offline_prepared/user_flywheel/make_user_flywheel_workflow.py
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/user_flywheel.json \
        --out example/offline_prepared/user_flywheel/user_flywheel.png
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "user_flywheel.json"
REL = "../example/offline_prepared/user_flywheel"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)


def build_workflow():
    workflow = {"id": "0ff1e5a0-f1e0-4b1d-9c3e-5c2e7a1b0d05", "revision": 0,
                "last_node_id": 0, "last_link_id": 0, "nodes": [], "links": [], "groups": [],
                "config": {}, "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}

    def add_node(node_type, title, pos, size, inputs, outputs, widgets_values):
        workflow["last_node_id"] += 1
        node = {"id": workflow["last_node_id"], "type": node_type, "title": title,
                "pos": list(pos), "size": list(size), "flags": {}, "order": workflow["last_node_id"], "mode": 0,
                "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
                "outputs": [{"name": n, "type": t, "links": None} for n, t in outputs],
                "properties": {"Node name for S&R": node_type}, "widgets_values": widgets_values}
        workflow["nodes"].append(node)
        return node

    def add_link(src, src_slot, dst, link_type):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], src_slot, dst["id"], 0, link_type])
        src["outputs"][src_slot]["links"] = (src["outputs"][src_slot]["links"] or []) + [link_id]
        dst["inputs"][0]["link"] = link_id

    # UserFeedbackLogParser: [log_dir, output_dir, uid_salt]
    parser = add_node("UserFeedbackLogParser", "用户反馈日志解析", (0, 200), (400, 150), [],
                      [("原始日志目录", "STRING"), ("结构化反馈目录", "STRING")],
                      [f"{REL}/data", f"{REL}/output", "edu-flywheel"])
    # PreviewOutputDir: [max_files, max_chars, file_pattern]
    # 预览节点运行后会被前端撑高到至少 360 (web/preview_dir.js), 两个节点之间留够距离
    raw = add_node("PreviewOutputDir", "预览: 原始网站日志", (460, 0), (560, 380),
                   [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 1000, "*.log"])
    # FeedbackToSFT: [output_dir, system_prompt]
    to_sft = add_node("FeedbackToSFT", "反馈转 SFT 样本", (0, 720), (400, 200), [("input_dir", "STRING")],
                      [("SFT 样本目录", "STRING")],
                      [f"{REL}/output/sft", "你是一名严谨的中小学学科教学助手，回答要准确、规范，符合课程标准。"])
    sft = add_node("PreviewOutputDir", "预览: SFT 训练样本", (460, 460), (560, 420),
                   [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 1000, "sft.jsonl"])
    add_link(parser, 0, raw, "STRING")
    add_link(parser, 1, to_sft, "STRING")
    add_link(to_sft, 0, sft, "STRING")

    workflow["groups"].append({"id": 1, "title": "用户贡献采集 (网站日志 → SFT 训练样本)",
                               "bounding": [-40, -80, 1100, 1120], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    build_workflow()
