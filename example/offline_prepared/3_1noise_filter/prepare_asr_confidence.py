"""3.1 离线准备: 取 2.3 ASR 同一段音频, 用同一模型 (faster-whisper medium) 重新转写, 保留置信度.

2.3 的转写结果 (../2_3asr_workflow_test/output/all_transcripts.jsonl) 只存了拼接后的全文, 没有置信度;
这里按分段输出 avg_logprob (平均对数概率, 置信度 = exp(avg_logprob))、no_speech_prob (静音概率)
和逐词概率, 写到 data/asr_segments.jsonl, 供 "置信度与噪音筛选" 节点使用. 繁转简与 2.3 节点一致 (OpenCC t2s).

用法 (在 COCLP 目录下): python example/offline_prepared/3_1noise_filter/prepare_asr_confidence.py
"""
import json
import math
from pathlib import Path

from faster_whisper import WhisperModel
from opencc import OpenCC

HERE = Path(__file__).resolve().parent
AUDIO_DIR = HERE.parent / "2_3asr_workflow_test" / "input"
OUT = HERE / "data" / "asr_segments.jsonl"
MODEL = "medium"  # 与 2.3 一致


def main():
    cc = OpenCC("t2s")
    model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    rows = []
    for audio in sorted(AUDIO_DIR.glob("*.m4a")):
        segments, _ = model.transcribe(str(audio), language="zh", beam_size=5, word_timestamps=True)
        for i, seg in enumerate(segments, start=1):
            rows.append({
                "id": f"{audio.stem}#seg{i}", "来源": "ASR", "文件": audio.name,
                "时间": f"{seg.start:.1f}-{seg.end:.1f}s", "text": cc.convert(seg.text.strip()),
                "置信度": round(math.exp(seg.avg_logprob), 3), "静音概率": round(seg.no_speech_prob, 3),
                "逐词": [{"词": cc.convert(w.word), "概率": round(w.probability, 3)} for w in (seg.words or [])],
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    for r in rows:
        print(r["时间"], r["置信度"], r["静音概率"], r["text"])


if __name__ == "__main__":
    main()
