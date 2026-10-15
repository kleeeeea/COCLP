"""6.1 图 2 专家抽样审核 截图: 审核节点阻塞到专家提交, 通用 shoot_workflow.py 等不到 "运行结束", 这里单独驱动:

    1. 运行 -> 等审核单出现 -> 等第一次 "定期提醒" (提醒间隔秒, 默认 60)
    2. 按专家视角填审核单 -> 截图 expert_review_审核中.png
         Q06《背影》: 学科 数学→语文, 质量档 B→A, 修改后通过;  Q03 听力: 格式改纯文本, 修改后通过;  A 档抽检: 通过
    3. 提交 (解除阻塞) -> 等节点汇总 -> 截图 expert_review_审核结果.png

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

# 节点上的 DOM 面板在无头浏览器里被画布浮层挡住, 直接设值并触发 change 事件
FILL_JS = """([sid, edits, conclusion, comment]) => {
  const card = document.querySelector(`.coclp-review .rv-card[data-sid="${sid}"]`);
  if (!card) return false;
  for (const [dim, value] of Object.entries(edits)) {
    const field = card.querySelector(`[data-dim="${dim}"]`);
    field.value = value;
    field.dispatchEvent(new Event('change'));
  }
  card.querySelectorAll('[data-check]').forEach(c => { c.checked = true; });
  const radio = card.querySelector(`input[type=radio][value="${conclusion}"]`);
  radio.checked = true;
  radio.dispatchEvent(new Event('change'));
  card.querySelector('.rv-comment').value = comment;
  return true;
}"""

HIDE_NOTICES_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length === 0 && /任务添加到队列|作业已完成|Job queued|jobs? completed/i.test(el.textContent)) {
      const box = el.closest('div.inline-flex.overflow-hidden.rounded-lg');
      if (box) box.style.display = 'none';
    }
  }
}"""


def shoot_both(page, name):
    framed = page.evaluate(FRAME_JS, [40, 110, 80])
    page.wait_for_timeout(1200)
    page.evaluate(HIDE_NOTICES_JS)
    page.screenshot(path=str(HERE / f"{name}.png"))
    page.screenshot(path=str(HERE / f"{name}_分组裁切.png"), clip=framed["clip"])
    print(f"截图 -> {HERE / name}.png")


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

        page.evaluate(FILL_JS, ["Q06", {"学科": "语文", "grade": "A"}, "修改后通过", "学科应为语文, 改正后可入库"])
        page.evaluate(FILL_JS, ["Q03", {"格式": "纯文本"}, "修改后通过", "无音频原文, 格式改为纯文本"])
        sids = page.evaluate("() => [...document.querySelectorAll('.coclp-review .rv-card')].map(c => c.dataset.sid)")
        for sid in sids:
            if sid not in ("Q03", "Q06"):
                page.evaluate(FILL_JS, [sid, {}, "通过", ""])  # A 档抽检样本
        page.evaluate("() => { document.querySelector('.coclp-review .rv-auditor').value = '语文教研组 刘老师'; }")
        shoot_both(page, "expert_review_审核中")

        page.evaluate("() => document.querySelector('.coclp-review .rv-submit').click()")
        page.wait_for_selector(".coclp-review .rv-result", timeout=60000)
        page.wait_for_timeout(1500)
        shoot_both(page, "expert_review_审核结果")
        browser.close()


if __name__ == "__main__":
    main()
