"""4.3 人工抽样审计 截图: 审计节点会一直阻塞到有人提交, 通用的 shoot_workflow.py 等不到 "运行结束", 这里单独驱动:

    1. 运行 -> 等审核面板出现 -> 等第一次 "定期提醒" (remind_interval_sec, 默认 60 秒)
    2. 勾选前 3 条 "通过" -> 截图 human_audit_审核中.png (面板 + 阻塞提醒)
    3. 第 4 条 (漏脱敏样本) 标 "不通过" 并填原因, 第 5 条 "通过", 填审核人, 提交
    4. 等节点汇总结论 (通过率 80% < 阈值 95%, 拦截下游) -> 截图 human_audit_审核结果.png

用法 (在 COCLP 目录下, ComfyUI 已启动): python example/offline_prepared/human_audit/shoot_human_audit.py
"""
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shoot_workflow import COMFY_URL, HIDE_CSS, FRAME_JS  # noqa: E402

WORKFLOW = "offline_prepared/human_audit.json"
REMIND_WAIT_MS = 75_000  # 等第一次提醒 (60 秒) 出现

LOAD_AND_QUEUE_JS = """
async (workflowPath) => {
  const wf = await fetch('/api/userdata/' + workflowPath).then(r => r.json());
  await app.loadGraphData(wf, true, true, 'human_audit');
  await new Promise(r => setTimeout(r, 800));
  app.canvas.show_info = false;
  await app.queuePrompt(0, 1);
}
"""

HIDE_NOTICES_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length === 0 && /任务添加到队列|作业已完成|Job queued|jobs? completed/i.test(el.textContent)) {
      let box = el.closest('div.inline-flex.overflow-hidden.rounded-lg');
      if (box) box.style.display = 'none';
    }
    // 下游被拦截时弹出的 "该节点在执行过程中发生错误" 提示框会挡住画布; 节点上的红色 "错误" 条已经能说明被拦截
    if (el.children.length === 0 && /该节点在执行过程中发生错误|error occurred while executing/i.test(el.textContent)) {
      let box = el;
      while (box && box !== document.body && !['fixed', 'absolute'].includes(getComputedStyle(box).position)) box = box.parentElement;
      if (box && box !== document.body) box.style.display = 'none';
    }
  }
}"""


SET_VERDICT_JS = """([index, verdict, comment]) => {
  // 节点上的 DOM 面板在无头浏览器里被画布浮层挡住, 模拟点击点不到, 直接设值并触发 change 事件
  const box = document.querySelectorAll('.coclp-audit .au-sample')[index];
  const radio = box.querySelector(`input[type=radio][value=${verdict}]`);
  radio.checked = true;
  radio.dispatchEvent(new Event('change'));
  if (comment) box.querySelector('.au-comment').value = comment;
}"""


def set_verdict(page, index, verdict, comment=""):
    page.evaluate(SET_VERDICT_JS, [index, verdict, comment])


def shoot_both(page, name):
    framed = page.evaluate(FRAME_JS, [40, 110, 80])
    page.wait_for_timeout(1200)
    page.evaluate(HIDE_NOTICES_JS)
    out = HERE / f"{name}.png"
    page.screenshot(path=str(out))
    page.screenshot(path=str(HERE / f"{name}_分组裁切.png"), clip=framed["clip"])
    print(f"截图 -> {out}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2, locale="zh-CN")
        page.goto(COMFY_URL)
        page.wait_for_function("window.app && window.app.graph", timeout=60000)
        page.add_style_tag(content=HIDE_CSS)
        page.evaluate(LOAD_AND_QUEUE_JS, quote("workflows/" + WORKFLOW, safe=""))

        page.wait_for_selector(".coclp-audit .au-sample", timeout=60000)
        print("审核面板已推送, 等待第一次提醒...")
        page.wait_for_selector(".coclp-audit .au-wait", state="visible", timeout=REMIND_WAIT_MS)
        for i in range(3):
            set_verdict(page, i, "pass")
        shoot_both(page, "human_audit_审核中")

        set_verdict(page, 3, "fail", "姓名、手机号未脱敏, 退回重新脱敏")
        set_verdict(page, 4, "pass")
        page.evaluate("""() => {
          document.querySelector('.coclp-audit .au-auditor').value = '隐私合规审核员 A';
          document.querySelector('.coclp-audit .au-submit').click();
        }""")
        page.wait_for_selector(".coclp-audit .au-result", timeout=60000)
        page.wait_for_timeout(1500)
        shoot_both(page, "human_audit_审核结果")
        browser.close()


if __name__ == "__main__":
    main()
