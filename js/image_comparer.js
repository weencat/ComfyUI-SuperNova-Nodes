import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ============================================================
// 1. 通用工具函数 (Helpers)
// ============================================================

const soundUrl = "../audio/sound.mp3";
const notificationSound = new Audio(soundUrl);

function playSound() {
    try {
        notificationSound.currentTime = 0;
        notificationSound.volume = 0.5;
        notificationSound.play().catch(() => {});
    } catch (e) {
        console.error("[Supernova] Audio error:", e);
    }
}

function getImageUrl(data) {
    if (!data) return null;
    return api.apiURL(`/view?filename=${encodeURIComponent(data.filename)}&type=${data.type}&subfolder=${data.subfolder}${app.getPreviewFormatParam()}${app.getRandParam()}`);
}

// 计算组件占用的顶部高度
function getWidgetHeight(node) {
    let height = 30; 
    if (node.widgets) {
        for (const w of node.widgets) {
            if (w.type === "HIDDEN") continue;
            const h = w.computeSize ? w.computeSize(node.size[0])[1] : 20;
            height += h + 10; 
        }
    }
    return height;
}

// --- [新增] 自定义重命名弹窗 (参考 switcher.js) ---
function showRenameDialog(title, defaultValue, onOk) {
    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
        backgroundColor: "rgba(0,0,0,0.5)", zIndex: "9999",
        display: "flex", justifyContent: "center", alignItems: "center"
    });

    const box = document.createElement("div");
    Object.assign(box.style, {
        backgroundColor: "#353535", color: "#fff", padding: "20px",
        borderRadius: "8px", boxShadow: "0 4px 15px rgba(0,0,0,0.5)",
        minWidth: "300px", fontFamily: "Arial, sans-serif", border: "1px solid #555"
    });

    const titleEl = document.createElement("h3");
    titleEl.textContent = title;
    titleEl.style.marginTop = "0";

    const input = document.createElement("input");
    input.type = "text";
    input.value = defaultValue;
    Object.assign(input.style, {
        width: "100%", padding: "8px", margin: "10px 0",
        borderRadius: "4px", border: "1px solid #666",
        backgroundColor: "#222", color: "#fff", boxSizing: "border-box"
    });

    const btnContainer = document.createElement("div");
    btnContainer.style.display = "flex";
    btnContainer.style.justifyContent = "flex-end";
    btnContainer.style.gap = "10px";

    const btnStyle = { padding: "6px 15px", borderRadius: "4px", border: "none", cursor: "pointer", fontWeight: "bold" };

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    Object.assign(cancelBtn.style, btnStyle, { backgroundColor: "#555", color: "#fff" });
    
    const okBtn = document.createElement("button");
    okBtn.textContent = "Save";
    Object.assign(okBtn.style, btnStyle, { backgroundColor: "#2366b8", color: "#fff" });

    const close = () => document.body.removeChild(overlay);
    
    cancelBtn.onclick = close;
    const submit = () => { onOk(input.value); close(); };
    okBtn.onclick = submit;
    
    input.onkeydown = (e) => {
        if (e.key === "Enter") submit();
        if (e.key === "Escape") close();
    };
    overlay.onclick = (e) => { if(e.target === overlay) close(); };

    btnContainer.appendChild(cancelBtn);
    btnContainer.appendChild(okBtn);
    box.appendChild(titleEl);
    box.appendChild(input);
    box.appendChild(btnContainer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    setTimeout(() => input.focus(), 50);
}

// ============================================================
// 2. Preview & Pause 逻辑
// ============================================================

function sendControl(node, action) {
    api.fetchApi("/supernova/preview_control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: node.id, action: action })
    });
}

function loadPreviewImageToNode(node, imgData) {
    // ... (保持原有的加载图片逻辑不变) ...
    const params = new URLSearchParams({
        filename: imgData.filename,
        type: imgData.type,
        subfolder: imgData.subfolder || ""
    });
    const url = api.apiURL(`/view?${params.toString()}&t=${Date.now()}`);
    const img = new Image();
    img.src = url;
    img.onload = () => {
        node.imgs = [img];
        node.setDirtyCanvas(true, true);
    };
    node.onDrawBackground = function(ctx) {
        if (!this.imgs || this.imgs.length === 0) return;
        const image = this.imgs[0];
        if (!image.complete || image.naturalWidth === 0) return;
        const topPadding = getWidgetHeight(this); 
        const w = this.size[0];
        const h = this.size[1] - topPadding; 
        if (h <= 0) return;
        const imgW = image.naturalWidth;
        const imgH = image.naturalHeight;
        const scale = Math.min(w / imgW, h / imgH);
        const drawW = imgW * scale;
        const drawH = imgH * scale;
        const drawX = (w - drawW) / 2;
        const drawY = topPadding + (h - drawH) / 2;
        ctx.save();
        ctx.drawImage(image, drawX, drawY, drawW, drawH);
        ctx.restore();
    };
}

