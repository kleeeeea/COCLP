"""音频波形可视化: 把目录里的音频画成波形图 (IMAGE), 接 ComfyUI 自带的 "预览图像" 节点显示.
同时把音频目录原样输出, 可以连到 Whisper 转写节点的 input_dir, 让画布上看到 "音频输入 -> 转写" 的数据流.
"""
import io
import os
from pathlib import Path

import numpy as np

AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".aac")
CJK_FONTS = ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "Arial Unicode MS", "Noto Sans CJK SC", "SimHei"]
WAVE_COLOR = "#E0569A"   # 与 cotton_candy 主题的连线颜色呼应
FILL_COLOR = "#F7C6DD"


def list_audio_files(audio_dir):
    root = Path(audio_dir)
    files = [root] if root.is_file() else sorted(p for p in root.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    return files


def load_mono_samples(path, sample_rate=16000):
    """读音频 -> 单声道 float32 [-1, 1] (和 Whisper 节点用同样的 pydub 读法)"""
    from pydub import AudioSegment
    audio = AudioSegment.from_file(path).set_channels(1).set_frame_rate(sample_rate)
    samples = np.array(audio.get_array_of_samples()).astype(np.float32) / (2 ** (8 * audio.sample_width - 1))
    return samples, sample_rate


def render_waveform(path, width_px=1200, height_px=320):
    """画一张波形图, 返回 PIL.Image (RGB)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    plt.rcParams["font.sans-serif"] = CJK_FONTS + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    samples, sr = load_mono_samples(path)
    duration = len(samples) / sr
    # 点太多时按包络降采样: 每个像素列取 min/max, 波形形状不变, 画图快
    n_cols = width_px * 2
    if len(samples) > n_cols:
        chunks = np.array_split(samples, n_cols)
        lo = np.array([c.min() for c in chunks])
        hi = np.array([c.max() for c in chunks])
        t = np.linspace(0, duration, n_cols)
    else:
        lo = hi = samples
        t = np.arange(len(samples)) / sr

    dpi = 100
    fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax.fill_between(t, lo, hi, color=FILL_COLOR, linewidth=0)
    ax.plot(t, hi, color=WAVE_COLOR, linewidth=0.6)
    ax.plot(t, lo, color=WAVE_COLOR, linewidth=0.6)
    peak = max(float(np.abs(samples).max()), 1e-3)
    ax.set_ylim(-peak * 1.1, peak * 1.1)
    ax.set_xlim(0, duration)
    ax.set_xlabel("时间 (秒)")
    ax.set_ylabel("振幅")
    ax.set_title(f"{Path(path).name}    时长 {duration:.1f} 秒 · 采样率 {sr // 1000} kHz · 单声道", fontsize=11)
    ax.grid(alpha=0.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


class AudioWaveform:
    """音频目录 -> 波形图 (每个音频一张, 最多 max_files 张) + 原样输出音频目录"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_dir": ("STRING", {"default": "./audio/"}),
                "max_files": ("INT", {"default": 3, "min": 1, "max": 20}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("波形图", "音频目录")
    FUNCTION = "render"
    CATEGORY = "MY_NODES/Preview"

    def render(self, audio_dir, max_files):
        import torch
        files = list_audio_files(audio_dir)[:max_files]
        if not files:
            raise ValueError(f"目录里没有音频文件 {AUDIO_EXTS}: {audio_dir}")
        images = [render_waveform(p) for p in files]
        size = images[0].size
        arrays = [np.asarray(img.resize(size)).astype(np.float32) / 255.0 for img in images]
        return (torch.from_numpy(np.stack(arrays)), audio_dir)


if __name__ == "__main__":
    # 脱离 ComfyUI 调试: python audio_waveform_node.py <音频文件或目录> [输出png]
    import sys
    target = list_audio_files(sys.argv[1])[0]
    out = sys.argv[2] if len(sys.argv) > 2 else "waveform_debug.png"
    render_waveform(target).save(out)
    print(f"{target} -> {os.path.abspath(out)}")
