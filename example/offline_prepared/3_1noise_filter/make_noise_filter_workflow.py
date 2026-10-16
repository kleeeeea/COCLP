"""3.1 噪音过滤与置信度筛选: 离线工作流 (用于标书截图), 复用 2.2 OCR 与 2.3 ASR 的产出.

    OCR 产出 (2.2, MinerU, 含识别置信度) ──┐
                                          ├─> 噪音过滤与置信度筛选 ── 节点上显示: 来源统计、剔除原因统计、剔除清单、保留清单
    ASR 产出 (2.3, 分段置信度) ───────────┘
全部规则处理, 阈值均为节点参数, 直接点 "运行".

本目录 (example/offline_prepared/3_1noise_filter/):
    data/asr_segments.jsonl     2.3 同一段音频用同一模型重新转写得到的分段置信度/逐词概率 (prepare_asr_confidence.py 生成;
                                2.3 原输出只存了全文, 没有置信度)
    output/保留.jsonl, 剔除.jsonl
    noise_filter.json / noise_filter*.png
节点代码: Corpus_Cleansing_Pipeline/noise_filter_node.py

用法 (在 COCLP 目录下):
    python example/offline_prepared/3_1noise_filter/prepare_asr_confidence.py      # 离线准备 ASR 置信度 (约 1 分钟)
    python example/offline_prepared/3_1noise_filter/make_noise_filter_workflow.py
    python example/offline_prepared/shoot_workflow.py --workflow offline_prepared/noise_filter.json \
        --out example/offline_prepared/3_1noise_filter/noise_filter.png
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DST = HERE / "noise_filter.json"
REL = "../example/offline_prepared"  # 相对 ComfyUI 工作目录 (COCLP/ComfyUI)


def build_workflow():
    def node(node_id, node_type, title, pos, size, inputs, outputs, widgets_values):
        return {"id": node_id, "type": node_type, "title": title, "pos": list(pos), "size": list(size),
                "flags": {}, "order": node_id, "mode": 0,
                "inputs": [{"name": n, "type": "STRING", "link": l} for n, l in inputs],
                "outputs": [{"name": n, "type": "STRING", "links": l} for n, l in outputs],
                "properties": {"Node name for S&R": node_type}, "widgets_values": widgets_values}

    ocr = node(1, "PassThroughDir", "OCR 产出 (2.2 MinerU, 含识别置信度)", (0, 0), (420, 90), [],
               [("语料目录", [1])], [f"{REL}/2_2ocr_workflow_test/output"])
    asr = node(2, "PassThroughDir", "ASR 产出 (2.3 Whisper, 分段置信度)", (0, 160), (420, 90), [],
               [("语料目录", [2])], [f"{REL}/3_1noise_filter/data/asr_segments.jsonl"])
    # ConfidenceNoiseFilter widgets: [output_dir, OCR置信度阈值, ASR置信度阈值, 静音概率阈值, 低置信词阈值, 最短字数]
    filt = node(3, "ConfidenceNoiseFilter", "噪音过滤与置信度筛选 · 保留/剔除清单", (500, 0), (900, 900),
                [("ocr_dir", 1), ("asr_segments", 2)], [("保留语料目录", None)],
                [f"{REL}/3_1noise_filter/output", 0.9, 0.6, 0.6, 0.6, 4])
    workflow = {"id": "0ff1e5a0-3a1f-4b1d-9c3e-5c2e7a1b0d15", "revision": 0, "last_node_id": 3, "last_link_id": 2,
                "nodes": [ocr, asr, filt],
                "links": [[1, 1, 0, 3, 0, "STRING"], [2, 2, 0, 3, 1, "STRING"]],
                "groups": [{"id": 1, "title": "噪音过滤与置信度筛选: OCR/ASR 置信度阈值 + 噪音规则",
                            "bounding": [-40, -80, 1480, 1040], "color": "#3f789e", "font_size": 24, "flags": {}}],
                "config": {}, "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    build_workflow()
