// 把 PIIMerge 节点返回的 ui.html (隐私实体高亮) 显示在节点上的 DOM 组件里, 风格与 compare_diff.js 一致
import { app } from "../../scripts/app.js";

const STYLE = `
.coclp-pii-box { box-sizing: border-box; width: 100%; height: 100%; overflow: auto; padding: 6px 8px;
  font-size: 11px; line-height: 1.8; color: var(--input-text, #222); background: var(--comfy-input-bg, #fff);
  border-radius: 6px; white-space: pre-wrap; word-break: break-all; }
.coclp-pii-box .coclp-summary { margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px dashed var(--border-color, #ccc); }
.coclp-pii-box .coclp-pii-num { color: #c0262d; }
.coclp-pii-box .coclp-rec { margin-bottom: 8px; }
.coclp-pii-box .coclp-rec-head { font-weight: 600; margin-bottom: 2px; }
.coclp-pii-box .coclp-stat { font-weight: 400; margin-left: 8px; opacity: 0.7; }
.coclp-pii-box mark.coclp-pii { background: #fde2e2; color: #c0262d; font-weight: 600; padding: 0 1px; border-radius: 2px; }
.coclp-pii-box .coclp-pii-tag { font-size: 9px; color: #c0262d; opacity: 0.75; margin: 0 2px 0 1px; vertical-align: super; }
`;
const PANEL_HEIGHT = 340;

app.registerExtension({
    name: "COCLP.PIIHighlight",
    setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PIIMerge") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const html = (message?.html || []).join("");

            if (!this.coclpPiiEl) {
                this.coclpPiiEl = document.createElement("div");
                this.coclpPiiEl.className = "coclp-pii-box";
                this.addDOMWidget("pii", "coclp_pii", this.coclpPiiEl, {
                    serialize: false,                     // 检测结果不写进 workflow json
                    getMinHeight: () => PANEL_HEIGHT,     // 固定高度, 内容多了框内滚动
                    getMaxHeight: () => PANEL_HEIGHT,
                });
            }
            this.coclpPiiEl.innerHTML = html;  // 内容在 Python 端已 html.escape
            this.setSize([Math.max(this.size[0], 520), Math.max(this.size[1], PANEL_HEIGHT + 140)]);
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
