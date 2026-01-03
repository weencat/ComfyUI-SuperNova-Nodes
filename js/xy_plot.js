import { app } from "/scripts/app.js";

// =================================================================================
// 通用辅助函数
// =================================================================================

const HIDDEN_TYPE = "supernova_hidden_widget";

/**
 * 切换控件的显示/隐藏
 */
function toggleWidgetVisibility(node, widget, show) {
    if (!widget) return;

    // 记录原始属性
    if (!widget.origProps) {
        widget.origProps = {
            type: widget.type,
            computeSize: widget.computeSize
        };
    }

    if (show) {
        // 恢复显示
        if (widget.type === HIDDEN_TYPE) {
            widget.type = widget.origProps.type;
            widget.computeSize = widget.origProps.computeSize;
        }
    } else {
        // 隐藏
        widget.type = HIDDEN_TYPE;
        widget.computeSize = () => [0, -4]; // 隐藏时不占空间
    }
}


// =================================================================================
// SECTION 1: Builder 节点 (XY_Input_Sampler_Scheduler_Builder)
// =================================================================================

function setupSamplerSchedulerBuilder(nodeType, nodeData, app) {
    if (nodeData.name === "XY_Input_Sampler_Scheduler_Builder") {
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const modeWidget = this.widgets.find((w) => w.name === "mode");
            const samplerWidget = this.widgets.find((w) => w.name === "sampler_name");
            const schedulerWidget = this.widgets.find((w) => w.name === "scheduler_name");
            if (!modeWidget || !samplerWidget || !schedulerWidget) return;

            const originalWidgets = this.widgets.slice();

            const updateWidgets = (modeValue) => {
                let newWidgets = [];
                for (const w of originalWidgets) {
                    if (w.name !== "sampler_name" && w.name !== "scheduler_name") {
                        newWidgets.push(w);
                    }
                }
                
                if (modeValue === "Sampler & Scheduler") {
                    newWidgets.push(samplerWidget, schedulerWidget);
                } else if (modeValue === "Sampler Only") {
                    newWidgets.push(samplerWidget);
                } else if (modeValue === "Scheduler Only") {
                    newWidgets.push(schedulerWidget);
                }

                this.widgets = newWidgets;
                this.computeSize();
                this.setDirtyCanvas(true, true);
            };

            modeWidget.callback = (value) => {
                updateWidgets(value);
            };

            setTimeout(() => updateWidgets(modeWidget.value), 0);
        };
    }
}


// =================================================================================
// SECTION 2: 通用 Batch 节点 (Sampler, Scheduler, Seed, Checkpoint, VAE, PromptSR)
// =================================================================================

// 定义需要应用此逻辑的节点列表
// 关键修复：同时包含 Python 中的映射键名 AND 类名，防止匹配失败
const BATCH_NODES = [
    "XY_Input_Sampler_Scheduler_Batch", // Class Name (修复这里)
    "XY_Input_Seeds_Batch",
    "XY_Input_Checkpoint_Batch",
    "XY_Input_VAE_Batch",
    "XY_Input_PromptSR_Batch"
];

function setupBatchNode(nodeType, nodeData, app) {
    // 检查当前节点是否在我们的支持列表中
    if (BATCH_NODES.includes(nodeData.name)) {
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const node = this;
            const countWidget = node.widgets.find(w => w.name === "input_count");
            // target_parameter 是可选的，只有 Sampler/Scheduler 节点有
            const targetWidget = node.widgets.find(w => w.name === "target_parameter");

            if (!countWidget) return;

            const refreshVisibility = () => {
                const count = countWidget.value;
                // 获取当前模式，如果没有这个控件或值为空，则默认为全选模式，避免逻辑错误
                const target = targetWidget ? (targetWidget.value || "sampler & scheduler") : ""; 

                for (const w of node.widgets) {
                    // 正则匹配：匹配所有可能的动态控件前缀
                    const match = w.name.match(/^(sampler|scheduler|seed|ckpt_name|vae_name|search_txt|replace_txt)_(\d+)$/);
                    
                    if (match) {
                        const type = match[1]; 
                        const index = parseInt(match[2], 10); 

                        let shouldShow = true;

                        // 1. 数量判断
                        if (index > count) {
                            shouldShow = false;
                        }

                        // 2. 特殊模式判断 (仅针对 Sampler/Scheduler)
                        if (shouldShow && target) {
                            // 如果是 sampler 控件，但模式字符串里不包含 "sampler"，则隐藏
                            if (type === "sampler" && !target.includes("sampler")) shouldShow = false;
                            // 如果是 scheduler 控件，但模式字符串里不包含 "scheduler"，则隐藏
                            if (type === "scheduler" && !target.includes("scheduler")) shouldShow = false;
                        }

                        toggleWidgetVisibility(node, w, shouldShow);
                    }
                }

                // 收缩高度：重置为最小高度，让 LiteGraph 自动计算合适的包裹高度
                node.size[1] = 1; 
                node.setSize(node.computeSize());
                app.graph.setDirtyCanvas(true, true);
            };

            // 绑定 count 回调
            const originalCountCallback = countWidget.callback;
            countWidget.callback = (value, canvas, node, pos, e) => {
                refreshVisibility();
                if (originalCountCallback) originalCountCallback(value, canvas, node, pos, e);
            };

            // 绑定 target 回调 (如果存在)
            if (targetWidget) {
                const originalTargetCallback = targetWidget.callback;
                targetWidget.callback = (value, canvas, node, pos, e) => {
                    refreshVisibility();
                    if (originalTargetCallback) originalTargetCallback(value, canvas, node, pos, e);
                };
            }

            // 初始化：延迟一点执行确保节点已完全渲染
            setTimeout(() => refreshVisibility(), 50);
        };
    }
}


// =================================================================================
// SECTION 3: 其他通用节点 (LoRA 等)
// =================================================================================

const widgetHiderHandlers = {
    "LoRA Stacker": ["lora_count", ["lora_name", "lora_wt", "model_str", "clip_str"]],
    "XY Input: LoRA": ["lora_count", ["lora_name", "model_str", "clip_str"]]
};

function setupGenericWidgetHider(nodeType, nodeData, app) {
    if (widgetHiderHandlers[nodeData.name]) {
        const [countName, targetBases] = widgetHiderHandlers[nodeData.name];

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const countWidget = this.widgets.find(w => w.name === countName);
            if (!countWidget) return;

            const handleUpdate = (count) => {
                const maxCount = 50; 
                for (let i = 1; i <= maxCount; i++) {
                    for (const base of targetBases) {
                        const w = this.widgets.find(w => w.name === `${base}_${i}`);
                        if (w) toggleWidgetVisibility(this, w, i <= count);
                    }
                }
                this.size[1] = 1;
                this.setSize(this.computeSize());
            };

            const cb = countWidget.callback;
            countWidget.callback = (val, ...args) => {
                handleUpdate(val);
                if (cb) cb(val, ...args);
            };
            
            setTimeout(() => handleUpdate(countWidget.value), 50);
        };
    }
}


// =================================================================================
// 最终注册
// =================================================================================

app.registerExtension({
    name: "supernova.XYPlot.AllDynamicWidgets",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        setupSamplerSchedulerBuilder(nodeType, nodeData, app);
        
        // 应用修复后的 setupBatchNode
        setupBatchNode(nodeType, nodeData, app);
        
        setupGenericWidgetHider(nodeType, nodeData, app);
    }
});