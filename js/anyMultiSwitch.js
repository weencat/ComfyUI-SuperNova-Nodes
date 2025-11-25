import { app } from "/scripts/app.js";

/**
 * 核心函数，负责节点的所有动态行为
 */
function configureDynamicSwitch(node) {
    // 1. 侦测连接的真实类型
    let newType = "*"; // 默认为通用类型

    for (const input of node.inputs) {
        if (input.link) {
            const linkInfo = app.graph.links[input.link];
            if (linkInfo) {
                const sourceNode = app.graph.getNodeById(linkInfo.origin_id);
                if (sourceNode?.outputs[linkInfo.origin_slot]) {
                    newType = sourceNode.outputs[linkInfo.origin_slot].type || "*";
                    break; // 找到第一个就停止，所有接口将统一为这个类型
                }
            }
        }
    }

    // 2. 将侦测到的类型应用到节点的所有输入和输出接口上
    // 这是最关键的一步：它直接修改了节点对象的定义，这将影响发送到后端的JSON
    node.inputs.forEach(input => (input.type = newType));
    node.outputs.forEach(output => {
        output.type = newType;
        output.label = newType.toLowerCase(); // 更新UI标签
    });

    // 3. 处理输入接口的动态增删
    const lastInput = node.inputs[node.inputs.length - 1];
    if (lastInput && lastInput.link != null) {
        // 如果最后一个被连接，添加一个新的
        node.addInput(`input_${node.inputs.length + 1}`, newType);
    } else {
        // 如果倒数第二个也没连接（且不止一个输入时），移除最后一个
        if (node.inputs.length > 1) {
            const secondLastInput = node.inputs[node.inputs.length - 2];
            if (!secondLastInput.link) {
                node.removeInput(node.inputs.length - 1);
            }
        }
    }
    
    // 重新编号，确保名字总是连续的
    node.inputs.forEach((input, i) => (input.name = `input_${i + 1}`));
    
    // 强制UI刷新
    node.setDirtyCanvas(true, true);
}

// 注册节点扩展
app.registerExtension({
    name: "supernova.AnyMultiSwitch.FinalSolution",

    beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AnyMultiSwitchScalable") {
            
            // 当连接发生变化时触发
            const onConnectionsChange = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function () {
                onConnectionsChange?.apply(this, arguments);
                configureDynamicSwitch(this);
            };

            // 当节点被添加到画布时触发（包括加载工作流）
            const onAdded = nodeType.prototype.onAdded;
            nodeType.prototype.onAdded = function() {
                onAdded?.apply(this, arguments);
                // 使用setTimeout确保加载工作流时，所有连接信息都已就绪
                setTimeout(() => configureDynamicSwitch(this), 10); 
            };
        }
    },
});