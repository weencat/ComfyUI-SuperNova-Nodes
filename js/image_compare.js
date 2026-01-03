import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function getImageUrl(data) {
    if (!data) return null;
    return api.apiURL(`/view?filename=${encodeURIComponent(data.filename)}&type=${data.type}&subfolder=${data.subfolder}${app.getPreviewFormatParam()}${app.getRandParam()}`);
}

app.registerExtension({
    name: "My.MultiImageComparer",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "MultiImageComparer") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) onNodeCreated.apply(this, arguments);

                // 基础设计参考值
                this.baseWidth = 512;
                this.boxTitleHeight = 30;
                this.boxSlotsHeight = 90;
                this.baseFooterHeight = 30; // 基础高度

                this.setSize([512, 620]);
                this.imgs = { 1: null, 2: null, 3: null, 4: null };
                this.imgDims = { 1: "", 2: "", 3: "", 4: "" };

                this.splitX = 0.5;
                this.splitY = 0.5;
                this.dragging = false;
            };

            // 动态控制缩放限制和比例
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

            nodeType.prototype.onMouseMove = function (event, pos, canvas) {
                if (this.dragging) this.updateSplitPos(pos);
            };
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
                if (this.flags.collapsed) return;

                const nodeW = this.size[0];
                const nodeH = this.size[1];

                // 计算实时比例因子
                const scaleFactor = nodeW / this.baseWidth;
                const currentFooterHeight = this.baseFooterHeight * scaleFactor;

                const b3Y = this.boxTitleHeight + this.boxSlotsHeight;
                const b3W = nodeW;
                const b3H = nodeH - b3Y - currentFooterHeight;

                const activeIds = [1, 2, 3, 4].filter(id => !!this.imgs[id]);
                const count = activeIds.length;
                if (count === 0) return;

                ctx.save();

                // --- Box 3 绘制 (对比预览区) ---
                const drawComp = (img, clipX, clipY, clipW, clipH) => {
                    if (!img || clipW <= 0 || clipH <= 0) return;
                    ctx.save();
                    ctx.beginPath();
                    ctx.rect(clipX, clipY, clipW, clipH);
                    ctx.clip();
                    const aspect = img.naturalWidth / img.naturalHeight;
                    const areaAspect = b3W / b3H;
                    let fw, fh;
                    if (aspect > areaAspect) {
                        fw = b3W; fh = b3W / aspect;
                    } else {
                        fh = b3H; fw = b3H * aspect;
                    }
                    const tx = (b3W - fw) / 2;
                    const ty = b3Y + (b3H - fh) / 2;
                    ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, tx, ty, fw, fh);
                    ctx.restore();
                };

                const sx = this.splitX * b3W;
                const sy = b3Y + (this.splitY * b3H);

                if (count === 1) {
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, b3W, b3H);
                } else if (count === 2) {
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, b3H);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, b3H);
                    ctx.strokeStyle = "rgba(255,255,255,0.4)";
                    ctx.beginPath(); ctx.moveTo(sx, b3Y); ctx.lineTo(sx, b3Y + b3H); ctx.stroke();
                } else if (count === 3) {
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[2]], 0, sy, b3W, b3H - (sy - b3Y));
                    ctx.strokeStyle = "rgba(255,255,255,0.4)";
                    ctx.beginPath();
                    ctx.moveTo(sx, b3Y); ctx.lineTo(sx, sy);
                    ctx.moveTo(0, sy); ctx.lineTo(b3W, sy);
                    ctx.stroke();
                } else if (count === 4) {
                    drawComp(this.imgs[activeIds[0]], 0, b3Y, sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[1]], sx, b3Y, b3W - sx, sy - b3Y);
                    drawComp(this.imgs[activeIds[2]], 0, sy, sx, b3H - (sy - b3Y));
                    drawComp(this.imgs[activeIds[3]], sx, sy, b3W - sx, b3H - (sy - b3Y));
                    ctx.strokeStyle = "rgba(255,255,255,0.4)";
                    ctx.beginPath();
                    ctx.moveTo(sx, b3Y); ctx.lineTo(sx, b3Y + b3H);
                    ctx.moveTo(0, sy); ctx.lineTo(b3W, sy);
                    ctx.stroke();
                }

                // ID 标签微调
                const labelSize = 18 * Math.sqrt(scaleFactor);
                ctx.font = `bold ${Math.max(10, 12 * scaleFactor)}px Arial`;
                const drawLabel = (id, x, y) => {
                    ctx.fillStyle = "rgba(0,0,0,0.6)";
                    ctx.fillRect(x, y, labelSize, labelSize);
                    ctx.fillStyle = "#FFF";
                    ctx.textAlign = "center";
                    ctx.fillText(id, x + labelSize / 2, y + labelSize / 1.4);
                };
                if (count >= 1) drawLabel(activeIds[0], 5, b3Y + 5);
                if (count >= 2) drawLabel(activeIds[1], b3W - 5 - labelSize, b3Y + 5);
                if (count >= 3) drawLabel(activeIds[2], 5, b3H + b3Y - 5 - labelSize);
                if (count >= 4) drawLabel(activeIds[3], b3W - 5 - labelSize, b3H + b3Y - 5 - labelSize);

                // --- Box 4 绘制 (润色重点：比例缩放 & 居中) ---
                const footerY = nodeH - currentFooterHeight;
                const footerW = nodeW - 10; // 左右留出间距
                const footerX = 5;
                ctx.fillStyle = "#00000000";
                ctx.beginPath();
                if (ctx.roundRect) {
                    ctx.roundRect(footerX, footerY, footerW, currentFooterHeight);
                }
                ctx.fillRect(0, footerY, nodeW, currentFooterHeight);

                // 绘制一个精致的顶部边框线
                //ctx.strokeStyle = "#333";
                //ctx.lineWidth = 1;
                //ctx.beginPath(); ctx.moveTo(0, footerY); ctx.lineTo(nodeW, footerY); ctx.stroke();


                // 动态计算字体大小
                const fontSize = Math.max(5, 11 * scaleFactor);
                ctx.font = `${fontSize}px Consolas, Monaco, monospace`;
                //ctx.fillStyle = "#ffffffff";
                // LiteGraph.NODE_TEXT_COLOR 会自动根据主题变为白色或黑色
                ctx.fillStyle = LiteGraph.NODE_TEXT_COLOR || "#EEE";
                ctx.textAlign = "center"; // 水平居中
                ctx.textBaseline = "middle"; // 垂直居中

                let info = activeIds.map(id => `${id}:${this.imgDims[id]}`).join("  |  ");
                ctx.fillText(info, nodeW / 2, footerY + (currentFooterHeight / 2));

                ctx.restore();
            };
        }
    }
});