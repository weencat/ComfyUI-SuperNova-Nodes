import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// CSS
const style = document.createElement("style");
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
    .simple-audio-container {
        width: 100%;
        height: 40px;
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        margin-top: 6px;
        box-sizing: border-box;
    }
    .simple-audio-container audio {
        width: 100%;
        height: 36px;
        outline: none;
    }
`;
document.head.appendChild(style);

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    const context = this;
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(context, args), wait);
  };
}

app.registerExtension({
  name: "supernova.PreviewMedia",
  async beforeRegisterNodeDef(nodeType, nodeData, app) {

    // ============================================================
    // 1. 视频节点逻辑 (保持原生完全不变)
    // ============================================================
    const videoNodes = ["SimpleVideoCombine", "SimpleLoadVideoPath"];

    if (videoNodes.includes(nodeData.name)) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated
          ? onNodeCreated.apply(this, arguments)
          : undefined;
        const node = this;

        let currentAspectRatio = 0;
        let hasContent = false;
        let previewHeight = 50;

        const previewElement = document.createElement("div");
        previewElement.className = "simple-video-container";

        const videoNode = document.createElement("video");
        Object.assign(videoNode, {
          controls: true,
          loop: true,
          muted: false,
          autoplay: true,
        });
        videoNode.style.display = "none";

        const imgNode = document.createElement("img");
        imgNode.style.display = "none";

        previewElement.appendChild(videoNode);
        previewElement.appendChild(imgNode);

        const widget = this.addDOMWidget(
          "video_preview",
          "preview",
          previewElement,
          {
            serialize: false,
            hideOnZoom: false,
          },
        );

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
        node.onResize = function (size) {
          if (origOnResize) origOnResize.apply(this, arguments);
          const headerHeight = calculateHeaderHeight();
          const newPreviewHeight = size[1] - headerHeight - 5;
          previewHeight = Math.max(20, newPreviewHeight);
        };

        const updatePreview = (url, isVideo = false) => {
          if (!url) {
            hasContent = false;
            videoNode.style.display = "none";
            imgNode.style.display = "none";
            return;
          }

          if (
            url.includes("/view?") ||
            url.includes("/preview_path?") ||
            url.includes("/fetch_frame?") ||
            url.includes("/fetch_preview?")
          ) {
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
                currentAspectRatio =
                  videoNode.videoWidth / videoNode.videoHeight;
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
                currentAspectRatio =
                  imgNode.naturalWidth / imgNode.naturalHeight;
                fitNodeToContent();
              }
            };
          }
        };

        node.updatePreviewFunc = updatePreview;

        if (nodeData.name === "SimpleLoadVideoPath") {
          const pathWidget = this.widgets.find((w) => w.name === "video_path");
          const indexWidget = this.widgets.find(
            (w) => w.name === "select_frame_index",
          );

          const skipWidget = this.widgets.find(
            (w) => w.name === "skip_first_frames",
          );
          const nthWidget = this.widgets.find(
            (w) => w.name === "select_every_nth",
          );
          const capWidget = this.widgets.find(
            (w) => w.name === "frame_load_cap",
          );

          const requestContent = async () => {
            const path = pathWidget?.value;
            const index = indexWidget?.value;

            const skip = skipWidget ? skipWidget.value : 0;
            const nth = nthWidget ? nthWidget.value : 1;
            const cap = capWidget ? capWidget.value : 0;

            if (!path || typeof path !== "string" || path.length < 3) return;

            try {
              const params = new URLSearchParams({
                path: path,
                index: index,
                skip: skip,
                nth: nth,
                cap: cap,
              });

              const res = await fetch(
                api.apiURL("/simple_video/fetch_preview?" + params.toString()),
              );

              if (res.ok) {
                const data = await res.json();
                if (data.filename) {
                  const url = api.apiURL(
                    `/view?filename=${data.filename}&type=${data.type}`,
                  );
                  const isVideo = data.format === "video";
                  node.updatePreviewFunc(url, isVideo);
                }
              }
            } catch (e) {
              console.error("Preview fetch error:", e);
            }
          };

          const debouncedRequest = debounce(requestContent, 300);

          const widgetsToWatch = [
            pathWidget,
            indexWidget,
            skipWidget,
            nthWidget,
            capWidget,
          ];

          widgetsToWatch.forEach((w) => {
            if (w) {
              const cb = w.callback;
              w.callback = function (value) {
                if (cb) cb.call(w, value);
                if (w.name === "video_path") requestContent();
                else debouncedRequest();
              };
            }
          });

          setTimeout(() => {
            if (pathWidget.value) requestContent();
          }, 500);
        }

        return r;
      };

      const onExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (message) {
        onExecuted?.apply(this, arguments);
        if (
          message &&
          message.video_preview &&
          message.video_preview.length > 0
        ) {
          const data = message.video_preview[0];
          const params = new URLSearchParams({
            filename: data.filename,
            type: data.type,
            subfolder: data.subfolder || "",
          });
          const url = api.apiURL("/view?" + params.toString());
          const isVideo = data.format !== "image";
          if (this.updatePreviewFunc) this.updatePreviewFunc(url, isVideo);
        }
      };
    }

    // ============================================================
    // 2. 音频加载节点专属逻辑 (对齐视频节点的稳定渲染结构)
    // ============================================================
    if (nodeData.name === "LoadAudioFromPath") {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated
          ? onNodeCreated.apply(this, arguments)
          : undefined;
        const node = this;

        // 固定预分配音频条高度，杜绝动态插入导致的画布排版崩坏
        const audioHeight = 44;

        const previewElement = document.createElement("div");
        previewElement.className = "simple-audio-container";

        const audioElement = document.createElement("audio");
        audioElement.controls = true;
        previewElement.appendChild(audioElement);

        const widget = this.addDOMWidget(
          "audio_preview",
          "preview",
          previewElement,
          {
            serialize: false,
            hideOnZoom: false,
          }
        );

        widget.computeSize = (width) => [width, audioHeight];

        // 适当扩充节点卡片整体高度
        const currentSize = [...node.size];
        node.setSize([Math.max(currentSize[0], 280), currentSize[1] + audioHeight]);

        const updateAudio = (url) => {
          if (!url) {
            audioElement.src = "";
            return;
          }
          if (url.includes("/view?")) {
            url += "&t=" + Date.now();
          }
          audioElement.src = url;
          audioElement.load();
          node.graph?.setDirtyCanvas(true, true);
        };

        node.updateAudioFunc = updateAudio;

        // 监听输入框
        const pathWidget = this.widgets?.find((w) => w.name === "audio_path");

        const requestAudioContent = async () => {
          const path = pathWidget?.value;
          if (!path || typeof path !== "string" || path.trim().length < 3) return;

          console.log("[SuperNova Audio] 请求预览:", path);

          try {
            const params = new URLSearchParams({ path: path.trim() });
            const res = await fetch(
              api.apiURL("/simple_video/fetch_audio_preview?" + params.toString())
            );

            if (res.ok) {
              const data = await res.json();
              if (data.filename) {
                const url = api.apiURL(`/view?filename=${data.filename}&type=${data.type}`);
                updateAudio(url);
              }
            } else {
              console.error("[SuperNova Audio] 请求失败:", res.status, await res.text());
            }
          } catch (e) {
            console.error("[SuperNova Audio] 网络或解析异常:", e);
          }
        };

        if (pathWidget) {
          const cb = pathWidget.callback;
          pathWidget.callback = function (value) {
            if (cb) cb.call(pathWidget, value);
            // 粘贴输入后立即拉取音频并显示，无需等待
            requestAudioContent();
          };
        }

        // 打开旧工作流时自动展示音频
        setTimeout(() => {
          if (pathWidget?.value) requestAudioContent();
        }, 500);

        return r;
      };

      const onExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (message) {
        onExecuted?.apply(this, arguments);
        const audioList = message?.audio;
        if (audioList && audioList.length > 0) {
          const data = audioList[0];
          const params = new URLSearchParams({
            filename: data.filename,
            type: data.type || "temp",
            subfolder: data.subfolder || "",
          });
          const url = api.apiURL("/view?" + params.toString());
          if (this.updateAudioFunc) this.updateAudioFunc(url);
        }
      };
    }

  },
});