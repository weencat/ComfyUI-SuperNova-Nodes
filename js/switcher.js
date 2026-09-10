import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

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

// --- [新增] 自定义弹窗函数 ---
// 解决浏览器拦截 prompt 的问题，同时提供更好看的 UI
function showRenameDialog(title, defaultValue, onOk) {
    // 1. 创建遮罩层
    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
        backgroundColor: "rgba(0,0,0,0.5)", zIndex: "9999",
        display: "flex", justifyContent: "center", alignItems: "center"
    });

    // 2. 创建对话框
    const box = document.createElement("div");
    Object.assign(box.style, {
        backgroundColor: "#353535", color: "#fff", padding: "20px",
        borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)",
        minWidth: "300px", fontFamily: "Arial, sans-serif", border: "1px solid #555"
    });

    // 3. 标题
    const titleEl = document.createElement("h3");
    titleEl.textContent = title;
    titleEl.style.marginTop = "0";

    // 4. 输入框
    const input = document.createElement("input");
    input.type = "text";
    input.value = defaultValue;
    Object.assign(input.style, {
        width: "100%", padding: "8px", margin: "10px 0",
        borderRadius: "4px", border: "1px solid #666",
        backgroundColor: "#222", color: "#fff", boxSizing: "border-box"
    });

    // 5. 按钮容器
    const btnContainer = document.createElement("div");
    btnContainer.style.display = "flex";
    btnContainer.style.justifyContent = "flex-end";
    btnContainer.style.gap = "10px";

    // 按钮样式辅助
    const btnStyle = {
        padding: "6px 15px", borderRadius: "4px", border: "none", cursor: "pointer", fontWeight: "bold"
    };

    // 取消按钮
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    Object.assign(cancelBtn.style, btnStyle, { backgroundColor: "#555", color: "#fff" });

    // 确定按钮
    const okBtn = document.createElement("button");
    okBtn.textContent = "Save";
    Object.assign(okBtn.style, btnStyle, { backgroundColor: "#2366b8", color: "#fff" });

    // 6. 事件处理
    const close = () => document.body.removeChild(overlay);

    cancelBtn.onclick = close;

    const submit = () => {
        onOk(input.value);
        close();
    };

    okBtn.onclick = submit;

    // 支持回车提交，ESC关闭
    input.onkeydown = (e) => {
        if (e.key === "Enter") submit();
        if (e.key === "Escape") close();
    };
    // 点击遮罩层关闭
    overlay.onclick = (e) => { if (e.target === overlay) close(); };

    // 7. 组装并添加到页面
    btnContainer.appendChild(cancelBtn);
    btnContainer.appendChild(okBtn);
    box.appendChild(titleEl);
    box.appendChild(input);
    box.appendChild(btnContainer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    // 自动聚焦输入框
    setTimeout(() => input.focus(), 50);
}


