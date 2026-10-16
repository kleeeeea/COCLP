"""3.3 去重与质量评分筛选: 离线工作流 (用于标书截图). 质量评分沿用 6.1 "质量评估" 节点的算法.

    语料输入 ────> 质量评估 (规则指标 + ecnu-plus 评审, 6.1 同一算法) ──> 近似去重与达标筛选 (SimHash)
    模型接口地址 ──┘
清洗阶段还没做五维标注, 质量评估的 "计入标注指标" 关闭 (不计 标注完备性 / 标注一致性).
近似去重: 64 位 SimHash (字符 3-gram), 海明距离 <= 阈值归为一簇, 簇内按质量总分保留最优; 低于最低保留档的剔除.

本目录 (example/offline_prepared/dedup_quality/):
    data/模拟_清洗后语料.jsonl   8 条: 光合作用 3 个近似版本 (原文 / 改词 / 加广告尾巴)、勾股定理 2 个 (原文 / 句序调换)、
                                《背影》、浮力实验、OCR 乱码 1 条
    output/quality/             ecnu-plus 评审缓存 + scored.jsonl;  output/dedup/  kept.jsonl + dedup_report.jsonl
    dedup_quality.json          工作流 (本脚本生成)
节点代码: Corpus_Cleansing_Pipeline/quality_control_node.py (质量评估), dedup_node.py (近似去重)

用法 (在 COCLP 目录下):
    python example/offline_prepared/dedup_quality/make_dedup_quality_workflow.py build
    (ComfyUI 里运行一次, 真正调 ecnu-plus 评审)
    python example/offline_prepared/dedup_quality/make_dedup_quality_workflow.py mark
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/dedup_quality.json \
        --out example/offline_prepared/dedup_quality/dedup_quality.png
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "dedup_quality.json"
REL = "../example/offline_prepared/dedup_quality"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)
API_URL = "https://chat.ecnu.edu.cn/open/api/v1"
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致


def build_workflow():
    workflow = {"id": "0ff1e5a0-dd01-4b1d-9c3e-5c2e7a1b0d14", "revision": 0, "last_node_id": 0, "last_link_id": 0,
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

    corpus = add_node("PassThroughDir", "语料输入 (清洗后)", (0, 0), (400, 90), [],
                      [("语料目录", "STRING")], [f"{REL}/data"])
    api = add_node("PromptTextEditor", "模型接口地址 (ecnu-plus)", (0, 180), (400, 160), [],
                   [("append_text", "STRING")], [API_URL])
    # QualityAssess widgets: [output_dir, api_key, model_name, A档线, B档线, 模型评审权重, 计入标注指标]
    quality = add_node("QualityAssess", "质量评分 (沿用 6.1 质量评估算法)", (480, 0), (720, 760),
                       [("batch_dir", "STRING"), ("api_url", "STRING")], [("评估结果目录", "STRING")],
                       [f"{REL}/output/quality", "None", "ecnu-plus", 0.8, 0.6, 0.4, False])
    # SimHashDedup widgets: [output_dir, 海明距离阈值, 最低保留档]
    dedup = add_node("SimHashDedup", "近似去重与达标筛选 (SimHash)", (1260, 0), (620, 760),
                     [("scored_dir", "STRING")], [("保留语料目录", "STRING")], [f"{REL}/output/dedup", 12, "B"])
    add_link(corpus, quality, 0)
    add_link(api, quality, 1)
    add_link(quality, dedup, 0)

    workflow["groups"].append({"id": 1, "title": "去重与质量评分筛选: 质量评分 → SimHash 近似去重 → 簇内优选 → 达标筛选",
                               "bounding": [-40, -80, 1960, 880], "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


def mark_offline_prepared():
    cache = HERE / "output" / "quality" / "judge_cache.jsonl"
    if not cache.exists():
        raise SystemExit(f"{cache} 不存在, 先在 ComfyUI 里运行一次")
    (cache.parent / OFFLINE_MARKER).write_text("ecnu-plus 评审已离线生成, 只用缓存\n", encoding="utf-8")
    print(f"标记 {cache.parent / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["build", "mark"])
    {"build": build_workflow, "mark": mark_offline_prepared}[parser.parse_args().step]()
