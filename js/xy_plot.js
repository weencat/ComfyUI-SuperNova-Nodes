import { app } from "/scripts/app.js";

// =================================================================================
// SECTION 1: "XY_Input_Sampler_Scheduler_Builder" 节点的动态UI
// 用法: 根据节点上 "mode" 下拉菜单的选择，动态地重新排列控件，以避免出现空白占位。
// 原理: 当 "mode" 改变时，它不是隐藏控件，而是重新构建节点的控件数组(this.widgets)，
//       只包含当前模式下应该显示的控件，然后刷新节点布局。
// =================================================================================

function setupSamplerSchedulerBuilder(nodeType, nodeData, app) {
    // 确保这个逻辑只应用在我们自定义的 "XY_Input_Sampler_Scheduler_Builder" 节点上
    if (nodeData.name === "XY_Input_Sampler_Scheduler_Builder") {
        const onNodeCreated = nodeType.prototype.onNodeCreated; // 保存原始的 onNodeCreated 方法

        // 扩展 onNodeCreated 方法，它在节点被创建时执行
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) {
                onNodeCreated.apply(this, arguments);
            }

            // 找到我们需要操作的三个控件
            const modeWidget = this.widgets.find((w) => w.name === "mode");
            const samplerWidget = this.widgets.find((w) => w.name === "sampler_name");
            const schedulerWidget = this.widgets.find((w) => w.name === "scheduler_name");

            if (!modeWidget || !samplerWidget || !schedulerWidget) return; // 如果找不到任何一个，则退出

            const originalWidgets = this.widgets.slice(); // 保存一份节点最初始的、完整的控件列表

            // 定义核心的更新函数
            const updateWidgetsAndLayout = (modeValue) => {
                let newWidgets = []; // 创建一个新的空数组来存放将要显示的控件

                // 首先，将所有静态的、位置不变的控件添加到新数组中
                for (const w of originalWidgets) {
                    if (w.name !== "sampler_name" && w.name !== "scheduler_name") {
                        newWidgets.push(w);
                    }
                }

                // 然后，根据 mode 的值，决定将哪个（或哪些）动态控件按顺序添加到新数组中
                if (modeValue === "Sampler & Scheduler") {
                    newWidgets.push(samplerWidget, schedulerWidget);
                } else if (modeValue === "Sampler Only") {
                    newWidgets.push(samplerWidget);
                } else if (modeValue === "Scheduler Only") {
                    newWidgets.push(schedulerWidget);
                }

                // 最关键的一步：用我们构建好的新数组，直接替换掉节点当前的控件数组
                this.widgets = newWidgets;

                // 最后，强制节点根据新的控件布局重新计算尺寸并重绘
                this.computeSize();
                this.setDirtyCanvas(true, true);
            };

            // 拦截 mode 控件的回调函数，当它的值改变时，执行我们的更新逻辑
            const originalCallback = modeWidget.callback;
            modeWidget.callback = (value) => {
                if (originalCallback) originalCallback.apply(this, arguments);
                updateWidgetsAndLayout(value);
            };

            // 在节点首次加载时，立即运行一次更新，以保证初始状态正确
            setTimeout(() => updateWidgetsAndLayout(modeWidget.value), 0);
        };
    }
}


// =================================================================================
// SECTION 2: “选多少，显示多少”的动态显隐逻辑
// 用法: 为那些带有 "count" (数量) 输入框的节点提供支持。当你改变数量时，
//       它会自动显示或隐藏对应数量的输入控件组（例如 LoRA 名称、权重等）。
// 原理: 通过修改控件的 `type` 为一个不可见的类型并把尺寸设为0，来实现可靠的隐藏。
//       当 "count" 控件的值改变时，它会遍历所有受控的控件，并根据新的数量
//       决定哪些该显示，哪些该隐藏，然后刷新节点。
// (此逻辑改编自 "Efficiency Nodes" 的 widgethider.js)
// =================================================================================

let origProps = {}; // 用于存储控件原始属性的对象，以便恢复
const HIDDEN_TAG = "tschide"; // 一个自定义的、不会被渲染的控件类型名

// 辅助函数：根据名称在节点内查找控件
function findWidgetByName(node, name) {
    return node.widgets ? node.widgets.find((w) => w.name === name) : null;
}

