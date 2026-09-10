"""
Image Metadata Unified
------------------------------------------------------
合并了元数据提取器 (Extractor) 和元数据保存器 (Saver) 的功能。
包含：
1. 读取图片 PNG Info/EXIF 的节点
2. 设置、组合元数据的节点
3. 支持元数据嵌入和声音播放的保存节点
"""

import os
import re
import json
import torch
import numpy as np
from datetime import datetime
from PIL.PngImagePlugin import PngInfo

# ComfyUI 核心模块
import folder_paths
import nodes
import comfy.samplers
import comfy.cli_args
from server import PromptServer

# 依赖检查
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️警告: Pillow 库未安装。依赖 Pillow 的节点将不可用。请运行 'pip install Pillow'。")

# ======================================================================
# SECTION 1: 通用辅助函数
# ======================================================================

def sanitize_filename(filename: str) -> str: 
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def parse_checkpoint_name(name: str) -> str: 
    return os.path.basename(name) if name else ""

def parse_checkpoint_name_without_extension(name: str) -> str:
    filename, ext = os.path.splitext(parse_checkpoint_name(name))
    supported = folder_paths.supported_pt_extensions | {".gguf"}
    return filename if ext.lower() in supported else parse_checkpoint_name(name)

def get_timestamp(time_format: str) -> str: 
    return datetime.now().strftime(time_format)

def get_civitai_sampler_name(sampler_name: str, scheduler: str) -> str:
    name_map = { 
        "dpm_fast": "DPM++ 2M", "dpm_adaptive": "DPM++ 2M", "lms": "LMS", 
        "heun": "Heun", "euler": "Euler", "euler_ancestral": "Euler a", 
        "ddim": "DDIM", "uni_pc": "UniPC" 
    }
    if sampler_name in name_map: return name_map[sampler_name]
    if sampler_name.startswith("dpmpp_2m"): return "DPM++ 2M"
    if sampler_name.startswith("dpmpp_sde"): return "DPM++ SDE"
    if sampler_name.startswith("dpmpp_2s_ancestral"): return "DPM2 a"
    if sampler_name.startswith("dpmpp_3m_sde"): return "DPM++ 3M SDE"
    return "Unknown"

# ======================================================================
# SECTION 2: 元数据读取节点 (Extractor)
# ======================================================================

class ReadPngInfoFromImage:
    def __init__(self):
        self.temp_dir = os.path.join(folder_paths.get_temp_directory(), "read_info_cache")
        os.makedirs(self.temp_dir, exist_ok=True)

    @classmethod
    def IS_CHANGED(s, image, **kwargs): return float("NaN")

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image": ("IMAGE",)}, "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("metadata_json",)
    FUNCTION = "extract"
    CATEGORY = "🪐 Superova/ImageMetadata"

    def extract(self, image, prompt=None, extra_pnginfo=None, **kwargs):
        is_valid_image_input = image is not None and isinstance(image, torch.Tensor) and image.numel() > 0
        if not is_valid_image_input: return ("错误: 'image' 输入无效或为空。",)
        if extra_pnginfo and ("workflow" in extra_pnginfo or "prompt" in extra_pnginfo):
            return (json.dumps(extra_pnginfo, indent=4, ensure_ascii=False),)
        if not PIL_AVAILABLE: return ("错误: 强力读取模式需要 Pillow 库，但它未被安装。",)
        try:
            first_image_tensor = image[0]
            i = 255. * first_image_tensor.cpu().numpy()
            img_pil = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            metadata = PngInfo()
            if not comfy.cli_args.args.disable_metadata:
                if prompt is not None: metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for x in extra_pnginfo: metadata.add_text(x, json.dumps(extra_pnginfo[x]))
            temp_filename = f"temp_read_info_{os.urandom(8).hex()}.png"
            temp_filepath = os.path.join(self.temp_dir, temp_filename)
            img_pil.save(temp_filepath, pnginfo=metadata, compress_level=1)

            output_string, found_meta = ReadPngInfoFromImage._read_with_pillow(temp_filepath)
            
            try: os.remove(temp_filepath)
            except Exception as e: print(f"ReadInfoNode 警告: 无法删除临时文件 {temp_filepath}: {e}")
            if not found_meta: return ("强力读取模式失败：Pillow 未能从临时保存的文件中提取任何元数据。",)
            return (output_string,)
        except Exception as e:
            return (f"在强力读取模式中发生错误: {e}",)

    @staticmethod
    def _read_with_pillow(full_path):
        """Pillow 读取逻辑的辅助函数。这是一个静态方法。"""
        with Image.open(full_path) as img:
            all_metadata = {"source_file": os.path.basename(full_path), "format": img.format, "mode": img.mode, "size": f"{img.width}x{img.height}"}
            found_meta = False
            if img.info:
                found_meta = True
                all_metadata["png_info"] = {k: (v.decode('utf-8', 'ignore') if isinstance(v, bytes) else str(v)) for k, v in img.info.items()}
            exif_data = img.getexif()
            if exif_data:
                found_meta = True
                exif_dict = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, bytes):
                        try: exif_dict[tag_name] = value.decode('utf-8', 'ignore')
                        except: exif_dict[tag_name] = repr(value)
                    elif hasattr(value, 'numerator'): exif_dict[tag_name] = f"{value.numerator}/{value.denominator}"
                    else: exif_dict[tag_name] = str(value)
                all_metadata["exif"] = exif_dict
            return json.dumps(all_metadata, indent=4, ensure_ascii=False), found_meta

