import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ============================================================
// 1. 通用工具函数 (Helpers)
// ============================================================

const soundUrl = "../audio/sound.mp3";
const notificationSound = new Audio(soundUrl);

// 播放节点就绪提示音
function playSound() {
    try {
        notificationSound.currentTime = 0;
        notificationSound.volume = 0.5;
        notificationSound.play().catch(() => { });
    } catch (e) {
        console.error("[Supernova] Audio error:", e);
    }
}

// 构建图片访问 URL
function getImageUrl(data) {
    if (!data) return null;
    return api.apiURL(`/view?filename=${encodeURIComponent(data.filename)}&type=${data.type}&subfolder=${data.subfolder}${app.getPreviewFormatParam()}${app.getRandParam()}`);
}

// 动态计算顶部组件占用的高度，确保图片显示区域位置准确
function getWidgetHeight(node) {
    let height = 30;
    if (node.widgets) {
        for (const w of node.widgets) {
            if (w.type === "HIDDEN" || w.type === "converted-widget" || w.hidden) continue;
            const h = w.computeSize ? w.computeSize(node.size[0])[1] : 20;
            height += h + 10;
        }
    }
    return height;
}

// 自定义按钮重命名弹窗
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
    const input = document.createElement("input");
    input.type = "text"; input.value = defaultValue;
    Object.assign(input.style, { width: "100%", padding: "8px", margin: "10px 0", borderRadius: "4px", border: "1px solid #666", backgroundColor: "#222", color: "#fff", boxSizing: "border-box" });
    const btnContainer = document.createElement("div");
    btnContainer.style.display = "flex"; btnContainer.style.justifyContent = "flex-end"; btnContainer.style.gap = "10px";
    const btnStyle = { padding: "6px 15px", borderRadius: "4px", border: "none", cursor: "pointer", fontWeight: "bold" };
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel"; Object.assign(cancelBtn.style, btnStyle, { backgroundColor: "#555", color: "#fff" });
    const okBtn = document.createElement("button");
    okBtn.textContent = "Save"; Object.assign(okBtn.style, btnStyle, { backgroundColor: "#2366b8", color: "#fff" });
    const close = () => document.body.removeChild(overlay);
    cancelBtn.onclick = close;
    const submit = () => { onOk(input.value); close(); };
    okBtn.onclick = submit;
    input.onkeydown = (e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") close(); };
    btnContainer.appendChild(cancelBtn); btnContainer.appendChild(okBtn);
    box.appendChild(titleEl); box.appendChild(input); box.appendChild(btnContainer);
    overlay.appendChild(box); document.body.appendChild(overlay);
    setTimeout(() => input.focus(), 50);
}

// ============================================================
// 2. 节点交互核心逻辑
// ============================================================

