"""3.2 格式归一化与语言规范化 (全部规则, 不调模型), 每项单独开关, 按顺序执行:

    1. 全半角      全角字母/数字/空格/运算符 -> 半角 (中文标点留给第 3 步按语境处理)
    2. 数学公式    Unicode 数学符号 -> LaTeX (x² -> x^{2}, ≥ -> \\ge, √ -> \\sqrt), 公式片段统一用 $...$ 包裹
    3. 中英标点    中文语境的 , . : ; ! ? ( ) -> ，。：；！？（）; 英文语境误用的 ，。 -> , .
                   ($...$ 公式内和小数点不动)
    4. 简繁统一    OpenCC 繁体 -> 简体
    5. 术语统一    按术语词典 (别名\\t标准术语\\t学科) 把别名替换为标准术语, 长词优先

输入/输出目录里是 jsonl (每行 {"id", "text", ...}), 输出保持文件名和 id 不变, 方便和 "清洗前后对比" 节点对齐.
示例: example/offline_prepared/normalization/
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

CJK = r"一-鿿"
CJK_RE = re.compile(f"[{CJK}]")

# ---------- 1. 全半角 ----------
FULLWIDTH_KEEP = set("，。：；！？（）【】《》“”‘’、")  # 中文标点不在这一步处理


def to_halfwidth(text):
    out = []
    for ch in text:
        code = ord(ch)
        if ch == "　":
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E and ch not in FULLWIDTH_KEEP:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


# ---------- 2. 数学公式 ----------
MATH_SYMBOLS = {"×": r"\times ", "÷": r"\div ", "≤": r"\le ", "≥": r"\ge ", "≠": r"\ne ", "≈": r"\approx ",
                "±": r"\pm ", "π": r"\pi ", "°": r"^{\circ}", "∞": r"\infty ", "α": r"\alpha ", "β": r"\beta ",
                "θ": r"\theta ", "Δ": r"\Delta "}
SUPERSCRIPTS = {"²": "2", "³": "3", "¹": "1", "⁰": "0", "⁴": "4", "ⁿ": "n"}
MATH_SPECIAL = set(MATH_SYMBOLS) | set(SUPERSCRIPTS) | {"√", "^"}
# 公式片段: 由字母数字、运算符、括号和数学符号组成的连续串, 且至少含一个数学专用符号
MATH_RUN_RE = re.compile(r"[A-Za-z0-9+\-=*/^().√" + "".join(MATH_SYMBOLS) + "".join(SUPERSCRIPTS) + r" ]+")


def unicode_math_to_latex(expr):
    expr = re.sub(r"√(\w+|\([^)]*\))", lambda m: r"\sqrt{" + m.group(1).strip("()") + "}", expr)
    expr = re.sub("[" + "".join(SUPERSCRIPTS) + "]+", lambda m: "^{" + "".join(SUPERSCRIPTS[c] for c in m.group()) + "}", expr)
    for sym, latex in MATH_SYMBOLS.items():
        expr = expr.replace(sym, latex)
    return re.sub(r" +", " ", expr).strip()


def normalize_math(text):
    # 已有的 \( ... \) 统一成 $...$, 去掉定界符内侧多余空格
    text = re.sub(r"\\\((.+?)\\\)", lambda m: f"${m.group(1).strip()}$", text)
    text = re.sub(r"\$\s*(.+?)\s*\$", lambda m: f"${m.group(1)}$", text)
    parts = re.split(r"(\$[^$]+\$)", text)  # 已在 $...$ 内的不再处理
    for i, part in enumerate(parts):
        if part.startswith("$"):
            continue

        def wrap(m):
            run = m.group()
            core = run.strip()
            if not any(c in MATH_SPECIAL for c in core):
                return run
            lead, tail = run[: len(run) - len(run.lstrip())], run[len(run.rstrip()):]
            while core and core[-1] in ".,":  # 句末标点不属于公式
                tail, core = core[-1] + tail, core[:-1]
            return f"{lead}${unicode_math_to_latex(core)}${tail}"

        parts[i] = MATH_RUN_RE.sub(wrap, part)
    return "".join(parts)


# ---------- 3. 中英标点 ----------
EN_TO_ZH = {",": "，", ".": "。", ":": "：", ";": "；", "!": "！", "?": "？"}
ZH_TO_EN = {"，": ", ", "。": ". ", "：": ": ", "；": "; ", "！": "! ", "？": "? "}
ZH_LIKE_RE = re.compile(f"[{CJK}　-〿！-／：-？]")  # 汉字或中文标点
FORMULA = ""  # $...$ 公式的占位符: 判断标点语境时跳过它, 看公式前后的文字
CONTEXT_WINDOW = 12


def normalize_punct_masked(text):
    """text 里的公式已替换成占位符"""
    chars = list(text)
    n = len(chars)

    def neighbor(i, step):
        j = i + step
        while 0 <= j < n and chars[j] in (" ", FORMULA):
            j += step
        return chars[j] if 0 <= j < n else ""

    def window_has_cjk(i, step):
        span = chars[max(0, i - CONTEXT_WINDOW):i] if step < 0 else chars[i + 1:i + 1 + CONTEXT_WINDOW]
        return bool(CJK_RE.search("".join(span)))

    for i, ch in enumerate(chars):
        prev, nxt = neighbor(i, -1), neighbor(i, 1)
        if ch in EN_TO_ZH:
            if ch == "." and prev.isdigit() and nxt.isdigit():
                continue  # 小数点
            if ZH_LIKE_RE.match(prev) or (ZH_LIKE_RE.match(nxt) and window_has_cjk(i, -1)):
                chars[i] = EN_TO_ZH[ch]
        elif ch == "(" and ZH_LIKE_RE.match(nxt):
            chars[i] = "（"
        elif ch == ")" and ZH_LIKE_RE.match(prev):
            chars[i] = "）"
        elif ch in ZH_TO_EN and prev.isascii() and prev.isalnum() and not window_has_cjk(i, -1):
            # 英文句子里误用的中文标点; 句末标点只看前文, 句中标点两侧都不能有汉字
            if ch in "。！？" or not window_has_cjk(i, 1):
                chars[i] = ZH_TO_EN[ch]
    text = "".join(chars)
    text = re.sub(r" *([，。：；！？（）]) *", r"\1", text)  # 中文标点两侧不留空格
    return re.sub(r"([,.;:!?]) {2,}", r"\1 ", text).rstrip()


def normalize_punct(text):
    formulas = re.findall(r"\$[^$]+\$", text)
    masked = normalize_punct_masked(re.sub(r"\$[^$]+\$", FORMULA, text))
    for formula in formulas:  # 按顺序放回公式
        masked = masked.replace(FORMULA, formula, 1)
    return masked


# ---------- 4. 简繁 / 5. 术语 ----------
_OPENCC = None


def to_simplified(text):
    global _OPENCC
    if _OPENCC is None:
        from opencc import OpenCC
        _OPENCC = OpenCC("t2s")
    return _OPENCC.convert(text)


def load_term_dict(path):
    """tsv: 别名\\t标准术语\\t学科 (首行表头); 返回按别名长度降序的 [(别名, 标准术语)]"""
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.reader(f, delimiter="\t") if r and not r[0].startswith("#")]
    pairs = [(r[0], r[1]) for r in rows[1:] if len(r) >= 2]
    return sorted(pairs, key=lambda p: -len(p[0]))


def unify_terms(text, pairs, hits):
    for alias, standard in pairs:
        if alias in text:
            hits[f"术语: {alias} → {standard}"] += text.count(alias)
            text = text.replace(alias, standard)
    return text


# ---------- 串起来 ----------

def normalize_text(text, steps, term_pairs=(), hits=None):
    """steps: 打开的规则集合, 取值 fullwidth / math / punct / t2s / terms"""
    hits = Counter() if hits is None else hits
    for name, func in [("fullwidth", to_halfwidth), ("math", normalize_math), ("punct", normalize_punct),
                       ("t2s", to_simplified)]:
        if name in steps:
            new = func(text)
            if new != text:
                hits[STEP_NAMES[name]] += 1
            text = new
    if "terms" in steps and term_pairs:
        text = unify_terms(text, term_pairs, hits)
    return text


STEP_NAMES = {"fullwidth": "全半角", "math": "数学公式", "punct": "中英标点", "t2s": "简繁统一", "terms": "术语统一"}


class TextNormalizer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "input_dir": ("STRING", {"default": "../example/offline_prepared/normalization/data/format"}),
            "output_dir": ("STRING", {"default": "../example/offline_prepared/normalization/output/format"}),
            "全半角": ("BOOLEAN", {"default": True}),
            "数学公式": ("BOOLEAN", {"default": True}),
            "中英标点": ("BOOLEAN", {"default": True}),
            "简繁统一": ("BOOLEAN", {"default": True}),
            "术语统一": ("BOOLEAN", {"default": True}),
            "term_dict": ("STRING", {"default": "../example/offline_prepared/normalization/data/t2s_terms/术语词典.tsv"}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("原始语料目录", "归一化后目录")
    FUNCTION = "run"
    CATEGORY = "MY_NODES/清洗"

    def run(self, input_dir, output_dir, 全半角, 数学公式, 中英标点, 简繁统一, 术语统一, term_dict):
        flags = {"fullwidth": 全半角, "math": 数学公式, "punct": 中英标点, "t2s": 简繁统一, "terms": 术语统一}
        steps = {k for k, on in flags.items() if on}
        term_pairs = load_term_dict(term_dict) if 术语统一 and term_dict and Path(term_dict).is_file() else []
        hits, out_root = Counter(), Path(output_dir)
        for src in sorted(Path(input_dir).rglob("*.jsonl")):
            dst = out_root / src.relative_to(input_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
                for line in fin:
                    if line.strip():
                        rec = json.loads(line)
                        rec["text"] = normalize_text(rec.get("text", ""), steps, term_pairs, hits)
                        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        (out_root / "rule_hits.json").write_text(json.dumps(dict(hits), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[格式归一化] 规则命中: {dict(hits)}")
        return (input_dir, output_dir)


if __name__ == "__main__":
    # python Corpus_Cleansing_Pipeline/text_normalizer_node.py <jsonl> [术语词典.tsv]
    import sys
    pairs = load_term_dict(sys.argv[2]) if len(sys.argv) > 2 else []
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        text = json.loads(line)["text"]
        print("前:", text)
        print("后:", normalize_text(text, set(STEP_NAMES), pairs))
        print()
