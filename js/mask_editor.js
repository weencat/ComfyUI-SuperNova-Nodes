import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ============================================================================
// 专业级遮罩编辑器 V6.4 - 增加反转功能 (Invert)
// ============================================================================
class SupernovaMaskEditor {
    constructor(imageUrl, callback) {
        this.imageUrl = imageUrl;
        this.callback = callback;

        this.tool = 'brush';
        this.operation = 'add';
        this.viewMode = 'overlay';

        this.isDrawing = false;
        this.isPanning = false;
        this.isSpacePressed = false;

        this.brush = {
            size: 50,
            strength: 1.0,
            opacity: 1.0,
            color: "#000000",
            tolerance: 15,
            hardness: 1.0,
            feather: 0
        };

        this.lassoPoints = [];
        this.history = [];
        this.historyStep = -1;
        this.maxHistory = 30;
        this.transform = { scale: 1.0, x: 0, y: 0 };
        this.antsOffset = 0;
        this.isClosed = false;
        
        this.brushTipCanvas = document.createElement("canvas");

        this.init();
    }

    async init() {
        this.createUI();
        await this.loadImage();
        this.updateBrushTip();
        this.saveHistoryState();
        this.initShortcuts();
        this.updateTransform();
        this.updateViewMode();
        this.animateLoop();
    }

    createUI() {
        this.container = document.createElement("div");
        Object.assign(this.container.style, {
            position: "fixed", top: "0", left: "0", width: "100vw", height: "100vh",
            backgroundColor: "#1e1e1e", zIndex: "99999",
            display: "flex", flexDirection: "column",
            userSelect: "none", outline: "none", fontFamily: "Segoe UI, Roboto, sans-serif"
        });
        this.container.tabIndex = 0;

        this.viewport = document.createElement("div");
        Object.assign(this.viewport.style, {
            position: "absolute", top: "0", left: "0", width: "100%", height: "100%",
            overflow: "hidden",
            cursor: "none",
            backgroundColor: "#000",
            backgroundImage: "conic-gradient(#222 0 90deg, #111 0 180deg, #222 0 270deg, #111 0)",
            backgroundSize: "20px 20px"
        });

        this.contentLayer = document.createElement("div");
        Object.assign(this.contentLayer.style, {
            position: "absolute", transformOrigin: "0 0", pointerEvents: "none"
        });

        this.imgCanvas = document.createElement("canvas");
        this.maskCanvas = document.createElement("canvas");
        this.antsCanvas = document.createElement("canvas");
        this.previewCanvas = document.createElement("canvas");

        const absStyle = { position: "absolute", top: "0", left: "0" };
        Object.assign(this.imgCanvas.style, absStyle);
        Object.assign(this.maskCanvas.style, { ...absStyle, mixBlendMode: "normal" });
        Object.assign(this.antsCanvas.style, { ...absStyle, zIndex: "4", opacity: "1.0", display: "none" });
        Object.assign(this.previewCanvas.style, { ...absStyle, zIndex: "5" });

        this.contentLayer.append(this.imgCanvas, this.maskCanvas, this.antsCanvas, this.previewCanvas);
        this.viewport.append(this.contentLayer);
        this.container.append(this.viewport);

        this.createFloatingToolbar();
        this.createTopRightButtons();
        this.createCursor();
        this.createHelpPanel();

        document.body.append(this.container);
        this.container.focus();
    }

