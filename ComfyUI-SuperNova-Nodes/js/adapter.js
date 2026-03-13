import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "supernova.Fixed5Adapter",
    async nodeCreated(node) {
        if (node.comfyClass === "AnyRerouteAdapter5") {
            
            // 当连接状态改变时触发
            node.onConnectionsChange = function (slotType, slotIndex, isConnected, link_info) {
                // slotType 为 1 表示输入端 (Input)
                if (slotType === 1) {
                    if (isConnected && link_info) {
                        // 1. 找到来源节点的输出类型
                        const originNode = app.graph.getNodeById(link_info.origin_id);
                        const originType = originNode.outputs[link_info.origin_slot].type;
                        
                        // 2. 同时修改输入和输出的类型
                        // 修改输入点（让输入点变色）
                        this.inputs[slotIndex].type = originType;
                        this.inputs[slotIndex].name = `in_${slotIndex + 1} [${originType}]`;
                        
                        // 修改输出点（让输出点变色）
                        this.outputs[slotIndex].type = originType;
                        this.outputs[slotIndex].name = `out_${slotIndex + 1} [${originType}]`;
                    } else {
                        // 3. 断开连接时，恢复为万能类型 "*"
                        this.inputs[slotIndex].type = "*";
                        this.inputs[slotIndex].name = `in_${slotIndex + 1}`;
                        
                        this.outputs[slotIndex].type = "*";
                        this.outputs[slotIndex].name = `out_${slotIndex + 1}`;
                    }
                }
                
                // 强制重绘，让颜色立即生效
                this.setDirtyCanvas(true, true);
            };
        }
    }
});