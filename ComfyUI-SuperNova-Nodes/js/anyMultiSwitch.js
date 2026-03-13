import { app } from "../../scripts/app.js";

function configureDynamicSwitch(node) {
    // 1. 安全检查：如果正在加载工作流，绝对不要动端口结构
    if (app.configuring) return;

    let hasChanged = false;

    // 2. 查找当前应有的类型
    let newType = "*";
    if (node.inputs) {
        for (const input of node.inputs) {
            if (input.link) {
                const linkInfo = app.graph.links[input.link];
                if (linkInfo) {
                    const sourceNode = app.graph.getNodeById(linkInfo.origin_id);
                    if (sourceNode) {
                        const originType = sourceNode.outputs[linkInfo.origin_slot]?.type;
                        if (originType && originType !== "*") {
                            newType = originType;
                            break;
                        }
                    }
                }
            }
        }
    }

    // 3. 更新输入端口类型和颜色 (Nodes 2.0 兼容)
    node.inputs?.forEach((input, idx) => {
        if (input.type !== newType) {
            input.type = newType;
            hasChanged = true;
        }
        input.name = `input_${idx + 1}`;
    });

    // 4. 更新输出端口类型和颜色
    node.outputs?.forEach(output => {
        if (output.type !== newType) {
            output.type = newType;
            output.label = newType === "*" ? "any" : newType;
            hasChanged = true;
        }
    });

    // 5. 动态增删端口逻辑 (保守策略：只在非加载状态下执行)
    const lastIndex = node.inputs.length - 1;
    if (node.inputs[lastIndex].link !== null) {
        // 最后一个端口连了，加一个
        node.addInput(`input_${node.inputs.length + 1}`, newType);
        hasChanged = true;
    } else if (node.inputs.length > 1) {
        // 倒数第二个也没连，且最后一个是空的，才删
        if (node.inputs[lastIndex - 1].link === null) {
            node.removeInput(lastIndex);
            hasChanged = true;
        }
    }

    // 6. 强制刷新 UI (Nodes 2.0 核心修复)
    if (hasChanged) {
        // 兼容 Nodes 1.0
        node.setDirtyCanvas(true, true);
        
        // 兼容 Nodes 2.0: 必须通知 graph 发生了结构或属性变化
        if (node.onGraphChanged) {
            node.onGraphChanged();
        }
        
        // 针对端口颜色不刷新的 HACK：
        // 2.0 的颜色由 type 决定，有时候需要触发 node 的 size 重新计算来强迫 Vue 组件重绘
        if (typeof node.computeSize === "function") {
            node.size = node.computeSize();
        }
    }
}

app.registerExtension({
    name: "Supernova.BooleanSwitch",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AnyBooleanSwitch") {
            
            // 保存原有的 onConnectionsChange（防冲突好习惯）
            const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
            
            // 核心功能：当节点连接状态改变时触发
            nodeType.prototype.onConnectionsChange = function (slotType, slotIndex, isConnected, link_info, ioSlot) {
                
                if (originalOnConnectionsChange) {
                    originalOnConnectionsChange.apply(this, arguments);
                }

                // 1. 获取当前所有已连接的输入类型
                let targetType = "*";
                
                // 注意：在 ComfyUI 中，boolean 渲染为控件(Widget)，不占用连线接口。
                // 所以 this.inputs[0] 是 input_false，this.inputs[1] 是 input_true。
                for (let i = 0; i < 2; i++) { 
                    if (this.inputs[i] && this.inputs[i].link) {
                        const link = app.graph.links[this.inputs[i].link];
                        if (link) {
                            const originNode = app.graph.getNodeById(link.origin_id);
                            if (originNode && originNode.outputs[link.origin_slot]) {
                                targetType = originNode.outputs[link.origin_slot].type;
                                break; // 找到第一个有效连接的类型就停止
                            }
                        }
                    }
                }

                // 2. 将所有接口类型同步为 targetType
                // 如果没有连接，重置为 "*"
                if (this.inputs[0]) this.inputs[0].type = targetType;
                if (this.inputs[1]) this.inputs[1].type = targetType;
                
                if (this.outputs[0]) {
                    this.outputs[0].type = targetType;
                    // 当没有连接时，名称变回 output，有连接时名字变成对应的类型（如 MODEL）
                    this.outputs[0].name = targetType === "*" ? "output" : targetType; 
                }

                // 3. 强制触发 ComfyUI 重新计算连接颜色
                app.graph.setDirtyCanvas(true, true);
            };
        }
    },
});
