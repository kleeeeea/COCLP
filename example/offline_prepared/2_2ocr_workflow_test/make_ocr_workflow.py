"""最简 OCR 工作流 (离线预生成结果, 用于标书截图): 只解析一篇 PDF 的第 1 页.

    PDF 文档解析 (MinerU OCR) ─┬─> 预览: OCR 识别文本 (*.md)
                               └─> PDF 页面预览 (*_layout.pdf 版面框标注) -> 预览图像
不分组执行器, 直接点 "运行".

本目录 (example/offline_prepared/ocr_workflow_test/):
    input/                    第 1 页单页 PDF (prepare 生成)
    output/                   MinerU 输出; 放 .offline_prepared 标记后, 再运行直接复用, 不加载 OCR 模型
    ocr_workflow_test.json    工作流 (build 生成)
    ocr_workflow_test*.png    截图 (../shoot_workflow.py 生成)

用法 (在 COCLP 目录下):
    python example/offline_prepared/ocr_workflow_test/make_ocr_workflow.py prepare   # 截取第 1 页
    python example/offline_prepared/ocr_workflow_test/make_ocr_workflow.py build     # 生成工作流 json
    (ComfyUI 里打开 offline_prepared/ocr_workflow_test 运行一次, 真正跑 OCR)
    python example/offline_prepared/ocr_workflow_test/make_ocr_workflow.py mark      # 打离线标记
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COCLP_DIR = HERE.parents[2]
SOURCE_PDF = COCLP_DIR / "example/test_data/初中地理教学中渗透环保理念的策略探讨_周西媛.pdf"
INPUT_DIR = HERE / "input"
OUTPUT_DIR = HERE / "output"
DST = HERE / "ocr_workflow_test.json"
OFFLINE_MARKER = ".offline_prepared"  # 与 Corpus_Cleansing_Pipeline/llm_utils.py 一致

# 工作流里的路径相对 ComfyUI 工作目录 (COCLP/ComfyUI)
REL = "../example/offline_prepared/ocr_workflow_test"


def prepare_first_page():
    """把源 PDF 的第 1 页另存为单页 PDF, 作为 OCR 输入"""
    import pypdfium2 as pdfium
    INPUT_DIR.mkdir(exist_ok=True)
    src = pdfium.PdfDocument(str(SOURCE_PDF))
    one_page = pdfium.PdfDocument.new()
    one_page.import_pages(src, [0])
    out = INPUT_DIR / f"{SOURCE_PDF.stem}_第1页.pdf"
    one_page.save(str(out))
    print(f"写入 {out} (源文件共 {len(src)} 页)")


def build_workflow():
    workflow = {"id": "0ff1e5a0-0c70-4b1d-9c3e-5c2e7a1b0d03", "revision": 0,
                "last_node_id": 0, "last_link_id": 0, "nodes": [], "links": [], "groups": [],
                "config": {}, "extra": {"ds": {"scale": 1, "offset": [0, 0]}}, "version": 0.4}

    def add_node(node_type, title, pos, size, inputs, outputs, widgets_values):
        workflow["last_node_id"] += 1
        node = {"id": workflow["last_node_id"], "type": node_type, "title": title,
                "pos": list(pos), "size": list(size), "flags": {}, "order": workflow["last_node_id"], "mode": 0,
                "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
                "outputs": [{"name": n, "type": t, "links": None} for n, t in outputs],
                "properties": {"Node name for S&R": node_type}, "widgets_values": widgets_values}
        workflow["nodes"].append(node)
        return node

    def add_link(src, dst, link_type):
        workflow["last_link_id"] += 1
        link_id = workflow["last_link_id"]
        workflow["links"].append([link_id, src["id"], 0, dst["id"], 0, link_type])
        src["outputs"][0]["links"] = (src["outputs"][0]["links"] or []) + [link_id]
        dst["inputs"][0]["link"] = link_id

    # Mineru_ocr: [read_path, out_path, backend, type]
    ocr = add_node("Mineru_ocr", "PDF 文档解析 (MinerU OCR)", (0, 0), (340, 160),
                   [], [("root_path", "STRING")], [f"{REL}/input", f"{REL}/output", "pipeline", "pdf"])
    # PreviewOutputDir: [max_files, max_chars, file_pattern]
    text = add_node("PreviewOutputDir", "预览: OCR 识别文本", (400, 260), (420, 460),
                    [("dir_path", "STRING")], [("preview_text", "STRING")], [1, 2000, "*.md"])
    # PreviewPdfPage: [file_pattern, file_index, first_page, num_pages, scale]
    page = add_node("PreviewPdfPage", "PDF 页面预览 (版面框标注)", (400, 0), (420, 200),
                    [("dir_path", "STRING")], [("页面图像", "IMAGE")], ["*_layout.pdf", 0, 0, 1, 1.5])
    image = add_node("PreviewImage", "预览: 版面识别 (第 1 页)", (880, 0), (520, 720),
                     [("images", "IMAGE")], [], [])
    add_link(ocr, text, "STRING")
    add_link(ocr, page, "STRING")
    add_link(page, image, "IMAGE")

    workflow["groups"].append({"id": 1, "title": "PDF 文档解析 (OCR)", "bounding": [-40, -100, 1480, 860],
                               "color": "#3f789e", "font_size": 24, "flags": {}})
    DST.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {DST}")


def mark_offline_prepared():
    if not any(OUTPUT_DIR.rglob("*.md")):
        raise SystemExit(f"{OUTPUT_DIR} 里还没有 OCR 结果, 先在 ComfyUI 里运行一次")
    (OUTPUT_DIR / OFFLINE_MARKER).write_text("结果已离线生成, OCR 节点直接复用\n", encoding="utf-8")
    print(f"标记 {OUTPUT_DIR / OFFLINE_MARKER}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["prepare", "build", "mark"])
    step = parser.parse_args().step
    {"prepare": prepare_first_page, "build": build_workflow, "mark": mark_offline_prepared}[step]()
