import { app } from "/scripts/app.js";

// =================================================================================
// 通用辅助函数 (完美兼容 旧版LiteGraph 与 新版Node 2.0)
// =================================================================================

function toggleWidgetVisibility(node, widget, show) {
    if (!widget) return;

    const HIDDEN_TYPE = "hidden";

    // 首次隐藏前，安全地备份原始属性
    if (widget.origType === undefined && widget.type !== HIDDEN_TYPE) {
        widget.origType = widget.type;
        widget.origComputeSize = widget.computeSize;
    }

    if (show) {
        // 恢复显示
        if (widget.origType !== undefined) {
            widget.type = widget.origType;
        }
        widget.computeSize = widget.origComputeSize;
        widget.hidden = false; // V2 前端标签
    } else {
        // 隐藏控件
        widget.type = HIDDEN_TYPE; // 解决旧版重叠绘制问题
        widget.computeSize = () => [0, -4]; // 压缩多余高度
        widget.hidden = true; // V2 前端标签
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

            const node = this;
            // 增加安全链式调用，防止 undefined
            const modeWidget = node.widgets?.find((w) => w && w.name === "mode");
            const samplerWidget = node.widgets?.find((w) => w && w.name === "sampler_name");
            const schedulerWidget = node.widgets?.find((w) => w && w.name === "scheduler_name");
            
            if (!modeWidget || !samplerWidget || !schedulerWidget) return;

            const updateWidgets = () => {
                const modeValue = modeWidget.value;
                const showSampler = (modeValue === "Sampler & Scheduler" || modeValue === "Sampler Only");
                const showScheduler = (modeValue === "Sampler & Scheduler" || modeValue === "Scheduler Only");

                toggleWidgetVisibility(node, samplerWidget, showSampler);
                toggleWidgetVisibility(node, schedulerWidget, showScheduler);

                setTimeout(() => {
                    if (node.computeSize) {
                        node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
                        app.graph.setDirtyCanvas(true, true);
                    }
                }, 10);
            };

            const originalCallback = modeWidget.callback;
            modeWidget.callback = function(...args) {
                updateWidgets();
                if (originalCallback) return originalCallback.apply(this, args);
            };

            setTimeout(() => updateWidgets(), 50);
        };

        // 解决加载已保存的工作流时，状态不刷新的问题
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            if (onConfigure) onConfigure.apply(this, arguments);
            const modeWidget = this.widgets?.find(w => w && w.name === "mode");
            if (modeWidget && modeWidget.callback) {
                modeWidget.callback(modeWidget.value);
            }
        };
    }
}


// =================================================================================
// SECTION 2: 通用 Batch 节点 (包含 UNet, CLIP 等)
// =================================================================================

const BATCH_NODES = [
    "XY_Input_Sampler_Scheduler_Batch",
    "XY_Input_Seeds_Batch",
    "XY_Input_Checkpoint_Batch",
    "XY_Input_VAE_Batch",
    "XY_Input_PromptSR_Batch",
    "XY_Input_UNet_Batch",   
    "XY_Input_CLIP_Batch"    
];

function setupBatchNode(nodeType, nodeData, app) {
    if (BATCH_NODES.includes(nodeData.name)) {
        
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const node = this;
            const countWidget = node.widgets?.find(w => w && w.name === "input_count");
            const targetWidget = node.widgets?.find(w => w && w.name === "target_parameter");

            if (!countWidget) return;

            const refreshVisibility = () => {
                if (!node.widgets) return;

                const count = countWidget.value;
                const target = targetWidget ? (targetWidget.value || "sampler & scheduler") : ""; 

                for (const w of node.widgets) {
                    // 终极防线：跳过任何异常或损坏的控件，防止 V2 引擎报错
                    if (!w || !w.name) continue; 

                    const match = w.name.match(/^(sampler|scheduler|seed|ckpt_name|vae_name|search_txt|replace_txt|unet_name|clip_name)_(\d+)$/);
                    
                    if (match) {
                        const type = match[1]; 
                        const index = parseInt(match[2], 10); 

                        let shouldShow = true;

                        if (index > count) {
                            shouldShow = false;
                        }

                        if (shouldShow && target) {
                            if (type === "sampler" && !target.includes("sampler")) shouldShow = false;
                            if (type === "scheduler" && !target.includes("scheduler")) shouldShow = false;
                        }

                        toggleWidgetVisibility(node, w, shouldShow);
                    }
                }

                setTimeout(() => {
                    if (node.computeSize) {
                        node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
                        app.graph.setDirtyCanvas(true, true);
                    }
                }, 10);
            };

            const originalCountCallback = countWidget.callback;
            countWidget.callback = function(...args) {
                refreshVisibility();
                if (originalCountCallback) return originalCountCallback.apply(this, args);
            };

            if (targetWidget) {
                const originalTargetCallback = targetWidget.callback;
                targetWidget.callback = function(...args) {
                    refreshVisibility();
                    if (originalTargetCallback) return originalTargetCallback.apply(this, args);
                };
            }

            setTimeout(() => refreshVisibility(), 50);
        };

        // 解决加载已保存的工作流时，状态不刷新的问题
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            if (onConfigure) onConfigure.apply(this, arguments);
            const countWidget = this.widgets?.find(w => w && w.name === "input_count");
            if (countWidget && countWidget.callback) {
                countWidget.callback(countWidget.value);
            }
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
        setupBatchNode(nodeType, nodeData, app);
    }
});