// ============================================================
// 3. Compare & Select 逻辑
// ============================================================

async function sendSelection(node, value) {
    try {
        await api.fetchApi("/supernova/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: node.id, selection: value })
        });
    } catch (error) { console.error(error); }
}

function setupImageCompareSelect(node) {
    node.imgs = { 1: null, 2: null }; 
    node.splitX = 0.5;
    node.dragging = false;
    const BOTTOM_PADDING = 15; 

    node.setSize([512, 600]);

    // ... (保持原有的 onResize, onMouseDown, onDrawForeground 逻辑不变) ...
    const origOnResize = node.onResize;
    node.onResize = function(size) {
        const minWidth = 300; 
        const widgetsHeight = getWidgetHeight(this);
        const minHeight = widgetsHeight + 150 + BOTTOM_PADDING;
        if (size[0] < minWidth) size[0] = minWidth;
        if (size[1] < minHeight) size[1] = minHeight;
        if (origOnResize) origOnResize.apply(this, arguments);
        this.setDirtyCanvas(true, true);
    };
    node.onMouseDown = function (event, pos, canvas) {
        const topMargin = getWidgetHeight(this);
        const bottomBoundary = this.size[1] - BOTTOM_PADDING; 
        if (pos[1] >= topMargin && pos[1] <= bottomBoundary) {
            if (event.ctrlKey || event.metaKey) return false;
            this.dragging = true;
            this.updateSplitPos(pos);
            return true;
        }
        return false;
    };
    node.onMouseMove = function (event, pos, canvas) { if (this.dragging) this.updateSplitPos(pos); };
    node.onMouseUp = function () { this.dragging = false; };
    node.updateSplitPos = function (pos) {
        this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
        this.setDirtyCanvas(true, false);
    };
    node.onDrawForeground = function (ctx) {
        if (this.flags.collapsed) return;
        const activeIds = [1, 2].filter(id => !!this.imgs[id]);
        const count = activeIds.length;
        if (count === 0) return; 
        const nodeW = this.size[0];
        const topMargin = getWidgetHeight(this);
        const drawH = this.size[1] - topMargin - BOTTOM_PADDING;
        if (drawH <= 0) return;
        ctx.save();
        ctx.beginPath(); ctx.rect(0, topMargin, nodeW, drawH); ctx.clip(); 
        ctx.fillStyle = "#00000000"; ctx.fillRect(0, topMargin, nodeW, drawH);
        const drawComp = (img, clipX, clipY, clipW, clipH) => {
            if (!img || clipW <= 0 || clipH <= 0) return;
            ctx.save(); ctx.beginPath(); ctx.rect(clipX, clipY, clipW, clipH); ctx.clip();
            const aspect = img.naturalWidth / img.naturalHeight;
            const areaAspect = nodeW / drawH; 
            let renderW, renderH;
            if (aspect > areaAspect) { renderW = nodeW; renderH = nodeW / aspect; } 
            else { renderH = drawH; renderW = drawH * aspect; }
            const tx = (nodeW - renderW) / 2;
            const ty = topMargin + (drawH - renderH) / 2;
            ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, tx, ty, renderW, renderH);
            ctx.restore();
        };
        const sx = this.splitX * nodeW;
        if (count === 1) {
            drawComp(this.imgs[activeIds[0]], 0, topMargin, nodeW, drawH);
        } else if (count === 2) {
            if (this.imgs[2]) drawComp(this.imgs[2], 0, topMargin, nodeW, drawH);
            if (this.imgs[1]) drawComp(this.imgs[1], 0, topMargin, sx, drawH);
            ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(sx, topMargin); ctx.lineTo(sx, topMargin + drawH); ctx.stroke();
            ctx.fillStyle = "rgba(255,255,255,1)"; ctx.beginPath(); ctx.arc(sx, topMargin + drawH/2, 5, 0, Math.PI*2); ctx.fill();
        }
        ctx.restore(); 
        ctx.font = "bold 14px Arial";
        const drawLabel = (id, x, y) => {
            ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillRect(x, y, 24, 24);
            ctx.fillStyle = "#FFF"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.fillText(id, x + 12, y + 12);
        };
        if (this.imgs[1]) drawLabel("1", 10, topMargin + 10);
        if (this.imgs[2]) drawLabel("2", nodeW - 34, topMargin + 10);
    };
}

