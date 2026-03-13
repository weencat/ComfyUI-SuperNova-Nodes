import time
import os
import random
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageColor
from aiohttp import web
from server import PromptServer
import nodes
from nodes import PreviewImage

# ==============================================================================
# 1. 全局配置与资源挂载
# ==============================================================================

# 全局状态存储
PAUSE_STATE = {}
SELECTION_STATE = {}

# 挂载音频目录 (用于前端提示音)
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
audio_path = os.path.join(root_dir, "audio")

if os.path.exists(audio_path):
    has_route = False
    for route in PromptServer.instance.app.router.routes():
        if route.resource and route.resource.canonical == "/supernova/audio":
            has_route = True
            break
    
    if not has_route:
        PromptServer.instance.app.add_routes([
            web.static("/supernova/audio", audio_path)
        ])
    # print(f"[Supernova] Audio mounted from: {audio_path}")
else:
    pass 

# ==============================================================================
# 2. API 路由定义
# ==============================================================================

@PromptServer.instance.routes.post("/supernova/preview_control")
async def preview_control(request):
    """控制 PreviewAndPause 节点的继续/停止"""
    try:
        data = await request.json()
        node_id = data.get("node_id")
        action = data.get("action")
        PAUSE_STATE[str(node_id)] = action
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

@PromptServer.instance.routes.post("/supernova/select")
async def select_node(request):
    """控制 ImageCompareAndSelect 节点的选择结果"""
    try:
        data = await request.json()
        node_id = data.get("node_id")
        selection = data.get("selection")
        SELECTION_STATE[str(node_id)] = selection
        return web.json_response({"status": "success", "selection": selection})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

# ==============================================================================
# 3. 辅助函数
# ==============================================================================

def wait_for_decision(unique_id, seed):
    """ImageCompareAndSelect 的阻塞等待逻辑"""
    node_id = str(unique_id)
    print(f"[ImageCompare] Node {node_id} Paused (Seed: {seed})...")
    
    # 标记状态为等待
    SELECTION_STATE[node_id] = "waiting"
    
    # 通知前端播放提示音（如果需要）
    PromptServer.instance.send_sync("supernova_pause_alert", {"node_id": node_id})
    
    # 阻塞循环，直到前端发送选择
    while True:
        if SELECTION_STATE.get(node_id, "waiting") != "waiting": 
            break
        time.sleep(0.1)
    
    decision = SELECTION_STATE.pop(node_id)
    print(f"[ImageCompare] Node {node_id} Resumed: {decision}")
    
    if decision == "stop": 
        raise Exception("Workflow stopped by user.")
    return decision

# ==============================================================================
# 4. 节点类定义
# ==============================================================================

# ------------------------------------------------------------------------------
# Preview & Pause Node
# ------------------------------------------------------------------------------
class PreviewAndPause:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": { "images": ("IMAGE",), },
            "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "🪐supernova/Image"
    OUTPUT_NODE = True
    
    def run(self, images, unique_id, prompt=None, extra_pnginfo=None):
        node_id = str(unique_id)
        
        # 调用原生预览保存图片
        previewer = nodes.PreviewImage()
        result = previewer.save_images(images, filename_prefix="Pause_Preview", prompt=prompt, extra_pnginfo=extra_pnginfo)
        ui_images = result['ui']['images']

        print(f"[PreviewPause] Pause at node {node_id}")
        
        # 重置状态为等待
        PAUSE_STATE[node_id] = "waiting"
        
        # 发送前端消息
        PromptServer.instance.send_sync("supernova_preview_data", {
            "node_id": node_id,
            "images": ui_images
        })

        # 阻塞循环
        while True:
            status = PAUSE_STATE.get(node_id, "waiting")
            if status == "continue": 
                break
            elif status == "stop": 
                PAUSE_STATE.pop(node_id, None)
                raise Exception("Workflow stopped by user.")
            time.sleep(0.1)
        
        # 清理状态
        PAUSE_STATE.pop(node_id, None)
        return {"ui": {"images": ui_images}, "result": (images,)}