// 核心函数：切换单个控件的显示或隐藏状态
function toggleWidget(node, widget, show = false, suffix = "") {
    if (!widget) return; // 如果找不到控件，则退出

    // 如果是第一次操作这个控件，就保存它的原始类型和尺寸计算函数
    if (!origProps[widget.name]) {
        origProps[widget.name] = { origType: widget.type, origComputeSize: widget.computeSize };
    }

    // 根据 `show` 参数决定是恢复原始类型（显示）还是设置为隐藏类型（隐藏）
    widget.type = show ? origProps[widget.name].origType : HIDDEN_TAG + suffix;
    // 隐藏时，让它的尺寸计算函数返回一个负值高度，使其不占空间
    widget.computeSize = show ? origProps[widget.name].origComputeSize : () => [0, -4];

    // 重新计算并设置节点的高度，以适应控件的变化
    const newHeight = node.computeSize()[1];
    node.setSize([node.size[0], newHeight]);
}

// 批量处理函数：根据数量值，显隐一组控件
function handleVisibilityByCount(node, countValue, baseNames) {
    if (!baseNames || baseNames.length === 0) return;
    
    const maxCount = 50; // 预设的最大控件数量

    // 循环检查从 1 到 50 的所有控件
    for (let i = 1; i <= maxCount; i++) {
        // 遍历所有需要控制的控件基础名 (如 'lora_name', 'lora_wt')
        for(const baseName of baseNames) {
            const widget = findWidgetByName(node, `${baseName}_${i}`); // 组合成完整的控件名，如 'lora_name_1'
            if(widget) {
                // 如果当前循环次数 i 小于等于指定的数量 countValue，则显示；否则隐藏。
                toggleWidget(node, widget, i <= countValue);
            }
        }
    }
}

// 节点与逻辑的映射表：定义哪个节点需要“数量选择”功能
const widgetHiderHandlers = {
    // 示例1: "LoRA Stacker" 节点
    "LoRA Stacker": (node) => {
        // 找到控制数量的控件，名为 "lora_count"
        const countWidget = findWidgetByName(node, "lora_count");
        if (countWidget) {
            // 当 "lora_count" 的值改变时，执行我们的批量处理函数
            const originalCallback = countWidget.callback;
            countWidget.callback = (value) => {
                if (originalCallback) originalCallback.apply(this, arguments);
                // 控制这些基础名的控件的显示/隐藏
                handleVisibilityByCount(node, value, ["lora_name", "lora_wt", "model_str", "clip_str"]);
            };
            // 首次加载时也运行一次
            handleVisibilityByCount(node, countWidget.value, ["lora_name", "lora_wt", "model_str", "clip_str"]);
        }
    },
    // 示例2: "XY Input: LoRA" 节点
    "XY Input: LoRA": (node) => {
        const countWidget = findWidgetByName(node, "lora_count");
        if (countWidget) {
            const originalCallback = countWidget.callback;
            countWidget.callback = (value) => {
                if (originalCallback) originalCallback.apply(this, arguments);
                handleVisibilityByCount(node, value, ["lora_name", "model_str", "clip_str"]);
            };
            handleVisibilityByCount(node, countWidget.value, ["lora_name", "model_str", "clip_str"]);
        }
    },
    // 你可以继续在这里添加更多节点的配置...
};

// 设置函数：将“数量选择”逻辑应用到所有在映射表中定义的节点上
function setupWidgetHider(nodeType, nodeData, app) {
    if (widgetHiderHandlers[nodeData.name]) {
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) {
                onNodeCreated.apply(this, arguments);
            }
            // 当节点被创建时，调用在映射表中为它指定的处理函数
            widgetHiderHandlers[this.comfyClass](this);
        };
    }
}


// =================================================================================
// 最终注册
// 用这一个扩展来统一加载我们所有的动态UI增强功能。
// =================================================================================

app.registerExtension({
    name: "supernova.XYPlot.AllDynamicWidgets", // 为整个扩展起一个统一的名字

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // 1. 应用我们为 "XY_Input_Sampler_Scheduler_Builder" 节点编写的动态布局逻辑
        setupSamplerSchedulerBuilder(nodeType, nodeData, app);

        // 2. 应用我们为 "Efficiency Nodes" 风格的节点编写的“选多少、显示多少”逻辑
        setupWidgetHider(nodeType, nodeData, app);
    }
});