class ReadMetaFromFilePillow:
    def __init__(self):
        if not PIL_AVAILABLE: raise ImportError("Pillow 库未安装，此节点无法工作。")

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image_path": ("STRING", {"default": "ComfyUI/input/your_image.png", "multiline": True})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("metadata_json",)
    FUNCTION = "extract_from_path"
    CATEGORY = "🪐 Superova/ImageMetadata"
    
    def extract_from_path(self, image_path):
        full_path = image_path.strip()
        if not os.path.isabs(full_path):
            comfy_root = os.path.abspath(os.path.join(folder_paths.get_input_directory(), ".."))
            full_path = os.path.join(comfy_root, full_path)
        if not os.path.isfile(full_path):
            return (f"错误: 文件未找到于路径 '{full_path}'",)

        try:
            output_string, found_meta = ReadPngInfoFromImage._read_with_pillow(full_path)
            
            if not found_meta:
                return ("未在该图片中找到可读的 PNG Info 或 EXIF 元数据。",)
            return (output_string,)
        except Exception as e:
            return (f"处理图片时发生错误: {e}",)

# ======================================================================
# SECTION 3: 元数据设置与组合节点 (Settings & Logic)
# ======================================================================

class ImageMetadataSettings:
    @classmethod
    def INPUT_TYPES(s):
        return { "required": {
                "filename": ("STRING", {"default": '%time_%basemodelname_%seed', "tooltip":"Original time format: {date} is year-month-day, {time} is hour-minute-second, {datetime} is year-month-day_hour-minute-second.\nFormat used when accessing metadata settings\n%date: year-month-day (%Y-%m-%d)\n%time: hour-minute-second (%H%M%S)\n%model: model name\n%width: width\n%height: height\n%seed: number of random seeds\n%sampler_name: sampler name\n%steps: number of steps\n%cfg: number of CFGs\n%scheduler_name: scheduler name\n%basemodelname: base model name"}), "modelname": ("STRING", {"default": ''}),
                "positive": ("STRING", {"default": 'positive_text', "multiline": True}), "negative": ("STRING", {"default": 'negative_text', "multiline": True}),
                "seed_value": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}), "steps": ("INT", {"default": 20}),
                "cfg": ("FLOAT", {"default": 7.0}), "sampler_name": (comfy.samplers.KSampler.SAMPLERS, ),
                "scheduler_name": (comfy.samplers.KSampler.SCHEDULERS, ), "width": ("INT", {"default": 512, "step": 8}),
                "height": ("INT", {"default": 512, "step": 8}),
            }, "optional": { "time_format": ("STRING", {"default": "%Y-%m-%d-%H%M%S"}), }
        }
    RETURN_TYPES = ("METADATA",); FUNCTION = "package_settings"; CATEGORY = "🪐 Superova/ImageMetadata"
    def package_settings(self, **kwargs): return (kwargs,)

