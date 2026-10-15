// 6.1 专家抽样审核 (ExpertSampleReview) 的审核单面板, 结构同 human_audit.js:
//   coclp.review.request -> 每条样本一张审核单: 自动质量档与原因、五维标签 (可改)、质量档 (可改)、
//                           三项核对、结论 (通过 / 修改后通过 / 退返)、备注
//   coclp.review.remind  -> 顶部 "已等待 x 分 x 秒" + 弹提示 + 节点闪烁
//   提交 -> POST /coclp/audit/submit (与 4.3 共用); 节点执行完 -> 显示审核结论
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const STYLE = `
.coclp-review { box-sizing: border-box; width: 100%; height: 100%; overflow: auto; padding: 6px 8px; font-size: 11px;
  line-height: 1.6; color: var(--input-text, #222); background: var(--comfy-input-bg, #fff); border-radius: 6px; }
.coclp-review .rv-head { font-weight: 600; margin-bottom: 4px; }
.coclp-review .rv-wait { display: none; margin: 4px 0 6px; padding: 4px 8px; border-radius: 4px;
  background: #fff4d6; color: #8a5a00; border: 1px solid #f0c36d; font-weight: 600; }
.coclp-review .rv-card { padding: 6px; margin-bottom: 6px; border: 1px solid var(--border-color, #ddd); border-radius: 4px; }
.coclp-review .rv-card.done { border-color: #9fd8b1; background: #f4fbf6; }
.coclp-review .rv-card.back { border-color: #e8a1a1; background: #fff5f5; }
.coclp-review .rv-meta { opacity: 0.7; font-size: 10px; }
.coclp-review .grade-A { color: #127a3a; font-weight: 700; } .coclp-review .grade-B { color: #b45309; font-weight: 700; }
.coclp-review .grade-C { color: #c0262d; font-weight: 700; }
.coclp-review .rv-text { margin: 2px 0 4px; white-space: pre-wrap; word-break: break-all; }
.coclp-review .rv-row { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; margin-top: 3px; }
.coclp-review select, .coclp-review input[type=text] { font-size: 11px; padding: 0 3px; border: 1px solid var(--border-color, #ccc);
  border-radius: 3px; background: transparent; color: inherit; }
.coclp-review select.changed { border-color: #c0262d; color: #c0262d; font-weight: 700; background: #fde2e2; }
.coclp-review input.rv-comment { flex: 1; min-width: 160px; }
.coclp-review .rv-foot { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
.coclp-review button { font-size: 11px; padding: 3px 12px; border-radius: 4px; border: none; background: #2563eb; color: #fff; cursor: pointer; }
.coclp-review .rv-result { margin-bottom: 6px; padding: 6px 8px; border-radius: 4px; white-space: pre-wrap; }
.coclp-review .rv-result.ok { background: #dcf5e3; color: #127a3a; } .coclp-review .rv-result.bad { background: #fde2e2; color: #c0262d; }
`;
const PANEL_HEIGHT = 560;
const LABEL_DIMS = ["学科", "学段", "场景", "难度"];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function findNode(nodeId) {
    return app.graph.getNodeById?.(Number(nodeId)) ?? app.graph._nodes_by_id?.[nodeId];
}

function ensurePanel(node) {
    if (node.coclpReviewEl) return node.coclpReviewEl;
    const el = document.createElement("div");
    el.className = "coclp-review";
    node.addDOMWidget("review", "coclp_review", el, {
        serialize: false, getMinHeight: () => PANEL_HEIGHT, getMaxHeight: () => PANEL_HEIGHT,
    });
    node.setSize([Math.max(node.size[0], 640), Math.max(node.size[1], PANEL_HEIGHT + 300)]);
    node.coclpReviewEl = el;
    return el;
}

function selectHtml(dim, options, value) {
    const opts = options.includes(value) ? options : [value, ...options];
    return `<label>${dim} <select data-dim="${dim}" data-orig="${esc(value)}">` +
        opts.map((o) => `<option${o === value ? " selected" : ""}>${esc(o)}</option>`).join("") + "</select></label>";
}

