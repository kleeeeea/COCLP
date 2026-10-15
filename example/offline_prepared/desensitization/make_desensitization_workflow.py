"""4.2 不可逆哈希处理、实体名称标记化替换、地理位置泛化处理: 离线工作流 (用于标书截图, 脱敏前后对比).

    脱敏处理 (节点上显示脱敏前后对比: 原文红色删除线 -> 替换值绿色, 后跟 类型·策略)
       └─(策略报告)──> 预览: 脱敏策略与统计
不用逐字 diff 的 "清洗前后对比" 节点: 哈希值和原号码会被拆成交错的碎片, 按实体整段对比更清楚.
输入是 4.1 双引擎隐私检测的结果 (../privacy_detection/output/merged/pii_detected.jsonl, 每条带检出的实体);
全部规则处理, 不调模型, 直接点 "运行".

本目录 (example/offline_prepared/desensitization/):
    output/data/desensitized.jsonl       脱敏后语料 (运行后生成)
    output/report/脱敏策略与统计.md        策略配置 + 本批统计
    output/映射表_仅授权可见.json          标记 -> 原文 (生产环境应加密单独存放)
    desensitization.json                 工作流 (本脚本生成)
    desensitization*.png                 截图 (../shoot_workflow.py 生成)
节点代码: Corpus_Cleansing_Pipeline/desensitize_node.py; 对比节点: compare_diff_node.py

用法 (在 COCLP 目录下, 先跑过 4.1 privacy_detection):
    python example/offline_prepared/desensitization/make_desensitization_workflow.py
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/desensitization.json \
        --out example/offline_prepared/desensitization/desensitization.png
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "desensitization.json"
REL = "../example/offline_prepared"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)


def build_workflow():
    workflow = {"id": "0ff1e5a0-de5e-4b1d-9c3e-5c2e7a1b0d09", "revision": 0, "last_node_id": 0, "last_link_id": 0,
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

    def add_link(src, src_slot, dst, dst_slot):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], src_slot, dst["id"], dst_slot, "STRING"])
        src["outputs"][src_slot]["links"] = (src["outputs"][src_slot]["links"] or []) + [link_id]
        dst["inputs"][dst_slot]["link"] = link_id

    # Desensitizer: [detection_dir, output_dir, 哈希类型, 标记化类型, 泛化类型, 泛化级别, salt]
    # 节点上直接显示脱敏前后对比: 每个实体整段 原文(红删除线) -> 替换值(绿) + 类型·策略 (web/pii_highlight.js)
    desens = add_node("Desensitizer", "脱敏处理 (脱敏前后对比)", (0, 0), (760, 720), [],
                      [("脱敏前目录", "STRING"), ("脱敏后目录", "STRING"), ("策略报告目录", "STRING")],
                      [f"{REL}/privacy_detection/output/merged", f"{REL}/desensitization/output",
                       "身份证号, 手机号, 学号, 邮箱", "姓名, 学校, 机构", "地址, 地名", "区县", "edu-pii-2026"])
    # PreviewOutputDir: [max_files, max_chars, file_pattern]
    report = add_node("PreviewOutputDir", "预览: 脱敏策略与统计", (820, 0), (440, 420),
                      [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 2000, "*.md"])
    add_link(desens, 2, report, 0)

    workflow["groups"].append({"id": 1, "title": "脱敏处理: 不可逆哈希处理、实体名称标记化替换、地理位置泛化处理",
                               "bounding": [-40, -80, 1340, 880], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    build_workflow()
