// 4.3 人工抽样审计 (HumanSampleAudit) 的审核面板:
//   coclp.audit.request -> 在节点上显示抽样样本 + 通过/不通过 + 备注 + 提交按钮
//   coclp.audit.remind  -> 面板顶部显示 "已等待 x 分 x 秒, 管道阻塞中" + 弹提示 + 节点闪烁 + 浏览器通知
//   提交 -> POST /coclp/audit/submit; 节点执行完 (onExecuted) -> 面板显示审计结论
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const STYLE = `
.coclp-audit { box-sizing: border-box; width: 100%; height: 100%; overflow: auto; padding: 6px 8px; font-size: 11px;
  line-height: 1.6; color: var(--input-text, #222); background: var(--comfy-input-bg, #fff); border-radius: 6px; }
.coclp-audit .au-head { font-weight: 600; margin-bottom: 4px; }
.coclp-audit .au-wait { display: none; margin: 4px 0 6px; padding: 4px 8px; border-radius: 4px;
  background: #fff4d6; color: #8a5a00; border: 1px solid #f0c36d; font-weight: 600; }
.coclp-audit .au-sample { padding: 5px 6px; margin-bottom: 5px; border: 1px solid var(--border-color, #ddd); border-radius: 4px; }
.coclp-audit .au-sample.fail { border-color: #e8a1a1; background: #fff5f5; }
.coclp-audit .au-sample.pass { border-color: #9fd8b1; background: #f4fbf6; }
.coclp-audit .au-meta { opacity: 0.65; font-size: 10px; }
.coclp-audit .au-text { margin: 2px 0 4px; white-space: pre-wrap; word-break: break-all; }
.coclp-audit .au-row { display: flex; gap: 10px; align-items: center; }
.coclp-audit input[type=text] { flex: 1; font-size: 11px; padding: 1px 4px; border: 1px solid var(--border-color, #ccc);
  border-radius: 3px; background: transparent; color: inherit; }
.coclp-audit .au-foot { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
.coclp-audit button { font-size: 11px; padding: 3px 12px; border-radius: 4px; border: none; background: #2563eb; color: #fff; cursor: pointer; }
.coclp-audit .au-result { margin-top: 6px; padding: 6px 8px; border-radius: 4px; white-space: pre-wrap; }
.coclp-audit .au-result.ok { background: #dcf5e3; color: #127a3a; }
.coclp-audit .au-result.bad { background: #fde2e2; color: #c0262d; }
`;
const PANEL_HEIGHT = 470;

function findNode(nodeId) {
    return app.graph.getNodeById?.(Number(nodeId)) ?? app.graph._nodes_by_id?.[nodeId];
}

function ensurePanel(node) {
    if (node.coclpAuditEl) return node.coclpAuditEl;
    const el = document.createElement("div");
    el.className = "coclp-audit";
    node.addDOMWidget("audit", "coclp_audit", el, {
        serialize: false,
        getMinHeight: () => PANEL_HEIGHT,
        getMaxHeight: () => PANEL_HEIGHT,
    });
    // 节点上方有 8 个参数控件 (约 420 高), 面板放在下面
    node.setSize([Math.max(node.size[0], 560), Math.max(node.size[1], PANEL_HEIGHT + 440)]);
    node.coclpAuditEl = el;
    return el;
}