function cardHtml(task, s, i) {
    const labels = LABEL_DIMS.map((d) => selectHtml(d, task.vocab[d] || [], s.labels[d])).join("");
    const grade = selectHtml("质量档", ["A", "B", "C"], s["质量档"]).replace('data-dim="质量档"', 'data-dim="grade"');
    return `
      <div class="rv-card" data-sid="${esc(s.sample_id)}">
        <div class="rv-meta">${esc(s.抽样原因)} · 自动评估 <span class="grade-${s["质量档"]}">${s["质量档"]} 档</span>
          (${Number(s["总分"]).toFixed(2)})${s["原因"].length ? " · " + esc(s["原因"].join("; ")) : ""}</div>
        <div><b>${esc(s.sample_id)} ${esc(s.title)}</b></div>
        <div class="rv-text">${esc(s.text)}</div>
        <div class="rv-row">${labels}<label>格式 <input type="text" data-dim="格式" value="${esc(s.labels["格式"])}" size="7"></label>${grade}</div>
        <div class="rv-row">核对:
          <label><input type="checkbox" data-check="内容准确"> 内容准确</label>
          <label><input type="checkbox" data-check="教育适宜"> 教育适宜</label>
          <label><input type="checkbox" data-check="无隐私残留"> 无隐私残留</label></div>
        <div class="rv-row">结论:
          ${["通过", "修改后通过", "退返"].map((c) => `<label><input type="radio" name="c-${esc(task.task_id)}-${i}" value="${c}"> ${c}</label>`).join("")}
          <input type="text" class="rv-comment" placeholder="备注 (修改/退返时说明原因)"></div>
      </div>`;
}

function renderTask(node, task) {
    const el = ensurePanel(node);
    if (el.dataset.taskId === task.task_id) return el;
    el.dataset.taskId = task.task_id;
    el.innerHTML = `
      <div class="rv-head">专家抽样审核: 批次 ${task.batch_size} 条, 抽审 ${task.samples.length} 条 · 通过率阈值 ${Math.round(task.pass_threshold * 100)}%</div>
      <div class="rv-wait"></div>
      ${task.samples.map((s, i) => cardHtml(task, s, i)).join("")}
      <div class="rv-foot">审核专家 <input type="text" class="rv-auditor" placeholder="姓名/工号">
        <button class="rv-submit">提交审核单</button></div>
      <div class="rv-status rv-meta"></div>`;
    el.querySelectorAll("select").forEach((sel) => sel.addEventListener("change", () =>
        sel.classList.toggle("changed", sel.value !== sel.dataset.orig)));
    el.querySelectorAll("input[type=radio]").forEach((r) => r.addEventListener("change", () => {
        r.closest(".rv-card").className = `rv-card ${r.value === "退返" ? "back" : "done"}`;
    }));
    el.querySelector(".rv-submit").addEventListener("click", () => submit(task.task_id, el));
    app.graph.setDirtyCanvas(true, true);
    return el;
}

async function submit(taskId, el) {
    const verdicts = [...el.querySelectorAll(".rv-card")].map((card) => {
        const labels = {};
        card.querySelectorAll("[data-dim]").forEach((f) => { if (f.dataset.dim !== "grade") labels[f.dataset.dim] = f.value; });
        const checks = {};
        card.querySelectorAll("[data-check]").forEach((c) => { checks[c.dataset.check] = c.checked; });
        return {
            sample_id: card.dataset.sid, labels, checks,
            grade: card.querySelector('[data-dim="grade"]').value,
            conclusion: card.querySelector("input[type=radio]:checked")?.value || "退返",  // 未选视为退返
            comment: card.querySelector(".rv-comment").value,
        };
    });
    const res = await api.fetchApi("/coclp/audit/submit", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, auditor: el.querySelector(".rv-auditor").value, verdicts }),
    });
    el.querySelector(".rv-status").textContent = res.ok ? "已提交, 等待节点汇总结论…" : "提交失败: 任务不存在或已结束";
}

function remind(node, task) {
    const el = renderTask(node, task);
    const m = Math.floor(task.waited_sec / 60), s = task.waited_sec % 60;
    const wait = el.querySelector(".rv-wait");
    wait.style.display = "block";
    wait.textContent = `⏰ 已等待 ${m} 分 ${s} 秒, 管道阻塞中, 请尽快完成专家审核`;
    app.extensionManager?.toast?.add({ severity: "warn", summary: "专家抽样审核提醒", detail: `已等待 ${m} 分 ${s} 秒`, life: 8000 });
    const color = node.color;
    node.color = "#d97706";
    app.graph.setDirtyCanvas(true, true);
    setTimeout(() => { node.color = color; app.graph.setDirtyCanvas(true, true); }, 1500);
}

app.registerExtension({
    name: "COCLP.ExpertSampleReview",
    async setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);
        api.addEventListener("coclp.review.request", ({ detail }) => { const n = findNode(detail.node_id); if (n) renderTask(n, detail); });
        api.addEventListener("coclp.review.remind", ({ detail }) => { const n = findNode(detail.node_id); if (n) remind(n, detail); });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "ExpertSampleReview") return;
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const report = (message?.text || []).join("\n");
            const el = ensurePanel(this);
            el.querySelector(".rv-wait")?.style.setProperty("display", "none");
            el.querySelector(".rv-foot")?.remove();
            el.querySelector(".rv-status")?.remove();
            el.querySelector(".rv-result")?.remove();
            const box = document.createElement("div");
            box.className = `rv-result ${report.includes("未通过") ? "bad" : "ok"}`;
            box.textContent = report;
            el.prepend(box);
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
