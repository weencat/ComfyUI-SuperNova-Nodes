import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// 统一发送函数
async function sendGateAction(nodeId, action, type) {
    try {
        const response = await fetch(`${api.api_base}/supernova/gate_control`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                node_id: String(nodeId),
                action: action,
                type: type
            })
        });
        if (!response.ok) throw new Error("Network response was not ok");
    } catch (error) {
        console.error("Failed to send gate action:", error);
    }
}

// 1. FlowControlSwitch20
app.registerExtension({
    name: "Supernova.FlowControlV2",
    async nodeCreated(node) {
        if (node.comfyClass === "FlowControlSwitch20") {
            node.onConnectionsChange = function (type, index, connected, link_info) {
                if (!link_info) return;
                if (connected) {
                    const link_type = link_info.type;
                    this.inputs[0].type = link_type;
                    this.outputs[0].type = link_type;
                    this.outputs[0].name = link_type;
                    this.inputs[0].label = link_type;
                } else {
                    const has_input = this.inputs[0].link !== null;
                    const has_output = this.outputs[0].links != null && this.outputs[0].links.length > 0;
                    if (!has_input && !has_output) {
                        this.inputs[0].type = "*";
                        this.outputs[0].type = "*";
                        this.outputs[0].name = "ANY";
                        this.inputs[0].label = "any_input";
                    }
                }
                if (app.graph) app.graph.setDirtyCanvas(true, true);
            };

            node.addWidget("button", "▶️ RUN", null, () => sendGateAction(node.id, "run", "flow"));
            node.addWidget("button", "🛑 STOP", null, () => sendGateAction(node.id, "stop", "flow"));
            setTimeout(() => node.setSize([240, 110]), 100);
        }
    }
});

// 2. ImageCompareBreakpoint20 (双图对比)
app.registerExtension({
    name: "Supernova.ImageCompareBreakpoint20",
    async nodeCreated(node) {
        if (node.comfyClass === "ImageCompareBreakpoint20") {
            node.properties = node.properties || {};
            if (node.properties.btnAName === undefined) node.properties.btnAName = "🅰️ RUN A";
            if (node.properties.btnBName === undefined) node.properties.btnBName = "🅱️ RUN B";

            const btnA = node.addWidget("button", node.properties.btnAName, null, () => sendGateAction(node.id, "pass_a", "compare"));
            const btnB = node.addWidget("button", node.properties.btnBName, null, () => sendGateAction(node.id, "pass_b", "compare"));
            const btnStop = node.addWidget("button", "🛑 STOP", null, () => sendGateAction(node.id, "stop", "compare"));

            if (node.widgets) {
                const myBtns = [btnA, btnB, btnStop];
                const otherWidgets = node.widgets.filter(w => !myBtns.includes(w));
                node.widgets = [...myBtns, ...otherWidgets];
            }

            node.onExecuted = function (message) {
                if (message?.a_images && message?.b_images) {
                    const compareWidget = this.widgets?.find(
                        w => w.name === "compare_view" || w.type === "IMAGECOMPARE"
                    );
                    if (compareWidget) {
                        compareWidget.value = {
                            a_images: message.a_images,
                            b_images: message.b_images
                        };
                    }
                    this.a_images = message.a_images;
                    this.b_images = message.b_images;
                    if (app.graph) app.graph.setDirtyCanvas(true, true);
                }
            };

            const origGetExtraMenuOptions = node.getExtraMenuOptions;
            node.getExtraMenuOptions = function (_, options) {
                if (origGetExtraMenuOptions) origGetExtraMenuOptions.apply(this, arguments);

                options.push({
                    content: "✏️ 修改 A 按钮名称",
                    callback: () => {
                        const newName = prompt("请输入 A 按钮新名称:", btnA.name);
                        if (newName !== null && newName.trim() !== "") {
                            btnA.name = newName;
                            node.properties.btnAName = newName;
                            app.graph.setDirtyCanvas(true, true);
                        }
                    }
                });

                options.push({
                    content: "✏️ 修改 B 按钮名称",
                    callback: () => {
                        const newName = prompt("请输入 B 按钮新名称:", btnB.name);
                        if (newName !== null && newName.trim() !== "") {
                            btnB.name = newName;
                            node.properties.btnBName = newName;
                            app.graph.setDirtyCanvas(true, true);
                        }
                    }
                });
            };

            setTimeout(() => { node.setSize([400, 450]); }, 100);
        }
    }
});

// 3. ImagePreviewBreakpoint20
app.registerExtension({
    name: "Supernova.ImagePreviewBreakpoint20",
    async nodeCreated(node) {
        if (node.comfyClass === "ImagePreviewBreakpoint20") {
            node.addWidget("button", "▶️ RUN", null, () => sendGateAction(node.id, "run", "image"));
            node.addWidget("button", "🛑 STOP", null, () => sendGateAction(node.id, "stop", "image"));
            setTimeout(() => node.setSize([320, 340]), 100);
        }
    }
});
