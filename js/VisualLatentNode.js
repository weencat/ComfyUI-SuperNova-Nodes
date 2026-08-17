import { app } from "../../scripts/app.js";

// ==========================================
// 预设数据字典
// ==========================================
const PRESET_CATEGORIES = {
    "SDXL / Flux": [
        { name: "1024×1024 (1:1)", w: 1024, h: 1024 },
        { name: "1152×896 (9:7)", w: 1152, h: 896 },
        { name: "896×1152 (7:9)", w: 896, h: 1152 },
        { name: "1216×832 (19:13)", w: 1216, h: 832 },
        { name: "832×1216 (13:19)", w: 832, h: 1216 },
        { name: "1344×768 (7:4)", w: 1344, h: 768 },
        { name: "768×1344 (4:7)", w: 768, h: 1344 },
        { name: "1536×640 (12:5)", w: 1536, h: 640 },
        { name: "640×1536 (5:12)", w: 640, h: 1536 }
    ],
    "SD 1.5": [
        { name: "512×512 (1:1)", w: 512, h: 512 },
        { name: "768×512 (3:2)", w: 768, h: 512 },
        { name: "512×768 (2:3)", w: 512, h: 768 },
        { name: "912×512 (16:9)", w: 912, h: 512 },
        { name: "512×912 (9:16)", w: 512, h: 912 }
    ],
    "Cinematic": [
        { name: "1920×1080 (1080p)", w: 1920, h: 1080 },
        { name: "2560×1440 (2K)", w: 2560, h: 1440 },
        { name: "3840×2160 (4K)", w: 3840, h: 2160 }
    ]
};

// 本地存储 Custom 预设的 Key
const CUSTOM_PRESETS_KEY = "VisualLatent_CustomPresets";

/**
 * 绘图逻辑
 */
