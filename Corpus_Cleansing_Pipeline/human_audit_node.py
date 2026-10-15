"""4.3 人工抽样审计: 阻塞节点.

流程: 从脱敏后的语料里按固定种子抽样 -> 推送到前端审核面板 -> 阻塞等待人工提交结论,
等待期间每隔 remind_interval_sec 提醒一次 (前端 toast + 节点闪烁 + 浏览器通知 + 日志)
-> 人工提交后写审计记录和报告 -> 通过率达标则放行下游, 否则用 ExecutionBlocker 拦截下游 (退回).

前端面板见 web/human_audit.js, 提交接口 POST /coclp/audit/submit.
"""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

# 等待中的审计任务: task_id -> {"event", "result", "payload"}
PENDING_AUDITS = {}
PENDING_LOCK = threading.Lock()


def load_jsonl_records(input_dir):
    """读取目录 (或单个文件) 下所有 jsonl, 返回 [(相对路径, 行号, 记录)]"""
    root = Path(input_dir)
    files = [root] if root.is_file() else sorted(root.rglob("*.jsonl"))
    records = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if line.strip():
                    rel = file_path.name if root.is_file() else str(file_path.relative_to(root))
                    records.append((rel, line_no, json.loads(line)))
    return records


def draw_samples(records, sample_size, seed, max_chars):
    """固定种子抽样, 保证同一批语料每次抽到同样的样本, 审计可复现"""
    picked = random.Random(seed).sample(records, min(sample_size, len(records)))
    samples = []
    for rel, line_no, obj in picked:
        text = obj.get("text", "")
        samples.append({
            "sample_id": f"{rel}:{line_no}",
            "record_id": obj.get("id", ""),
            "text": text[:max_chars] + ("…" if len(text) > max_chars else ""),
            "text_len": len(text),
        })
    return samples


def wait_for_verdict(task_id, remind_interval_sec, timeout_sec, send_reminder, check_interrupt, poll_sec=1.0):
    """阻塞直到 submit_verdict(task_id, ...) 被调用; 每 remind_interval_sec 调一次 send_reminder(已等待秒数).
    timeout_sec=0 表示一直等. check_interrupt 用来响应 ComfyUI 的 "取消" (抛异常).
    """
    task = PENDING_AUDITS[task_id]
    start = time.monotonic()
    next_remind = start + remind_interval_sec
    while not task["event"].wait(timeout=poll_sec):
        check_interrupt()
        now = time.monotonic()
        if timeout_sec and now - start >= timeout_sec:
            raise TimeoutError(f"人工抽样审计超时 ({timeout_sec}s 无人提交): {task_id}")
        if now >= next_remind:
            send_reminder(int(now - start))
            next_remind = now + remind_interval_sec
    return task["result"]


def submit_verdict(task_id, result):
    """前端提交审核结论 (由 HTTP 路由调用); 返回 False 表示任务不存在或已结束"""
    with PENDING_LOCK:
        task = PENDING_AUDITS.get(task_id)
        if task is None or task["event"].is_set():
            return False
        task["result"] = result
        task["event"].set()
        return True


def summarize(samples, result, pass_threshold):
    """合并样本与结论, 计算通过率, 生成报告文本"""
    verdicts = {v["sample_id"]: v for v in result.get("verdicts", [])}
    rows = []
    for s in samples:
        v = verdicts.get(s["sample_id"], {})
        rows.append({**s, "verdict": v.get("verdict", "fail"), "comment": v.get("comment", "")})
    n_pass = sum(r["verdict"] == "pass" for r in rows)
    pass_rate = n_pass / len(rows) if rows else 0.0
    passed = pass_rate >= pass_threshold

    lines = [
        f"人工抽样审计: {'通过, 放行入库' if passed else '未通过, 已拦截并退回'}",
        f"审核人: {result.get('auditor') or '未填写'}    提交时间: {result.get('submitted_at', '')}",
        f"抽样 {len(rows)} 条, 通过 {n_pass} 条, 通过率 {pass_rate:.0%} (阈值 {pass_threshold:.0%})",
    ]
    failed = [r for r in rows if r["verdict"] != "pass"]
    if failed:
        lines.append("不通过样本:")
        lines += [f"  - {r['sample_id']}: {r['comment'] or '(无说明)'}" for r in failed]
    return rows, pass_rate, passed, "\n".join(lines)


def send_event(event, data):
    try:
        from server import PromptServer
        PromptServer.instance.send_sync(event, data)
    except Exception as e:  # 脱离 ComfyUI 单独调试时没有 server
        print(f"[人工抽样审计] {event}: {e}")


def raise_if_interrupted():
    try:
        import comfy.model_management
    except ImportError:
        return
    comfy.model_management.throw_exception_if_processing_interrupted()


