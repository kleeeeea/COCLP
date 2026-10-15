// 把 CompareTextDiff 节点返回的 ui.html (清洗前后逐字对比) 显示在节点上的 DOM 组件里
import { app } from "../../scripts/app.js";

const STYLE = `
.coclp-diff { box-sizing: border-box; width: 100%; height: 100%; max-height: 300px; overflow: auto; padding: 6px 8px;
  font-size: 11px; line-height: 1.6; color: var(--input-text, #222); background: var(--comfy-input-bg, #fff);
  border-radius: 6px; white-space: pre-wrap; word-break: break-all; }
.coclp-diff .coclp-summary { margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px dashed var(--border-color, #ccc); }
.coclp-diff .coclp-rec { margin-bottom: 8px; }
.coclp-diff .coclp-rec-head { font-weight: 600; margin-bottom: 2px; }
.coclp-diff .coclp-stat { font-weight: 400; margin-left: 8px; opacity: 0.7; }
.coclp-diff del.coclp-del { background: #fde2e2; color: #c0262d; text-decoration: line-through; }
.coclp-diff ins.coclp-ins { background: #dcf5e3; color: #127a3a; text-decoration: none; }
`;

app.registerExtension({
    name: "COCLP.CompareTextDiff",
    setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "CompareTextDiff") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const html = (message?.html || []).join("");

            if (!this.coclpDiffEl) {
                this.coclpDiffEl = document.createElement("div");
                this.coclpDiffEl.className = "coclp-diff";
                this.addDOMWidget("diff", "coclp_diff", this.coclpDiffEl, {
                    serialize: false,           // 对比内容不写进 workflow json
                    getMinHeight: () => 300,    // 固定高度, 内容多了在框内滚动, 不把节点撑出分组
                    getMaxHeight: () => 300,
                });
            }
            this.coclpDiffEl.innerHTML = html;  // 内容在 Python 端已 html.escape
            this.setSize([Math.max(this.size[0], 420), Math.max(this.size[1], 460)]);
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
