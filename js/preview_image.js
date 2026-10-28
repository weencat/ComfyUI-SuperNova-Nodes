import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// 注入官方 2.0 遮罩按钮专用的 SVG 图标
const OFFICIAL_MASK_SVG = `
<svg width="1.2em" height="1.2em" class="size-4" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6.05048 2C5.52055 7.29512 9.23033 10.4722 14 9.94267" stroke="currentColor" stroke-width="1.3"></path>
  <path d="M6.5 5.5L10 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"></path>
  <path d="M8 8L12.5 3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="square"></path>
  <path d="M10.5 9.5L14 6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"></path>
  <path d="M7.99992 14.6667C11.6818 14.6667 14.6666 11.6819 14.6666 8.00004C14.6666 4.31814 11.6818 1.33337 7.99992 1.33337C4.31802 1.33337 1.33325 4.31814 1.33325 8.00004C1.33325 11.6819 4.31802 14.6667 7.99992 14.6667Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"></path>
</svg>
`;

// 遮罩画笔容器与按钮样式
const style = document.createElement('style');
style.innerHTML = `
    .supernova-preview-container {
        position: relative;
        width: 100%;
        height: 100%;
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
        margin-top: 5px;
        border-radius: 8px;
    }
    .supernova-preview-container img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
        user-select: none;
        pointer-events: none;
    }
    .supernova-official-mask-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        height: 32px;
        min-height: 32px;
        width: 32px;
        display: none;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        border: none;
        background: rgba(36, 36, 36, 0.9);
        color: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.3);
        cursor: pointer;
        padding: 6px;
        z-index: 100;
        transition: all 0.2s ease-in-out;
    }
    .supernova-preview-container:hover .supernova-official-mask-btn {
        display: flex;
    }
    .supernova-official-mask-btn:hover {
        background: #2563eb;
        transform: scale(1.05);
    }
`;
document.head.appendChild(style);

/**
 * 安全唤起 MaskEditor（点击时动态喂给 node.imgs）
 */
async function triggerNodes2MaskEditor(node, imgElement) {
    if (!imgElement || !imgElement.src || !imgElement.complete || imgElement.naturalWidth === 0) {
        alert("图片尚未加载完成，请稍候。");
        return;
    }

    // 在点击唤起的瞬间挂载 node.imgs，提供给遮罩编辑器提取像素
    node.imgs = [imgElement];
    node.imageIndex = 0;

    // 途径 1：Nodes 2.0 Command 系统
    try {
        const commandSystem = 
            window.comfyAPI?.command?.execute || 
            app.extensionManager?.commandStore?.execute ||
            app.command?.execute;

        if (typeof commandSystem === "function") {
            const success = await commandSystem("comfy.maskeditor.open", { node: node });
            if (success !== false) return;
        }
    } catch (err) {}

    // 途径 2：经典 ComfyApp 通道
    try {
        const ComfyAppClass = window.ComfyApp || app.constructor;
        if (ComfyAppClass && typeof ComfyAppClass.copyToClipspace === "function") {
            ComfyAppClass.copyToClipspace(node);
            ComfyAppClass.clipspace_return_node = node;
            if (typeof ComfyAppClass.open_maskeditor === "function") {
                ComfyAppClass.open_maskeditor();
                return;
            }
        }

        if (typeof app.copyToClipspace === "function") {
            app.copyToClipspace(node);
            app.clipspace_return_node = node;
            if (typeof app.open_maskeditor === "function") {
                app.open_maskeditor();
                return;
            }
        }
    } catch (e) {
        console.error("遮罩通道异常:", e);
    }
}

