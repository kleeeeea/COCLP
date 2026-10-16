"""6.1 图 2 专家抽样审核 截图: 审核节点阻塞到专家提交, 通用 shoot_workflow.py 等不到 "运行结束", 这里单独驱动:

    1. 运行 -> 等审核单推送到节点 -> 等第一次 "定期提醒" (提醒间隔秒, 默认 60)
    2. 截图 expert_review.png (审核单待专家填写, 不预填任何专家结论)
    3. 中断本次运行, 解除阻塞 (不代替专家提交)

用法 (在 COCLP 目录下, ComfyUI 已启动, 已跑过图 1): python example/offline_prepared/quality_control/shoot_expert_review.py
"""
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shoot_workflow import COMFY_URL, HIDE_CSS, FRAME_JS  # noqa: E402

WORKFLOW = "offline_prepared/expert_review.json"
REMIND_WAIT_MS = 75_000

LOAD_AND_QUEUE_JS = """
async (workflowPath) => {
  const wf = await fetch('/api/userdata/' + workflowPath).then(r => r.json());
  await app.loadGraphData(wf, true, true, 'expert_review');
  await new Promise(r => setTimeout(r, 800));
  app.canvas.show_info = false;
  await app.queuePrompt(0, 1);
}
"""

HIDE_NOTICES_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length === 0 && /任务添加到队列|作业已完成|Job queued|jobs? completed/i.test(el.textContent)) {
      const box = el.closest('div.inline-flex.overflow-hidden.rounded-lg');
      if (box) box.style.display = 'none';
    }
  }
}"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2, locale="zh-CN")
        page.goto(COMFY_URL)
        page.wait_for_function("window.app && window.app.graph", timeout=60000)
        page.add_style_tag(content=HIDE_CSS)
        page.evaluate(LOAD_AND_QUEUE_JS, quote("workflows/" + WORKFLOW, safe=""))
        page.wait_for_selector(".coclp-review .rv-card", timeout=60000)
        print("审核单已推送, 等待第一次提醒...")
        page.wait_for_selector(".coclp-review .rv-wait", state="visible", timeout=REMIND_WAIT_MS)

        framed = page.evaluate(FRAME_JS, [40, 110, 80])
        page.wait_for_timeout(1200)
        page.evaluate(HIDE_NOTICES_JS)
        page.screenshot(path=str(HERE / "expert_review.png"))
        page.screenshot(path=str(HERE / "expert_review_分组裁切.png"), clip=framed["clip"])
        print(f"截图 -> {HERE / 'expert_review.png'}")

        # 结束阻塞: 中断本次运行, 不代替专家提交审核结论
        page.evaluate("() => fetch('/interrupt', {method: 'POST'})")
        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    main()