    createFloatingToolbar() {
        const panel = document.createElement("div");
        Object.assign(panel.style, {
            position: "absolute", left: "20px", top: "20px", width: "220px",
            backgroundColor: "rgba(40, 40, 40, 0.95)", borderRadius: "8px",
            boxShadow: "0 4px 15px rgba(0,0,0,0.5)", border: "1px solid #555",
            backdropFilter: "blur(5px)", display: "flex", flexDirection: "column",
            color: "#eee", fontSize: "13px", zIndex: "100001", cursor: "default"
        });

        panel.addEventListener("mouseenter", () => {
            this.viewport.style.cursor = "default";
            if(this.cursor) this.cursor.style.display = "none";
        });
        panel.addEventListener("mouseleave", () => {
            if(!this.isPanning) this.viewport.style.cursor = "none";
            if(this.cursor && !this.isSpacePressed) this.cursor.style.display = "block";
        });

        panel.addEventListener("mousedown", (e) => e.stopPropagation());
        panel.addEventListener("wheel", (e) => e.stopPropagation());

        const header = document.createElement("div");
        header.innerText = "🛠️ Toolbox";
        Object.assign(header.style, {
            padding: "8px 12px", background: "#333", borderTopLeftRadius: "8px", borderTopRightRadius: "8px",
            cursor: "move", fontWeight: "bold", borderBottom: "1px solid #555", userSelect: "none"
        });
        this.makeDraggable(panel, header);
        panel.appendChild(header);

        const content = document.createElement("div");
        Object.assign(content.style, { padding: "12px", display: "flex", flexDirection: "column", gap: "12px" });

        // Tool Row
        const toolRow = this.createRow();
        this.brushBtn = this.createIconBtn("🖌️", "Brush (B)", true, () => this.setTool('brush'));
        this.lassoBtn = this.createIconBtn("➰", "Lasso (L)", false, () => this.setTool('lasso'));
        this.fillBtn = this.createIconBtn("🪣", "Fill (F)", false, () => this.setTool('fill'));
        toolRow.append(this.brushBtn, this.lassoBtn, this.fillBtn);

        // Operation Row
        const opRow = this.createRow();
        this.addBtn = this.createIconTextBtn("➕", "Add", true, () => this.setOperation('add'));
        this.subBtn = this.createIconTextBtn("➖", "Sub", false, () => this.setOperation('sub'));
        opRow.append(this.addBtn, this.subBtn);

        // Color Row
        const colorRow = this.createRow();
        colorRow.innerHTML = `<span style="color:#aaa">Color:</span>`;
        this.colorInput = document.createElement("input");
        this.colorInput.type = "color"; this.colorInput.value = this.brush.color;
        Object.assign(this.colorInput.style, { flex: "1", height: "24px", cursor: "pointer", border: "none", background: "transparent" });
        this.colorInput.oninput = (e) => this.setMaskColor(e.target.value);
        colorRow.appendChild(this.colorInput);

        // Sliders
        const sliderContainer = document.createElement("div");
        sliderContainer.style.display = "flex"; sliderContainer.style.flexDirection = "column"; sliderContainer.style.gap = "8px";

        this.sizeWrap = this.createSlider("Size", 1, 300, this.brush.size, (v) => {
            this.brush.size = v; this.updateBrushTip(); this.updateCursorPreview();
        });
        this.hardWrap = this.createSlider("Hard", 0.0, 1.0, this.brush.hardness, (v) => {
            this.brush.hardness = parseFloat(v); this.updateBrushTip(); this.updateCursorPreview();
        }, 0.05);
        this.tolWrap = this.createSlider("Tol", 0, 100, this.brush.tolerance, (v) => {
            this.brush.tolerance = parseInt(v);
        });
        this.featherWrap = this.createSlider("Fthr", 0, 50, this.brush.feather, (v) => {
            this.brush.feather = parseInt(v);
        });
        const strWrap = this.createSlider("Flow", 0.05, 1.0, this.brush.strength, (v) => this.brush.strength = parseFloat(v), 0.05);

        sliderContainer.append(this.sizeWrap, this.hardWrap, this.tolWrap, this.featherWrap, strWrap);

        // Actions Row (Updated with Invert)
        const actionRow = this.createRow();
        const undoBtn = this.createIconBtn("↩️", "Undo", () => this.undo());
        const redoBtn = this.createIconBtn("↪️", "Redo", () => this.redo());
        // 新增反转按钮
        const invertBtn = this.createIconBtn("🌗", "Invert", () => this.invertMask()); 
        const clearBtn = this.createIconBtn("🗑️", "Clear", () => this.clearMask());
        
        actionRow.append(undoBtn, redoBtn, invertBtn, clearBtn);

        // View Mode
        this.viewSelect = document.createElement("select");
        Object.assign(this.viewSelect.style, {
            width: "100%", background: "#222", color: "#ccc", border: "1px solid #444", padding: "4px", borderRadius: "4px", cursor: "pointer"
        });
        ["Overlay", "Marching Ants", "Mask (B&W)", "Image Only"].forEach(opt => {
            const o = document.createElement("option"); o.value = opt.split(" ")[0].toLowerCase(); o.innerText = opt;
            this.viewSelect.appendChild(o);
        });
        this.viewSelect.onchange = (e) => this.setViewMode(e.target.value);

        content.append(toolRow, opRow, colorRow, sliderContainer, this.createSeparator(), actionRow, this.viewSelect);
        panel.appendChild(content);
        this.viewport.appendChild(panel);

        this.setTool(this.tool);
    }

    createTopRightButtons() {
        const container = document.createElement("div");
        Object.assign(container.style, {
            position: "absolute", top: "70px", right: "30px",
            display: "flex", gap: "15px", zIndex: "100001"
        });

        ["mousedown", "mouseup", "click", "mouseenter", "mouseleave"].forEach(type => {
            container.addEventListener(type, e => e.stopPropagation());
        });

        const saveBtn = this.createBigButton("💾 Save Mask", "#2e7d32", () => this.save());
        const closeBtn = this.createBigButton("❌ Close", "#7a2020", () => this.close());

        container.append(saveBtn, closeBtn);
        this.viewport.appendChild(container);
    }

    createBigButton(text, bgColor, onClick) {
        const btn = document.createElement("button");
        btn.innerText = text;
        Object.assign(btn.style, {
            padding: "10px 20px", backgroundColor: bgColor, color: "white",
            border: "none", borderRadius: "6px", cursor: "pointer",
            fontWeight: "bold", fontSize: "14px", boxShadow: "0 3px 8px rgba(0,0,0,0.4)",
            transition: "all 0.15s ease", outline: "none", display: "flex", alignItems: "center", gap: "8px"
        });
        btn.onmouseenter = () => {
            btn.style.filter = "brightness(1.2)"; btn.style.transform = "translateY(-2px)";
            this.viewport.style.cursor = "default";
            if(this.cursor) this.cursor.style.display = "none";
        };
        btn.onmouseleave = () => {
            btn.style.filter = "brightness(1)"; btn.style.transform = "translateY(0)";
            this.viewport.style.cursor = "none";
            if(this.cursor && !this.isSpacePressed) this.cursor.style.display = "block";
        };
        btn.onmousedown = (e) => { e.stopPropagation(); btn.style.transform = "translateY(1px) scale(0.96)"; };
        btn.onmouseup = () => btn.style.transform = "translateY(-2px) scale(1)";
        btn.onclick = (e) => { e.stopPropagation(); onClick(); };
        return btn;
    }

