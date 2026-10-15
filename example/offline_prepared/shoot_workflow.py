"""用无头 Chrome 打开 ComfyUI 里的某个工作流, 运行 (离线结果直接回放), 对准分组后截高清 PNG, 用于标书.

前提: ComfyUI 已在 http://127.0.0.1:8188 运行 (bash run.sh start), 工作流已在 ComfyUI/user/default/workflows/ 下.
用法:
    python example/offline_prepared/shoot_workflow.py \
        --workflow offline_prepared/docx_workflow_test.json \
        --out example/offline_prepared/docx_workflow_test/docx_workflow_test.png
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

COMFY_URL = "http://127.0.0.1:8188"

# 只影响这次无头页面, 不改用户的 ComfyUI 设置: 隐藏小地图和画布左下角的调试信息 (T/I/N/V/FPS)
HIDE_CSS = ('[class*="minimap" i], [class*="toast" i], [class*="sonner" i], '
            '.graph-canvas-panel div.bottom-0 .p-buttongroup { display: none !important; }')  # 最后一项: 画布右下角缩放控件

LOAD_AND_RUN_JS = """
async ([workflowPath, runTimeoutMs]) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const wf = await fetch('/api/userdata/' + workflowPath).then(r => r.json());
  const name = decodeURIComponent(workflowPath).replace(/^workflows\\//, '').replace(/\\.json$/, '');
  await app.loadGraphData(wf, true, true, name);
  await sleep(800);
  app.canvas.show_info = false;
  app.graph._nodes.forEach(n => n.updateArea?.());  // GroupExecutor 靠节点边界找组内节点
  await app.queuePrompt(0, 1);
  await sleep(2000);
  const t0 = Date.now();
  while (Date.now() - t0 < runTimeoutMs) {
    const sender = app.graph._nodes.find(n => n.type === 'GroupExecutorSender');
    const q = await fetch('/queue').then(r => r.json());
    const busy = (sender && sender.properties.isExecuting) || q.queue_running.length || q.queue_pending.length;
    if (!busy) break;
    await sleep(1000);
  }
  const sender = app.graph._nodes.find(n => n.type === 'GroupExecutorSender');
  return sender ? sender.properties.statusText : 'done';
}
"""

FRAME_JS = """
([margin, topBar, leftBar]) => {
  // leftBar: 左侧边栏宽度 (CSS 像素); 画布铺满整个窗口, 侧边栏盖在上面, 取景要避开
  // 对准所有分组 + 所有节点 (组外的执行器节点也要完整入画)
  const boxes = app.graph._groups.map(g => Array.from(g._bounding))
    .concat(app.graph._nodes.map(n => [n.pos[0], n.pos[1] - 30, n.size[0], n.size[1] + 30]));
  const x0 = Math.min(...boxes.map(b => b[0])), y0 = Math.min(...boxes.map(b => b[1]));
  const x1 = Math.max(...boxes.map(b => b[0] + b[2])), y1 = Math.max(...boxes.map(b => b[1] + b[3]));
  const c = app.canvas, W = c.canvas.width / devicePixelRatio, H = c.canvas.height / devicePixelRatio;
  const s = Math.min((W - leftBar - 2 * margin) / (x1 - x0), (H - topBar - 2 * margin) / (y1 - y0));
  c.ds.scale = s;
  c.ds.offset = [-x0 + (leftBar + (W - leftBar - (x1 - x0) * s) / 2) / s, -y0 + (topBar + margin) / s];
  c.setDirty(true, true);
  // 返回分组在页面上的矩形 (CSS 像素), 用来另存一张只含分组的裁切图
  const rect = c.canvas.getBoundingClientRect();
  const pad = 12;
  return {scale: s, clip: {
    x: rect.left + (x0 + c.ds.offset[0]) * s - pad, y: rect.top + (y0 + c.ds.offset[1]) * s - pad,
    width: (x1 - x0) * s + 2 * pad, height: (y1 - y0) * s + 2 * pad}};
}
"""


BOXES_JS = """
() => {
  // 节点/分组/运行按钮在页面上的矩形 (CSS 像素), 给 add_highlight.py 画标注用
  const c = app.canvas, rect = c.canvas.getBoundingClientRect(), s = c.ds.scale, [ox, oy] = c.ds.offset;
  const toPage = (x, y, w, h) => [rect.left + (x + ox) * s, rect.top + (y + oy) * s, w * s, h * s];
  const titleH = LiteGraph.NODE_TITLE_HEIGHT || 30;
  const nodes = app.graph._nodes.map(n => ({kind: 'node', type: n.type, title: n.title || n.type,
    box: toPage(n.pos[0], n.pos[1] - titleH, n.size[0], n.size[1] + titleH)}));
  const groups = app.graph._groups.map(g => ({kind: 'group', title: g.title, box: toPage(...g._bounding)}));
  const buttons = [...document.querySelectorAll('button')]
    .filter(b => /^\\s*(运行|Run)\\s*$/.test(b.textContent))
    .map(b => { const r = b.getBoundingClientRect(); return {kind: 'button', title: '运行', box: [r.left, r.top, r.width, r.height]}; });
  return nodes.concat(groups, buttons);
}
"""


def shoot(workflow, out_png, width=1600, height=1000, scale=2, run_timeout_s=120):
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        # 中文界面: ComfyUI 按浏览器语言选 locale
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale,
                                locale="zh-CN")
        page.goto(COMFY_URL)
        page.wait_for_function("window.app && window.app.graph", timeout=60000)
        page.add_style_tag(content=HIDE_CSS)
        status = page.evaluate(LOAD_AND_RUN_JS, [quote("workflows/" + workflow, safe=""), run_timeout_s * 1000])
        framed = page.evaluate(FRAME_JS, [40, 110, 80])
        page.wait_for_timeout(1500)  # 等画布和预览文本框重绘
        # 去掉 "任务添加到队列" 之类的通知提示 (类名随前端版本变, 按文本找到所在的浮层再隐藏)
        page.evaluate("""() => {
          for (const el of document.querySelectorAll('body *')) {
            if (el.children.length === 0 && /任务添加到队列|作业已完成|Job queued|jobs? completed/i.test(el.textContent)) {
              // 新版前端: 操作栏下方的圆角提示条; 旧版: fixed 定位的 toast 浮层. 两种都找不到就不动
              let box = el.closest('div.inline-flex.overflow-hidden.rounded-lg');
              if (!box) {
                box = el;
                while (box && box !== document.body && getComputedStyle(box).position !== 'fixed') box = box.parentElement;
              }
              if (box && box !== document.body) box.style.display = 'none';
            }
          }
        }""")
        page.screenshot(path=str(out_png))  # 整页 (含 ComfyUI 界面)
        crop_png = out_png.with_name(out_png.stem + "_分组裁切.png")
        page.screenshot(path=str(crop_png), clip=framed["clip"])  # 只含分组画布
        # 元素坐标 (换算成 PNG 像素), 整页图直接用; 裁切图需减去 clip 的左上角
        boxes = [{**b, "box": [round(v * scale) for v in b["box"]]} for b in page.evaluate(BOXES_JS)]
        clip_px = [round(framed["clip"][k] * scale) for k in ("x", "y", "width", "height")]
        out_png.with_suffix(".boxes.json").write_text(
            json.dumps({"png_scale": scale, "crop_clip": clip_px, "elements": boxes}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        browser.close()
    print(f"运行状态: {status}; 缩放 {framed['scale']:.2f}; 截图 -> {out_png}, {crop_png}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workflow", default="offline_prepared/docx_workflow_test.json",
                        help="相对 ComfyUI/user/default/workflows/ 的路径")
    parser.add_argument("--out", default=str(Path(__file__).parent / "docx_workflow_test" / "docx_workflow_test.png"))
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--run-timeout", type=int, default=120, help="等待运行结束的秒数 (首次真实跑 OCR/ASR 要调大)")
    args = parser.parse_args()
    shoot(args.workflow, args.out, args.width, args.height, args.scale, args.run_timeout)