// --- 静态节点配置逻辑 ---
function configureStaticNode(node, buttonsDef) {
    // 1. 初始化 properties
    if (!node.properties) node.properties = {};
    if (!node.properties.labels) node.properties.labels = {};

    // 2. 提取底部 Widget
    const bottomWidgets = node.widgets ? node.widgets.filter(w =>
        w.name === "seed" || w.name === "control_after_generate" || w.name === "noise_seed" || w.name === "fixed_seed"
    ) : [];

    // 3. 清空现有 Widgets
    node.widgets = [];

    // 4. 添加按钮
    buttonsDef.forEach((b) => {
        const savedLabel = node.properties.labels[b.value];
        const displayLabel = savedLabel !== undefined ? savedLabel : b.label;

        const w = node.addWidget("button", displayLabel, null, () => sendSelection(node, b.value));

        if (savedLabel !== undefined) w.label = savedLabel;

        w.supernovaValue = b.value;
        w.supernovaDefaultLabel = b.label;
    });

    // 5. 添加停止按钮
    node.addWidget("button", "⛔ STOP", null, () => sendSelection(node, "stop"));

    // 6. 加回底部 Widget
    bottomWidgets.forEach(w => node.widgets.push(w));

    // 7. 处理右键菜单 (使用自定义弹窗 showRenameDialog)
    const origGetExtraMenuOptions = node.getExtraMenuOptions;
    node.getExtraMenuOptions = function (_, options) {
        if (origGetExtraMenuOptions) origGetExtraMenuOptions.apply(this, arguments);

        options.push(null);
        options.push({ content: "🖊️ Rename Buttons...", disabled: true });

        if (this.widgets) {
            this.widgets.forEach((w) => {
                if (w.supernovaValue) {
                    const currentLabel = w.label || w.name;

                    options.push({
                        content: `   📝 Rename "${currentLabel}"`,
                        callback: () => {
                            // 使用自定义弹窗替代 prompt
                            showRenameDialog(
                                `Rename "${currentLabel}"`,
                                currentLabel,
                                (newName) => { // 回调函数
                                    if (newName !== null) {
                                        if (newName.trim() === "") {
                                            // 恢复默认
                                            w.label = w.supernovaDefaultLabel;
                                            w.name = w.supernovaDefaultLabel;
                                            delete this.properties.labels[w.supernovaValue];
                                        } else {
                                            // 设置新名
                                            w.label = newName;
                                            this.properties.labels[w.supernovaValue] = newName;
                                        }
                                        app.graph.setDirtyCanvas(true, true);
                                    }
                                }
                            );
                        }
                    });
                }
            });
        }
    };

    // 8. 状态恢复
    const origConfigure = node.onConfigure;
    node.onConfigure = function () {
        if (origConfigure) origConfigure.apply(this, arguments);
        if (this.properties && this.properties.labels && this.widgets) {
            this.widgets.forEach(w => {
                if (w.supernovaValue && this.properties.labels[w.supernovaValue]) {
                    w.label = this.properties.labels[w.supernovaValue];
                }
            });
        }
    };

    // 9. 绑定类型同步
    const origConnectionsChange = node.onConnectionsChange;
    node.onConnectionsChange = function () {
        if (origConnectionsChange) origConnectionsChange.apply(this, arguments);
        syncNodeType(this);
    };
    setTimeout(() => syncNodeType(node), 50);

    // 10. 调整大小
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
        // 👇 这里使用 window.playSupernovaSound?.() 进行安全调用
        api.addEventListener("supernova_pause_alert", () => {
            window.playSupernovaSound?.();
        });
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
            case "MultiInputSelector":
                configureStaticNode(node, [
                    { label: "▶️ Input 1", value: "input_1" },
                    { label: "▶️ Input 2", value: "input_2" },
                    { label: "▶️ Input 3", value: "input_3" },
                    { label: "▶️ Input 4", value: "input_4" },
                    { label: "▶️ Input 5", value: "input_5" },
                ]);
                break;
            case "MultiOutputSplitter":
                configureStaticNode(node, [
                    { label: "▶️ Output 1", value: "output_1" },
                    { label: "▶️ Output 2", value: "output_2" },
                    { label: "▶️ Output 3", value: "output_3" },
                    { label: "▶️ Output 4", value: "output_4" },
                    { label: "▶️ Output 5", value: "output_5" },
                ]);
                break;
            case "PlaySoundAlert":
                // 1. 添加测试按钮，并在前端做等价的路径字符清理 (鲁棒性加强)
                node.addWidget("button", "▶️ Test Sound", null, () => {
                    const useCustWidget = node.widgets.find(w => w.name === "use_custom_path");
                    const pathWidget = node.widgets.find(w => w.name === "audio_path");

                    if (useCustWidget && useCustWidget.value) {
                        let p = (pathWidget?.value || "").trim();
                        // 去除两端引号
                        p = p.replace(/^["']|["']$/g, "").trim();
                        // 移除不区分大小写的 "path:" 前缀
                        if (p.toLowerCase().startsWith("path:")) {
                            p = p.substring(5).trim();
                            // 再次移除潜在引号
                            p = p.replace(/^["']|["']$/g, "").trim();
                        }
                        if (p) window.playSupernovaCustomSound?.(p);
                    } else {
                        window.playSupernovaSound?.();
                    }
                });

                // 2. 绑定连线类型自动同步
                const origConnectionsChangeSound = node.onConnectionsChange;
                node.onConnectionsChange = function () {
                    if (origConnectionsChangeSound) origConnectionsChangeSound.apply(this, arguments);
                    syncNodeType(this);
                };
                setTimeout(() => syncNodeType(node), 50);

                // 3. 微调初始高度
                const size = node.computeSize();
                node.setSize([220, Math.max(size[1], 120)]);
                break;
        }
    }
});