    createCursor() {
        this.cursor = document.createElement("div");
        Object.assign(this.cursor.style, {
            position: "absolute", pointerEvents: "none", borderRadius: "50%",
            border: "1px solid rgba(255,255,255,0.9)", transform: "translate(-50%, -50%)", display: "none", zIndex: "1000",
            boxShadow: "0 0 3px rgba(0,0,0,0.8)"
        });
        const crosshair = document.createElement("div");
        Object.assign(crosshair.style, { position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)" });
        const lh = document.createElement("div");
        Object.assign(lh.style, { position: "absolute", top: "0", left: "-5px", width: "10px", height: "1px", background: "#fff", boxShadow: "0 0 2px #000" });
        const lv = document.createElement("div");
        Object.assign(lv.style, { position: "absolute", top: "-5px", left: "0", width: "1px", height: "10px", background: "#fff", boxShadow: "0 0 2px #000" });
        crosshair.append(lh, lv);
        this.cursor.appendChild(crosshair);
        
        this.cursorInner = document.createElement("div");
        Object.assign(this.cursorInner.style, {
            position: "absolute", top: "50%", left: "50%", borderRadius: "50%",
            border: "1px dashed rgba(255,255,255,0.5)", transform: "translate(-50%, -50%)",
            pointerEvents: "none"
        });
        this.cursor.appendChild(this.cursorInner);
        
        this.viewport.append(this.cursor);
    }

    createHelpPanel() {
        const panel = document.createElement("div");
        Object.assign(panel.style, {
            position: "absolute", bottom: "10px", right: "10px",
            background: "rgba(0,0,0,0.6)", padding: "8px 12px", borderRadius: "4px",
            color: "#aaa", fontSize: "11px", pointerEvents: "none", zIndex: "100"
        });
        panel.innerHTML = `Left: Draw | Right/Space: Pan | Wheel: Zoom | [ ]: Size | Ctrl+Z: Undo | Shift+I: Invert`;
        this.viewport.appendChild(panel);
    }

    // ========================================================================
    // 逻辑功能
    // ========================================================================

    makeDraggable(element, handle) {
        let isDragging = false;
        let startX, startY, initialLeft, initialTop;
        handle.addEventListener("mousedown", (e) => {
            isDragging = true; startX = e.clientX; startY = e.clientY;
            initialLeft = element.offsetLeft; initialTop = element.offsetTop;
            handle.style.cursor = "grabbing";
        });
        window.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const dx = e.clientX - startX; const dy = e.clientY - startY;
            element.style.left = `${initialLeft + dx}px`; element.style.top = `${initialTop + dy}px`;
        });
        window.addEventListener("mouseup", () => { isDragging = false; handle.style.cursor = "move"; });
    }

    setTool(tool) {
        this.tool = tool;
        this.updateBtnState(this.brushBtn, tool === 'brush');
        this.updateBtnState(this.lassoBtn, tool === 'lasso');
        this.updateBtnState(this.fillBtn, tool === 'fill');
        this.sizeWrap.style.display = tool === 'brush' ? "flex" : "none";
        this.hardWrap.style.display = tool === 'brush' ? "flex" : "none";
        this.tolWrap.style.display = tool === 'fill' ? "flex" : "none";
        this.featherWrap.style.display = tool === 'fill' ? "flex" : "none";
        this.updateCursorPreview();
    }

    setOperation(op) {
        this.operation = op;
        this.updateBtnState(this.addBtn, op === 'add');
        this.updateBtnState(this.subBtn, op === 'sub');
        this.updateBrushTip();
        this.updateCursorPreview();
    }

    setMaskColor(color) {
        this.brush.color = color;
        this.recolorEntireMask(color);
        this.updateBrushTip();
        this.updateCursorPreview();
    }

    setViewMode(mode) {
        this.viewMode = mode;
        this.updateViewMode();
    }

    updateViewMode() {
        this.maskCanvas.style.display = "block";
        this.maskCanvas.style.filter = "none";
        this.maskCanvas.style.opacity = "1.0";
        this.imgCanvas.style.display = "block";
        this.antsCanvas.style.display = "none";

        if (this.viewMode === 'marching') {
            this.maskCanvas.style.display = "none";
            this.antsCanvas.style.display = "block";
            this.resetAntsCache();
        } else if (this.viewMode === 'mask') {
            this.imgCanvas.style.display = "none";
            this.maskCanvas.style.filter = "brightness(0) invert(1)";
        } else if (this.viewMode === 'image') {
            this.maskCanvas.style.display = "none";
        }
    }

    updateBrushTip() {
        const size = this.brush.size;
        const hardness = this.brush.hardness;
        const color = this.brush.color;
        
        this.brushTipCanvas.width = size;
        this.brushTipCanvas.height = size;
        const ctx = this.brushTipCanvas.getContext("2d");
        const center = size / 2;
        const radius = size / 2;

        if (hardness >= 0.98) {
            ctx.beginPath(); ctx.arc(center, center, radius, 0, Math.PI * 2);
            ctx.fillStyle = color; ctx.fill();
        } else {
            const gradient = ctx.createRadialGradient(center, center, radius * hardness, center, center, radius);
            const hex = color.replace("#", "");
            const r = parseInt(hex.substring(0, 2), 16), g = parseInt(hex.substring(2, 4), 16), b = parseInt(hex.substring(4, 6), 16);
            gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 1)`);
            gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
            ctx.fillStyle = gradient; ctx.fillRect(0, 0, size, size);
        }
    }

    animateLoop() {
        if (this.isClosed) return;
        requestAnimationFrame(() => this.animateLoop());
        if (this.viewMode !== 'marching') return;

        if (!this.edgeImgData && this.maskCanvas) {
            const w = this.width, h = this.height;
            const offC = document.createElement('canvas'); offC.width = w; offC.height = h;
            const ctx = offC.getContext('2d');
            ctx.drawImage(this.maskCanvas, 0, 0);
            const data = ctx.getImageData(0, 0, w, h).data;
            const edge = ctx.createImageData(w, h);
            const ed = edge.data;
            for (let y = 1; y < h - 1; y++) {
                for (let x = 1; x < w - 1; x++) {
                    const i = (y * w + x) * 4;
                    if (data[i + 3] > 10) {
                        const t = ((y - 1) * w + x) * 4, b = ((y + 1) * w + x) * 4, l = (y * w + x - 1) * 4, r = (y * w + x + 1) * 4;
                        if (data[t + 3] < 10 || data[b + 3] < 10 || data[l + 3] < 10 || data[r + 3] < 10) {
                            ed[i] = 255; ed[i + 1] = 255; ed[i + 2] = 255; ed[i + 3] = 255;
                        }
                    }
                }
            }
            this.edgeImgData = edge;
        }
        if (this.edgeImgData) {
            const ctx = this.antsCanvas.getContext('2d'); ctx.clearRect(0, 0, this.width, this.height);
            if (!this.edgeBitmap) createImageBitmap(this.edgeImgData).then(b => this.edgeBitmap = b);
            if (this.edgeBitmap) {
                ctx.globalCompositeOperation = "source-over"; ctx.drawImage(this.edgeBitmap, 0, 0);
                ctx.globalCompositeOperation = "source-in";
                this.antsOffset = (this.antsOffset + 0.5) % 16;
                const pC = document.createElement('canvas'); pC.width = 16; pC.height = 16;
                const pCtx = pC.getContext('2d');
                pCtx.fillStyle = "white"; pCtx.fillRect(0, 0, 16, 16); pCtx.fillStyle = "black";
                pCtx.beginPath(); pCtx.moveTo(0, 0); pCtx.lineTo(8, 0); pCtx.lineTo(0, 8); pCtx.fill();
                pCtx.beginPath(); pCtx.moveTo(8, 16); pCtx.lineTo(16, 8); pCtx.lineTo(16, 16); pCtx.fill();
                pCtx.beginPath(); pCtx.moveTo(8, 0); pCtx.lineTo(16, 0); pCtx.lineTo(0, 16); pCtx.lineTo(0, 8); pCtx.fill();
                const pat = ctx.createPattern(pC, "repeat");
                const m = new DOMMatrix(); m.translateSelf(this.antsOffset, 0); pat.setTransform(m);
                ctx.fillStyle = pat; ctx.fillRect(0, 0, this.width, this.height);
            }
        }
    }
    resetAntsCache() { this.edgeImgData = null; this.edgeBitmap = null; }

    createRow() { const d = document.createElement("div"); d.style.display = "flex"; d.style.gap = "8px"; d.style.alignItems = "center"; return d; }
    createIconBtn(i, t, a, c) {
        const b = document.createElement("button"); b.innerText = i; b.title = t;
        Object.assign(b.style, {
            flex: "1", padding: "6px", border: "1px solid #444", borderRadius: "4px", cursor: "pointer",
            background: a ? "#444" : "#2a2a2a", color: "#eee", transition: "all 0.1s"
        });
        b.onclick = (e) => { e.stopPropagation(); c ? c() : a(); };
        b.onmousedown = (e) => e.stopPropagation();
        return b;
    }
    createIconTextBtn(i, t, a, c) {
        const b = document.createElement("button"); b.innerHTML = `<span>${i}</span> ${t}`;
        Object.assign(b.style, {
            flex: "1", padding: "6px", border: "1px solid #444", borderRadius: "4px", cursor: "pointer",
            background: a ? "#444" : "#2a2a2a", color: a ? "#fff" : "#bbb", display: "flex", alignItems: "center", justifyContent: "center", gap: "5px", fontSize: "12px"
        });
        b.onclick = (e) => { e.stopPropagation(); c(); };
        b.onmousedown = (e) => e.stopPropagation();
        return b;
    }
    updateBtnState(b, a) { b.style.background = a ? "#444" : "#2a2a2a"; b.style.color = a ? "#fff" : "#bbb"; b.style.borderColor = a ? "#888" : "#444"; }
    createSlider(l, min, max, val, cb, step = 1) {
        const d = document.createElement("div"); d.style.display = "flex"; d.style.alignItems = "center"; d.style.gap = "5px";
        const lb = document.createElement("span"); lb.innerText = l; lb.style.width = "30px"; lb.style.color = "#aaa";
        const i = document.createElement("input"); i.type = "range"; i.min = min; i.max = max; i.step = step; i.value = val;
        i.style.flex = "1"; i.style.cursor = "pointer";
        const v = document.createElement("span"); v.innerText = val; v.style.width = "25px"; v.style.textAlign = "right"; v.style.color = "#ccc";
        i.oninput = (e) => { v.innerText = e.target.value; cb(e.target.value); };
        i.onmousedown = (e) => e.stopPropagation();
        d.append(lb, i, v); return d;
    }
    createSeparator() { const d = document.createElement("div"); Object.assign(d.style, { height: "1px", background: "#444", margin: "4px 0" }); return d; }

    updateCursorPreview() {
        if (!this.cursor) return;
        if (this.tool === 'lasso' || this.tool === 'fill') {
            this.cursor.style.width = "0"; this.cursor.style.height = "0";
            this.cursor.style.border = "none"; this.cursor.style.background = "none";
            this.cursorInner.style.display = "none";
            this.cursor.querySelector('div').style.display = "block";
        } else {
            const s = this.brush.size * this.transform.scale;
            this.cursor.style.width = `${s}px`; this.cursor.style.height = `${s}px`;
            this.cursor.style.border = "1px solid rgba(255,255,255,0.9)";
            this.cursor.style.background = "none";
            this.cursor.querySelector('div').style.display = "block";
            
            if (this.brush.hardness < 1.0) {
                this.cursorInner.style.display = "block";
                const innerSize = s * this.brush.hardness;
                this.cursorInner.style.width = `${innerSize}px`; this.cursorInner.style.height = `${innerSize}px`;
            } else {
                this.cursorInner.style.display = "none";
            }
        }
        this.cursor.style.display = this.isSpacePressed ? "none" : "block";
    }

    recolorEntireMask(c) {
        const tc = document.createElement('canvas'); tc.width = this.width; tc.height = this.height;
        const tctx = tc.getContext('2d'); tctx.drawImage(this.maskCanvas, 0, 0);
        const ctx = this.maskCanvas.getContext('2d'); ctx.clearRect(0, 0, this.width, this.height); ctx.drawImage(tc, 0, 0);
        ctx.globalCompositeOperation = "source-in"; ctx.fillStyle = c; ctx.fillRect(0, 0, this.width, this.height);
        ctx.globalCompositeOperation = "source-over"; this.saveHistoryState();
    }

    updateTransform() {
        const { x, y, scale } = this.transform;
        this.contentLayer.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
        this.updateCursorPreview();
    }

    bindEvents() {
        const vp = this.viewport;
        const getPos = (e) => {
            const b = vp.getBoundingClientRect();
            const mx = e.clientX - b.left, my = e.clientY - b.top;
            const cx = (mx - this.transform.x) / this.transform.scale;
            const cy = (my - this.transform.y) / this.transform.scale;
            return { mx, my, cx, cy };
        };
        vp.addEventListener("mousemove", e => {
            const { mx, my, cx, cy } = getPos(e);
            if(this.cursor) { this.cursor.style.left = `${mx}px`; this.cursor.style.top = `${my}px`; }
            if (this.isPanning) {
                this.transform.x += e.movementX; this.transform.y += e.movementY; this.updateTransform();
            } else if (this.isDrawing) {
                if (this.tool === 'brush') { this.drawBrush(cx, cy); this.lastPos = { x: cx, y: cy }; }
                else if (this.tool === 'lasso') this.drawLassoTrace(cx, cy);
            }
        });
        vp.addEventListener("mousedown", e => {
            if (e.target !== vp) return;

            if (e.button === 2 || e.button === 1 || this.isSpacePressed) {
                this.isPanning = true; vp.style.cursor = "grabbing"; if(this.cursor) this.cursor.style.display = "none"; e.preventDefault();
            } else if (e.button === 0) {
                const { cx, cy } = getPos(e);
                if (this.tool === 'fill') this.performFloodFill(cx, cy);
                else {
                    this.isDrawing = true;
                    if (this.tool === 'brush') { this.lastPos = { x: cx, y: cy }; this.drawBrush(cx, cy); }
                    else if (this.tool === 'lasso') { this.lassoPoints = [{ x: cx, y: cy }]; this.drawLassoTrace(cx, cy); }
                }
            }
        });
        window.addEventListener("mouseup", () => {
            if (this.isDrawing) {
                this.isDrawing = false;
                if (this.tool === 'lasso') this.applyLasso();
                this.saveHistoryState();
            }
            if (this.isPanning) {
                this.isPanning = false; vp.style.cursor = "none";
                if (this.isSpacePressed) vp.style.cursor = "grab"; else if(this.cursor) this.cursor.style.display = "block";
            }
        });
        vp.addEventListener("wheel", e => {
            e.preventDefault(); const d = e.deltaY > 0 ? 0.9 : 1.1; const ns = this.transform.scale * d;
            if (ns < 0.1 || ns > 20) return;
            const b = vp.getBoundingClientRect(); const mx = e.clientX - b.left; const my = e.clientY - b.top;
            this.transform.x = mx - (mx - this.transform.x) * (ns / this.transform.scale);
            this.transform.y = my - (my - this.transform.y) * (ns / this.transform.scale);
            this.transform.scale = ns; this.updateTransform();
        }, { passive: false });
        vp.addEventListener("contextmenu", e => e.preventDefault());
    }

    getCompOp() { return this.operation === 'sub' ? 'destination-out' : 'source-over'; }
    
    drawBrush(x, y) {
        const ctx = this.maskCanvas.getContext('2d');
        ctx.globalCompositeOperation = this.getCompOp();
        ctx.globalAlpha = this.brush.strength;

        if (this.brush.hardness >= 0.98) {
            ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = this.brush.size;
            if (this.operation === 'sub') {} else { ctx.strokeStyle = this.brush.color; }
            ctx.beginPath(); ctx.moveTo(this.lastPos.x, this.lastPos.y); ctx.lineTo(x, y); ctx.stroke();
        } else {
            const dist = Math.hypot(x - this.lastPos.x, y - this.lastPos.y);
            const step = Math.max(1, this.brush.size * 0.15); 
            const steps = Math.ceil(dist / step);
            const halfSize = this.brush.size / 2;
            const dx = x - this.lastPos.x; const dy = y - this.lastPos.y;
            
            for (let i = 0; i < steps; i++) {
                const t = i / steps;
                const cx = this.lastPos.x + dx * t; const cy = this.lastPos.y + dy * t;
                ctx.drawImage(this.brushTipCanvas, cx - halfSize, cy - halfSize);
            }
            ctx.drawImage(this.brushTipCanvas, x - halfSize, y - halfSize);
        }
    }

    drawLassoTrace(x, y) {
        this.lassoPoints.push({ x, y });
        const ctx = this.previewCanvas.getContext('2d'); ctx.clearRect(0, 0, this.width, this.height);
        ctx.beginPath(); if (this.lassoPoints.length > 0) ctx.moveTo(this.lassoPoints[0].x, this.lassoPoints[0].y);
        for (let i = 1; i < this.lassoPoints.length; i++) ctx.lineTo(this.lassoPoints[i].x, this.lassoPoints[i].y);
        ctx.strokeStyle = this.operation === 'sub' ? "#f55" : "#fff"; ctx.lineWidth = 2 / this.transform.scale; ctx.setLineDash([5, 5]); ctx.stroke();
        ctx.lineTo(this.lassoPoints[0].x, this.lassoPoints[0].y); ctx.stroke();
    }
    
    applyLasso() {
        const pCtx = this.previewCanvas.getContext('2d'); pCtx.clearRect(0, 0, this.width, this.height);
        if (this.lassoPoints.length < 3) return;
        const ctx = this.maskCanvas.getContext('2d'); ctx.globalCompositeOperation = this.getCompOp();
        if (this.operation === 'sub') { ctx.fillStyle = "black"; ctx.globalAlpha = 1.0; }
        else { ctx.fillStyle = this.brush.color; ctx.globalAlpha = this.brush.strength; }
        ctx.beginPath(); ctx.moveTo(this.lassoPoints[0].x, this.lassoPoints[0].y);
        for (let i = 1; i < this.lassoPoints.length; i++) ctx.lineTo(this.lassoPoints[i].x, this.lassoPoints[i].y);
        ctx.closePath(); ctx.fill(); this.lassoPoints = [];
    }
    
    performFloodFill(startX, startY) {
        startX = Math.floor(startX); startY = Math.floor(startY);
        if(startX < 0 || startX >= this.width || startY < 0 || startY >= this.height) return;

        const w = this.width; const h = this.height;
        const imgData = this.imgCanvas.getContext('2d').getImageData(0, 0, w, h);
        const pixelData = imgData.data;
        const startPos = (startY * w + startX) * 4;
        const r0 = pixelData[startPos], g0 = pixelData[startPos+1], b0 = pixelData[startPos+2];
        const tol = this.brush.tolerance;

        const match = (pos) => {
            const r = pixelData[pos], g = pixelData[pos+1], b = pixelData[pos+2];
            return Math.abs(r - r0) <= tol && Math.abs(g - g0) <= tol && Math.abs(b - b0) <= tol;
        };

        const fillCanvas = document.createElement('canvas'); fillCanvas.width = w; fillCanvas.height = h;
        const fillCtx = fillCanvas.getContext('2d');
        const fillImgData = fillCtx.createImageData(w, h);
        const fillData = fillImgData.data;
        const stack = [[startX, startY]];
        const visited = new Uint8Array(w * h); 

        while (stack.length) {
            let [x, y] = stack.pop();
            let pixelPos = (y * w + x) * 4;
            let visitPos = y * w + x;

            while (y >= 0 && match(pixelPos) && visited[visitPos] === 0) {
                y--; pixelPos -= w * 4; visitPos -= w;
            }
            y++; pixelPos += w * 4; visitPos += w;

            let spanLeft = false, spanRight = false;
            while (y < h && match(pixelPos) && visited[visitPos] === 0) {
                fillData[pixelPos+3] = 255; visited[visitPos] = 1;

                if (x > 0) {
                    const leftMatch = match(pixelPos - 4) && visited[visitPos - 1] === 0;
                    if (!spanLeft && leftMatch) { stack.push([x - 1, y]); spanLeft = true; }
                    else if (spanLeft && !leftMatch) spanLeft = false;
                }
                if (x < w - 1) {
                    const rightMatch = match(pixelPos + 4) && visited[visitPos + 1] === 0;
                    if (!spanRight && rightMatch) { stack.push([x + 1, y]); spanRight = true; }
                    else if (spanRight && !rightMatch) spanRight = false;
                }
                y++; pixelPos += w * 4; visitPos += w;
            }
        }
        fillCtx.putImageData(fillImgData, 0, 0);

        const maskCtx = this.maskCanvas.getContext('2d');
        maskCtx.globalCompositeOperation = this.getCompOp();
        
        if (this.brush.feather > 0) {
            const tempC = document.createElement('canvas'); tempC.width = w; tempC.height = h;
            const tempCtx = tempC.getContext('2d');
            tempCtx.filter = `blur(${this.brush.feather}px)`;
            tempCtx.drawImage(fillCanvas, 0, 0);
            
            maskCtx.save();
            if (this.operation !== 'sub') {
                const colorC = document.createElement('canvas'); colorC.width = w; colorC.height = h;
                const cCtx = colorC.getContext('2d'); cCtx.drawImage(tempC, 0, 0);
                cCtx.globalCompositeOperation = "source-in"; cCtx.fillStyle = this.brush.color; cCtx.fillRect(0,0,w,h);
                maskCtx.drawImage(colorC, 0, 0);
            } else {
                maskCtx.drawImage(tempC, 0, 0);
            }
            maskCtx.restore();
        } else {
            if (this.operation !== 'sub') {
                fillCtx.globalCompositeOperation = "source-in"; fillCtx.fillStyle = this.brush.color; fillCtx.fillRect(0, 0, w, h);
            }
            maskCtx.drawImage(fillCanvas, 0, 0);
        }
        this.saveHistoryState();
    }

    // --- 新增：反转遮罩逻辑 ---
    invertMask() {
        const tempC = document.createElement('canvas'); tempC.width = this.width; tempC.height = this.height;
        const tCtx = tempC.getContext('2d');
        
        // 1. 用当前颜色填满临时层
        tCtx.fillStyle = this.brush.color;
        tCtx.fillRect(0, 0, this.width, this.height);
        
        // 2. 挖掉已有的遮罩区域 (destination-out)
        tCtx.globalCompositeOperation = "destination-out";
        tCtx.drawImage(this.maskCanvas, 0, 0);
        
        // 3. 将结果画回主遮罩层
        const ctx = this.maskCanvas.getContext('2d');
        ctx.globalCompositeOperation = "source-over";
        ctx.clearRect(0, 0, this.width, this.height);
        ctx.drawImage(tempC, 0, 0);
        
        this.saveHistoryState();
    }

    loadImage() {
        return new Promise((res, rej) => {
            const img = new Image(); img.crossOrigin = "anonymous"; img.src = this.imageUrl;
            img.onload = () => {
                this.width = img.naturalWidth; this.height = img.naturalHeight;
                [this.imgCanvas, this.maskCanvas, this.antsCanvas, this.previewCanvas].forEach(c => { c.width = this.width; c.height = this.height; });
                this.imgCanvas.getContext("2d").drawImage(img, 0, 0);
                this.fitScreen(); this.bindEvents(); res();
            };
            img.onerror = () => { alert("Load Error"); this.close(); rej(); };
        });
    }
    fitScreen() {
        const vw = this.viewport.clientWidth; const vh = this.viewport.clientHeight;
        const s = Math.min((vw * 0.9) / this.width, (vh * 0.9) / this.height, 1.0);
        this.transform = { scale: s, x: (vw - this.width * s) / 2, y: (vh - this.height * s) / 2 };
    }
    saveHistoryState() {
        if (this.historyStep < this.history.length - 1) this.history = this.history.slice(0, this.historyStep + 1);
        this.history.push(this.maskCanvas.getContext('2d').getImageData(0, 0, this.width, this.height));
        if (this.history.length > this.maxHistory) this.history.shift(); else this.historyStep++;
        this.resetAntsCache();
    }
    undo() { if (this.historyStep > 0) { this.historyStep--; this.restoreHistory(); } }
    redo() { if (this.historyStep < this.history.length - 1) { this.historyStep++; this.restoreHistory(); } }
    restoreHistory() { this.maskCanvas.getContext('2d').putImageData(this.history[this.historyStep], 0, 0); this.resetAntsCache(); }
    clearMask() { this.maskCanvas.getContext('2d').clearRect(0, 0, this.width, this.height); this.saveHistoryState(); }

    initShortcuts() {
        const handleKeyDown = (e) => {
            if (!this.container) return;
            if (e.code === "Space" && !this.isSpacePressed) { 
                this.isSpacePressed = true; this.viewport.style.cursor = "grab"; if(this.cursor) this.cursor.style.display = "none"; 
            }
            if (e.key === "[") {
                this.brush.size = Math.max(1, this.brush.size - 5);
                this.sizeWrap.querySelector("input").value = this.brush.size;
                this.updateBrushTip(); this.updateCursorPreview();
            }
            if (e.key === "]") {
                this.brush.size += 5;
                this.sizeWrap.querySelector("input").value = this.brush.size;
                this.updateBrushTip(); this.updateCursorPreview();
            }
            if (e.code === "KeyB") this.setTool('brush'); 
            if (e.code === "KeyL") this.setTool('lasso'); 
            if (e.code === "KeyF") this.setTool('fill');
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? this.redo() : this.undo(); }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); this.redo(); }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); this.save(); }
            
            // 新增快捷键 Shift + I 反转
            if (e.shiftKey && e.code === "KeyI") { e.preventDefault(); this.invertMask(); }
            
            if (e.key === "Escape") this.close();
        };
        const handleKeyUp = (e) => {
            if (!this.container) return;
            if (e.code === "Space") { 
                this.isSpacePressed = false; this.isPanning = false; this.viewport.style.cursor = "none"; if(this.cursor) this.cursor.style.display = "block"; 
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        window.addEventListener("keyup", handleKeyUp);
        this.cleanupShortcuts = () => {
            window.removeEventListener("keydown", handleKeyDown);
            window.removeEventListener("keyup", handleKeyUp);
        };
    }

    async save() {
        const sc = document.createElement("canvas"); sc.width = this.width; sc.height = this.height;
        const ctx = sc.getContext("2d"); ctx.drawImage(this.imgCanvas, 0, 0);
        ctx.globalCompositeOperation = "destination-out"; ctx.drawImage(this.maskCanvas, 0, 0);
        const fn = `temp-mask-${Date.now()}.png`;
        sc.toBlob(async (b) => {
            const fd = new FormData(); fd.append("image", b, fn); fd.append("type", "temp"); fd.append("overwrite", "true");
            try {
                const r = await fetch(api.apiURL("/upload/image"), { method: "POST", body: fd });
                if (r.ok) { const d = await r.json(); if (this.callback) this.callback(d); this.close(); }
                else alert("Save Failed: " + r.status);
            } catch (e) { alert("Net Error: " + e); }
        }, "image/png");
    }
    close() { 
        this.isClosed = true; 
        if(this.cleanupShortcuts) this.cleanupShortcuts();
        if (this.container) { document.body.removeChild(this.container); this.container = null; } 
    }
}

app.registerExtension({
    name: "Supernova.MaskEditor",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (["LoadImageUnified", "load_image_by_path"].includes(nodeData.name)) {
            const orig = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, opts) {
                if (orig) orig.apply(this, arguments);
                const n = this; 
                // 兼容 image (LoadImageUnified) 和 img_path (load_image_by_path)
                const w = n.widgets.find(w => w.name === "image" || w.name === "img_path");
                if (!w || !w.value) return;
                
                opts.push({
                    content: "🎨 Open in MaskEditor (Pro)",
                    callback: async () => {
                        const rp = w.value; 
                        let url = "";
                        try {
                            if (nodeData.name === "load_image_by_path") {
                                // --- 处理绝对路径节点逻辑 (保持不变) ---
                                if (rp.startsWith("temp/")) {
                                    url = api.apiURL(`/view?filename=${encodeURIComponent(rp.replace("temp/", ""))}&type=temp`);
                                } else {
                                    const p = new URLSearchParams({ path: rp });
                                    const r = await fetch(api.apiURL("/mape/preview_absolute_path?" + p.toString()));
                                    if (!r.ok) throw new Error("API Error");
                                    const d = await r.json(); 
                                    url = api.apiURL(`/view?filename=${encodeURIComponent(d.filename)}&type=${d.type}`);
                                }
                            } else {
                                // --- 修复 LoadImageUnified 的子文件夹逻辑 ---
                                const parts = rp.split('/');
                                const type = parts[0];

                                // 检查是否是 LoadImageUnified 的标准格式 (例如: input/subfolder/img.png)
                                if (parts.length > 1 && ["input", "output", "temp", "clipspace"].includes(type)) {
                                    // 移除第一个元素 (type)
                                    const remainingParts = parts.slice(1);
                                    
                                    // 文件名是最后一部分
                                    const filename = remainingParts.pop();
                                    
                                    // 剩下的部分重新组合成 subfolder
                                    const subfolder = remainingParts.join('/');

                                    // 使用 URLSearchParams 构建参数，确保特殊字符被正确编码
                                    const params = new URLSearchParams({
                                        filename: filename,
                                        type: type,
                                        subfolder: subfolder
                                    });
                                    
                                    url = api.apiURL(`/view?${params.toString()}`);
                                } else {
                                    // 常规回退逻辑 (如果没有子文件夹或格式不匹配)
                                    url = api.apiURL(`/view?filename=${encodeURIComponent(rp)}&type=input`);
                                }
                            }
                            
                            new SupernovaMaskEditor(url, (res) => {
                                if (res && res.name) {
                                    // 回填逻辑
                                    const np = `temp/${res.name}`; 
                                    w.value = np; 
                                    if (w.callback) w.callback(np); 
                                    n.graph.setDirtyCanvas(true, true);
                                }
                            });
                        } catch (e) { alert("Err: " + e.message); }
                    }
                });
            };
        }
    }
});