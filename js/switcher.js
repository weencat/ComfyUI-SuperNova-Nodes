import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const soundUrl = "../audio/sound.mp3";
const notificationSound = new Audio(soundUrl);

// --- API ---
async function sendSelection(node, value) {
    try {
        await api.fetchApi("/supernova/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: node.id, selection: value })
        });
        app.graph.setDirtyCanvas(true, true);
    } catch (error) { console.error(error); }
}

// --- 类型同步 ---
function syncNodeType(node, typeSourceIndex = 0) {
    let newType = "*";
    if (node.inputs) {
        if (node.inputs[typeSourceIndex] && node.inputs[typeSourceIndex].link) {
             const link = app.graph.links[node.inputs[typeSourceIndex].link];
             if (link) {
                 const sourceNode = app.graph.getNodeById(link.origin_id);
                 if (sourceNode?.outputs[link.origin_slot]) {
                     newType = sourceNode.outputs[link.origin_slot].type || "*";
                 }
             }
        } else {
            for (const input of node.inputs) {
                if (input.link) {
                    const link = app.graph.links[input.link];
                    if (link) {
                        const sourceNode = app.graph.getNodeById(link.origin_id);
                        if (sourceNode?.outputs[link.origin_slot]) {
                            newType = sourceNode.outputs[link.origin_slot].type || "*";
                            break;
                        }
                    }
                }
            }
        }
    }
    if (node.inputs) node.inputs.forEach(i => i.type = newType);
    if (node.outputs) {
        node.outputs.forEach(o => { o.type = newType; o.label = o.name; });
    }
    return newType;
}

function playSound() {
    try {
        notificationSound.currentTime = 0;
        notificationSound.volume = 0.5;
        notificationSound.play().catch(() => {});
    } catch (e) {}
}

// --- 静态节点配置逻辑 ---
function configureStaticNode(node, buttonsDef) {
    // 1. 提取底部 Widget (Seed等)
    const bottomWidgets = node.widgets ? node.widgets.filter(w => 
        w.name === "seed" || w.name === "control_after_generate" || w.name === "noise_seed" || w.name === "fixed_seed"
    ) : [];

    // 2. 清空并添加按钮
    node.widgets = [];
    buttonsDef.forEach(b => {
        node.addWidget("button", b.label, null, () => sendSelection(node, b.value));
    });
    node.addWidget("button", "⛔ STOP", null, () => sendSelection(node, "stop"));
    
    // 3. 加回底部 Widget
    bottomWidgets.forEach(w => node.widgets.push(w));

    // 4. 绑定类型同步
    const orig = node.onConnectionsChange;
    node.onConnectionsChange = function() {
        if(orig) orig.apply(this, arguments);
        syncNodeType(this);
    };
    setTimeout(() => syncNodeType(node), 50);

    // 5. 调整大小
    const baseH = 60;
    const hPerW = 32;
    node.setSize([220, baseH + (node.widgets.length * hPerW)]);
}

// ============================================================
// 注册扩展
// ============================================================
app.registerExtension({
    name: "Supernova.FlowNodes",
    setup() {
        api.addEventListener("supernova_pause_alert", ({ detail }) => { playSound(); });
    },
    async nodeCreated(node) {
        switch (node.comfyClass) {
            case "PauseAndSelectOutput": 
                configureStaticNode(node, [
                    { label: "👉 Output 1", value: "1" },
                    { label: "👉 Output 2", value: "2" }
                ]);
                break;
            case "PauseAndSelectInput": 
                configureStaticNode(node, [
                    { label: "👈 Input 1", value: "1" },
                    { label: "👈 Input 2", value: "2" }
                ]);
                break;
            case "PauseAndMatrix": 
                configureStaticNode(node, [
                    { label: "In 1 ➡️ Out 1", value: "1-1" },
                    { label: "In 1 ↘️ Out 2", value: "1-2" },
                    { label: "In 2 ↗️ Out 1", value: "2-1" },
                    { label: "In 2 ➡️ Out 2", value: "2-2" }
                ]);
                break;
            // 固定 5 个输入
            case "MultiInputSelector": 
                configureStaticNode(node, [
                    { label: "▶️ Input 1", value: "input_1" },
                    { label: "▶️ Input 2", value: "input_2" },
                    { label: "▶️ Input 3", value: "input_3" },
                    { label: "▶️ Input 4", value: "input_4" },
                    { label: "▶️ Input 5", value: "input_5" },
                ]);
                break;
            // 固定 5 个输出
            case "MultiOutputSplitter": 
                configureStaticNode(node, [
                    { label: "▶️ Output 1", value: "output_1" },
                    { label: "▶️ Output 2", value: "output_2" },
                    { label: "▶️ Output 3", value: "output_3" },
                    { label: "▶️ Output 4", value: "output_4" },
                    { label: "▶️ Output 5", value: "output_5" },
                ]);
                break;
        }
    }
});