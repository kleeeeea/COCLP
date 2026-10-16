"""最简 ASR 工作流 (离线预生成结果, 用于标书截图): 只有一个处理步骤, 不做清洗.

    音频输入与波形 ─(音频目录)─> 语音识别转写 (Whisper medium, 含繁转简) ──> 预览: 转写结果
                   └(波形图)──> 预览: 音频波形
不分组执行器, 直接点 "运行".

本目录 (example/offline_prepared/asr_workflow_test/):
    input/                    待转写音频 (prepare 用 macOS say 合成一两句话的模拟课堂讲解, 约 8 秒)
    output/                   转写结果 all_transcripts.jsonl; 放 .offline_prepared 标记后, 再运行直接复用, 不加载 ASR 模型
    asr_workflow_test.json    工作流 (build 生成)
    asr_workflow_test*.png    截图 (../shoot_workflow.py 生成)

用法 (在 COCLP 目录下):
    python example/offline_prepared/asr_workflow_test/make_asr_workflow.py prepare    # 合成模拟音频
    python example/offline_prepared/asr_workflow_test/make_asr_workflow.py build      # 生成工作流 json
    python example/offline_prepared/asr_workflow_test/make_asr_workflow.py generate   # 离线转写
    python example/offline_prepared/asr_workflow_test/make_asr_workflow.py mark       # 打离线标记
generate 和在 ComfyUI 里运行调用的是同一个节点 (WhisperNoVADTranscribeNode), 结果一致.
"""
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COCLP_DIR = HERE.parents[2]
EXAMPLE_DIR = COCLP_DIR / "example"
sys.path.insert(0, str(EXAMPLE_DIR))
from make_pdf_test_workflow import find_node, add_preview_node, PREVIEW_W  # noqa: E402

DEMO_SENTENCE = "同学们好，今天我们学习勾股定理。直角三角形两条直角边的平方和，等于斜边的平方。"
DEMO_AUDIO_NAME = "课堂讲解_模拟.m4a"
TTS_VOICE = "Tingting"
SRC_WORKFLOW = EXAMPLE_DIR / "audio_workflow.json"
INPUT_DIR = HERE / "input"
OUTPUT_DIR = HERE / "output"
DST = HERE / "asr_workflow_test.json"
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致

# 工作流里的路径相对 ComfyUI 工作目录 (COCLP/ComfyUI)
REL = "../example/offline_prepared/asr_workflow_test"
OUTPUT_FILENAME = "all_transcripts.jsonl"
WHISPER_MODEL = "medium"  # 与仓库 config/faster-whisper 的 LFS 权重 sha256 一致
DEVICE = "cpu"
WAVEFORM_ID, IMAGE_PREVIEW_ID = 20, 21  # 新增节点的 id, 避开 audio_workflow.json 里 Whisper 节点的 id


def prepare_audio():
    """用 macOS 自带 TTS 合成一两句话的模拟课堂讲解 (内容可控, 方便核对转写; 不含真人声音和姓名)"""
    INPUT_DIR.mkdir(exist_ok=True)
    for old in INPUT_DIR.glob("*"):
        old.unlink()
    aiff = INPUT_DIR / "tmp.aiff"
    subprocess.run(["say", "--voice", TTS_VOICE, "--output-file", str(aiff), DEMO_SENTENCE], check=True)
    m4a = INPUT_DIR / DEMO_AUDIO_NAME
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), "-ac", "1", "-ar", "16000",
                    "-c:a", "aac", "-b:a", "64k", str(m4a)], check=True)
    aiff.unlink()
    print(f"合成 {m4a.name}: {DEMO_SENTENCE}")


