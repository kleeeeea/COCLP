"""3.1 噪音过滤与置信度筛选: OCR / ASR 产出按置信度阈值 + 噪音规则筛选, 输出保留/剔除清单与剔除原因统计.

    OCR (MinerU middle.json)  每个段落一条, 置信度 = 段落内各识别片段 score 的最小值;
                              版面检测判为页眉/页脚/页码的区块 (discarded_blocks) 直接按噪音剔除
    ASR (分段 jsonl)          每个分段一条, 置信度 = exp(avg_logprob), 另有静音概率和逐词概率
剔除规则 (阈值均为节点参数): 置信度低于阈值、静音概率高于阈值、页眉页脚页码、含网址/版权信息、字数过短、乱码比例高.
保留的 ASR 分段里, 概率低于 "低置信词阈值" 的字作为提示列出, 供人工抽查.
示例: example/offline_prepared/3_1noise_filter/
"""
import html
import json
import re
from collections import Counter
from pathlib import Path

URL_RE = re.compile(r"https?://|www\.|\.(com|net|cn)\b", re.I)
COPYRIGHT_RE = re.compile(r"版权|©|copyright|中国知网", re.I)
PAGE_NO_RE = re.compile(r"^\s*(第?\s*\d+\s*页?|\d+\s*/\s*\d+)\s*$")


def span_texts(block):
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            yield span
    for sub in block.get("blocks", []):
        yield from span_texts(sub)


def load_ocr_units(ocr_dir):
    units = []
    for middle in sorted(Path(ocr_dir).rglob("*_middle.json")):
        doc = middle.name[: -len("_middle.json")]
        for page in json.loads(middle.read_text(encoding="utf-8"))["pdf_info"]:
            for kind, blocks in (("正文", page["para_blocks"]), ("版面噪音", page.get("discarded_blocks", []))):
                for i, block in enumerate(blocks, start=1):
                    spans = [s for s in span_texts(block) if s.get("content")]
                    if not spans:
                        continue
                    units.append({"id": f"{doc}#p{page['page_idx'] + 1}-{'b' if kind == '正文' else 'd'}{i}",
                                  "来源": "OCR", "text": "".join(s["content"] for s in spans),
                                  "置信度": round(min(s.get("score", 1.0) for s in spans), 3), "版面": kind})
    return units


def load_asr_units(asr_segments):
    path = Path(asr_segments)
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def garbled_ratio(text):
    bad = sum(1 for c in text if c == "�" or (not c.isprintable() and c not in "\n\t"))
    return bad / max(len(text), 1)


def drop_reasons(unit, ocr_min, asr_min, silence_max, min_chars):
    text, reasons = unit["text"].strip(), []
    if unit.get("版面") == "版面噪音":
        reasons.append("页眉页脚/页码 (版面检测)")
    if URL_RE.search(text) or COPYRIGHT_RE.search(text):
        reasons.append("网址/版权信息")
    if PAGE_NO_RE.match(text):
        reasons.append("纯页码")
    if len(re.sub(r"\W", "", text)) < min_chars:
        reasons.append(f"字数过短 (<{min_chars})")
    if garbled_ratio(text) > 0.1:
        reasons.append("乱码比例高")
    if unit["来源"] == "OCR" and unit["置信度"] < ocr_min:
        reasons.append(f"OCR 置信度低 (<{ocr_min})")
    if unit["来源"] == "ASR" and unit["置信度"] < asr_min:
        reasons.append(f"ASR 置信度低 (<{asr_min})")
    if unit["来源"] == "ASR" and unit.get("静音概率", 0) > silence_max:
        reasons.append(f"静音/无效语音 (>{silence_max})")
    return reasons


def filter_units(units, ocr_min, asr_min, silence_max, word_min, min_chars):
    kept, dropped = [], []
    for u in units:
        reasons = drop_reasons(u, ocr_min, asr_min, silence_max, min_chars)
        if reasons:
            dropped.append({**u, "剔除原因": reasons})
        else:
            low = [f'{w["词"]}({w["概率"]:.2f})' for w in u.get("逐词", []) if w["概率"] < word_min]
            kept.append({**u, "提示": f"低置信词 {'、'.join(low)}, 建议抽查" if low else ""})
    return kept, dropped