# ------------------------------------------------------------------------------
# Multi Image Comparer Node (Pure UI)
# ------------------------------------------------------------------------------
class MultiImageComparer:
    """
    A node that compares up to 4 images (1, 2, 3, 4) with click-to-slide interaction
    and dynamic resolution display.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
            },
            "hidden": {
                "prompt": "PROMPT", 
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    CATEGORY = "🪐supernova/Image"
    FUNCTION = "compare_images"

    def compare_images(self, image_1=None, image_2=None, image_3=None, image_4=None, 
                       filename_prefix="comparer", prompt=None, extra_pnginfo=None):
        
        previewer = PreviewImage()

        def get_ui_image(images, suffix):
            if images is None:
                return []
            saved = previewer.save_images(images, f"{filename_prefix}_{suffix}", prompt, extra_pnginfo)
            return saved['ui']['images']

        result = { 
            "ui": { 
                "images_1": get_ui_image(image_1, "1"),
                "images_2": get_ui_image(image_2, "2"),
                "images_3": get_ui_image(image_3, "3"),
                "images_4": get_ui_image(image_4, "4"),
            } 
        }
        return result

# ------------------------------------------------------------------------------
# Image Compare And Select Node (Flow Control)
# ------------------------------------------------------------------------------
class ImageCompareAndSelect:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # 1. 将 "seed" 改名为 "compare_id"，绕开 ComfyUI 对 "seed" 这个词的特殊 UI 渲染逻辑
                "compare_id": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT", 
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Selected Image",)
    FUNCTION = "run"
    CATEGORY = "🪐supernova/Image"
    OUTPUT_NODE = True

    # 2. 这里参数名也要从 seed 改为 compare_id
    def run(self, compare_id, unique_id, image_1=None, image_2=None, prompt=None, extra_pnginfo=None):
        previewer = PreviewImage()
        ui_images = { "1": [], "2": [] }
        
        def save_and_get_meta(img_tensor, key):
            if img_tensor is not None:
                prefix = f"compare_{unique_id}_{key}_{random.randint(1, 1000)}"
                res = previewer.save_images(img_tensor, prefix, prompt, extra_pnginfo)
                return res['ui']['images']
            return []

        ui_images["1"] = save_and_get_meta(image_1, "1")
        ui_images["2"] = save_and_get_meta(image_2, "2")

        PromptServer.instance.send_sync("supernova_preview_update", {
            "node_id": unique_id,
            "images": ui_images
        })

        # 3. 传入 compare_id 确保逻辑一致
        decision = wait_for_decision(unique_id, compare_id)

        result = None
        if decision == "1": result = image_1
        elif decision == "2": result = image_2
        
        return (result, )
    
# ------------------------------------------------------------------------------
# Image Add Text Node
# ------------------------------------------------------------------------------
class ImageAddText:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "text": ("STRING", {"multiline": True, "default": "TEXT"}),
                "direction": (["top", "bottom", "left", "right"], {"default": "top"}),
                "font_path": ("STRING", {"default": "","tooltip":"If empty, the default file used is local.ttf from Fonts."}), 
                "font_size": ("INT", {"default": 50, "min": 1, "max": 2048, "step": 1}),
                "text_color": ("STRING", {"default": "#000000"}),
                "bg_color": ("STRING", {"default": "#FFFFFF"}),
                "bg_mode": (["inside", "outside"], {"default": "outside"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "add_text"
    CATEGORY = "🪐supernova/Image"

    def add_text(self, image, text, direction, font_path, font_size, text_color, bg_color, bg_mode):
        if not font_path.strip():
            current_dir = os.path.dirname(__file__)
            # 假设 Fonts 文件夹在当前节点文件的上一级同级目录中
            font_path = os.path.abspath(os.path.join(current_dir, "..", "Fonts", "local.ttf"))

        padding = int(font_size + 2)
        img_batches = []
        
        for i in range(image.shape[0]):
            img_np = (image[i].cpu().numpy() * 255).astype(np.uint8)
            pil_img = Image.fromarray(img_np)
            orig_w, orig_h = pil_img.size
            
            try:
                font = ImageFont.truetype(font_path, font_size) if os.path.exists(font_path) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            def get_color(hex_str, default):
                try: return ImageColor.getrgb(hex_str)
                except: return default
            txt_col = get_color(text_color, (0, 0, 0))
            bg_col = get_color(bg_color, (255, 255, 255))

            draw_tasks = [] # 存储 (文字内容, x_offset, y_offset)
            final_text_w = 0
            final_text_h = 0

            # ---------------------------------------------------------
            # 核心排版引擎
            # ---------------------------------------------------------
            if direction in ["top", "bottom"]:
                # --- 水平换行模式 ---
                max_w = orig_w - (padding * 2)
                lines = []
                current_line = ""
                for char in text:
                    if char == '\n':
                        lines.append(current_line)
                        current_line = ""
                        continue
                    test_line = current_line + char
                    if font.getlength(test_line) <= max_w:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = char
                lines.append(current_line)
                
                processed_text = "\n".join(lines)
                temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                bbox = temp_draw.textbbox((0, 0), processed_text, font=font, align="center")
                final_text_w, final_text_h = int(bbox[2]-bbox[0]), int(bbox[3]-bbox[1])
                draw_tasks.append((processed_text, 0, 0))
            
            else:
                # --- 垂直多列模式 ---
                max_h = orig_h - (padding * 2)
                columns = [] # 存储每一列的字符串
                current_col_chars = []
                current_col_h = 0
                
                # 过滤并处理文字
                for char in text.replace('\n', ' '):
                    bbox = font.getbbox(char)
                    char_h = (bbox[3] - bbox[1]) + (font_size // 5)
                    if current_col_h + char_h > max_h and current_col_chars:
                        columns.append("\n".join(current_col_chars))
                        current_col_chars = [char]
                        current_col_h = char_h
                    else:
                        current_col_chars.append(char)
                        current_col_h += char_h
                columns.append("\n".join(current_col_chars))
                
                # 计算每一列的宽度和总宽度
                col_widths = []
                temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                for col_txt in columns:
                    c_bbox = temp_draw.textbbox((0, 0), col_txt, font=font)
                    col_widths.append(int(c_bbox[2] - c_bbox[0]))
                
                column_gap = int(font_size // 2)
                final_text_w = sum(col_widths) + (len(columns) - 1) * column_gap
                
                # 获取文字块最大高度
                max_actual_h = 0
                curr_x = 0
                for idx, col_txt in enumerate(columns):
                    c_bbox = temp_draw.textbbox((0, 0), col_txt, font=font)
                    c_h = int(c_bbox[3] - c_bbox[1])
                    max_actual_h = max(max_actual_h, c_h)
                    # 记录每一列相对于文字块左上角的偏移
                    draw_tasks.append((col_txt, curr_x, 0))
                    curr_x += col_widths[idx] + column_gap
                final_text_h = max_actual_h

            # ---------------------------------------------------------
            # 画布与位置计算
            # ---------------------------------------------------------
            if bg_mode == "outside":
                if direction in ["top", "bottom"]:
                    new_w, new_h = orig_w, orig_h + final_text_h + (padding * 2)
                    res_img = Image.new("RGB", (int(new_w), int(new_h)), bg_col)
                    paste_pos = (0, final_text_h + padding * 2) if direction == "top" else (0, 0)
                    base_txt_x, base_txt_y = (new_w - final_text_w) // 2, (padding if direction == "top" else orig_h + padding)
                else:
                    new_w, new_h = orig_w + final_text_w + (padding * 2), orig_h
                    res_img = Image.new("RGB", (int(new_w), int(new_h)), bg_col)
                    paste_pos = (final_text_w + padding * 2, 0) if direction == "left" else (0, 0)
                    base_txt_x, base_txt_y = (padding if direction == "left" else orig_w + padding), (orig_h - final_text_h) // 2
                res_img.paste(pil_img, [int(i) for i in paste_pos])
            else:
                res_img = pil_img.copy()
                if direction == "top": base_txt_x, base_txt_y = (orig_w - final_text_w) // 2, padding
                elif direction == "bottom": base_txt_x, base_txt_y = (orig_w - final_text_w) // 2, orig_h - final_text_h - padding
                elif direction == "left": base_txt_x, base_txt_y = padding, (orig_h - final_text_h) // 2
                else: base_txt_x, base_txt_y = orig_w - final_text_w - padding, (orig_h - final_text_h) // 2

            # 绘制文字
            draw = ImageDraw.Draw(res_img)
            for content, off_x, off_y in draw_tasks:
                draw.text((int(base_txt_x + off_x), int(base_txt_y + off_y)), content, font=font, fill=txt_col, align="center", spacing=4)

            # 输出
            img_batches.append(torch.from_numpy(np.array(res_img).astype(np.float32) / 255.0).unsqueeze(0))

        return (torch.cat(img_batches, dim=0),)

# ==============================================================================
# 5. 节点映射
# ==============================================================================
NODE_CLASS_MAPPINGS = {
    "PreviewAndPause": PreviewAndPause,
    "MultiImageComparer": MultiImageComparer,
    "ImageCompareAndSelect": ImageCompareAndSelect,
    "ImageAddText": ImageAddText
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewAndPause": "Preview & Pause ⏯️",
    "MultiImageComparer": "Mult Image Comparer 🪟",
    "ImageCompareAndSelect": "Compare & Select ⏯️🖼️",
    "ImageAddText": "Image Add Text ✍️"
}