function drawGraphics(canvas, wVal, hVal, activeHandle = null) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const maxRes = 4096;

    ctx.fillStyle = "#121212";
    ctx.beginPath();
    ctx.roundRect(0, 0, w, h, 8);
    ctx.fill();

    ctx.fillStyle = "rgb(255, 255, 255)"; 
    const dotStep = 256; 
    for (let x = 0; x <= maxRes; x += dotStep) {
        for (let y = 0; y <= maxRes; y += dotStep) {
            const px = (x / maxRes) * w;
            const py = h - (y / maxRes) * h; 
            ctx.beginPath();
            ctx.arc(px, py, 1, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "rgba(0, 234, 255, 0.63)";
    ctx.fillStyle = "rgb(255, 255, 255)"; 
    ctx.font = "13px monospace";               
    
    [512, 1024, 1536, 2048, 2560, 3072, 3584, 4096].forEach(size => {
        const s = (size / maxRes) * w;
        const sy = h - s;
        ctx.strokeRect(0, sy, s, s);
        ctx.fillText(size, s - 30, sy + 12); 
    });
    ctx.setLineDash([]);

    const rectW = (wVal / maxRes) * w;
    const rectH = (hVal / maxRes) * h;
    const rectY = h - rectH;

    ctx.fillStyle = "rgba(0, 160, 255, 0.2)";
    ctx.fillRect(0, rectY, rectW, rectH);
    ctx.strokeStyle = "#00a0ff";
    ctx.lineWidth = 2;
    ctx.strokeRect(0, rectY, rectW, rectH);

    const drawHandle = (x, y, isActive, isRound = true) => {
        ctx.fillStyle = isActive ? "#fff" : "#00a0ff";
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (isRound) ctx.arc(x, y, 5, 0, Math.PI * 2);
        else ctx.rect(x - 4, y - 4, 8, 8);
        ctx.fill();
        ctx.stroke();
    };

    drawHandle(rectW, rectY, activeHandle === 'both', true);
    drawHandle(rectW, rectY + rectH / 2, activeHandle === 'width', false);
    drawHandle(rectW / 2, rectY, activeHandle === 'height', false);
}

app.registerExtension({
    name: "Custom.VisualLatentNode.UltimateFix",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "VisualLatentNode") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) onNodeCreated.apply(this, arguments);

                const self = this;
                const wWidget = this.widgets.find(w => w.name === "width");
                const hWidget = this.widgets.find(w => w.name === "height");
                const snapWidget = this.widgets.find(w => w.name === "pixel_alignment");

                if (!wWidget || !hWidget) return;

                // --- 1. 基础 UI 容器 ---
                const container = document.createElement("div");
                container.style.cssText = "width:100%; height:100%; display:flex; flex-direction:column; align-items:center; padding:10px 10px 20px 10px; box-sizing:border-box; font-family:sans-serif;";

                // --- 2. 画布 ---
                const canvasEl = document.createElement("canvas");
                canvasEl.style.cssText = "width:100%; aspect-ratio:1/1; background:#000; border-radius:8px; cursor:crosshair; touch-action:none;";

                // --- 3. 手动输入框 ---
                const inputRow = document.createElement("div");
                inputRow.style.cssText = "margin-top:12px; display:flex; align-items:center; justify-content:center; gap:8px;";

                const createInput = (widget) => {
                    const input = document.createElement("input");
                    input.type = "text";
                    input.value = widget.value;
                    input.style.cssText = "width:60px; background:#222; border:1px solid #444; color:#fff; text-align:center; border-radius:4px; font-weight:bold; outline:none; padding:4px 0;";
                    
                    const finalize = () => {
                        let val = parseInt(input.value) || 64;
                        if (snapWidget && snapWidget.value === true) val = Math.round(val / 8) * 8;
                        val = Math.max(64, Math.min(4096, val));
                        widget.value = val;
                        input.value = val;
                        if (widget.callback) widget.callback(val);
                        syncToUI();
                    };

                    input.addEventListener("blur", finalize);
                    input.addEventListener("keydown", (e) => { if (e.key === "Enter") finalize(); });
                    return input;
                };

                const inputW = createInput(wWidget);
                const inputH = createInput(hWidget);
                const separator = document.createElement("span");
                separator.innerText = "X";
                separator.style.color = "#888";

                inputRow.appendChild(inputW);
                inputRow.appendChild(separator);
                inputRow.appendChild(inputH);

                // --- 4. 功能栏 (Swap + Presets) ---
                const controlsRow = document.createElement("div");
                controlsRow.style.cssText = "width:100%; margin-top:12px; display:flex; flex-direction:column; gap:8px;";

                const btnStyle = "flex:1; background:#333; color:#ddd; border:1px solid #555; border-radius:4px; padding:6px; cursor:pointer; font-size:12px; transition:0.2s;";
                const selectStyle = "width:100%; background:#222; color:#fff; border:1px solid #555; border-radius:4px; padding:6px; font-size:12px; outline:none; cursor:pointer;";

                // 4.1 Swap对调按钮
                const swapBtn = document.createElement("button");
                swapBtn.innerHTML = "⇄ Swap (对调宽高)";
                swapBtn.style.cssText = btnStyle;
                swapBtn.onmouseover = () => swapBtn.style.background = "#444";
                swapBtn.onmouseout = () => swapBtn.style.background = "#333";
                
                swapBtn.onclick = () => {
                    const temp = wWidget.value;
                    wWidget.value = hWidget.value;
                    hWidget.value = temp;
                    if (wWidget.callback) wWidget.callback(wWidget.value);
                    if (hWidget.callback) hWidget.callback(hWidget.value);
                    syncToUI();
                };

                // 4.2 预设系统区域
                const presetRow1 = document.createElement("div");
                presetRow1.style.cssText = "display:flex; gap:6px; width:100%;";
                const presetRow2 = document.createElement("div");
                presetRow2.style.cssText = "display:flex; gap:6px; width:100%;";

                // 类别与保存
                const categorySelect = document.createElement("select");
                categorySelect.style.cssText = selectStyle + "flex:1;";
                const saveBtn = document.createElement("button");
                saveBtn.innerHTML = "💾 保存";
                saveBtn.style.cssText = btnStyle + "flex:0.4;";
                saveBtn.onmouseover = () => saveBtn.style.background = "#444";
                saveBtn.onmouseout = () => saveBtn.style.background = "#333";

                // 具体预设与删除
                const itemSelect = document.createElement("select");
                itemSelect.style.cssText = selectStyle + "flex:1;";
                const deleteBtn = document.createElement("button");
                deleteBtn.innerHTML = "🗑️ 删";
                deleteBtn.style.cssText = btnStyle + "flex:0.4; background:#522; color:#f88; display:none;";
                deleteBtn.title = "删除选中的自定义预设";
                deleteBtn.onmouseover = () => deleteBtn.style.background = "#722";
                deleteBtn.onmouseout = () => deleteBtn.style.background = "#522";

                const loadCategories = () => {
                    categorySelect.innerHTML = "";
                    Object.keys(PRESET_CATEGORIES).forEach(cat => {
                        const opt = document.createElement("option");
                        opt.value = cat;
                        opt.innerText = cat;
                        categorySelect.appendChild(opt);
                    });
                    
                    const optCustom = document.createElement("option");
                    optCustom.value = "Custom";
                    optCustom.innerText = "⭐ 我的预设";
                    categorySelect.appendChild(optCustom);
                };

                const loadItems = (categoryName) => {
                    itemSelect.innerHTML = "<option value=''>-- 选择预设 --</option>";
                    // 切换到“我的预设”时，显示删除按钮
                    deleteBtn.style.display = (categoryName === "Custom") ? "block" : "none";
                    
                    let items = [];
                    if (categoryName === "Custom") {
                        const stored = localStorage.getItem(CUSTOM_PRESETS_KEY);
                        if (stored) items = JSON.parse(stored);
                    } else {
                        items = PRESET_CATEGORIES[categoryName] || [];
                    }

                    items.forEach((item, index) => {
                        const opt = document.createElement("option");
                        // 如果是自定义预设，把 index 写进 value 里，方便精准删除
                        if (categoryName === "Custom") {
                            opt.value = `custom_${index}_${item.w}_${item.h}`;
                        } else {
                            opt.value = `${item.w},${item.h}`;
                        }
                        opt.innerText = item.name;
                        itemSelect.appendChild(opt);
                    });
                };

                loadCategories();
                loadItems(categorySelect.value);

                categorySelect.addEventListener("change", (e) => loadItems(e.target.value));

                itemSelect.addEventListener("change", (e) => {
                    const val = e.target.value;
                    if (!val) return;

                    let nw, nh;
                    if (val.startsWith("custom_")) {
                        const parts = val.split("_");
                        nw = Number(parts[2]);
                        nh = Number(parts[3]);
                    } else {
                        [nw, nh] = val.split(",").map(Number);
                    }

                    wWidget.value = nw;
                    hWidget.value = nh;
                    if (wWidget.callback) wWidget.callback(nw);
                    if (hWidget.callback) hWidget.callback(nh);
                    syncToUI();
                });

                // 保存当前预设
                saveBtn.onclick = () => {
                    const cw = wWidget.value;
                    const ch = hWidget.value;
                    const defaultName = `${cw}x${ch} Custom`;
                    const presetName = prompt(`保存当前尺寸 (${cw} x ${ch})\n请输入预设名称：`, defaultName);
                    
                    if (presetName) {
                        let customPresets = [];
                        const stored = localStorage.getItem(CUSTOM_PRESETS_KEY);
                        if (stored) customPresets = JSON.parse(stored);
                        
                        customPresets.push({ name: presetName, w: cw, h: ch });
                        localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(customPresets));
                        
                        categorySelect.value = "Custom";
                        loadItems("Custom");
                        // 自动选中刚刚新建的预设
                        itemSelect.selectedIndex = itemSelect.options.length - 1;
                    }
                };

                // 【新增】删除当前预设
                deleteBtn.onclick = () => {
                    if (categorySelect.value !== "Custom") return;
                    
                    const val = itemSelect.value;
                    if (!val || !val.startsWith("custom_")) {
                        alert("请先选择一个自定义预设后再删除！");
                        return;
                    }

                    const parts = val.split("_");
                    const index = Number(parts[1]); // 获取选中的是第几个
                    const selectedName = itemSelect.options[itemSelect.selectedIndex].text;

                    if (confirm(`确定要删除预设 [ ${selectedName} ] 吗？`)) {
                        let customPresets = [];
                        const stored = localStorage.getItem(CUSTOM_PRESETS_KEY);
                        if (stored) customPresets = JSON.parse(stored);
                        
                        // 从数组中删掉
                        customPresets.splice(index, 1); 
                        localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(customPresets));
                        
                        // 刷新列表
                        loadItems("Custom");
                    }
                };

                presetRow1.appendChild(categorySelect);
                presetRow1.appendChild(saveBtn);
                presetRow2.appendChild(itemSelect);
                presetRow2.appendChild(deleteBtn);
                
                controlsRow.appendChild(swapBtn);
                controlsRow.appendChild(presetRow1);
                controlsRow.appendChild(presetRow2);

                container.appendChild(canvasEl);
                container.appendChild(inputRow);
                container.appendChild(controlsRow);

                this.addDOMWidget("visual_ui", "custom", container, { serialize: false });

                if (wWidget) wWidget.hidden = true;
                if (hWidget) hWidget.hidden = true;

                const syncToUI = (activeMode = null) => {
                    if (document.activeElement !== inputW) inputW.value = wWidget.value;
                    if (document.activeElement !== inputH) inputH.value = hWidget.value;
                    drawGraphics(canvasEl, wWidget.value, hWidget.value, activeMode);
                    self.setDirtyCanvas(true, true);
                };

                [wWidget, hWidget].forEach(w => {
                    const cb = w.callback;
                    w.callback = function (v) {
                        if (cb) cb.apply(this, arguments);
                        syncToUI();
                    };
                });

                // 画布拖拽（阻尼感）
                let dragMode = null;
                const DRAG_STEP = 64; 

                const handlePointer = (e) => {
                    const rect = canvasEl.getBoundingClientRect();
                    const x = (e.clientX - rect.left) / rect.width;
                    const y = 1 - (e.clientY - rect.top) / rect.height;

                    const isSnap = snapWidget && snapWidget.value === true;
                    const step = isSnap ? DRAG_STEP : 1;

                    let valX = Math.max(64, Math.min(4096, Math.round((x * 4096) / step) * step));
                    let valY = Math.max(64, Math.min(4096, Math.round((y * 4096) / step) * step));

                    if (dragMode === 'width' || dragMode === 'both') wWidget.value = valX;
                    if (dragMode === 'height' || dragMode === 'both') hWidget.value = valY;

                    if (wWidget.callback) wWidget.callback(wWidget.value);
                    if (hWidget.callback) hWidget.callback(hWidget.value);
                    syncToUI(dragMode);
                };

                canvasEl.onpointerdown = (e) => {
                    const rect = canvasEl.getBoundingClientRect();
                    const mx = e.clientX - rect.left;
                    const my = e.clientY - rect.top;
                    const rw = (wWidget.value / 4096) * rect.width;
                    const rh = (hWidget.value / 4096) * rect.height;
                    const ry = rect.height - rh;

                    const distCorner = Math.hypot(mx - rw, my - ry);
                    const distW = Math.hypot(mx - rw, my - (ry + rh / 2));
                    const distH = Math.hypot(mx - (rw / 2), my - ry);

                    if (distCorner < 15) dragMode = 'both';
                    else if (distW < 15) dragMode = 'width';
                    else if (distH < 15) dragMode = 'height';
                    else dragMode = 'both';

                    canvasEl.setPointerCapture(e.pointerId);
                    handlePointer(e);
                };

                canvasEl.onpointermove = (e) => { if (dragMode) handlePointer(e); };
                canvasEl.onpointerup = () => { dragMode = null; syncToUI(); };

                const observer = new ResizeObserver(() => {
                    canvasEl.width = canvasEl.clientWidth;
                    canvasEl.height = canvasEl.clientHeight;
                    syncToUI();
                });
                observer.observe(canvasEl);

                // 【修改】拉高了节点的整体高度 (从520提高到了560)
                this.size = [280, 560];
            };

            // 【修改】重构拉高的尺寸设定
            nodeType.prototype.computeSize = function () { 
                return [280, 560]; 
            };
            
            nodeType.prototype.onResize = function (size) {
                // 保证调整宽度时，高度依然有充裕的空间展示组件
                size[1] = size[0] + 280;
                if (this.syncUI) this.syncUI();
            };
        }
    }
});