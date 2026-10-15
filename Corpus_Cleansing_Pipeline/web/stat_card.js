// 把 CorpusStatCard 节点返回的 ui.html (大字号指标卡) 显示在节点上的 DOM 组件里
import { app } from "../../scripts/app.js";

const STYLE = `
.coclp-card { box-sizing: border-box; width: 100%; height: 100%; padding: 10px 14px; border-radius: 10px;
  background: var(--comfy-input-bg, #fff); color: var(--input-text, #222); font-family: inherit; }
.coclp-card-title { font-size: 16px; font-weight: 600; opacity: 0.75; }
.coclp-card-number { font-size: 52px; font-weight: 800; line-height: 1.15; margin: 6px 0 2px; color: #d6336c; letter-spacing: 1px; }
.coclp-card-unit { font-size: 22px; font-weight: 600; margin-left: 6px; color: var(--input-text, #222); }
.coclp-card-caption { font-size: 12px; opacity: 0.6; margin-top: 6px; }
.coclp-bar-row { display: flex; align-items: center; gap: 8px; margin: 7px 0; font-size: 15px; }
.coclp-bar-label { width: 64px; text-align: right; font-weight: 600; }
.coclp-bar-track { flex: 1; height: 16px; border-radius: 8px; background: rgba(214, 51, 108, 0.12); overflow: hidden; }
.coclp-bar-fill { display: block; height: 100%; border-radius: 8px; background: linear-gradient(90deg, #f783ac, #d6336c); }
.coclp-bar-pct { width: 40px; font-weight: 700; color: #d6336c; }
`;

app.registerExtension({
    name: "COCLP.CorpusStatCard",
    setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "CorpusStatCard") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            if (!this.coclpCardEl) {
                this.coclpCardEl = document.createElement("div");
                this.coclpCardEl.style.width = "100%";
                this.addDOMWidget("card", "coclp_card", this.coclpCardEl, { serialize: false });
            }
            this.coclpCardEl.innerHTML = (message?.html || []).join("");  // 内容在 Python 端已 html.escape
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