class HumanSampleAudit:
    """阻塞节点: 等人工审核脱敏语料的抽样结果, 期间定期提醒; 不达标则拦截下游"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_dir": ("STRING", {"default": "../example/bid_data/audit_demo"}),
                "output_dir": ("STRING", {"default": "../example/test_out/audit"}),
                "sample_size": ("INT", {"default": 5, "min": 1, "max": 200}),
                "seed": ("INT", {"default": 2026, "min": 0, "max": 2**31 - 1}),
                "pass_threshold": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
                "remind_interval_sec": ("INT", {"default": 60, "min": 5, "max": 86400}),
                "timeout_min": ("INT", {"default": 0, "min": 0, "max": 100000}),  # 0 = 一直等
                "max_chars": ("INT", {"default": 300, "min": 50, "max": 5000}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("放行目录", "审计报告")
    FUNCTION = "audit"
    OUTPUT_NODE = True
    CATEGORY = "MY_NODES/Privacy"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # 每次运行都要重新人工审核, 不走缓存

    def audit(self, input_dir, output_dir, sample_size, seed, pass_threshold,
              remind_interval_sec, timeout_min, max_chars, unique_id=None):
        samples = draw_samples(load_jsonl_records(input_dir), sample_size, seed, max_chars)
        if not samples:
            raise ValueError(f"没有可审计的 jsonl 记录: {input_dir}")

        task_id = f"audit-{datetime.now():%Y%m%d-%H%M%S}-{unique_id}"
        task_dir = Path(output_dir) / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        payload = {"task_id": task_id, "node_id": unique_id, "input_dir": input_dir,
                   "pass_threshold": pass_threshold, "samples": samples}
        (task_dir / "task.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with PENDING_LOCK:
            PENDING_AUDITS[task_id] = {"event": threading.Event(), "result": None, "payload": payload}
        send_event("coclp.audit.request", payload)
        print(f"[人工抽样审计] {task_id}: 已推送 {len(samples)} 条样本, 等待人工审核...")

        def send_reminder(waited_sec):
            print(f"[人工抽样审计] 提醒: {task_id} 已等待 {waited_sec // 60} 分 {waited_sec % 60} 秒, 管道阻塞中")
            send_event("coclp.audit.remind", {**payload, "waited_sec": waited_sec})

        try:
            result = wait_for_verdict(task_id, remind_interval_sec, timeout_min * 60,
                                      send_reminder, raise_if_interrupted)
        finally:
            with PENDING_LOCK:
                PENDING_AUDITS.pop(task_id, None)
            send_event("coclp.audit.closed", {"task_id": task_id, "node_id": unique_id})

        rows, pass_rate, passed, report = summarize(samples, result, pass_threshold)
        with open(task_dir / "audit_result.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps({**row, "auditor": result.get("auditor", ""),
                                    "submitted_at": result.get("submitted_at", "")}, ensure_ascii=False) + "\n")
        (task_dir / "report.md").write_text(report + "\n", encoding="utf-8")
        print(f"[人工抽样审计] {task_id}: 通过率 {pass_rate:.0%}, {'放行' if passed else '拦截'}")

        if passed:
            released = input_dir
        else:
            from comfy_execution.graph_utils import ExecutionBlocker
            released = ExecutionBlocker(f"人工抽样审计未通过 (通过率 {pass_rate:.0%} < {pass_threshold:.0%}), 语料已退回, 禁止入库")
        return {"ui": {"text": [report]}, "result": (released, report)}


def register_routes():
    """POST /coclp/audit/submit  {task_id, auditor, verdicts:[{sample_id, verdict: pass|fail, comment}]}
    GET  /coclp/audit/pending   页面刷新后恢复审核面板"""
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    routes = PromptServer.instance.routes

    @routes.post("/coclp/audit/submit")
    async def audit_submit(request):
        body = await request.json()
        body["submitted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ok = submit_verdict(body.get("task_id"), body)
        return web.json_response({"ok": ok}, status=200 if ok else 404)

    @routes.get("/coclp/audit/pending")
    async def audit_pending(request):
        with PENDING_LOCK:
            return web.json_response([t["payload"] for t in PENDING_AUDITS.values()])


register_routes()


if __name__ == "__main__":
    # 脱离 ComfyUI 调试: 抽样 -> 另一个线程 2 秒后模拟人工提交 -> 看报告
    import sys
    demo_dir = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent.parent / "example/bid_data/audit_demo")
    samples = draw_samples(load_jsonl_records(demo_dir), 4, 2026, 80)
    PENDING_AUDITS["demo"] = {"event": threading.Event(), "result": None, "payload": {}}
    fake = {"auditor": "测试", "verdicts": [{"sample_id": s["sample_id"], "verdict": "pass"} for s in samples[:-1]]
            + [{"sample_id": samples[-1]["sample_id"], "verdict": "fail", "comment": "姓名未脱敏"}]}
    threading.Timer(2.5, submit_verdict, args=("demo", fake)).start()
    result = wait_for_verdict("demo", 1, 0, lambda s: print(f"提醒: 已等待 {s}s"), lambda: None)
    print(summarize(samples, result, 0.8)[3])
