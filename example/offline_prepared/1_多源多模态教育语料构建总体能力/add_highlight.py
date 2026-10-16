# 界面的字比较小，add arrow to highlight the key sections, buttons /Users/l/klee_code/documents_common/funding/静安-训练数据管线/COCLP/example/offline_prepared/多源多模态教育语料构建总体能力/管道总览与规模看板.png
# 核心是要对应标书的要求
# /Users/l/klee_code/documents_common/funding/静安-训练数据管线/标书/招标参数-华师大.docx
# /Users/l/klee_code/documents_common/funding/静安-训练数据管线/标书/提纲.md
"""在 管道总览与规模看板.png 上加彩色框 + 编号标注 + 箭头, 底部加图例对应招标第 1 条要求.

元素位置来自截图时导出的 管道总览与规模看板.boxes.json (shoot_workflow.py 生成), 布局变了重新截图即可, 不用手调坐标.
用法: python add_highlight.py    ->  输出 管道总览与规模看板_标注.png
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC_PNG = HERE / "管道总览与规模看板.png"
BOXES_JSON = HERE / "管道总览与规模看板.boxes.json"
OUT_PNG = HERE / "管道总览与规模看板_标注.png"

FONT_CANDIDATES = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                   "/System/Library/Fonts/Supplemental/Songti.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
FONT_PATH = next((f for f in FONT_CANDIDATES if Path(f).exists()), FONT_CANDIDATES[-1])
EXTRA_RIGHT, EXTRA_BOTTOM = 0, 700  # 画布只向下扩, 放底部标注和图例 (向右扩会留一大片空白)
BAND_COLOR = "white"

CLAUSE = "招标要求 · 训练语料构建管道 第 1 条：多源多模态教育语料的采集与构建"
# 编号, 颜色, 标注文字, 指向的元素标题 (多个取外接矩形), 标注框左上角, 箭头指向目标框的哪条边, 图例 (功能 —— 对应招标原文)
ANNOTATIONS = [
    ("①", "#E8590C", "多源多格式原始文档采集", ["原始文档 (首页预览)"], (330, 250), "top",
     "多源采集：Word / PDF 等多种格式的原始教育文档 —— “支持从多种教育数据源中采集”"),
    ("②", "#1C7ED6", "多格式解析 → 统一 JSONL", ["Word 文档转换", "Markdown → JSONL"], (760, 520), "top",
     "格式解析：多格式文档统一转换为结构化 JSONL 语料 —— “构建高质量的多模态语料集”"),
    ("③", "#2F9E44", "规则清洗", ["多功能文本清洗器"], (1560, 520), "top",
     "自然语言清洗：去除标记、链接、噪声，前后差异逐字高亮 —— “采集、清洗……构建高质量语料集”"),
    ("③", "#2F9E44", "清洗前后对比（高亮差异）", ["清洗前后对比 (高亮差异)"], (1080, 2050), "bottom",
     None),
    ("④", "#7048E8", "五维标注与分类", ["五维标注与分类 (ecnu-plus)"],
     (1960, 535), "top",
     "五维标注：学科、学段、场景、难度、格式 —— “覆盖全学段及全学科教育场景”"),
    ("④", "#7048E8", "标注结果预览", ["预览: 分类结果"], (1880, 2050), "bottom", None),
    ("⑤", "#D6336C", "输出规模不低于两千亿词元", ["规模看板: 文档数", "规模看板: Token 数"], (2450, 440), "top",
     "规模看板：入库 2,680 万篇、2,040 亿 Token —— “支持输出规模不低于两千亿词元”"),
    ("⑥", "#D6336C", "学段全覆盖", ["规模看板: 学段分布"], (2560, 2050), "bottom",
     "学段分布：学前、小学、初中、高中、职业教育、高等教育 —— “覆盖全学段”"),
    ("⑦", "#F08C00", "一键运行全流程", ["运行"], (2230, 245), "bottom",
     "分组编排：点击“运行”按分组依次执行采集 → 清洗 → 标注 → 统计 —— 长期稳定的语料构建能力"),
]


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def union_box(elements, titles):
    boxes = [e["box"] for e in elements if e["title"] in titles]
    if not boxes:
        raise KeyError(f"截图里找不到: {titles}")
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    return x0, y0, x1, y1


def draw_arrow(draw, start, end, color, width=7, head=26):
    import math
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - head * math.cos(angle - 0.45), end[1] - head * math.sin(angle - 0.45))
    right = (end[0] - head * math.cos(angle + 0.45), end[1] - head * math.sin(angle + 0.45))
    draw.polygon([end, left, right], fill=color)


def draw_label(draw, pos, number, text, color, size=40):
    """白底彩边的标注框: 实心圆编号 + 文字; 返回框的矩形"""
    f, pad, circle = font(size), 16, int(size * 1.35)
    text_w = draw.textlength(text, font=f)
    x0, y0 = pos
    x1, y1 = x0 + pad * 3 + circle + text_w, y0 + circle + pad * 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=18, fill="white", outline=color, width=5)
    cx, cy = x0 + pad + circle / 2, (y0 + y1) / 2
    draw.ellipse([cx - circle / 2, cy - circle / 2, cx + circle / 2, cy + circle / 2], fill=color)
    draw.text((cx, cy), number, fill="white", font=font(int(size * 0.9)), anchor="mm")
    draw.text((x0 + pad * 2 + circle, cy), text, fill="#212529", font=f, anchor="lm")
    return x0, y0, x1, y1


def arrow_points(label, target, side):
    """从标注框指向目标框 side 那条边的中点"""
    lx0, ly0, lx1, ly1 = label
    tx0, ty0, tx1, ty1 = target
    if side == "top":
        return ((lx0 + lx1) / 2, ly1), ((tx0 + tx1) / 2, ty0 - 6)
    if side == "bottom":
        return ((lx0 + lx1) / 2, ly0), ((tx0 + tx1) / 2, ty1 + 6)
    if side == "right":
        return (lx0, (ly0 + ly1) / 2), (tx1 + 6, (ty0 + ty1) / 2)
    return (lx1, (ly0 + ly1) / 2), (tx0 - 6, (ty0 + ty1) / 2)  # left


def draw_legend(draw, top, width):
    draw.rectangle([0, top, width, top + EXTRA_BOTTOM], fill=BAND_COLOR)
    draw.line([(0, top), (width, top)], fill="#E599B8", width=4)
    y = top + 150
    draw.text((60, y), "图例　" + CLAUSE, fill="#212529", font=font(38))
    y += 70
    for number, color, _, _, _, _, legend in ANNOTATIONS:
        if legend is None:
            continue
        draw.ellipse([60, y, 108, y + 48], fill=color)
        draw.text((84, y + 24), number, fill="white", font=font(32), anchor="mm")
        draw.text((128, y + 24), legend, fill="#343A40", font=font(32), anchor="lm")
        y += 58


def main():
    elements = json.loads(BOXES_JSON.read_text(encoding="utf-8"))["elements"]
    shot = Image.open(SRC_PNG).convert("RGB")
    canvas = Image.new("RGB", (shot.width + EXTRA_RIGHT, shot.height + EXTRA_BOTTOM), BAND_COLOR)
    canvas.paste(shot, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw_legend(draw, shot.height, canvas.width)

    for number, color, text, titles, pos, side, _ in ANNOTATIONS:
        target = union_box(elements, titles)
        pad = 10
        draw.rounded_rectangle([target[0] - pad, target[1] - pad, target[2] + pad, target[3] + pad],
                               radius=16, outline=color, width=8)
        label = draw_label(draw, pos, number, text, color)
        start, end = arrow_points(label, (target[0] - pad, target[1] - pad, target[2] + pad, target[3] + pad), side)
        draw_arrow(draw, start, end, color)

    canvas.save(OUT_PNG)
    print(f"写入 {OUT_PNG}  ({canvas.width}x{canvas.height})")


if __name__ == "__main__":
    main()
