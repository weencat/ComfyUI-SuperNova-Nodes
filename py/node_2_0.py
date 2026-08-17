import os
import time
import random
import string
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from server import PromptServer
from aiohttp import web
import folder_paths
import comfy.model_management
import nodes

# ================= 万能类型通配符 =================
class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False
ANY = AnyType("*")

# ================= 全局状态管理器 =================
if "GATE_STATES" not in globals():
    GATE_STATES = {
        "flow": {},
        "image": {},
        "compare": {},
        "compare4": {}
    }

# ================= 1. Flow Control Switch =================
class FlowControlSwitch20:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"any_input": (ANY,)}, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("ANY",)
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/node2.0"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("nan")

    def execute(self, any_input, unique_id):
        node_id = str(unique_id)
        GATE_STATES["flow"][node_id] = "pause"
        print(f"\n[\033[34mFlowSwitch20\033[0m] 🚧 节点 {node_id} 已暂停...")

        while GATE_STATES["flow"].get(node_id) == "pause":
            time.sleep(0.5)
            if comfy.model_management.processing_interrupted():
                GATE_STATES["flow"][node_id] = "stop"
                break
        
        if GATE_STATES["flow"].get(node_id) == "stop":
            comfy.model_management.interrupt_current_processing()
            raise Exception("工作流已被 Flow Breakpoint 终止。")
        
        return (any_input,)

# ================= 2. Image Preview Breakpoint =================
class ImagePreviewBreakpoint20:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image": ("IMAGE",)}, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/node2.0"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("nan")

    def execute(self, image, unique_id):
        node_id = str(unique_id)
        results = []
        for batch_number, img in enumerate(image):
            i = 255. * img.cpu().numpy()
            img_pil = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            rand_str = ''.join(random.choices(string.ascii_letters, k=8))
            filename = f"preview_pause_{node_id}_{batch_number}_{rand_str}.png"
            filepath = os.path.join(folder_paths.get_temp_directory(), filename)
            img_pil.save(filepath, compress_level=4)
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        PromptServer.instance.send_sync("executed", {"node": node_id, "output": {"images": results}})
        GATE_STATES["image"][node_id] = "pause"
        
        while GATE_STATES["image"].get(node_id) == "pause":
            time.sleep(0.5)
            if comfy.model_management.processing_interrupted():
                GATE_STATES["image"][node_id] = "stop"
                break
        
        if GATE_STATES["image"].get(node_id) == "stop":
            comfy.model_management.interrupt_current_processing()
            raise Exception("工作流已被 Image Breakpoint 终止。")
            
        return {"ui": {"images": results}, "result": (image,)}

