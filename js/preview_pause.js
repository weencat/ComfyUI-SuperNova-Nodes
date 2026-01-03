import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// --- 1. 声音配置 ---
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

// --- 2. 发送控制 ---
function sendControl(node, action) {
    api.fetchApi("/supernova/preview_control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: node.id, action: action })
    });
}

// --- 3. 计算组件占用的顶部高度 ---
function getWidgetHeight(node) {
    // 基础高度 (标题栏等)
    let height = 30; 
    if (node.widgets) {
        for (const w of node.widgets) {
            // 跳过隐藏组件
            if (w.type === "HIDDEN") continue;
            // 获取组件高度
            const h = w.computeSize ? w.computeSize(node.size[0])[1] : 20;
            height += h + 10; // 增加间距
        }
    }
    return height;
}

app.registerExtension({
    name: "Supernova.PreviewPause",

    setup() {
        api.addEventListener("supernova_preview_data", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node_id);
            if (node) {
                playSound();
                if (detail.images && detail.images.length > 0) {
                    loadImageToNode(node, detail.images[0]);
                }
            }
        });
    },

    async nodeCreated(node) {
        if (node.comfyClass === "PreviewAndPause") {
            // 初始默认尺寸
            node.setSize([300, 400]); 

            // 添加按钮
            node.addWidget("button", "✅ CONTINUE", null, () => sendControl(node, "continue"));
            node.addWidget("button", "⛔ STOP", null, () => sendControl(node, "stop"));
            
            // --- 核心修改：添加最小尺寸限制 ---
            const origOnResize = node.onResize;
            node.onResize = function(size) {
                // 1. 定义最小宽度 (保证按钮能放下)
                const minWidth = 256; 
                
                // 2. 定义最小高度 (按钮高度 + 至少100px看图区域)
                const widgetsHeight = getWidgetHeight(this);
                const minHeight = widgetsHeight + 256;

                // 3. 强制修正尺寸
                if (size[0] < minWidth) size[0] = minWidth;
                if (size[1] < minHeight) size[1] = minHeight;

                // 4. 执行原生逻辑
                if (origOnResize) origOnResize.apply(this, arguments);
                
                // 5. 触发重绘
                this.setDirtyCanvas(true, true);
            };
        }
    }
});

// --- 4. 加载图片逻辑 ---
function loadImageToNode(node, imgData) {
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

    // --- 5. 绘制逻辑 (Aspect Fit) ---
    node.onDrawBackground = function(ctx) {
        if (!this.imgs || this.imgs.length === 0) return;

        const image = this.imgs[0];
        if (!image.complete || image.naturalWidth === 0) return;

        // 计算可用绘图区域
        const topPadding = getWidgetHeight(this); 
        const w = this.size[0];
        const h = this.size[1] - topPadding; 

        if (h <= 0) return;

        // 保持比例缩放
        const imgW = image.naturalWidth;
        const imgH = image.naturalHeight;
        const scale = Math.min(w / imgW, h / imgH);
        
        const drawW = imgW * scale;
        const drawH = imgH * scale;

        // 居中
        const drawX = (w - drawW) / 2;
        const drawY = topPadding + (h - drawH) / 2;

        ctx.save();
        ctx.drawImage(image, drawX, drawY, drawW, drawH);
        ctx.restore();
    };
}