function renderTask(node, task) {
    const el = ensurePanel(node);
    if (el.dataset.taskId === task.task_id) return el;  // 同一任务不重复渲染, 保留已勾选的结论
    el.dataset.taskId = task.task_id;
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const samples = task.samples.map((s, i) => `
      <div class="au-sample" data-sid="${esc(s.sample_id)}">
        <div class="au-meta">样本 ${i + 1} · ${esc(s.sample_id)} · ${s.text_len} 字</div>
        <div class="au-text">${esc(s.text)}</div>
        <div class="au-row">
          <label><input type="radio" name="v-${esc(task.task_id)}-${i}" value="pass"> 通过</label>
          <label><input type="radio" name="v-${esc(task.task_id)}-${i}" value="fail"> 不通过</label>
          <input type="text" class="au-comment" placeholder="备注 (不通过时说明原因)">
        </div>
      </div>`).join("");
    el.innerHTML = `
      <div class="au-head">待人工审核: 抽样 ${task.samples.length} 条 · 通过率阈值 ${Math.round(task.pass_threshold * 100)}%</div>
      <div class="au-wait"></div>
      ${samples}
      <div class="au-foot">审核人 <input type="text" class="au-auditor" placeholder="姓名/工号">
        <button class="au-submit">提交审核结论</button></div>
      <div class="au-status au-meta"></div>`;
    el.querySelectorAll(".au-sample input[type=radio]").forEach((r) =>
        r.addEventListener("change", () => {
            r.closest(".au-sample").className = `au-sample ${r.value}`;
        }));
    el.querySelector(".au-submit").addEventListener("click", () => submit(task.task_id, el));
    app.graph.setDirtyCanvas(true, true);
    return el;
}

async function submit(taskId, el) {
    const verdicts = [...el.querySelectorAll(".au-sample")].map((box) => ({
        sample_id: box.dataset.sid,
        verdict: box.querySelector("input[type=radio]:checked")?.value || "fail",  // 未选视为不通过
        comment: box.querySelector(".au-comment").value,
    }));
    const auditor = el.querySelector(".au-auditor").value;
    const res = await api.fetchApi("/coclp/audit/submit", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, auditor, verdicts }),
    });
    el.querySelector(".au-status").textContent = res.ok ? "已提交, 等待节点汇总结论…" : "提交失败: 任务不存在或已结束";
}

function remind(node, task) {
    const el = renderTask(node, task);
    const m = Math.floor(task.waited_sec / 60), s = task.waited_sec % 60;
    const wait = el.querySelector(".au-wait");
    wait.style.display = "block";
    wait.textContent = `⏰ 已等待 ${m} 分 ${s} 秒, 管道阻塞中, 请尽快完成审核`;
    app.extensionManager?.toast?.add({ severity: "warn", summary: "人工抽样审计提醒",
        detail: `${node.title}: 已等待 ${m} 分 ${s} 秒`, life: 8000 });
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification("人工抽样审计提醒", { body: `管道已阻塞 ${m} 分 ${s} 秒, 等待审核` });
    }
    const color = node.color;  // 节点标题栏闪一下
    node.color = "#d97706";
    app.graph.setDirtyCanvas(true, true);
    setTimeout(() => { node.color = color; app.graph.setDirtyCanvas(true, true); }, 1500);
}

app.registerExtension({
    name: "COCLP.HumanSampleAudit",
    async setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);

        api.addEventListener("coclp.audit.request", ({ detail }) => {
            const node = findNode(detail.node_id);
            if (node) renderTask(node, detail);
            if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
        });
        api.addEventListener("coclp.audit.remind", ({ detail }) => {
            const node = findNode(detail.node_id);
            if (node) remind(node, detail);
        });
        // 页面刷新后恢复仍在等待的审核任务
        try {
            const pending = await api.fetchApi("/coclp/audit/pending").then((r) => r.json());
            pending.forEach((task) => { const node = findNode(task.node_id); if (node) renderTask(node, task); });
        } catch (e) { /* 服务端没有该接口时忽略 */ }
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "HumanSampleAudit") return;
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const report = (message?.text || []).join("\n");
            const el = ensurePanel(this);
            el.querySelector(".au-wait")?.style.setProperty("display", "none");
            el.querySelector(".au-foot")?.remove();
            el.querySelector(".au-status")?.remove();
            el.querySelector(".au-result")?.remove();
            const box = document.createElement("div");
            box.className = `au-result ${report.includes("未通过") ? "bad" : "ok"}`;
            box.textContent = report;
            el.prepend(box);
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
