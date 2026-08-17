import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// 图片节点专用样式
const style = document.createElement('style');
style.innerHTML = `
    .simple-image-container {
        width: 100%;
        height: 100%;
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
        margin-top: 5px;
    }
    .simple-image-container img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
        pointer-events: none;
        user-select: none;
    }
`;
document.head.appendChild(style);

// --- 核心修复：修复 ComfyUI Node 2.0 双预览图问题 ---
// Node 2.0 会为包含 image_upload 的节点自动创建一个原生的预览，
// 但它无法正确解析带有 'output/', 'temp/' 等前缀的自定义合并路径，导致加载失败并显示一个损坏的图像图标。
// 这里通过全局捕获这些已知的错误请求并隐式将其隐藏，来保持界面只保留我们自己的正常预览。
if (!window._supernova_img_error_handler) {
    window.addEventListener('error', function(e) {
        if (e.target && e.target.tagName === 'IMG') {
            const src = e.target.src;
            if (src && src.includes('/view?')) {
                try {
                    const url = new URL(src, window.location.origin);
                    const filename = url.searchParams.get('filename');
                    const type = url.searchParams.get('type') || 'input';
                    
                    // 如果原生系统错误地用 type=input 强行加载带有前缀的相对路径
                    if (filename && type === 'input') {
                        if (filename.startsWith('output/') || 
                            filename.startsWith('temp/') || 
                            filename.startsWith('clipspace/') ||
                            filename.startsWith('input/')) {
                            // 隐藏加载失败的内置原图
                            e.target.style.display = 'none';
                        }
                    }
                } catch (err) {}
            }
        }
    }, true); // 必须设置为 true 以在捕获阶段拦截错误（IMG error事件不会冒泡）
    window._supernova_img_error_handler = true;
}

app.registerExtension({
    name: "supernova.PreviewImage",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (
            nodeData.name === "LoadImageUnified" || nodeData.name === "load_image_by_path"
        ) {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                // 状态
                let currentAspectRatio = 0;
                let hasContent = false;
                let previewHeight = 50;

                // DOM
                const previewElement = document.createElement("div");
                previewElement.className = "simple-image-container";
                
                const imgNode = document.createElement("img");
                imgNode.style.display = "none";
                
                previewElement.appendChild(imgNode);

                const widget = this.addDOMWidget("image_preview", "preview", previewElement, {
                    serialize: false,
                    hideOnZoom: false
                });

                // --- 布局逻辑 (同视频节点) ---
                const calculateHeaderHeight = () => {
                    const originalCompute = widget.computeSize;
                    widget.computeSize = () => [node.size[0], 0];
                    const baseSize = node.computeSize([node.size[0], 0]);
                    widget.computeSize = originalCompute;
                    return baseSize[1];
                };

                widget.computeSize = (width) => {
                    return [width, previewHeight];
                };

                const fitNodeToContent = () => {
                    if (!hasContent || currentAspectRatio === 0) return;
                    const currentWidth = node.size[0];
                    const headerHeight = calculateHeaderHeight();
                    const idealImgHeight = currentWidth / currentAspectRatio;
                    
                    previewHeight = idealImgHeight;
                    node.setSize([currentWidth, headerHeight + idealImgHeight + 5]);
                    node.graph.setDirtyCanvas(true, true);
                };

                const origOnResize = node.onResize;
                node.onResize = function(size) {
                    if (origOnResize) origOnResize.apply(this, arguments);
                    const headerHeight = calculateHeaderHeight();
                    const newPreviewHeight = size[1] - headerHeight - 5;
                    previewHeight = Math.max(20, newPreviewHeight);
                };

                // --- 更新逻辑 ---
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

                // --- 监听输入 ---
                
                // 1. LoadImageUnified (下拉菜单)
                if (nodeData.name === "LoadImageUnified") {
                    const imageWidget = this.widgets.find(w => w.name === "image");
                    if (imageWidget) {
                        const cb = imageWidget.callback;
                        imageWidget.callback = (value) => {
                            if (cb) cb.call(imageWidget, value);
                            
                            // --- 核心修复：防止 V1/V2 引擎根据下拉值渲染出多余的原生缩略图 ---
                            // 延时清除原生系统的内置预览池
                            setTimeout(() => {
                                if (node.imgs) {
                                    node.imgs = undefined;
                                }
                            }, 10);
                            
                            if (value) {
                                let type = "input";
                                let filename = value;
                                let subfolder = "";
                                const parts = value.split('/');
                                if (parts.length > 0 && ["input", "output", "temp", "clipspace"].includes(parts[0])) {
                                    type = parts[0];
                                    filename = parts[parts.length - 1];
                                    if (parts.length > 2) {
                                        subfolder = parts.slice(1, parts.length - 1).join('/');
                                    }
                                }
                                const params = new URLSearchParams({ filename, type, subfolder });
                                const url = api.apiURL("/view?" + params.toString());
                                updatePreview(url);
                            }
                        };
                        setTimeout(() => { if(imageWidget.value) imageWidget.callback(imageWidget.value); }, 100);
                    }
                }

                // 2. load_image_by_path (绝对路径)
                if (nodeData.name === "load_image_by_path") {
                    const pathWidget = this.widgets.find(w => w.name === "img_path");
                    if (pathWidget) {
                        const cb = pathWidget.callback;
                        pathWidget.callback = async (value) => {
                            if (cb) cb.call(pathWidget, value);
                            if (value && value.length > 3) {
                                try {
                                    const params = new URLSearchParams({ path: value });
                                    const res = await fetch(api.apiURL("/mape/preview_absolute_path?" + params.toString()));
                                    if (res.ok) {
                                        const data = await res.json();
                                        if (data.filename) {
                                            const url = api.apiURL(`/view?filename=${data.filename}&type=${data.type}`);
                                            updatePreview(url);
                                        }
                                    }
                                } catch (e) {}
                            }
                        };
                    }
                }

                return r;
            };
        }
    },
});