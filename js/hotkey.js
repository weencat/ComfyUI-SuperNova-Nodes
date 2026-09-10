import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ============================================================
// 1. 辅助函数：与后端通信及定位目标节点
// ============================================================

// 发送 PreviewAndPause 控制动作
function sendControl(node, action) {
    if (!node) return;
    api.fetchApi("/supernova/preview_control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: node.id, action: action })
    });
}

// 发送 ImageCompareAndSelect 选择动作并刷新种子
async function sendSelection(node, value) {
    if (!node) return;
    const idWidget = node.widgets?.find(w => w.name === "compare_id" || w.name === "seed");
    if (idWidget) {
        idWidget.value = Math.floor(Math.random() * 1000000000000);
        node.setDirtyCanvas(true, true);
    }
    try {
        await api.fetchApi("/supernova/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: node.id, selection: value })
        });
    } catch (error) {
        console.error("[Supernova Shortcuts] Select error:", error);
    }
}

/**
 * 获取当前目标节点：
 * 优先取当前选中的节点；若未选中，则自动在画布上查找第一个匹配类型的节点（更方便操作）
 */
function getTargetNode(targetType) {
    const selectedNodes = Object.values(app.canvas?.selected_nodes || {});
    
    // 1. 如果选中了目标类型的节点，直接返回选中的节点
    const matchedSelected = selectedNodes.find(n => n.comfyClass === targetType || n.type === targetType);
    if (matchedSelected) return matchedSelected;

    // 2. 如果当前选中的不是目标节点（或没选），在画布中自动搜索已存在的该类节点
    if (app.graph?._nodes) {
        return app.graph._nodes.find(n => n.comfyClass === targetType || n.type === targetType);
    }
    return null;
}

// ============================================================
// 2. 注册快捷键扩展及设置项
// ============================================================

app.registerExtension({
    name: "Supernova.Shortcuts",

    // 指令定义：用户可在设置面板搜到这些操作
    commands: [
        // ---------- [ImageCompareAndSelect 节点指令] ----------
        {
            id: "supernova.selectImage1",
            label: "选择图 1 (Select Image 1)",
            function: () => {
                const node = getTargetNode("ImageCompareAndSelect");
                if (node) {
                    sendSelection(node, "1");
                }
            }
        },
        {
            id: "supernova.selectImage2",
            label: "选择图 2 (Select Image 2)",
            function: () => {
                const node = getTargetNode("ImageCompareAndSelect");
                if (node) {
                    sendSelection(node, "2");
                }
            }
        },
        {
            id: "supernova.stopCompare",
            label: "停止对比流程 (Stop Compare)",
            function: () => {
                const node = getTargetNode("ImageCompareAndSelect");
                if (node) {
                    sendSelection(node, "stop");
                }
            }
        },

        // ---------- [PreviewAndPause 节点指令] ----------
        {
            id: "supernova.previewContinue",
            label: "预览暂停 - 继续 (Continue)",
            function: () => {
                const node = getTargetNode("PreviewAndPause");
                if (node) {
                    sendControl(node, "continue");
                }
            }
        },
        {
            id: "supernova.previewStop",
            label: "预览暂停 - 终止 (Stop)",
            function: () => {
                const node = getTargetNode("PreviewAndPause");
                if (node) {
                    sendControl(node, "stop");
                }
            }
        }
    ]
});