// 发送流程控制指令
function sendControl(node, action) {
    api.fetchApi("/supernova/preview_control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: node.id, action: action }) });
}

// 处理选择并随机化种子以强制刷新缓存
async function sendSelection(node, value) {
    const idWidget = node.widgets.find(w => w.name === "compare_id" || w.name === "seed");
    if (idWidget) idWidget.value = Math.floor(Math.random() * 1000000000000);
    try {
        await api.fetchApi("/supernova/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: node.id, selection: value }) });
    } catch (error) { console.error(error); }
}

// 通用图片预览加载逻辑
// 处理 PreviewAndPause 节点的图片加载与绘制
function loadPreviewImageToNode(node, imgData) {
    // 构造图片请求参数，加入时间戳防止浏览器缓存
    const params = new URLSearchParams({ filename: imgData.filename, type: imgData.type, subfolder: imgData.subfolder || "" });
    const url = api.apiURL(`/view?${params.toString()}&t=${Date.now()}`);
    const img = new Image(); // 创建新图片对象
    img.src = url; // 设置图片来源

    img.onload = () => {
        node.imgs = [img]; // 加载成功后存入节点的图片数组
        node.imgDim = `${img.naturalWidth}x${img.naturalHeight}`; // 【新增】捕获并存储图片的原始分辨率
        node.setDirtyCanvas(true, true); // 请求画布重绘
    };

    // 重写背景绘制函数
    node.onDrawBackground = function (ctx) {
        if (!this.imgs || this.imgs.length === 0) return; // 如果没有图片则跳过
        const image = this.imgs[0]; // 获取当前图片
        const topPadding = getWidgetHeight(this); // 计算顶部按钮占用的高度
        const footerHeight = 15; // 为底部分辨率文字留出的安全间距

        const w = this.size[0]; // 节点当前宽度
        const h = this.size[1] - topPadding - footerHeight; // 扣除按钮和底部文字后的图片可用高度

        if (h <= 0) return; // 如果高度不足则不绘制

        // 计算图片保持比例缩放后的尺寸
        const scale = Math.min(w / image.naturalWidth, h / image.naturalHeight);
        const drawW = image.naturalWidth * scale; // 绘制宽度
        const drawH = image.naturalHeight * scale; // 绘制高度

        // --- 核心计算：图片的起始 Y 坐标 ---
        const drawX = (w - drawW) / 2;
        const drawY = topPadding + (h - drawH) / 2;

        ctx.save(); // 保存当前绘图状态

        // 绘制图片(1.0版)
        // ctx.drawImage(image, (w - drawW) / 2, topPadding + (h - drawH) / 2, drawW, drawH);

        // 绘制图片
        ctx.drawImage(image, drawX, drawY, drawW, drawH);

        // 【新增】在节点底部绘制分辨率文字
        if (this.imgDim) {
            ctx.fillStyle = "#AAA"; // 设置文字颜色为深灰色
            ctx.font = "11px Arial"; // 设置文字大小和字体
            ctx.textAlign = "center"; // 文字水平居中

            //textBaseline = "bottom" 的写法
            //ctx.textBaseline = "bottom"; // 文字以底部为基准线
            //ctx.fillText(this.imgDim, w / 2, this.size[1] - 2); // 在节点底部中心绘制文字 // w / 2 是水平居中 // this.size[1] - 5 代表：从节点的最底端往上移动 5 像素

            //textBaseline = "top" 的写法
            ctx.textBaseline = "top"; // 让文字从图片底部往下排
            // 文字的坐标 = 图片的底部(drawY + drawH) + 5像素的间隙
            // 这样无论图片多大、节点框多长，文字永远在图片屁股后面
            ctx.fillText(this.imgDim, w / 2, drawY + drawH + 3);
        }

        ctx.restore(); // 恢复状态
    };
}

// ============================================================
// 3. 注册扩展
// ============================================================

app.registerExtension({
    name: "Supernova.Nodes",

    async beforeRegisterNodeDef(nodeType, nodeData) {

        // ============================================================
        // [A] ImageCompareAndSelect (双图对比与选择节点核心逻辑)
        // ============================================================
        if (nodeData.name === "ImageCompareAndSelect") {
            // 获取并暂存 LiteGraph 原生的节点创建函数
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            // 重写节点创建后的执行逻辑
            nodeType.prototype.onNodeCreated = function () {
                // 执行原生的创建逻辑，确保基础功能正常
                if (onNodeCreated) onNodeCreated.apply(this, arguments);

                // 定义内部函数：通过属性修改彻底让指定组件在 UI 上消失
                const hideWidget = (name) => {
                    const w = this.widgets?.find(w => w.name === name); // 寻找目标组件
                    if (w) {
                        w.type = "HIDDEN";     // 设置类型为隐藏
                        w.hidden = true;       // 标记为隐藏状态
                        w.computeSize = () => [0, -4]; // 强制物理高度为负，抹除占位
                        w.draw = () => { };    // 清空绘制函数，防止渲染残影
                    }
                };
                hideWidget("compare_id"); // 隐藏用于刷新的 compare_id
                hideWidget("seed");       // 隐藏可能存在的 seed 组件

                // 初始化节点内部存储图片的容器
                this.imgs = { 1: null, 2: null };
                // 初始化对比分割线的比例位置（0.5 代表中间）
                this.splitX = 0.5;
                // 初始化拖拽状态标识
                this.dragging = false;

                // 确保节点属性对象存在
                if (!this.properties) this.properties = {};
                // 初始化鼠标跟随功能，默认设为关闭
                if (this.properties.mouseFollow === undefined) this.properties.mouseFollow = false;
                // 初始化按钮标签存储对象，用于持久化自定义改名
                if (!this.properties.labels) this.properties.labels = {};

                // 定义需要创建的功能性选择按钮
                const btns = [{ l: "▶️ Image 1", v: "1" }, { l: "▶️ Image 2", v: "2" }, { l: "⛔ STOP", v: "stop" }];
                // 暂存当前节点已有的组件（如从 Python 加载的）
                const existing = [...(this.widgets || [])];
                // 清空组件列表，准备按正确顺序重新排列
                this.widgets = [];
                // 遍历并添加功能按钮
                btns.forEach(b => {
                    // 读取保存的标签名，若无则使用默认名
                    const labelText = this.properties.labels[b.v] || b.l;
                    // 向节点添加按钮组件，并绑定点击发送选择的逻辑
                    const w = this.addWidget("button", labelText, null, () => sendSelection(this, b.v));
                    w.name = labelText; // 设置组件内部名称
                    w.label = labelText; // 设置组件显示标签
                    w.supernovaValue = b.v; // 绑定业务逻辑值
                    w.supernovaDefaultLabel = b.l; // 记录初始默认标签，用于恢复
                });
                // 将之前暂存的非功能按钮组件（如隐藏的 id）放回列表末尾
                existing.forEach(w => { if (!w.supernovaValue) this.widgets.push(w); });

                // 设置节点创建时的默认显示尺寸
                this.setSize([256, 350]);
            };

            // --- 核心渲染函数：处理图片对比、分割线及交互滑块 ---
            nodeType.prototype.onDrawForeground = function (ctx) {
                // 如果节点被折叠，则跳过绘制
                if (this.flags.collapsed) return;
                // 筛选当前已加载成功的图片 ID
                const activeIds = [1, 2].filter(id => !!this.imgs[id]);
                // 如果一张图都没有，直接退出
                if (activeIds.length === 0) return;

                const nodeW = this.size[0]; // 获取节点宽度
                const topMargin = getWidgetHeight(this); // 计算顶部组件占据的高度高度
                const drawH = this.size[1] - topMargin - 15; // 计算图片实际可绘制高度
                const sx = this.splitX * nodeW; // 根据比例计算分割线的绝对像素坐标

                ctx.save(); // 保存当前绘图上下文状态
                // 开启路径并创建一个矩形裁剪区域，防止图片画到节点边框外面
                ctx.beginPath(); ctx.rect(0, topMargin, nodeW, drawH); ctx.clip();

                // 定义内部绘图函数：处理图片等比缩放与居中裁剪
                const drawComp = (img, clipX, clipY, clipW, clipH) => {
                    if (!img || clipW <= 0) return; // 图片无效或裁剪宽度为0则跳过
                    ctx.save(); ctx.beginPath(); ctx.rect(clipX, clipY, clipW, clipH); ctx.clip(); // 再次裁剪单张图范围
                    const aspect = img.naturalWidth / img.naturalHeight; // 计算图片原始宽高比
                    const areaAspect = nodeW / drawH; // 计算绘制区域宽高比
                    let rw, rh;
                    // 根据比例决定是以宽度为准还是以高度为准进行缩放
                    if (aspect > areaAspect) { rw = nodeW; rh = nodeW / aspect; } else { rh = drawH; rw = drawH * aspect; }
                    // 在计算出的居中位置绘制图片
                    ctx.drawImage(img, (nodeW - rw) / 2, topMargin + (drawH - rh) / 2, rw, rh);
                    ctx.restore(); // 恢复到单图裁剪前的状态
                };

                // 情况1：只有一张图片时，全屏绘制该图片
                if (activeIds.length === 1) {
                    drawComp(this.imgs[activeIds[0]], 0, topMargin, nodeW, drawH);
                } else {
                    // 情况2：两张图都有，进行对比绘制
                    drawComp(this.imgs[2], 0, topMargin, nodeW, drawH); // 先画底层图（图2）
                    drawComp(this.imgs[1], 0, topMargin, sx, drawH);    // 再画顶层图（图1），宽度截断到 sx

                    // 绘制中间的白色垂直分割线
                    ctx.strokeStyle = "rgba(255, 255, 255, 0.5)"; // 设置半透明白色
                    ctx.lineWidth = 2; // 线宽 2px
                    ctx.beginPath(); ctx.moveTo(sx, topMargin); ctx.lineTo(sx, topMargin + drawH); ctx.stroke();

                    // --- 绘制交互手柄：< | > 样式 ---
                    const labelL = "<", labelR = ">"; // 定义手柄符号
                    const gap = 6, padding = 10, btnH = 24; // 定义间距、内边距和手柄高度
                    ctx.font = "bold 15px Arial"; // 设置字体

                    const wL = ctx.measureText(labelL).width; // 测量左符号宽度
                    const wR = ctx.measureText(labelR).width; // 测量右符号宽度
                    const btnW = wL + wR + gap + padding;    // 计算手柄背景总宽度
                    const btnY = topMargin + drawH / 2;      // 计算手柄垂直中心点
                    const xL = sx - (gap / 2 + wL / 2);      // 计算左符号绘制 X 坐标
                    const xR = sx + (gap / 2 + wR / 2);      // 计算右符号绘制 X 坐标

                    ctx.save(); // 保存状态用于手柄绘制
                    // if (!isNaN(btnW)) { // 确保数值有效，防止绘图报错卡死
                    //     ctx.beginPath();
                    //     // 绘制圆角矩形背景
                    //     ctx.roundRect(sx - btnW / 2, btnY - btnH / 2, btnW, btnH, 6);
                    //     ctx.fillStyle = "rgba(0, 0, 0, 0.5)"; // 深色半透明背景
                    //     ctx.fill();
                    //     ctx.strokeStyle = "rgba(255, 255, 255, 0.3)"; // 浅灰色边框
                    //     ctx.lineWidth = 1.5;
                    //     ctx.stroke();
                    // }

                    // 设置文字对齐方式为中心对齐
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    ctx.lineJoin = "round"; // 文字折角平滑处理

                    // A层：绘制文字的黑色描边，增加辨识度
                    ctx.strokeStyle = "rgba(0, 0, 0, 0.3)";
                    ctx.lineWidth = 3;
                    ctx.strokeText(labelL, xL, btnY);
                    ctx.strokeText(labelR, xR, btnY);

                    // B层：绘制文字的白色填充，叠在描边上方
                    ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
                    ctx.fillText(labelL, xL, btnY);
                    ctx.fillText(labelR, xR, btnY);
                    ctx.restore(); // 恢复手柄绘制前的状态
                }
                ctx.restore(); // 恢复最开始保存的全局上下文状态
            };

            // 监听鼠标按下事件
            nodeType.prototype.onMouseDown = function (event, pos) {
                const topMargin = getWidgetHeight(this); // 获取图片区域起始位置
                // 判断点击位置是否在图片显示区域内
                if (pos[1] >= topMargin && pos[1] <= this.size[1] - 15) {
                    this.dragging = true; // 开启拖拽状态
                    // 立即更新分割线比例
                    this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
                    this.setDirtyCanvas(true, false); // 请求刷新画布重绘
                    return true; // 拦截事件，不让画布移动
                }
                return false; // 点击其他地方，交还控制权给画布
            };

            // 监听鼠标移动事件
            nodeType.prototype.onMouseMove = function (event, pos) {
                const topMargin = getWidgetHeight(this);
                const isOverImg = pos[1] >= topMargin && pos[1] <= this.size[1] - 15;
                // 触发条件：(开启了跟随模式 且 鼠标在图上 且 没点按键) 或 (正在拖拽中)
                if ((this.properties.mouseFollow && isOverImg && event.buttons === 0) || this.dragging) {
                    this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
                    this.setDirtyCanvas(true, false); // 刷新画面
                }
            };

            // 监听鼠标抬起事件
            nodeType.prototype.onMouseUp = function () { this.dragging = false; };

            // 监听节点尺寸改变事件
            nodeType.prototype.onResize = function (size) {
                const minW = 230; // 设定最小宽度
                const minH = getWidgetHeight(this) + 200; // 根据组件高度计算最小节点高度
                if (size[0] < minW) size[0] = minW; // 强制宽度限制
                if (size[1] < minH) size[1] = minH; // 强制高度限制
                this.setDirtyCanvas(true, true); // 刷新画布，重新布局
            };
        }
        //----------------ImageCompareAndSelect结束-------------------

        // --- MultiImageComparer (四图对比节点) 原型定义 ---
        if (nodeData.name === "MultiImageComparer") {
            // 获取并暂存原生的节点创建函数
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                // 执行基础创建逻辑
                if (onNodeCreated) onNodeCreated.apply(this, arguments);

                // 初始化节点属性
                if (!this.properties) this.properties = {};
                this.properties.mouseFollow = false; // 默认关闭鼠标跟随模式

                // 设置 UI 布局基础参数（用于后续缩放计算）
                this.baseWidth = 270;        // 基础参考宽度
                this.boxTitleHeight = 30;    // 标题栏高度
                this.boxSlotsHeight = 90;    // 输入插槽区域高度
                this.baseFooterHeight = 30;  // 底部信息栏基础高度

                // 设置节点的默认初始尺寸
                this.setSize([270, 320]);

                // 初始化图片存储对象及分辨率文本存储
                this.imgs = { 1: null, 2: null, 3: null, 4: null };
                this.imgDims = { 1: "", 2: "", 3: "", 4: "" };

                // 初始化分割线位置比例 (0.5, 0.5 代表中心十字)
                this.splitX = 0.5; this.splitY = 0.5;
                this.dragging = false; // 拖拽状态标识
            };

            // 核心功能：当后端节点执行完毕并返回结果时，触发此函数加载图片
            nodeType.prototype.onExecuted = function (message) {
                // 定义内部图片加载工具函数
                const load = (key, list) => {
                    if (list?.length > 0) {
                        const img = new Image();
                        // 图片异步加载成功后的回调
                        img.onload = () => {
                            // 记录图片的原始分辨率，例如 "1024x1024"
                            this.imgDims[key] = `${img.naturalWidth}x${img.naturalHeight}`;
                            this.setDirtyCanvas(true, true); // 加载完成后刷新画面
                        };
                        // 从消息数据中获取 URL 并开始加载
                        img.src = getImageUrl(list[0]);
                        this.imgs[key] = img;
                    } else {
                        // 如果后端未提供该插槽的图片，则清空状态
                        this.imgs[key] = null; this.imgDims[key] = "";
                    }
                };
                // 尝试加载 4 个插槽可能存在的图片
                load(1, message.images_1); load(2, message.images_2);
                load(3, message.images_3); load(4, message.images_4);
            };

            // 核心渲染函数：在 Canvas 上绘制图片布局、分割线和信息栏
            nodeType.prototype.onDrawForeground = function (ctx) {
                if (this.flags.collapsed) return; // 节点折叠时不绘制

                const nodeW = this.size[0]; const nodeH = this.size[1];
                // 计算当前节点相对于基础宽度的缩放比例
                const scale = nodeW / this.baseWidth;
                // 动态计算底部栏高度
                const footerH = this.baseFooterHeight * scale;
                // 图片显示区域的顶部起点 Y 坐标
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3W = nodeW;
                // 图片显示区域的实际可用高度
                const b3H = nodeH - b3Y - footerH;

                // 获取当前已有效加载的图片 ID 列表
                const activeIds = [1, 2, 3, 4].filter(id => !!this.imgs[id]);
                if (activeIds.length === 0) return;

                ctx.save();
                // 内部函数：在指定的裁剪区域内，等比缩放并居中绘制单张图片
                const drawComp = (img, clipX, clipY, clipW, clipH) => {
                    if (!img || clipW <= 0 || clipH <= 0) return;
                    ctx.save(); ctx.beginPath(); ctx.rect(clipX, clipY, clipW, clipH); ctx.clip();
                    const aspect = img.naturalWidth / img.naturalHeight;
                    const areaAspect = b3W / b3H; // 注意：缩放参考系为整个图片显示区，以实现对齐
                    let fw, fh;
                    if (aspect > areaAspect) { fw = b3W; fh = b3W / aspect; } else { fh = b3H; fw = b3H * aspect; }
                    // 居中绘制计算
                    ctx.drawImage(img, (b3W - fw) / 2, b3Y + (b3H - fh) / 2, fw, fh);
                    ctx.restore();
                };

                // 根据 split 比例计算分割线的实际像素坐标
                const sx = this.splitX * b3W; const sy = b3Y + (this.splitY * b3H);
                const count = activeIds.length;

                // --- 自动布局逻辑：根据图片数量决定划分方式 ---
                if (count === 1) {
                    // 1张图：铺满全屏
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, b3W, b3H);
                }
                else if (count === 2) {
                    // 2张图：左右对比
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, b3H);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, b3H);
                }
                else if (count === 3) {
                    // 3张图：上二下一
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[2]], 0, sy, b3W, b3H - (sy - b3Y));
                }
                else if (count === 4) {
                    // 4张图：田字格布局
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[2]], 0, sy, sx, b3H - (sy - b3Y));
                    drawComp(this.imgs[activeIds[3]], sx, sy, b3W - sx, b3H - (sy - b3Y));
                }

                // --- 绘制经典的十字分割线与中心手柄 ---
                if (count > 1) {
                    ctx.strokeStyle = "rgba(255,255,255,0.4)"; ctx.lineWidth = 1.5; ctx.beginPath();
                    // 垂直线
                    ctx.moveTo(sx, b3Y); ctx.lineTo(sx, b3Y + b3H);
                    // 如果超过2张图，绘制水平线
                    if (count > 2) { ctx.moveTo(0, sy); ctx.lineTo(b3W, sy); }
                    ctx.stroke();
                    // 绘制中心的小圆点手柄
                    ctx.fillStyle = "rgba(255, 255, 255, 0.5)"; ctx.beginPath(); ctx.arc(sx, sy, 4, 0, Math.PI * 2); ctx.fill();
                    ctx.strokeStyle = "rgba(0, 0, 0, 0.25)"; ctx.lineWidth = 1.3; ctx.stroke();
                }

                // --- 绘制底部信息栏（分辨率文字） ---
                ctx.fillStyle = "#ffffffc0";
                ctx.font = `${Math.max(8, 11 * scale)}px Arial`;
                ctx.textAlign = "center";
                // 拼接文字，例如 "1:512x512 | 2:1024x1024"
                let info = activeIds.map(id => `${id}:${this.imgDims[id]}`).join(" | ");
                ctx.fillText(info, nodeW / 2, nodeH - (footerH / 2) + 4);
                ctx.restore();
            };

            // 监听节点尺寸改变事件
            nodeType.prototype.onResize = function (size) {
                const minW = 280; // 设定最小宽度
                const minH = getWidgetHeight(this) + 280; // 根据组件高度计算最小节点高度
                if (size[0] < minW) size[0] = minW; // 强制宽度限制
                if (size[1] < minH) size[1] = minH; // 强制高度限制
                this.setDirtyCanvas(true, true); // 刷新画布，重新布局
            };

            // 监听鼠标按下事件：判断点击是否在图片区，开启拖拽
            nodeType.prototype.onMouseDown = function (event, pos) {
                const scale = this.size[0] / this.baseWidth;
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3Bottom = this.size[1] - (this.baseFooterHeight * scale);
                // 仅在图片显示区域响应鼠标点击
                if (pos[1] >= b3Y && pos[1] <= b3Bottom) {
                    this.dragging = true;
                    // 记录点击位置对应的比例
                    this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
                    this.splitY = Math.max(0, Math.min(1, (pos[1] - b3Y) / (b3Bottom - b3Y)));
                    this.setDirtyCanvas(true, false); return true;
                } return false;
            };

            // 监听鼠标移动：处理“鼠标跟随”或“拖拽中”的分割线更新
            nodeType.prototype.onMouseMove = function (event, pos) {
                const scale = this.size[0] / this.baseWidth;
                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3H = this.size[1] - b3Y - (this.baseFooterHeight * scale);
                const isOver = pos[1] >= b3Y && pos[1] <= b3Y + b3H;

                // 触发条件：(跟随模式开启 且 鼠标滑过图片区 且 无按键按下) 或 (正在手动拖拽)
                if ((this.properties.mouseFollow && isOver && event.buttons === 0) || this.dragging) {
                    this.splitX = Math.max(0, Math.min(1, pos[0] / this.size[0]));
                    this.splitY = Math.max(0, Math.min(1, (pos[1] - b3Y) / b3H));
                    this.setDirtyCanvas(true, false);
                }
            };

            // 鼠标抬起：结束拖拽
            nodeType.prototype.onMouseUp = function () { this.dragging = false; };
        }
    },

    setup() {
        // 全局事件监听：处理 Preview & Pause 的实时图片推送
        api.addEventListener("supernova_preview_data", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node_id);
            if (node) { playSound(); if (detail.images?.length > 0) loadPreviewImageToNode(node, detail.images[0]); }
        });

        // 全局事件监听：处理 Compare & Select 的图片推送
        api.addEventListener("supernova_preview_update", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node_id);
            if (node && node.comfyClass === "ImageCompareAndSelect") {
                const load = (key, list) => {
                    if (list?.length > 0) {
                        const img = new Image();
                        img.onload = () => { node.imgs[key] = img; node.setDirtyCanvas(true, true); };
                        img.src = getImageUrl(list[0]);
                    }
                };
                load(1, detail.images["1"]); load(2, detail.images["2"]);
            }
        });

        //--------------------PreviewAndPause节点监听-------------------------------
        // 监听节点执行事件
        api.addEventListener("executing", ({ detail }) => {
            if (!detail) return; // 如果没有节点ID则忽略
            const node = app.graph.getNodeById(detail); // 根据ID获取画布上的节点对象
            // 当 PreviewAndPause 节点开始重新执行时
            if (node && node.comfyClass === "PreviewAndPause") {
                node.imgs = []; // 清空当前的图片缓存
                node.imgDim = ""; // 清空之前记录的分辨率文字
                node.setDirtyCanvas(true, true); // 立即刷新画布，清除界面残影
            }
        });
    },

    async nodeCreated(node) {
        // Preview & Pause 节点的初始化逻辑
        if (node.comfyClass === "PreviewAndPause") {
            // 设置节点诞生时的初始尺寸 [宽度, 高度]
            node.setSize([270, 320]);

            // 添加“继续”按钮，点击时向后端发送继续信号
            node.addWidget("button", "✅ CONTINUE", null, () => sendControl(node, "continue"));
            // 添加“停止”按钮，点击时向后端发送停止信号
            node.addWidget("button", "⛔ STOP", null, () => sendControl(node, "stop"));

            // --- 核心修改：加入节点框最小值限制 ---
            const origOnResize = node.onResize; // 备份 LiteGraph 原始的缩放函数
            node.onResize = function (size) {
                // 定义硬性限制的最小宽度
                const minW = 270;
                // 动态获取当前按钮组件占用的高度
                const widgetsHeight = getWidgetHeight(this);
                // 定义最小高度限制（按钮总高 + 200像素的图片预览及分辨率显示空间）
                const minH = widgetsHeight + 200;

                // 强制尺寸约束：若用户缩放尺寸小于阈值，则自动弹回最小值
                if (size[0] < minW) size[0] = minW;
                if (size[1] < minH) size[1] = minH;

                // 调用原生的缩放逻辑以确保引擎内部状态同步
                if (origOnResize) origOnResize.apply(this, arguments);

                // 每次缩放后强制重绘画布，保证图片和分辨率文字位置实时对齐
                this.setDirtyCanvas(true, true);
            };
        }
        //---------------------PreviewAndPause结束--------------------------

        // 双图/四图节点的右键菜单增强（跟随、重命名）
        if (node.comfyClass === "ImageCompareAndSelect" || node.comfyClass === "MultiImageComparer") {
            const origMenu = node.getExtraMenuOptions;
            node.getExtraMenuOptions = function (_, options) {
                if (origMenu) origMenu.apply(this, arguments);
                options.push({
                    content: (this.properties.mouseFollow ? "✔️ " : "") + "🖱️ 鼠标跟随 (Mouse Follow)",
                    callback: () => { this.properties.mouseFollow = !this.properties.mouseFollow; this.setDirtyCanvas(true); }
                });
                if (this.comfyClass === "ImageCompareAndSelect") {
                    options.push(null, { content: "🖊️ 重命名按钮 (Rename Buttons)", disabled: true });
                    this.widgets?.forEach(w => {
                        if (w.supernovaValue) {
                            const cur = w.name || w.label || "Button";
                            options.push({
                                content: `   📝 重命名 "${cur}"`, callback: () => {
                                    showRenameDialog(`重命名 "${cur}"`, cur, (newName) => {
                                        if (newName !== null) {
                                            const final = newName.trim() === "" ? w.supernovaDefaultLabel : newName;
                                            w.name = final; w.label = final; this.properties.labels[w.supernovaValue] = final;
                                            app.graph.setDirtyCanvas(true, true);
                                        }
                                    });
                                }
                            });
                        }
                    });
                }
            };
            const origConf = node.onConfigure;
            node.onConfigure = function () {
                if (origConf) origConf.apply(this, arguments);
                if (this.comfyClass === "ImageCompareAndSelect" && this.properties?.labels) {
                    this.widgets?.forEach(w => { if (w.supernovaValue && this.properties.labels[w.supernovaValue]) { w.name = this.properties.labels[w.supernovaValue]; w.label = w.name; } });
                }
            };
        }
    }
});