app.registerExtension({
    name: "supernova.PreviewImage",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        
        // ====================================================================
        // 1. LoadImageUnified: 原生 Nodes 2.0
        // ====================================================================
        if (nodeData.name === "LoadImageUnified") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const imageWidget = this.widgets?.find(w => w.name === "image");
                if (imageWidget) {
                    const originalCallback = imageWidget.callback;
                    imageWidget.callback = function (value) {
                        if (value && value.endsWith("[output]") && !value.includes("/")) {
                            const pureName = value.replace(" [output]", "");
                            const fullMatch = imageWidget.options?.values?.find(
                                v => v.endsWith("/" + pureName + " [output]") || v.endsWith(pureName + " [output]")
                            );
                            if (fullMatch && fullMatch !== value) {
                                imageWidget.value = fullMatch;
                                value = fullMatch;
                            }
                        }
                        if (originalCallback) return originalCallback.apply(this, arguments);
                    };
                }
                return r;
            };
        }

        // ====================================================================
        // 2. LoadImageFromTemp: 解决双预览图并保留遮罩能力
        // ====================================================================
        if (nodeData.name === "LoadImageFromTemp") {
            // 【核心修复 1】：拦截 1.0 LiteGraph 的原生背景图片绘制，防止画布在底部画出第二张图
            const origDrawBackground = nodeType.prototype.onDrawBackground;
            nodeType.prototype.onDrawBackground = function (ctx) {
                // 临时隐藏 node.imgs，阻止底层 Canvas 重绘第二张原生图
                const backupImgs = this.imgs;
                this.imgs = undefined;
                let r;
                if (origDrawBackground) {
                    r = origDrawBackground.apply(this, arguments);
                }
                this.imgs = backupImgs;
                return r;
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                let currentAspectRatio = 0;
                let hasContent = false;
                let previewHeight = 50;

                this.pasteFromClipspace = function (clipspace) {
                    if (clipspace && clipspace.filename) {
                        const fullClip = `clipspace/${clipspace.filename}`;
                        const imageWidget = node.widgets?.find(w => w.name === "image");
                        if (imageWidget) {
                            imageWidget.value = fullClip;
                            if (imageWidget.callback) imageWidget.callback(fullClip);
                        }
                    }
                };

                const previewElement = document.createElement("div");
                previewElement.className = "supernova-preview-container";

                const imgNode = document.createElement("img");
                imgNode.crossOrigin = "anonymous";
                imgNode.style.display = "none";
                previewElement.appendChild(imgNode);

                const maskBtn = document.createElement("button");
                maskBtn.className = "supernova-official-mask-btn";
                maskBtn.title = "编辑或遮罩图片";
                maskBtn.setAttribute("aria-label", "编辑或遮罩图片");
                maskBtn.innerHTML = OFFICIAL_MASK_SVG;

                maskBtn.addEventListener("mousedown", (e) => e.stopPropagation());
                maskBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    triggerNodes2MaskEditor(node, imgNode);
                });
                previewElement.appendChild(maskBtn);

                const widget = this.addDOMWidget("image_preview", "preview", previewElement, {
                    serialize: false,
                    hideOnZoom: false
                });

                const calculateHeaderHeight = () => {
                    const originalCompute = widget.computeSize;
                    widget.computeSize = () => [node.size[0], 0];
                    const baseSize = node.computeSize([node.size[0], 0]);
                    widget.computeSize = originalCompute;
                    return baseSize[1];
                };

                widget.computeSize = (width) => [width, previewHeight];

                const fitNodeToContent = () => {
                    if (!hasContent || currentAspectRatio === 0) return;
                    const currentWidth = node.size[0];
                    const headerHeight = calculateHeaderHeight();
                    const idealImgHeight = currentWidth / currentAspectRatio;
                    previewHeight = idealImgHeight;
                    // 精确设定尺寸，不给第二张图留出多余空白
                    node.setSize([currentWidth, headerHeight + idealImgHeight + 10]);
                    node.graph?.setDirtyCanvas(true, true);
                };

                const updatePreview = (url) => {
                    if (!url) return;
                    if (url.includes("/view?")) url += "&t=" + Date.now();
                    imgNode.style.display = "block";
                    imgNode.src = url;
                    imgNode.onload = () => {
                        if (imgNode.naturalWidth && imgNode.naturalHeight) {
                            hasContent = true;
                            currentAspectRatio = imgNode.naturalWidth / imgNode.naturalHeight;
                            fitNodeToContent();
                        }
                    };
                };

                const imageWidget = this.widgets?.find(w => w.name === "image");
                if (imageWidget) {
                    const cb = imageWidget.callback;
                    imageWidget.callback = function (value) {
                        if (cb) cb.apply(this, arguments);
                        if (value && value !== "none") {
                            if (value.startsWith("clipspace/")) {
                                const filename = value.split("/").pop().replace(" [input]", "").replace(" [temp]", "");
                                updatePreview(api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=clipspace`));
                                return;
                            }
                            let clean = value;
                            if (clean.endsWith(" [temp]")) clean = clean.slice(0, -7);
                            let subfolder = "";
                            let filename = clean;
                            if (clean.includes("/")) {
                                const parts = clean.split("/");
                                filename = parts[parts.length - 1];
                                subfolder = parts.slice(0, -1).join("/");
                            }
                            const params = new URLSearchParams({ filename, type: "temp", subfolder });
                            updatePreview(api.apiURL("/view?" + params.toString()));
                        }
                    };
                    setTimeout(() => { if (imageWidget.value) imageWidget.callback(imageWidget.value); }, 100);
                }

                return r;
            };
        }

        // ====================================================================
        // 3. load_image_by_path: 解决双预览图并保留遮罩能力
        // ====================================================================
        if (nodeData.name === "load_image_by_path") {
            // 【核心修复 1】：同样拦截绝对路径节点的原生背景绘制
            const origDrawBackground = nodeType.prototype.onDrawBackground;
            nodeType.prototype.onDrawBackground = function (ctx) {
                const backupImgs = this.imgs;
                this.imgs = undefined;
                let r;
                if (origDrawBackground) {
                    r = origDrawBackground.apply(this, arguments);
                }
                this.imgs = backupImgs;
                return r;
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                let currentAspectRatio = 0;
                let hasContent = false;
                let previewHeight = 50;

                this.pasteFromClipspace = function (clipspace) {
                    if (clipspace && clipspace.filename) {
                        const fullClip = `clipspace/${clipspace.filename}`;
                        const pathWidget = node.widgets?.find(w => w.name === "img_path");
                        if (pathWidget) {
                            pathWidget.value = fullClip;
                            if (pathWidget.callback) pathWidget.callback(fullClip);
                        }
                    }
                };

                const previewElement = document.createElement("div");
                previewElement.className = "supernova-preview-container";

                const imgNode = document.createElement("img");
                imgNode.crossOrigin = "anonymous";
                imgNode.style.display = "none";
                previewElement.appendChild(imgNode);

                const maskBtn = document.createElement("button");
                maskBtn.className = "supernova-official-mask-btn";
                maskBtn.title = "编辑或遮罩图片";
                maskBtn.setAttribute("aria-label", "编辑或遮罩图片");
                maskBtn.innerHTML = OFFICIAL_MASK_SVG;

                maskBtn.addEventListener("mousedown", (e) => e.stopPropagation());
                maskBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    triggerNodes2MaskEditor(node, imgNode);
                });
                previewElement.appendChild(maskBtn);

                const widget = this.addDOMWidget("image_preview", "preview", previewElement, {
                    serialize: false,
                    hideOnZoom: false
                });

                const calculateHeaderHeight = () => {
                    const originalCompute = widget.computeSize;
                    widget.computeSize = () => [node.size[0], 0];
                    const baseSize = node.computeSize([node.size[0], 0]);
                    widget.computeSize = originalCompute;
                    return baseSize[1];
                };

                widget.computeSize = (width) => [width, previewHeight];

                const fitNodeToContent = () => {
                    if (!hasContent || currentAspectRatio === 0) return;
                    const currentWidth = node.size[0];
                    const headerHeight = calculateHeaderHeight();
                    const idealImgHeight = currentWidth / currentAspectRatio;
                    previewHeight = idealImgHeight;
                    node.setSize([currentWidth, headerHeight + idealImgHeight + 10]);
                    node.graph?.setDirtyCanvas(true, true);
                };

                const updatePreview = (url) => {
                    if (!url) return;
                    if (url.includes("/view?")) url += "&t=" + Date.now();
                    imgNode.style.display = "block";
                    imgNode.src = url;
                    imgNode.onload = () => {
                        if (imgNode.naturalWidth && imgNode.naturalHeight) {
                            hasContent = true;
                            currentAspectRatio = imgNode.naturalWidth / imgNode.naturalHeight;
                            fitNodeToContent();
                        }
                    };
                };

                const pathWidget = this.widgets?.find(w => w.name === "img_path");
                if (pathWidget) {
                    const cb = pathWidget.callback;
                    pathWidget.callback = async (value) => {
                        if (cb) cb.call(pathWidget, value);
                        if (value && value.length > 3) {
                            if (value.startsWith("clipspace/")) {
                                const filename = value.split("/").pop().replace(" [input]", "");
                                updatePreview(api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=clipspace`));
                                return;
                            }
                            try {
                                const params = new URLSearchParams({ path: value });
                                const res = await fetch(api.apiURL("/mape/preview_absolute_path?" + params.toString()));
                                if (res.ok) {
                                    const data = await res.json();
                                    if (data.filename) {
                                        updatePreview(api.apiURL(`/view?filename=${data.filename}&type=${data.type}`));
                                    }
                                }
                            } catch (e) {}
                        }
                    };
                    setTimeout(() => { if (pathWidget.value) pathWidget.callback(pathWidget.value); }, 100);
                }

                return r;
            };
        }
    },
});