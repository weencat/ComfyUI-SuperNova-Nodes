import { app } from "../../scripts/app.js";

/**
 * 绘图逻辑
 */
function drawGraphics(canvas, wVal, hVal, activeHandle = null) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const maxRes = 4096;

    // --- 1. 背景底色 ---
    ctx.fillStyle = "#121212";
    ctx.beginPath();
    ctx.roundRect(0, 0, w, h, 8);
    ctx.fill();

    // --- 【新增】 2. 背景参考点位 (网格点) ---
    // 每隔 512 分辨率画一个点
    ctx.fillStyle = "rgb(255, 255, 255)"; // 点的颜色，非常淡
    const dotStep = 256; 
    for (let x = 0; x <= maxRes; x += dotStep) {
        for (let y = 0; y <= maxRes; y += dotStep) {
            const px = (x / maxRes) * w;
            const py = h - (y / maxRes) * h; // Y轴翻转对齐
            ctx.beginPath();
            ctx.arc(px, py, 1, 0, Math.PI * 2); // 画一个小圆点
            ctx.fill();
        }
    }

    // --- 3. 1:1 参考框 + 【新增】尺寸备注 ---
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "rgba(0, 234, 255, 0.63)";
    ctx.fillStyle = "rgb(255, 255, 255)"; // 文字颜色
    ctx.font = "13px monospace";               // 文字字体
    
    [512, 1024, 1536, 2048, 2560, 3072, 3584, 4096].forEach(size => {
        const s = (size / maxRes) * w;
        const sy = h - s;
        
        // 绘制参考线
        ctx.strokeRect(0, sy, s, s);
        
        // 绘制尺寸备注 (放在框的右上角内部)
        ctx.fillText(size, s - 30, sy + 12); 
    });
    ctx.setLineDash([]);

    // --- 4. 当前选区 ---
    const rectW = (wVal / maxRes) * w;
    const rectH = (hVal / maxRes) * h;
    const rectY = h - rectH;

    ctx.fillStyle = "rgba(0, 160, 255, 0.2)";
    ctx.fillRect(0, rectY, rectW, rectH);
    ctx.strokeStyle = "#00a0ff";
    ctx.lineWidth = 2;
    ctx.strokeRect(0, rectY, rectW, rectH);

    // --- 5. 绘制手柄 ---
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

                // --- UI 布局 ---
                const container = document.createElement("div");
                container.style.cssText = "width:100%; height:100%; display:flex; flex-direction:column; align-items:center; padding:10px; box-sizing:border-box;";

                const canvasEl = document.createElement("canvas");
                canvasEl.style.cssText = "width:100%; aspect-ratio:1/1; background:#000; border-radius:8px; cursor:crosshair; touch-action:none;";

                const inputRow = document.createElement("div");
                inputRow.style.cssText = "margin-top:12px; display:flex; align-items:center; color:#ccc; font-family:monospace; font-size:14px; gap:8px;";

                const createInput = (widget) => {
                    const input = document.createElement("input");
                    input.type = "text";
                    input.value = widget.value;
                    input.style.cssText = "width:64px; background:#222; border:1px solid #444; color:#fff; text-align:center; border-radius:4px; font-weight:bold; outline:none; padding:2px 0;";

                    input.addEventListener("input", () => {
                        const val = parseInt(input.value);
                        if (!isNaN(val)) {
                            widget.value = val;
                            drawGraphics(canvasEl, wWidget.value, hWidget.value);
                        }
                    });

                    const finalize = () => {
                        let val = parseInt(input.value) || 64;
                        if (snapWidget && snapWidget.value === true) {
                            val = Math.max(64, Math.min(4096, Math.round(val / 8) * 8));
                        } else {
                            val = Math.max(64, Math.min(4096, val));
                        }
                        widget.value = val;
                        input.value = val;
                        if (widget.callback) widget.callback(val);
                        self.setDirtyCanvas(true, true);
                        drawGraphics(canvasEl, wWidget.value, hWidget.value);
                    };

                    input.addEventListener("blur", finalize);
                    input.addEventListener("keydown", (e) => { if (e.key === "Enter") finalize(); });
                    return input;
                };

                const inputW = createInput(wWidget);
                const inputH = createInput(hWidget);
                const separator = document.createElement("span");
                separator.innerText = "X";
                separator.style.color = "#666";

                inputRow.appendChild(inputW);
                inputRow.appendChild(separator);
                inputRow.appendChild(inputH);

                container.appendChild(canvasEl);
                container.appendChild(inputRow);

                this.addDOMWidget("visual_ui", "custom", container, { serialize: false });

                if (wWidget) wWidget.hidden = true;
                if (hWidget) hWidget.hidden = true;

                const syncToUI = (activeMode = null) => {
                    if (document.activeElement !== inputW) inputW.value = wWidget.value;
                    if (document.activeElement !== inputH) inputH.value = hWidget.value;
                    drawGraphics(canvasEl, wWidget.value, hWidget.value, activeMode);
                };

                [wWidget, hWidget].forEach(w => {
                    const cb = w.callback;
                    w.callback = function (v) {
                        if (cb) cb.apply(this, arguments);
                        syncToUI();
                    };
                });

                // 交互
                let dragMode = null;
                const handlePointer = (e) => {
                    const rect = canvasEl.getBoundingClientRect();
                    const x = (e.clientX - rect.left) / rect.width;
                    const y = 1 - (e.clientY - rect.top) / rect.height;

                    let valX, valY;
                    const isSnap = snapWidget && snapWidget.value === true;
                    valX = Math.max(64, Math.min(4096, isSnap ? Math.round((x * 4096) / 8) * 8 : Math.round(x * 4096)));
                    valY = Math.max(64, Math.min(4096, isSnap ? Math.round((y * 4096) / 8) * 8 : Math.round(y * 4096)));

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

                this.size = [280, 440];
            };

            // 尺寸与联动
            nodeType.prototype.computeSize = function () {
                return [260, 430];
            };

            nodeType.prototype.onResize = function (size) {
                size[1] = size[0] + 160;
                if (this.syncUI) this.syncUI();
            };
        }
    }
});