// ============================================================
// 4. Multi Image Comparer 逻辑 (Prototype Override)
// ============================================================
// ... (MultiImageComparer 逻辑保持不变，为节省篇幅省略，请确保原代码存在) ...
function registerMultiImageComparer(nodeType, nodeData) {
    // ... 保持原有代码 ...
    // 这里为了不中断代码块，假设已包含原 MultiImageComparer 的所有逻辑
    // 如需我完整粘贴这部分请告知
}

// ============================================================
// 5. 注册扩展
// ============================================================

app.registerExtension({
    name: "Supernova.Nodes",

    setup() {
        // ... (事件监听保持不变) ...
        api.addEventListener("supernova_preview_data", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node_id);
            if (node) {
                playSound();
                if (detail.images && detail.images.length > 0) loadPreviewImageToNode(node, detail.images[0]);
            }
        });
        api.addEventListener("supernova_preview_update", ({ detail }) => {
            const { node_id, images } = detail;
            const node = app.graph.getNodeById(node_id);
            if (node && node.comfyClass === "ImageCompareAndSelect") {
                let firstLoad = false;
                const loadImg = (key, imgList) => {
                    if (imgList && imgList.length > 0) {
                        const url = getImageUrl(imgList[0]);
                        const img = new Image();
                        img.onload = () => {
                            node.imgs[key] = img;
                            if (!firstLoad) {
                                firstLoad = true;
                                const aspect = img.naturalHeight / img.naturalWidth;
                                const targetW = node.size[0];
                                const widgetsH = getWidgetHeight(node);
                                const imgH = Math.min(targetW * aspect, 800);
                                const totalH = imgH + widgetsH + 15; 
                                node.setSize([targetW, totalH]); 
                            }
                            node.setDirtyCanvas(true, true);
                        };
                        img.src = url;
                    } else {
                        node.imgs[key] = null;
                    }
                };
                loadImg(1, images["1"]);
                loadImg(2, images["2"]);
            }
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "MultiImageComparer") {
            // registerMultiImageComparer(nodeType, nodeData); // 确保你的文件里有这个函数定义
             const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) onNodeCreated.apply(this, arguments);
                this.baseWidth = 512;
                this.boxTitleHeight = 30;
                this.boxSlotsHeight = 90;
                this.baseFooterHeight = 30;
                this.setSize([512, 620]);
                this.imgs = { 1: null, 2: null, 3: null, 4: null };
                this.imgDims = { 1: "", 2: "", 3: "", 4: "" };
                this.splitX = 0.5;
                this.splitY = 0.5;
                this.dragging = false;
            };
            nodeType.prototype.onResize = function (size) {
                const scale = size[0] / this.baseWidth;
                const currentFooterHeight = this.baseFooterHeight * scale;
                const minH = this.boxTitleHeight + this.boxSlotsHeight + currentFooterHeight + 100;
                if (size[0] < 260) size[0] = 260;
                if (size[1] < minH) size[1] = minH;
                return size;
            };
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                if (onExecuted) onExecuted.apply(this, arguments);
                const loadImg = (key, imgList) => {
                    if (imgList && imgList.length > 0) {
                        const url = getImageUrl(imgList[0]);
                        const img = new Image();
                        img.onload = () => {
                            this.imgDims[key] = `${img.naturalWidth}x${img.naturalHeight}`;
                            this.setDirtyCanvas(true, true);
                        };
                        img.src = url;
                        this.imgs[key] = img;
                    } else {
                        this.imgs[key] = null;
                        this.imgDims[key] = "";
                    }
                };
                loadImg(1, message.images_1); loadImg(2, message.images_2);
                loadImg(3, message.images_3); loadImg(4, message.images_4);
            };
            nodeType.prototype.onMouseDown = function (event, pos, canvas) {
                const scale = this.size[0] / this.baseWidth;
                const footerH = this.baseFooterHeight * scale;
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3Bottom = this.size[1] - footerH;
                if (pos[1] >= b3Y && pos[1] <= b3Bottom) {
                    if (event.ctrlKey || event.metaKey) return false;
                    this.dragging = true;
                    this.updateSplitPos(pos);
                    return true;
                }
                return false;
            };
            nodeType.prototype.onMouseMove = function (event, pos, canvas) { if (this.dragging) this.updateSplitPos(pos); };
            nodeType.prototype.onMouseUp = function () { this.dragging = false; };
            nodeType.prototype.updateSplitPos = function (pos) {
                const scale = this.size[0] / this.baseWidth;
                const footerH = this.baseFooterHeight * scale;
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3H = this.size[1] - b3Y - footerH;
                this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
                this.splitY = Math.max(0, Math.min(1, (pos[1] - b3Y) / b3H));
                this.setDirtyCanvas(true, false);
            };
            nodeType.prototype.onDrawForeground = function (ctx) {
               // ... 保持原有绘制逻辑 ... 
               if (this.flags.collapsed) return;

                const nodeW = this.size[0];
                const nodeH = this.size[1];
                const scaleFactor = nodeW / this.baseWidth;
                const currentFooterHeight = this.baseFooterHeight * scaleFactor;
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3W = nodeW;
                const b3H = nodeH - b3Y - currentFooterHeight;

                const activeIds = [1, 2, 3, 4].filter(id => !!this.imgs[id]);
                const count = activeIds.length;
                if (count === 0) return;

                ctx.save();
                const drawComp = (img, clipX, clipY, clipW, clipH) => {
                    if (!img || clipW <= 0 || clipH <= 0) return;
                    ctx.save(); ctx.beginPath(); ctx.rect(clipX, clipY, clipW, clipH); ctx.clip();
                    const aspect = img.naturalWidth / img.naturalHeight;
                    const areaAspect = b3W / b3H;
                    let fw, fh;
                    if (aspect > areaAspect) { fw = b3W; fh = b3W / aspect; } else { fh = b3H; fw = b3H * aspect; }
                    const tx = (b3W - fw) / 2; const ty = b3Y + (b3H - fh) / 2;
                    ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, tx, ty, fw, fh);
                    ctx.restore();
                };

                const sx = this.splitX * b3W; const sy = b3Y + (this.splitY * b3H);
                if (count === 1) { drawComp(this.imgs[activeIds[0]], 0, b3Y, b3W, b3H); } 
                else if (count === 2) { drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, b3H); drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, b3H); ctx.strokeStyle = "rgba(255,255,255,0.4)"; ctx.beginPath(); ctx.moveTo(sx, b3Y); ctx.lineTo(sx, b3Y + b3H); ctx.stroke(); } 
                else if (count === 3) { drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y); drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y); drawComp(this.imgs[activeIds[2]], 0, sy, b3W, b3H - (sy - b3Y)); ctx.strokeStyle = "rgba(255,255,255,0.4)"; ctx.beginPath(); ctx.moveTo(sx, b3Y); ctx.lineTo(sx, sy); ctx.moveTo(0, sy); ctx.lineTo(b3W, sy); ctx.stroke(); } 
                else if (count === 4) { drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y); drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y); drawComp(this.imgs[activeIds[2]], 0, sy, sx, b3H - (sy - b3Y)); drawComp(this.imgs[activeIds[3]], sx, sy, b3W - sx, b3H - (sy - b3Y)); ctx.strokeStyle = "rgba(255,255,255,0.4)"; ctx.beginPath(); ctx.moveTo(sx, b3Y); ctx.lineTo(sx, b3Y + b3H); ctx.moveTo(0, sy); ctx.lineTo(b3W, sy); ctx.stroke(); }

                const labelSize = 18 * Math.sqrt(scaleFactor);
                ctx.font = `bold ${Math.max(10, 12 * scaleFactor)}px Arial`;
                const drawLabel = (id, x, y) => { ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillRect(x, y, labelSize, labelSize); ctx.fillStyle = "#FFF"; ctx.textAlign = "center"; ctx.fillText(id, x + labelSize / 2, y + labelSize / 1.4); };
                if (count >= 1) drawLabel(activeIds[0], 5, b3Y + 5);
                if (count >= 2) drawLabel(activeIds[1], b3W - 5 - labelSize, b3Y + 5);
                if (count >= 3) drawLabel(activeIds[2], 5, b3H + b3Y - 5 - labelSize);
                if (count >= 4) drawLabel(activeIds[3], b3W - 5 - labelSize, b3H + b3Y - 5 - labelSize);

                const footerY = nodeH - currentFooterHeight;
                ctx.fillStyle = "#00000000"; ctx.fillRect(0, footerY, nodeW, currentFooterHeight);
                const fontSize = Math.max(5, 11 * scaleFactor);
                ctx.font = `${fontSize}px Consolas, Monaco, monospace`;
                ctx.fillStyle = LiteGraph.NODE_TEXT_COLOR || "#EEE";
                ctx.textAlign = "center"; ctx.textBaseline = "middle";
                let info = activeIds.map(id => `${id}:${this.imgDims[id]}`).join("  |  ");
                ctx.fillText(info, nodeW / 2, footerY + (currentFooterHeight / 2));
                ctx.restore();
            };
        }
    },

    async nodeCreated(node) {
        // --- 1. Preview & Pause ---
        if (node.comfyClass === "PreviewAndPause") {
            node.setSize([300, 400]); 
            node.addWidget("button", "✅ CONTINUE", null, () => sendControl(node, "continue"));
            node.addWidget("button", "⛔ STOP", null, () => sendControl(node, "stop"));
            
            const origOnResize = node.onResize;
            node.onResize = function(size) {
                const minWidth = 256; 
                const widgetsHeight = getWidgetHeight(this);
                const minHeight = widgetsHeight + 256;
                if (size[0] < minWidth) size[0] = minWidth;
                if (size[1] < minHeight) size[1] = minHeight;
                if (origOnResize) origOnResize.apply(this, arguments);
                this.setDirtyCanvas(true, true);
            };
        }

        // --- 2. Compare & Select (修改：添加改名功能) ---
        if (node.comfyClass === "ImageCompareAndSelect") {
            setupImageCompareSelect(node);

            // 1. 初始化 labels 存储
            if (!node.properties) node.properties = {};
            if (!node.properties.labels) node.properties.labels = {};

            // 2. 暂存原有 Widgets
            const existingWidgets = node.widgets || [];
            node.widgets = [];

            // 3. 定义按钮配置
            const buttonsDef = [
                { label: "▶️ Image 1", value: "1" },
                { label: "▶️ Image 2", value: "2" },
                { label: "⛔ STOP", value: "stop" }
            ];

            // 4. 添加按钮并应用自定义名称
            buttonsDef.forEach((b) => {
                const savedLabel = node.properties.labels[b.value];
                const displayLabel = savedLabel !== undefined ? savedLabel : b.label;

                const w = node.addWidget("button", displayLabel, null, () => sendSelection(node, b.value));
                
                // 关键：标记属性以便右键识别
                w.supernovaValue = b.value;
                w.supernovaDefaultLabel = b.label;
            });

            // 5. 还原其他组件
            for (const w of existingWidgets) {
                node.widgets.push(w);
            }

            // 6. 添加右键菜单 (参考 switcher.js)
            const origGetExtraMenuOptions = node.getExtraMenuOptions;
            node.getExtraMenuOptions = function(_, options) {
                if (origGetExtraMenuOptions) origGetExtraMenuOptions.apply(this, arguments);
                
                options.push(null); // 分隔线
                options.push({ content: "🖊️ Rename Buttons...", disabled: true });

                if (this.widgets) {
                    this.widgets.forEach((w) => {
                        if (w.supernovaValue) {
                            const currentLabel = w.label || w.name;
                            options.push({
                                content: `   📝 Rename "${currentLabel}"`,
                                callback: () => {
                                    showRenameDialog(
                                        `Rename "${currentLabel}"`, 
                                        currentLabel, 
                                        (newName) => {
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

            // 7. 状态恢复 (onConfigure)
            const origConfigure = node.onConfigure;
            node.onConfigure = function() {
                if (origConfigure) origConfigure.apply(this, arguments);
                if (this.properties && this.properties.labels && this.widgets) {
                    this.widgets.forEach(w => {
                        if (w.supernovaValue && this.properties.labels[w.supernovaValue]) {
                            w.label = this.properties.labels[w.supernovaValue];
                        }
                    });
                }
            };
        }
    }
});