class MetadataFilenameSettings:
    @classmethod
    def INPUT_TYPES(s): return { "required": { "filename": ("STRING", {"default": '%time_%basemodelname_%seed', "tooltip":"Original time format: {date} is year-month-day, {time} is hour-minute-second, {datetime} is year-month-day_hour-minute-second.\nFormat used when accessing metadata settings\n%date: year-month-day (%Y-%m-%d)\n%time: hour-minute-second (%H%M%S)\n%model: model name\n%width: width\n%height: height\n%seed: number of random seeds\n%sampler_name: sampler name\n%steps: number of steps\n%cfg: number of CFGs\n%scheduler_name: scheduler name\n%basemodelname: base model name"}), "time_format": ("STRING", {"default": "%Y-%m-%d-%H%M%S"}), }, "optional": {"METADATA": ("METADATA",)} }
    RETURN_TYPES = ("METADATA",); FUNCTION = "Metadata"; CATEGORY = "🪐 Superova/ImageMetadata/MetadataSeries"
    def Metadata(self, filename, time_format, METADATA=None):
        package = (METADATA or {}).copy(); package.update({"filename": filename, "time_format": time_format}); return (package,)

class MetadataPromptsSettings:
    @classmethod
    def INPUT_TYPES(s): return { "required": { "positive": ("STRING", {"default": "positive_text", "multiline": True}), "negative": ("STRING", {"default": "negative_text", "multiline": True}), }, "optional": {"METADATA": ("METADATA",)} }
    RETURN_TYPES = ("METADATA",); FUNCTION = "Metadata"; CATEGORY = "🪐 Superova/ImageMetadata/MetadataSeries"
    def Metadata(self, positive, negative, METADATA=None):
        package = (METADATA or {}).copy(); package.update({"positive": positive, "negative": negative}); return (package,)

class MetadataSamplingSettings:
    @classmethod
    def INPUT_TYPES(s):
        return { "required": { "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}), "steps": ("INT", {"default": 20}), "cfg": ("FLOAT", {"default": 7.0}), "sampler_name": (comfy.samplers.KSampler.SAMPLERS, ), "scheduler_name": (comfy.samplers.KSampler.SCHEDULERS, ), }, "optional": {"METADATA": ("METADATA",)} }
    RETURN_TYPES = ("METADATA",); FUNCTION = "Metadata"; CATEGORY = "🪐 Superova/ImageMetadata/MetadataSeries"
    def Metadata(self, seed, steps, cfg, sampler_name, scheduler_name, METADATA=None):
        package = (METADATA or {}).copy(); package.update({ "seed_value": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler_name, "scheduler_name": scheduler_name }); return (package,)

class MetadataDimensionsSettings:
    @classmethod
    def INPUT_TYPES(s): return { "required": { "width": ("INT", {"default": 512, "step": 8}), "height": ("INT", {"default": 512, "step": 8}), }, "optional": {"METADATA": ("METADATA",)} }
    RETURN_TYPES = ("METADATA",); FUNCTION = "Metadata"; CATEGORY = "🪐 Superova/ImageMetadata/MetadataSeries"
    def Metadata(self, width, height, METADATA=None):
        package = (METADATA or {}).copy(); package.update({"width": width, "height": height}); return (package,)

class CombineMetadata:
    @classmethod
    def INPUT_TYPES(s): return { "optional": { "METADATA_a": ("METADATA",), "METADATA_b": ("METADATA",), "METADATA_c": ("METADATA",), "METADATA_d": ("METADATA",), }}
    RETURN_TYPES = ("METADATA",); FUNCTION = "combine"; CATEGORY = "🪐 Superova/ImageMetadata/MetadataSeries"
    def combine(self, **kwargs):
        combined = {}; [combined.update(p) for k, p in kwargs.items() if p]; return (combined,)

# ======================================================================
# SECTION 4: 保存节点 (Saver)
# ======================================================================

class SaveImageWithSoundAndMetadata(nodes.SaveImage):
    def __init__(self): super().__init__()
    @classmethod
    def INPUT_TYPES(s):
        types = super().INPUT_TYPES(); types["optional"] = { "METADATA": ("METADATA",), "sound_file": ("STRING", {"default": "sound.mp3"}), "volume": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}), }; types["required"]["filename_prefix"][1].update({"default": "ComfyUI_{date}", "tooltip":"Original time format: {date} is year-month-day, {time} is hour-minute-second, {datetime} is year-month-day_hour-minute-second.\nFormat used when accessing metadata settings\n%date: year-month-day (%Y-%m-%d)\n%time: hour-minute-second (%H%M%S)\n%model: model name\n%width: width\n%height: height\n%seed: number of random seeds\n%sampler_name: sampler name\n%steps: number of steps\n%cfg: number of CFGs\n%scheduler_name: scheduler name\n%basemodelname: base model name"}); return types
    
    FUNCTION = "save_images"; CATEGORY = "🪐 Superova/ImageMetadata"
    
    def save_images(self, images, filename_prefix="ComfyUI_{date}", prompt=None, extra_pnginfo=None, METADATA=None, sound_file="sound.mp3", volume=0.8):
        final_filename = filename_prefix
        final_pnginfo = extra_pnginfo.copy() if extra_pnginfo else {}

        if METADATA and isinstance(METADATA, dict):
            p = METADATA
            p_filename = p.get('filename','f'); p_model = p.get('modelname',''); p_pos = p.get('positive',''); p_neg = p.get('negative',''); p_seed = p.get('seed_value',0); p_steps = p.get('steps',20); p_cfg = p.get('cfg',7.0); p_sampler = p.get('sampler_name',''); p_scheduler = p.get('scheduler_name',''); p_w = p.get('width',512); p_h = p.get('height',512); p_tf = p.get('time_format','')
            replacements = { "%date": get_timestamp("%Y-%m-%d"), "%time": get_timestamp(p_tf), "%model": parse_checkpoint_name(p_model), "%width": str(p_w), "%height": str(p_h), "%seed": str(p_seed), "%sampler_name": p_sampler, "%steps": str(p_steps), "%cfg": str(p_cfg), "%scheduler_name": p_scheduler, "%basemodelname": parse_checkpoint_name_without_extension(p_model), }
            for k, v in replacements.items(): p_filename = p_filename.replace(k, str(v))
            
            # 分离路径和文件名，只净化文件名以保留子目录
            directory, basename = os.path.split(p_filename)
            sanitized_basename = sanitize_filename(basename)
            final_filename = os.path.join(directory, sanitized_basename)

            final_pnginfo['parameters'] = ( f"{p_pos.strip()}\nNegative prompt: {p_neg.strip()}\n" f"Steps: {p_steps}, Sampler: {get_civitai_sampler_name(p_sampler, p_scheduler)}, CFG scale: {p_cfg}, " f"Seed: {p_seed}, Size: {p_w}x{p_h}, Model: {parse_checkpoint_name_without_extension(p_model)}" )
        else:
            now = datetime.now()
            final_filename = final_filename.replace("{date}", now.strftime("%Y-%m-%d")).replace("{time}", now.strftime("%H-%M-%S")).replace("{datetime}", now.strftime("%Y-%m-%d_%H-%M-%S"))

        results = super().save_images(images, final_filename, prompt, final_pnginfo)

        if sound_file and sound_file.strip():
            try: PromptServer.instance.send_sync("play_sound_on_save", {"sound_file": sound_file, "volume": volume})
            except Exception as e: print(f"ImageSaver 错误: 无法播放声音。 {e}")
        
        return results