def build_workflow():
    """音频波形 ─(音频目录)─> 语音识别转写 ──> 预览: 转写结果
                └(波形图)──> 预览: 音频波形 (ComfyUI 自带 PreviewImage)"""
    source = json.loads(SRC_WORKFLOW.read_text(encoding="utf-8"))
    whisper = copy.deepcopy(find_node(source, "WhisperNoVADTranscribeNode"))
    # input_dir 改成连线输入 (由音频波形节点传入), 其余参数仍是控件
    whisper["inputs"] = [{"name": "input_dir", "type": "STRING", "widget": {"name": "input_dir"}, "link": None}]
    whisper["outputs"][0]["links"] = None
    # WhisperNoVADTranscribeNode: [input_dir, model_path, output_dir, output_filename, language, beam_size, device]
    whisper["widgets_values"] = [f"{REL}/input", WHISPER_MODEL, f"{REL}/output", OUTPUT_FILENAME, "zh", 5, DEVICE]
    whisper["title"] = "语音识别转写 (调用平台 ASR)"

    wave_w = 360
    waveform = {
        "id": WAVEFORM_ID, "type": "AudioWaveform", "title": "音频输入与波形", "pos": [0, 0], "size": [wave_w, 110],
        "flags": {}, "order": 0, "mode": 0, "inputs": [],
        "outputs": [{"name": "波形图", "type": "IMAGE", "links": None},
                    {"name": "音频目录", "type": "STRING", "links": None}],
        "properties": {"Node name for S&R": "AudioWaveform"},
        "widgets_values": [f"{REL}/input", 3],
    }
    image_preview = {
        # 放在整排节点 (波形/转写) 下方, 不和转写节点重叠; 转写节点实际渲染比 json 里的 size 高, 多留 160
        "id": IMAGE_PREVIEW_ID, "type": "PreviewImage", "title": "预览: 音频波形",
        "pos": [0, max(110, whisper["size"][1]) + 160],
        "size": [wave_w + 80 + whisper["size"][0], 300], "flags": {}, "order": 1, "mode": 0,
        "inputs": [{"name": "images", "type": "IMAGE", "link": None}], "outputs": [],
        "properties": {"Node name for S&R": "PreviewImage"}, "widgets_values": [],
    }
    whisper["pos"] = [wave_w + 80, 0]

    workflow = {
        "id": "a5b0f1c2-3d4e-4f50-8a61-7b8c9d0e1f23",
        "revision": 0,
        "last_node_id": max(whisper["id"], WAVEFORM_ID, IMAGE_PREVIEW_ID),
        "last_link_id": 0,
        "nodes": [waveform, image_preview, whisper],
        "links": [],
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.8, "offset": [50, 50]}},
        "version": 0.4,
    }
    add_link(workflow, waveform, 0, image_preview, 0, "IMAGE")
    add_link(workflow, waveform, 1, whisper, 0, "STRING")
    add_preview_node(workflow, whisper, (whisper["pos"][0] + whisper["size"][0] + 80, 0), "预览: 转写结果")
    workflow["nodes"][-1]["size"] = [PREVIEW_W + 220, 330]  # 转写只有一两句, 预览框和转写节点差不多高

    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


def add_link(workflow, from_node, from_slot, to_node, to_slot, link_type):
    """连线格式: [link_id, from_node, from_slot, to_node, to_slot, type]"""
    link_id = workflow["last_link_id"] + 1
    workflow["last_link_id"] = link_id
    workflow["links"].append([link_id, from_node["id"], from_slot, to_node["id"], to_slot, link_type])
    from_node["outputs"][from_slot]["links"] = (from_node["outputs"][from_slot]["links"] or []) + [link_id]
    to_node["inputs"][to_slot]["link"] = link_id


def generate_offline():
    sys.path.insert(0, str(COCLP_DIR))
    from Corpus_Cleansing_Pipeline.whisper_novad_node import WhisperNoVADTranscribeNode
    marker = OUTPUT_DIR / OFFLINE_MARKER
    if marker.exists():
        marker.unlink()  # 重新生成: 先去掉标记, 否则节点会直接回放旧结果
    result = WhisperNoVADTranscribeNode().run(str(INPUT_DIR), WHISPER_MODEL, str(OUTPUT_DIR), "zh", 5, DEVICE,
                                              OUTPUT_FILENAME)
    relativize_audio_paths()
    print(f"转写完成: {result}")


def relativize_audio_paths():
    """结果里的 audio_path 改成和 ComfyUI 里运行时一样的相对路径, 不留本机绝对路径"""
    out_file = OUTPUT_DIR / OUTPUT_FILENAME
    records = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for rec in records:
        rec["audio_path"] = f"{REL}/input/{Path(rec['audio_path']).name}"
    out_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def mark_offline_prepared():
    if not any(OUTPUT_DIR.glob("*.jsonl")):
        raise SystemExit(f"{OUTPUT_DIR} 里还没有转写结果, 先运行 generate")
    (OUTPUT_DIR / OFFLINE_MARKER).write_text("结果已离线生成, ASR 节点直接复用\n", encoding="utf-8")
    print(f"标记 {OUTPUT_DIR / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["prepare", "build", "generate", "mark"])
    args = parser.parse_args()
    {"prepare": prepare_audio, "build": build_workflow, "generate": generate_offline,
     "mark": mark_offline_prepared}[args.step]()
