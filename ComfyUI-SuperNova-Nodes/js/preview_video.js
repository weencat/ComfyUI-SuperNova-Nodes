import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// CSS
const style = document.createElement('style');
style.innerHTML = `
    .simple-video-container {
        width: 100%;
        height: 100%;
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
        margin-top: 5px;
    }
    .simple-video-container img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
        pointer-events: none;
        user-select: none;
    }
    .simple-video-container video {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
        pointer-events: auto;
    }
`;
document.head.appendChild(style);

// 防抖工具
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), wait);
    };
}

app.registerExtension({
    name: "supernova.PreviewVideo",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        
        const videoNodes = ["SimpleVideoCombine", "SimpleLoadVideoPath"];

        if (videoNodes.includes(nodeData.name)) {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                let currentAspectRatio = 0;
                let hasContent = false;
                let previewHeight = 50;

                // DOM
                const previewElement = document.createElement("div");
                previewElement.className = "simple-video-container";

                const videoNode = document.createElement("video");
                Object.assign(videoNode, { controls: true, loop: true, muted: false, autoplay: true });
                videoNode.style.display = "none";

                const imgNode = document.createElement("img");
                imgNode.style.display = "none";

                previewElement.appendChild(videoNode);
                previewElement.appendChild(imgNode);

                const widget = this.addDOMWidget("video_preview", "preview", previewElement, {
                    serialize: false,
                    hideOnZoom: false
                });

                // Layout
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

                // Update logic
                const updatePreview = (url, isVideo = false) => {
                    if (!url) {
                        hasContent = false;
                        videoNode.style.display = "none";
                        imgNode.style.display = "none";
                        return;
                    }

                    if (url.includes("/view?") || url.includes("/preview_path?") || url.includes("/fetch_frame?") || url.includes("/fetch_preview?")) {
                         url += "&t=" + Date.now();
                    }

                    if (isVideo) {
                        imgNode.style.display = "none";
                        imgNode.src = "";
                        videoNode.style.display = "block";
                        videoNode.src = url;
                        videoNode.onloadedmetadata = () => {
                            if (videoNode.videoWidth && videoNode.videoHeight) {
                                hasContent = true;
                                currentAspectRatio = videoNode.videoWidth / videoNode.videoHeight;
                                fitNodeToContent();
                            }
                            videoNode.play();
                        };
                    } else {
                        videoNode.style.display = "none";
                        videoNode.pause();
                        videoNode.src = "";
                        imgNode.style.display = "block";
                        imgNode.src = url;
                        imgNode.onload = () => {
                            if (imgNode.naturalWidth && imgNode.naturalHeight) {
                                hasContent = true;
                                currentAspectRatio = imgNode.naturalWidth / imgNode.naturalHeight;
                                fitNodeToContent();
                            }
                        };
                    }
                };

                node.updatePreviewFunc = updatePreview;


                // ============================================================
                // SimpleLoadVideoPath: 自动监听逻辑
                // ============================================================
                if (nodeData.name === "SimpleLoadVideoPath") {
                    const pathWidget = this.widgets.find(w => w.name === "video_path");
                    const indexWidget = this.widgets.find(w => w.name === "select_frame_index");
                    
                    const skipWidget = this.widgets.find(w => w.name === "skip_first_frames");
                    const nthWidget = this.widgets.find(w => w.name === "select_every_nth");
                    const capWidget = this.widgets.find(w => w.name === "frame_load_cap");

                    const requestContent = async () => {
                        const path = pathWidget?.value;
                        const index = indexWidget?.value;
                        
                        const skip = skipWidget ? skipWidget.value : 0;
                        const nth = nthWidget ? nthWidget.value : 1;
                        const cap = capWidget ? capWidget.value : 0;

                        if (!path || typeof path !== "string" || path.length < 3) return;

                        try {
                            // 构造查询参数
                            const params = new URLSearchParams({ 
                                path: path, 
                                index: index,
                                skip: skip,
                                nth: nth,
                                cap: cap
                            });
                            
                            // 调用统一接口
                            const res = await fetch(api.apiURL("/simple_video/fetch_preview?" + params.toString()));
                            
                            if (res.ok) {
                                const data = await res.json();
                                if (data.filename) {
                                    const url = api.apiURL(`/view?filename=${data.filename}&type=${data.type}`);
                                    // format="video" 为视频，否则为图片
                                    const isVideo = data.format === "video";
                                    node.updatePreviewFunc(url, isVideo);
                                }
                            }
                        } catch (e) { console.error("Preview fetch error:", e); }
                    };

                    const debouncedRequest = debounce(requestContent, 300);

                    // 绑定监听
                    const widgetsToWatch = [pathWidget, indexWidget, skipWidget, nthWidget, capWidget];
                    
                    widgetsToWatch.forEach(w => {
                        if (w) {
                            const cb = w.callback;
                            w.callback = function (value) {
                                if (cb) cb.call(w, value);
                                // 路径变化立即请求，其他参数变化使用防抖
                                if (w.name === "video_path") requestContent();
                                else debouncedRequest();
                            };
                        }
                    });
                    
                    // 初始化
                    setTimeout(() => { if(pathWidget.value) requestContent(); }, 500);
                }

                return r;
            };

            // --- 监听 Saver 执行结果 ---
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);
                if (message && message.video_preview && message.video_preview.length > 0) {
                    const data = message.video_preview[0];
                    const params = new URLSearchParams({
                        filename: data.filename,
                        type: data.type,
                        subfolder: data.subfolder || ""
                    });
                    const url = api.apiURL("/view?" + params.toString());
                    const isVideo = data.format !== "image";
                    if (this.updatePreviewFunc) this.updatePreviewFunc(url, isVideo);
                }
            };
        }
    },
});