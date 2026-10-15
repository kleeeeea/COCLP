// 把 PIIMerge (隐私实体高亮) 和 Desensitizer (脱敏前后对比) 返回的 ui.html 显示在节点上的 DOM 组件里,
// 风格与 compare_diff.js 一致
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
.coclp-pii-box del.coclp-del { background: #fde2e2; color: #c0262d; text-decoration: line-through; }
.coclp-pii-box ins.coclp-ins { background: #dcf5e3; color: #127a3a; text-decoration: none; font-weight: 600; }
.coclp-pii-box .q-a { color: #127a3a; font-weight: 700; }
.coclp-pii-box .q-b { color: #b45309; font-weight: 700; }
.coclp-pii-box .q-c { color: #c0262d; font-weight: 700; }
.coclp-pii-box table.coclp-table { width: 100%; border-collapse: collapse; white-space: normal; margin-top: 4px; }
.coclp-pii-box .coclp-table th, .coclp-pii-box .coclp-table td { border: 1px solid var(--border-color, #ddd);
  padding: 2px 5px; text-align: left; vertical-align: top; }
.coclp-pii-box .coclp-table th { background: rgba(0, 0, 0, 0.04); white-space: nowrap; }
.coclp-pii-box .coclp-table td:not(:last-child) { white-space: nowrap; }  /* ID/语料/总分/档 不折行, 原因列自动换行 */
.coclp-pii-box .coclp-retour { margin-top: 6px; padding: 6px 8px; border-radius: 4px; background: #fde2e2; color: #c0262d; }
.coclp-pii-box .coclp-pass { margin-top: 6px; padding: 6px 8px; border-radius: 4px; background: #dcf5e3; color: #127a3a; }
`;
// 4.1 隐私检测合并、4.2 脱敏、6.1 质量评估 / 黄金集质控、3.3 近似去重 都用这个面板显示 ui.html
const NODE_TYPES = ["PIIMerge", "Desensitizer", "QualityAssess", "GoldenLabelCheck", "SimHashDedup",
                    "BatchVersionRegister", "ModelCorpusTrace", "ComplianceAudit"];
const PANEL_HEIGHT = 340;

app.registerExtension({
    name: "COCLP.PIIHighlight",
    setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.appendChild(style);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_TYPES.includes(nodeData.name)) return;

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
