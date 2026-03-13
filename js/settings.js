import { app } from "../../scripts/app.js";

let t = {
    "auto": "🚀 Auto",
    "manual": "🎲 Random",
    "last": "♻️ Last", // 缩短前缀
    "no_history": "No history found"
};

// 辅助函数：格式化超长种子
const formatSeed = (seed) => {
    if (!seed) return "";
    const str = String(seed);
    if (str.length <= 12) return str; // 12位以内直接显示
    // 超长则显示为: 1125...2624
    return str.slice(0, 4) + "..." + str.slice(-4);
};

app.registerExtension({
    name: "Supernova.SeedHub",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "SeedHub") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onNodeCreated?.apply(this, arguments);

                const self = this;
                const seedWidget = this.widgets.find(w => w.name === "seed");
                
                // 移除自带的生成后控制
                const ctrlWidget = this.widgets.find(w => w.name === "control_after_generate");
                if (ctrlWidget) this.widgets.splice(this.widgets.indexOf(ctrlWidget), 1);

                // --- 按钮排版优化 ---
                // 按钮 1: 自动 (-1)
                this.addWidget("button", t.auto, "", () => {
                    seedWidget.value = -1;
                });

                // 按钮 2: 随机数
                this.addWidget("button", t.manual, "", () => {
                    seedWidget.value = Math.floor(Math.random() * 1125899906842624);
                });

                this.lastSeed = null; 

                // 按钮 3: 上次种子 (添加缩略逻辑)
                const lastBtn = this.addWidget("button", t.last, "", () => {
                    let targetSeed = self.lastSeed;
                    if (!targetSeed) {
                        const history = app.nodeOutputs?.[self.id];
                        if (history && history.seed) {
                            targetSeed = Array.isArray(history.seed) ? history.seed[0] : history.seed;
                        }
                    }

                    if (targetSeed) {
                        seedWidget.value = targetSeed;
                    } else {
                        alert(t.no_history);
                    }
                });

                // 监听执行完毕事件
                const executionHandler = (e) => {
                    if (e.detail.node === String(self.id)) {
                        const output = e.detail.output;
                        if (output && output.seed) {
                            const realSeed = Array.isArray(output.seed) ? output.seed[0] : output.seed;
                            self.lastSeed = realSeed;
                            
                            // 润色文字：使用 formatSeed 缩略显示
                            lastBtn.name = `${t.last}: ${formatSeed(realSeed)}`;
                            
                            // 自动根据文字宽度微调节点大小
                            const size = self.computeSize();
                            size[0] = Math.max(size[0], 220); // 设置一个最小宽度防止太窄
                            self.setSize(size);
                        }
                    }
                };

                app.api.addEventListener("executed", executionHandler);

                this.onRemoved = function() {
                    app.api.removeEventListener("executed", executionHandler);
                };

                // 设置初始大小
                this.setSize([220, 160]);
            };
        }
    }
});