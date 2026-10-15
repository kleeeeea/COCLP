"""生成只用 ASR、不用大模型的工作流 simple_asr_clean_workflow.json:
    WhisperNoVADTranscribeNode (faster-whisper 转写 + 繁转简)  ->  MultiPruner (正则/规则清洗)
每一步后面接一个 "预览输出目录" 节点; 不分组, 不用 GroupExecutor, 直接点 "运行" 即可.

- 仓库里 config/faster-whisper/model.bin 是 git LFS 指针 (没拉权重), 这里 model_path 填模型名 (small/medium),
  由 faster-whisper 从 HuggingFace 下载 Systran/faster-whisper-<name> 到缓存
- Mac 没有 CUDA, device 用 cpu

节点定义从 audio_workflow.json 里复制 (保证 widgets_values 格式和前端一致), 只改参数.
用法: python example/make_simple_asr_clean_workflow.py
"""
import copy
import json
from pathlib import Path

from make_pdf_test_workflow import find_node, add_preview_node, PREVIEW_W

EXAMPLE_DIR = Path(__file__).resolve().parent
SRC = EXAMPLE_DIR / "audio_workflow.json"
DST = EXAMPLE_DIR / "simple_asr_clean_workflow.json"

# Mac CPU 上 medium 约 2.4x 实时 (8.5 分钟要 ~20 分钟), 先用 small + 1 分钟片段:
#   ffmpeg -i example/test_data/speak.m4a -t 60 -c copy example/test_data_asr_clip/speak_60s.m4a
# 要跑完整音频: TEST_INPUT_DIR = "../example/test_data", WHISPER_MODEL = "medium" (和仓库 LFS 里的权重 sha256 一致)
TEST_INPUT_DIR = "../example/test_data_asr_clip"  # 不放在 test_data 里, 免得完整音频流程把片段也转写一遍
OUTPUT_ROOT = "../example/test_out/simple_asr"
WHISPER_MODEL = "small"
DEVICE = "cpu"


def main():
    source = json.loads(SRC.read_text(encoding="utf-8"))
    whisper = copy.deepcopy(find_node(source, "WhisperNoVADTranscribeNode"))
    pruner = copy.deepcopy(find_node(source, "MultiPruner"))

    # 只保留一条连线: whisper -> pruner
    link_asr = 1
    whisper["outputs"][0]["links"] = [link_asr]
    pruner["inputs"][0]["link"] = link_asr
    pruner["outputs"][0]["links"] = None

    # WhisperNoVADTranscribeNode: [input_dir, model_path, output_dir, output_filename, language, beam_size, device]
    whisper["widgets_values"] = [TEST_INPUT_DIR, WHISPER_MODEL, f"{OUTPUT_ROOT}/whisper",
                                 "all_transcripts.jsonl", "zh", 5, DEVICE]
    # MultiPruner: [input_dir(连线), output_dir, num_processes, min_text_length, enable_* x12]
    pruner["widgets_values"][1] = f"{OUTPUT_ROOT}/clean"
    pruner["widgets_values"][2] = 1   # 单进程
    pruner["widgets_values"][3] = 10

    whisper["pos"] = [0, 0]
    pruner["pos"] = [PREVIEW_W + 40, 0]

    workflow = {
        "id": "7a1d2e3f-4b5c-4d6e-8f90-a1b2c3d4e5f6",
        "revision": 0,
        "last_node_id": max(whisper["id"], pruner["id"]),
        "last_link_id": link_asr,
        "nodes": [whisper, pruner],
        "links": [[link_asr, whisper["id"], 0, pruner["id"], 0, "STRING"]],
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.8, "offset": [50, 50]}},
        "version": 0.4,
    }
    add_preview_node(workflow, whisper, (0, 480), "预览: Whisper 转写")
    add_preview_node(workflow, pruner, (PREVIEW_W + 40, 480), "预览: 规则清洗后")

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