# ================= 3. Image Compare Breakpoint (双图对比) =================
class ImageCompareBreakpoint20:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_a": ("IMAGE",), 
                "image_b": ("IMAGE",),
                "compare_view": ("IMAGECOMPARE",) 
            }, 
            "hidden": {
                "unique_id": "UNIQUE_ID"
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/node2.0"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("nan")

    def execute(self, image_a=None, image_b=None, compare_view=None, unique_id=None):
        node_id = str(unique_id)
        preview_node = nodes.PreviewImage()
        
        a_imgs = preview_node.save_images(image_a, "comfy.compare.a")["ui"]["images"] if image_a is not None else []
        b_imgs = preview_node.save_images(image_b, "comfy.compare.b")["ui"]["images"] if image_b is not None else []

        result_ui = {
            "a_images": a_imgs, 
            "b_images": b_imgs
        }

        PromptServer.instance.send_sync("executed", {"node": node_id, "output": result_ui})
        
        if "compare" not in GATE_STATES:
            GATE_STATES["compare"] = {}
            
        GATE_STATES["compare"][node_id] = "pause"

        while GATE_STATES["compare"].get(node_id) == "pause":
            time.sleep(0.5)
            if comfy.model_management.processing_interrupted():
                GATE_STATES["compare"][node_id] = "stop"
                break
        
        action = GATE_STATES["compare"].get(node_id)
        if action == "stop":
            comfy.model_management.interrupt_current_processing()
            raise Exception("工作流已被 Compare Breakpoint 终止。")
        
        final_image = image_a if action == "pass_a" else image_b
        return {"ui": result_ui, "result": (final_image,)}

# ================= 4. ⭐ 全新：4 图对比与选择断点节点 ⭐ =================
class ImageCompare4Way20:
    """A 4-way image comparison preview node with auto-layout and labels."""
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "layout": (["side-by-side (并排)", "grid (2x2网格)"], {"default": "side-by-side (并排)"}),
                "target_height": ("INT", {"default": 512, "min": 256, "max": 2048, "step": 64}),
            },
            "optional": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "image_c": ("IMAGE",),
                "image_d": ("IMAGE",),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/node2.0"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, layout="side-by-side (并排)", target_height=512, image_a=None, image_b=None, image_c=None, image_d=None):
        inputs = [("Image A", image_a), ("Image B", image_b), ("Image C", image_c), ("Image D", image_d)]
        active_inputs = [(label, img) for label, img in inputs if img is not None and len(img) > 0]

        # 没有传入任何图像时，清空预览
        if not active_inputs:
            return {"ui": {"images": []}}

        pil_images = []

        # 动态加载字体
        font_size = max(18, int(target_height * 0.06))
        font = None
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "msyh.ttc", "simhei.ttf"]:
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except IOError:
                continue
        if font is None:
            font = ImageFont.load_default()

        # 处理每一张输入的图片
        for label, img_tensor in active_inputs:
            # 取 Batch 中的第一张图片
            img = img_tensor[0]
            i = 255. * img.cpu().numpy()
            pil_img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            # 等比例缩放图片到统一的高度
            w, h = pil_img.size
            new_w = max(1, int(w * (target_height / h)))
            pil_resized = pil_img.resize((new_w, target_height), Image.Resampling.LANCZOS)

            # 在左上角绘制深色标签框
            draw = ImageDraw.Draw(pil_resized)
            padding = 10
            
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except AttributeError:
                text_w = font_size * len(label) * 0.6
                text_h = font_size

            # 绘制黑底与白色标记文字
            rect_shape = [padding, padding, padding + text_w + 16, padding + text_h + 10]
            draw.rectangle(rect_shape, fill=(0, 0, 0))
            draw.text((padding + 8, padding + 4), label, fill=(255, 255, 255), font=font)

            pil_images.append(pil_resized)

        num_imgs = len(pil_images)

        # 拼接图像
        if num_imgs == 1:
            combined_img = pil_images[0]
        elif layout == "grid (2x2网格)" and num_imgs >= 3:
            # 2x2 田字格拼图
            if num_imgs == 3:
                blank = Image.new("RGB", pil_images[0].size, (30, 30, 30))
                pil_images.append(blank)

            img1, img2, img3, img4 = pil_images[:4]
            w1 = max(img1.size[0], img3.size[0])
            w2 = max(img2.size[0], img4.size[0])

            grid_w = w1 + w2
            grid_h = target_height * 2
            combined_img = Image.new("RGB", (grid_w, grid_h), (30, 30, 30))

            combined_img.paste(img1, (0, 0))
            combined_img.paste(img2, (w1, 0))
            combined_img.paste(img3, (0, target_height))
            combined_img.paste(img4, (w1, target_height))
        else:
            # 1xN 水平并排拼图
            total_w = sum(img.size[0] for img in pil_images)
            combined_img = Image.new("RGB", (total_w, target_height))
            curr_x = 0
            for img in pil_images:
                combined_img.paste(img, (curr_x, 0))
                curr_x += img.size[0]

        # 保存临时预览图
        rand_str = ''.join(random.choices(string.ascii_letters, k=8))
        filename = f"compare_4way_{rand_str}.png"
        filepath = os.path.join(folder_paths.get_temp_directory(), filename)
        combined_img.save(filepath, compress_level=4)

        return {"ui": {"images": [{"filename": filename, "subfolder": "", "type": "temp"}]}}

# ================= API 路由 =================
@PromptServer.instance.routes.post("/supernova/gate_control")
async def gate_control(request):
    data = await request.json()
    g_type = data.get("type") 
    GATE_STATES[g_type][str(data.get("node_id"))] = data.get("action")
    return web.json_response({"status": "ok"})

# ================= 注册节点 =================
NODE_CLASS_MAPPINGS = {
    "FlowControlSwitch20": FlowControlSwitch20,
    "ImagePreviewBreakpoint20": ImagePreviewBreakpoint20,
    "ImageCompareBreakpoint20": ImageCompareBreakpoint20,
    "ImageCompare4Way20": ImageCompare4Way20
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FlowControlSwitch20": "Flow Breakpoint 2.0 🕹️",
    "ImagePreviewBreakpoint20": "Image Breakpoint 2.0 ⏯️🖼️",
    "ImageCompareBreakpoint20": "Compare Breakpoint 2.0 ⚖️🖼️",
    "ImageCompare4Way20": "Image Compare 4-Way 🖼️4️⃣"
}