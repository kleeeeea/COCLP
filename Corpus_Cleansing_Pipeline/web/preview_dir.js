// 把 PreviewOutputDir 节点返回的 ui.text 显示成节点上的只读多行文本框
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "COCLP.PreviewOutputDir",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PreviewOutputDir") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const text = (message?.text || []).join("\n");

            let widget = this.widgets?.find((w) => w.name === "preview");
            if (!widget) {
                widget = ComfyWidgets["STRING"](this, "preview", ["STRING", { multiline: true }], app).widget;
                widget.inputEl.readOnly = true;
                widget.inputEl.style.opacity = 0.85;
                widget.serialize = false;  // 预览内容不写进 workflow json
            }
            widget.value = text;
            this.setSize([Math.max(this.size[0], 420), Math.max(this.size[1], 360)]);
            app.graph.setDirtyCanvas(true, true);
        };
    },
});