def report_html(kept, dropped, params, max_kept_rows=5):  # 面板固定高度, 保留清单只列前几条, 全量见 保留.jsonl
    esc = html.escape
    by_source = Counter((u["来源"], "保留") for u in kept) + Counter((u["来源"], "剔除") for u in dropped)
    sources = sorted({s for s, _ in by_source})
    reasons = Counter(r for u in dropped for r in u["剔除原因"])
    summary = (f'<div class="coclp-summary">共 {len(kept) + len(dropped)} 条: <span class="q-a">保留 {len(kept)}</span> · '
               f'<span class="q-c">剔除 {len(dropped)}</span>　' +
               "　".join(f'{s} 保留 {by_source[(s, "保留")]} / 剔除 {by_source[(s, "剔除")]}' for s in sources) +
               f'<br>阈值: {esc(params)}</div>')
    reason_tbl = ('<div class="coclp-rec-head">剔除原因统计</div><table class="coclp-table"><tr><th>原因</th><th>条数</th></tr>' +
                  "".join(f"<tr><td>{esc(r)}</td><td>{n}</td></tr>" for r, n in reasons.most_common()) + "</table>")
    drop_tbl = ('<div class="coclp-rec-head" style="margin-top:6px">剔除清单</div><table class="coclp-table">'
                '<tr><th>来源</th><th>内容</th><th>置信度</th><th>原因</th></tr>' +
                "".join(f'<tr><td>{u["来源"]}</td><td class="q-c">{esc(u["text"][:40])}</td><td>{u["置信度"]:.3f}</td>'
                        f'<td>{esc("; ".join(u["剔除原因"]))}</td></tr>' for u in dropped) + "</table>")
    shown = sorted(kept, key=lambda u: (u["来源"] != "ASR", u["置信度"]))[:max_kept_rows]  # ASR 和低置信度的排前面
    keep_tbl = (f'<div class="coclp-rec-head" style="margin-top:6px">保留清单 (按置信度升序, 显示 {len(shown)}/{len(kept)} 条)</div>'
                '<table class="coclp-table"><tr><th>来源</th><th>内容</th><th>置信度</th><th>提示</th></tr>' +
                "".join(f'<tr><td>{u["来源"]}</td><td class="q-a">{esc(u["text"][:40])}{"…" if len(u["text"]) > 40 else ""}</td>'
                        f'<td>{u["置信度"]:.3f}</td><td class="q-b">{esc(u.get("提示", ""))}</td></tr>' for u in shown) + "</table>")
    return summary + reason_tbl + drop_tbl + keep_tbl


class ConfidenceNoiseFilter:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "ocr_dir": ("STRING", {"forceInput": True}),
            "asr_segments": ("STRING", {"forceInput": True}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/3_1noise_filter/output"}),
            "OCR置信度阈值": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01}),
            "ASR置信度阈值": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
            "静音概率阈值": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05}),
            "低置信词阈值": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05}),
            "最短字数": ("INT", {"default": 4, "min": 0, "max": 200}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("保留语料目录",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/清洗"

    def run(self, ocr_dir, asr_segments, output_dir, OCR置信度阈值, ASR置信度阈值, 静音概率阈值, 低置信词阈值, 最短字数):
        units = load_ocr_units(ocr_dir) + load_asr_units(asr_segments)
        kept, dropped = filter_units(units, OCR置信度阈值, ASR置信度阈值, 静音概率阈值, 低置信词阈值, 最短字数)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, rows in (("保留.jsonl", kept), ("剔除.jsonl", dropped)):
            (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        params = (f"OCR≥{OCR置信度阈值} · ASR≥{ASR置信度阈值} · 静音≤{静音概率阈值} · "
                  f"低置信词<{低置信词阈值} · 最短 {最短字数} 字")
        return {"ui": {"html": [report_html(kept, dropped, params)]}, "result": (output_dir,)}


if __name__ == "__main__":
    # python Corpus_Cleansing_Pipeline/noise_filter_node.py <OCR 输出目录> <asr_segments.jsonl>
    import sys
    kept, dropped = filter_units(load_ocr_units(sys.argv[1]) + load_asr_units(sys.argv[2]), 0.9, 0.6, 0.6, 0.6, 4)
    print(f"保留 {len(kept)}, 剔除 {len(dropped)}")
    for u in dropped:
        print("剔除", u["来源"], u["置信度"], u["剔除原因"], u["text"][:30])
    for u in sorted(kept, key=lambda u: u["置信度"])[:4]:
        print("保留", u["来源"], u["置信度"], u["提示"], u["text"][:30])