# ======================================================================
# SECTION 5: 节点注册
# ======================================================================

NODE_CLASS_MAPPINGS = {
    "ReadPngInfoFromImage": ReadPngInfoFromImage,
    "ImageMetadataSettings": ImageMetadataSettings,
    "MetadataFilenameSettings": MetadataFilenameSettings,
    "MetadataPromptsSettings": MetadataPromptsSettings,
    "MetadataSamplingSettings": MetadataSamplingSettings,
    "MetadataDimensionsSettings": MetadataDimensionsSettings,
    "CombineMetadata": CombineMetadata,
    "SaveImageWithSoundAndMetadata": SaveImageWithSoundAndMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ReadPngInfoFromImage": "Read PNG Info 📄",
    "ImageMetadataSettings": "Metadata Settings 🛠️",
    "MetadataFilenameSettings": "Metadata Filename ⚙️",
    "MetadataPromptsSettings": "Metadata Prompts ⚙️",
    "MetadataSamplingSettings": "Metadata Sampling ⚙️",
    "MetadataDimensionsSettings": "Metadata Dimensions ⚙️",
    "CombineMetadata": "Combine Metadata 📦",
    "SaveImageWithSoundAndMetadata": "Save Image (MetadataSet) 🔊",
}

if PIL_AVAILABLE:
    NODE_CLASS_MAPPINGS["ReadMetaFromFilePillow"] = ReadMetaFromFilePillow
    NODE_DISPLAY_NAME_MAPPINGS["ReadMetaFromFilePillow"] = "Read Meta from Image File 📄"