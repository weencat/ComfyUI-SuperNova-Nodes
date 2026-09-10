import os
import datetime
import json
import random
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

# 导入 ComfyUI 核心模块
import folder_paths
from nodes import SaveImage
from server import PromptServer

# ============================================================================
# 公共辅助函数：处理日期占位符
# ============================================================================
def apply_filename_formatting(filename_prefix):
    """
    统一处理 {date}, {time}, {datetime} 替换逻辑。
    两个节点都调用这个函数，实现逻辑共用。
    """
    now = datetime.datetime.now()
    formatted_prefix = filename_prefix.replace("{date}", now.strftime("%Y-%m-%d"))
    formatted_prefix = formatted_prefix.replace("{time}", now.strftime("%H-%M-%S"))
    formatted_prefix = formatted_prefix.replace("{datetime}", now.strftime("%Y-%m-%d_%H-%M-%S"))
    return formatted_prefix

# ============================================================================
# 节点 1: SaveImageToInput
# ============================================================================
class SaveImageToInput:
    def __init__(self):
        self.temp_dir = folder_paths.get_temp_directory()
        self.type = "temp"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "Comfy_{date}","tooltip": "Original time format: {date} is year-month-day, {time} is hour-minute-second, {datetime} is year-month-day_hour-minute-second.\nFormat used when accessing metadata settings\n%date: year-month-day (%Y-%m-%d)\n%time: hour-minute-second (%H%M%S)\n%model: model name\n%width: width\n%height: height\n%seed: number of random seeds\n%sampler_name: sampler name\n%steps: number of steps\n%cfg: number of CFGs\n%scheduler_name: scheduler name\n%basemodelname: base model name"}),
                "save_to_reload": ("BOOLEAN", {"default": False, "label_on": "save to 'input/reload'", "label_off": "save to 'input'"})
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "🪐 Superova/ImageSaver"

    def save_images(self, images, filename_prefix="{date}", save_to_reload=False, prompt=None, extra_pnginfo=None):
        # 1. 确定保存路径
        input_dir = folder_paths.get_input_directory()
        if save_to_reload:
            output_dir = os.path.join(input_dir, "reload")
            tooltip_prefix = "保存到 'input/reload' 文件夹的文件名前缀"
        else:
            output_dir = input_dir
            tooltip_prefix = "保存到 'input' 文件夹的文件名前缀"

        # 2. 更新 Tooltip (可选)
        try:
            self.INPUT_TYPES()["required"]["filename_prefix"] = ("STRING", {"default": "{date}", "tooltip": tooltip_prefix})
        except:
            pass

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # ==========================================
        # 3. 【共用逻辑】调用公共函数处理文件名
        # ==========================================
        processed_prefix = apply_filename_formatting(filename_prefix)

        # 4. 获取保存路径 (Input 目录需要手动处理保存，不能用 super)
        full_output_folder, filename, counter, subfolder, final_filename_prefix = folder_paths.get_save_image_path(processed_prefix, output_dir, images[0].shape[1], images[0].shape[0])
        
        preview_results = list()
        for image in images:
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for x in extra_pnginfo:
                    metadata.add_text(x, json.dumps(extra_pnginfo[x]))

            file = f"{filename}_{counter:05}_.png"
            img.save(os.path.join(full_output_folder, file), pnginfo=metadata, compress_level=4)
            
            # 生成预览
            preview_filename = f"{final_filename_prefix}_{''.join(random.choice('abcdefghijklmnopqrstupvxyz') for x in range(5))}.png"
            img.save(os.path.join(self.temp_dir, preview_filename), pnginfo=metadata, compress_level=1) 
            
            preview_results.append({
                "filename": preview_filename,
                "subfolder": "",
                "type": self.type
            })
            
            counter += 1

        return {"ui": {"images": preview_results}}


# ============================================================================
# 节点 2: SaveImageWithSound
# ============================================================================
class SaveImageWithSound(SaveImage):
    def __init__(self):
        super().__init__()

    @classmethod
    def INPUT_TYPES(s):
        types = super().INPUT_TYPES()
        
        if "filename_prefix" in types["required"]:
            types["required"]["filename_prefix"][1]["default"] = "Comfy_{date}"
            types["required"]["filename_prefix"][1]["tooltip"] = "支持 {date}, {time}, {datetime} 占位符"

        # 添加可选的输入接入口
        if "optional" not in types:
            types["optional"] = {}
            
        # 增加 Prompt 和 Negative Prompt 的接入口
        types["optional"]["positive_prompt"] = ("STRING", {"default": "", "multiline": True, "forceInput": True})
        types["optional"]["negative_prompt"] = ("STRING", {"default": "", "multiline": True, "forceInput": True})

        return types

    def save_images(self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None, positive_prompt="", negative_prompt=""):
        # 1. 格式化前缀 (假设该函数在外部已定义)
        formatted_prefix = apply_filename_formatting(filename_prefix)
        
        # 2. 注入提示词到图像元数据 (extra_pnginfo)
        if extra_pnginfo is None:
            extra_pnginfo = {}
        else:
            extra_pnginfo = extra_pnginfo.copy()
            
        # 按照需求，将正负提示词组合成列表格式的 JSON 结构
        # 如果未接入或者为空，则填入空字符串 [""]，表示空值
        custom_prompts = {
            "Positive_Prompt": [positive_prompt] if positive_prompt else [""],
            "Negative_Prompt": [negative_prompt] if negative_prompt else [""]
        }
        
        # 将组合好的字典作为一个整体存入，键名可以自定义，这里用 "Custom_Prompts"
        # ComfyUI 最终会自动把它序列化为: {"Positive_Prompt": ["你的正向词"], "Negative_Prompt": ["你的反向词"]}
        extra_pnginfo["Custom_Prompts"] = custom_prompts
            
        # 3. 调用父类方法保存图片
        results = super().save_images(images, formatted_prefix, prompt, extra_pnginfo)

        # 4. 仅发送一个触发信号
        try:
            PromptServer.instance.send_sync("supernova_save_image_done", {})
        except Exception as e:
            print(f"[SaveImageWithSound] 错误: 无法发送播放声音的信号: {e}")

        return results

    CATEGORY = "🪐 Superova/ImageSaver"

# ============================================================================
# 节点注册
# ============================================================================
NODE_CLASS_MAPPINGS = {
    "SaveImageToInput": SaveImageToInput,
    "SaveImageWithSound": SaveImageWithSound
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveImageToInput": "Save Image To Input 🖼️",
    "SaveImageWithSound": "Save Image (with Sound) 🔊🖼️"
}