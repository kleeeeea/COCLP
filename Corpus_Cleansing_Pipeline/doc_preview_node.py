"""文档首页预览: 把目录里 docx / pdf 的第一页渲染成图片, 用 ComfyUI 自带的图片预览显示在节点上.

渲染方式:
- pdf : pypdfium2 直接渲染第 1 页
- docx: 先转 pdf 再渲染. 有 LibreOffice (soffice) 就用它 (排版最准, Linux 服务器上用这个);
        没有的话在 macOS 上用 textutil (系统自带) 转 html, 再用本机 Chrome 无头打印成 pdf.
渲染结果按文件内容哈希缓存到 cache_dir, 同一文件不重复渲染.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

CHROME_CANDIDATES = [
    os.environ.get("COCLP_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]
CAPTION_FONTS = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def docx_to_pdf(docx_path, work_dir):
    """docx -> pdf, 返回 pdf 路径"""
    work_dir = Path(work_dir)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(work_dir), str(docx_path)],
                       check=True, capture_output=True, timeout=120)
        return work_dir / (Path(docx_path).stem + ".pdf")

    chrome = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)
    if not shutil.which("textutil") or not chrome:
        raise RuntimeError("渲染 docx 需要 LibreOffice (soffice), 或 macOS textutil + Chrome")
    html_path, pdf_path = work_dir / "doc.html", work_dir / "doc.pdf"
    subprocess.run(["textutil", "-convert", "html", "-output", str(html_path), str(docx_path)],
                   check=True, capture_output=True, timeout=60)
    # 有的 docx 段落带从右到左 (RTL) 属性, textutil 原样保留, 中文句号会跑到行首; 统一改回从左到右
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    fix_css = "<style>* { direction: ltr !important; unicode-bidi: normal !important; }</style>"
    html_path.write_text(html_text.replace("</head>", fix_css + "</head>", 1), encoding="utf-8")
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=120)
    return pdf_path


def render_pdf_first_page(pdf_path, width_px):
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    scale = width_px / page.get_width()
    image = page.render(scale=scale).to_pil().convert("RGB")
    pdf.close()
    return image


def crop_to_content(image, ratio=0.7):
    """只保留页面顶部 (高 = 宽 x ratio): 多个文档统一成同样的横向比例, 节点上排得整齐, 缩略图里字也更大"""
    return image.crop((0, 0, image.width, min(image.height, int(image.width * ratio))))


def add_caption(image, caption):
    """图片下方加一条文件名, 多张图并排时分得清 (找不到中文字体就不加)"""
    font_path = next((f for f in CAPTION_FONTS if os.path.exists(f)), None)
    if not font_path:
        return image
    font = ImageFont.truetype(font_path, max(14, image.width // 28))
    bar_h = int(font.size * 2)
    canvas = Image.new("RGB", (image.width, image.height + bar_h), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line([(0, image.height), (image.width, image.height)], fill="#d0d7e2", width=2)
    draw.text((image.width // 2, image.height + bar_h // 2), caption, fill="#334155", font=font, anchor="mm")
    # 页面外加一圈细边框, 白底页面放在浅色画布上也看得出边界
    ImageDraw.Draw(canvas).rectangle([0, 0, canvas.width - 1, canvas.height - 1], outline="#c7d2e0", width=2)
    return canvas


def render_first_page(doc_path, cache_dir, width_px=800):
    """渲染 docx/pdf 第一页, 返回缓存里的 png 路径"""
    doc_path = Path(doc_path)
    cache_png = Path(cache_dir) / f"{doc_path.stem}_{file_hash(doc_path)}_{width_px}_top.png"
    if cache_png.exists():
        return cache_png
    cache_png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work_dir:
        pdf_path = doc_path if doc_path.suffix.lower() == ".pdf" else docx_to_pdf(doc_path, work_dir)
        image = crop_to_content(render_pdf_first_page(pdf_path, width_px))
    add_caption(image, f"{doc_path.name}  · 第 1 页").save(cache_png)
    return cache_png


def list_documents(input_dir, file_types):
    exts = {"." + e.strip().lower().lstrip(".") for e in file_types.split(",") if e.strip()}
    root = Path(input_dir)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
    return [p for p in files if p.suffix.lower() in exts and not p.name.startswith("~$")]


class DocFirstPagePreview:
    """文档首页预览: 输入目录里每个 docx / pdf 的第一页截图显示在节点上"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_dir": ("STRING", {"default": "../example/test_data"}),
                "file_types": ("STRING", {"default": "docx,pdf"}),
                "max_docs": ("INT", {"default": 4, "min": 1, "max": 20}),
                "width_px": ("INT", {"default": 800, "min": 200, "max": 2400, "step": 100}),
                "cache_dir": ("STRING", {"default": "../example/test_out/doc_preview_cache"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文档目录",)
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Preview"

    def preview(self, input_dir, file_types, max_docs, width_px, cache_dir):
        import folder_paths  # ComfyUI 的临时目录, /view 接口从这里读图

        docs = list_documents(input_dir, file_types)[:max_docs]
        if not docs:
            raise ValueError(f"{input_dir} 里没有 {file_types} 文件")
        temp_dir = Path(folder_paths.get_temp_directory()) / "coclp_doc_preview"
        temp_dir.mkdir(parents=True, exist_ok=True)
        images = []
        for doc in docs:
            png = render_first_page(doc, cache_dir, width_px)
            shutil.copy(png, temp_dir / png.name)
            images.append({"filename": png.name, "subfolder": "coclp_doc_preview", "type": "temp"})
        return {"ui": {"images": images}, "result": (input_dir,)}


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent.parent / "example/test_data")
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent.parent / "example/test_out/doc_preview_cache")
    for doc in list_documents(src, "docx,pdf"):
        print(render_first_page(doc, out))
