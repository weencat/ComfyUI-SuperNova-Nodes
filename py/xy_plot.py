# XY Plot Node V9 (with Settings Node)
# Extracted and adapted from Efficiency Nodes by Luciano Cirino (https://github.com/LucianoCirino/efficiency-nodes-comfyui)

import os
import sys
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
import comfy.samplers
import comfy.sd
import comfy.utils
import folder_paths
from nodes import KSampler, VAEDecode, CLIPTextEncode

# ======================================================================================================================
# 全局变量和辅助函数
# ======================================================================================================================

my_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(my_dir, '..', 'Fonts', 'local.ttf')

if not os.path.exists(font_path):
    print(f"警告：在指定路径找不到字体文件 '{font_path}'。将尝试系统备用字体。")
    try:
        if sys.platform == "win32": font_path = "C:/Windows/Fonts/arial.ttf"
        elif sys.platform == "darwin": font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
        else: font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        if not os.path.exists(font_path): font_path = None
    except:
        font_path = None

XYPLOT_LIM = 50
XYPLOT_DEF = 3
LORA_EXTENSIONS = ['.safetensors', '.ckpt']
try:
    xy_batch_default_path = os.path.abspath(os.sep)
except Exception:
    xy_batch_default_path = ""

def pil2tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)

def tensor2pil(image):
    return Image.fromarray(np.clip(255. * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))

def generate_floats(batch_count, first_float, last_float):
    if batch_count > 1:
        interval = (last_float - first_float) / (batch_count - 1) if (batch_count - 1) != 0 else 0
        return [round(first_float + i * interval, 3) for i in range(batch_count)]
    else:
        return [first_float] if batch_count == 1 else []

def generate_ints(batch_count, first_int, last_int):
    if batch_count > 1:
        interval = (last_int - first_int) / (batch_count - 1) if (batch_count - 1) != 0 else 0
        values = [int(first_int + i * interval) for i in range(batch_count)]
    else:
        values = [first_int] if batch_count == 1 else []
    values = sorted(list(set(values)))
    return values

def get_batch_files(directory_path, valid_extensions, include_subdirs=False):
    batch_files = []
    try:
        if include_subdirs:
            for dirpath, _, filenames in os.walk(directory_path):
                for file in filenames:
                    if any(file.lower().endswith(ext) for ext in valid_extensions):
                        batch_files.append(os.path.join(dirpath, file))
        else:
            batch_files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) if
                           os.path.isfile(os.path.join(directory_path, f)) and any(
                               f.lower().endswith(ext) for ext in valid_extensions)]
    except Exception as e:
        print(f"在 {directory_path} 中列出文件时出错: {e}")
    return batch_files

# ======================================================================================================================
# 核心 XY Plot 节点 (V9)
# ======================================================================================================================
class StandaloneXYPlot:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive_text": ("STRING", {"multiline": True, "default": "positive prompt"}),
                "negative_text": ("STRING", {"multiline": True, "default": "negative prompt"}),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }, 
            "optional": { "X": ("XY",), "Y": ("XY",), "XY_PLOT_SETTINGS": ("XY_PLOT_SETTINGS",) }
        }
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("IMAGE", "IMAGE"), ("XY Plot Image", "Batched Images"), "plot", "🪐supernova/XY Plot"

    def plot(self, model, clip, vae, positive_text, negative_text, latent_image, seed, steps, cfg, sampler_name, scheduler, denoise, X=None, Y=None, XY_PLOT_SETTINGS=None):
        # --- 新增：从设置节点或默认值中获取参数 ---
        if XY_PLOT_SETTINGS:
            grid_spacing = XY_PLOT_SETTINGS.get("grid_spacing", 10)
            xy_flip = XY_PLOT_SETTINGS.get("xy_flip", "False")
            y_label_orientation = XY_PLOT_SETTINGS.get("y_label_orientation", "Horizontal")
        else:
            grid_spacing, xy_flip, y_label_orientation = 10, "False", "Horizontal"
        
        X_type, X_value = X if X else ("Nothing", [""])
        Y_type, Y_value = Y if Y else ("Nothing", [""])
        
        if xy_flip == "True":
            X_type, Y_type = Y_type, X_type
            X_value, Y_value = Y_value, X_value

        if X_type == Y_type and X_type != "Nothing":
            print("XY Plot 错误：X 和 Y 输入类型必须不同。")
            return (None, None)

        image_pil_list, image_tensor_list = [], []
        
        # ... (内部的图像生成循环代码保持不变) ...
        for y_idx, y_val in enumerate(Y_value):
            for x_idx, x_val in enumerate(X_value):
                # ... 省略与 V8 版本相同的内部逻辑 ...
                current_seed, current_steps, current_cfg = seed, steps, cfg
                current_sampler, current_scheduler, current_denoise = sampler_name, scheduler, denoise
                current_model, current_clip = model.clone(), clip.clone()
                lora_stack = []
                lora_types = ["LoRA Batch", "LoRA Wt", "LoRA MStr", "LoRA CStr"]
                is_mstr_cstr_plot = (X_type == "LoRA MStr" and Y_type == "LoRA CStr") or (X_type == "LoRA CStr" and Y_type == "LoRA MStr")
                
                if is_mstr_cstr_plot:
                    lora_path = x_val[0][0] 
                    m_str = x_val[0][1] if X_type == "LoRA MStr" else y_val[0][1]
                    c_str = y_val[0][2] if Y_type == "LoRA CStr" else x_val[0][2]
                    lora_stack = [(lora_path, m_str, c_str)]
                else:
                    if X_type == "LoRA Batch" and Y_type in lora_types:
                        lora_path = x_val[0][0]
                        m_str = y_val if Y_type == "LoRA MStr" else (y_val if Y_type == "LoRA Wt" else x_val[0][1])
                        c_str = y_val if Y_type == "LoRA CStr" else (y_val if Y_type == "LoRA Wt" else x_val[0][2])
                        lora_stack = [(lora_path, m_str, c_str)]
                    elif Y_type == "LoRA Batch" and X_type in lora_types:
                        lora_path = y_val[0][0]
                        m_str = x_val if X_type == "LoRA MStr" else (x_val if X_type == "LoRA Wt" else y_val[0][1])
                        c_str = x_val if X_type == "LoRA CStr" else (x_val if X_type == "LoRA Wt" else y_val[0][2])
                        lora_stack = [(lora_path, m_str, c_str)]
                    else:
                        temp_params = [(X_type, x_val), (Y_type, y_val)]
                        for param_type, param_val in temp_params:
                            if not param_val: continue
                            if param_type == "Seeds++ Batch": current_seed += param_val
                            elif param_type == "Steps": current_steps = param_val
                            elif param_type == "CFG Scale": current_cfg = param_val
                            elif param_type == "Denoise": current_denoise = param_val
                            elif param_type == "Sampler":
                                current_sampler, scheduler_override = param_val
                                if scheduler_override: current_scheduler = scheduler_override
                            elif param_type == "Scheduler":
                                current_scheduler = param_val[0] if isinstance(param_val, tuple) else param_val
                            elif param_type in lora_types:
                                lora_stack.extend(param_val)
                
                if lora_stack:
                    print(f"应用LoRA栈: {lora_stack}")
                    for lora_path, model_str, clip_str in lora_stack:
                        if lora_path is None or lora_path.lower() == 'none' or not lora_path.strip(): continue
                        if os.path.exists(lora_path) and os.path.isfile(lora_path):
                            try:
                                lora_data = comfy.utils.load_torch_file(lora_path)
                                lora_model, lora_clip = comfy.sd.load_lora_for_models(current_model, current_clip, lora_data, model_str, clip_str)
                                current_model, current_clip = lora_model, lora_clip
                            except Exception as e:
                                print(f"加载 LoRA '{os.path.basename(lora_path)}' 失败: {e}")
                        else:
                            print(f"找不到 LoRA 文件，路径无效: {lora_path}")

                positive_cond, negative_cond = CLIPTextEncode().encode(current_clip, positive_text)[0], CLIPTextEncode().encode(current_clip, negative_text)[0]
                print(f"正在生成: X={x_idx}, Y={y_idx} | seed={current_seed}")
                latent_out = KSampler().sample(current_model, current_seed, current_steps, current_cfg, current_sampler, current_scheduler, positive_cond, negative_cond, latent_image, denoise=current_denoise)[0]
                image = VAEDecode().decode(vae, latent_out)[0]
                image_tensor_list.append(image)
                image_pil_list.append(tensor2pil(image))
                
        if not image_pil_list: return (None, None)

        # ... (绘图逻辑与 V8 版本相同) ...
        num_cols, num_rows = len(X_value), len(Y_value)
        i_width, i_height = image_pil_list[0].size
        
        def format_label(val, type):
            if type == "LoRA Batch":
                if isinstance(val, list) and val:
                    lora_path, _, _ = val[0]
                    if lora_path is None or lora_path.lower() == 'none': return "None"
                    name_part = os.path.splitext(os.path.basename(lora_path))[0]
                    return name_part[:22] + "..." if len(name_part) > 25 else name_part
            if type == "LoRA Wt": return f"Wt: {val:.2f}"
            if type == "LoRA MStr": return f"MStr: {val:.2f}"
            if type == "LoRA CStr": return f"CStr: {val:.2f}"
            return str(val[0]) if isinstance(val, (list, tuple)) else str(val)

        X_label, Y_label = [format_label(v, X_type) for v in X_value], [format_label(v, Y_type) for v in Y_value]

        border_size_top, border_size_left = i_height // 15, i_width // 15
        x_offset_initial = border_size_left * 4 if Y_type != "Nothing" else 0
        y_offset_initial = border_size_top * 3 if X_type != "Nothing" else 0
        bg_width = (num_cols * i_width) + ((num_cols - 1) * grid_spacing) + x_offset_initial
        bg_height = (num_rows * i_height) + ((num_rows - 1) * grid_spacing) + y_offset_initial
        background = Image.new('RGB', (bg_width, bg_height), color=(255, 255, 255))
        
        font_size = max(12, int(min(i_width, i_height) * 0.04))
        try: font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except Exception as e: font = ImageFont.load_default()

        y_offset = y_offset_initial
        for row in range(num_rows):
            x_offset = x_offset_initial
            for col in range(num_cols):
                background.paste(image_pil_list[row * num_cols + col], (x_offset, y_offset))
                if row == 0 and X_type != "Nothing":
                    draw = ImageDraw.Draw(background)
                    draw.text((x_offset + i_width / 2, y_offset_initial / 2), X_label[col], font=font, fill="black", anchor="mm")
                x_offset += i_width + grid_spacing
            
            if Y_type != "Nothing":
                draw = ImageDraw.Draw(background)
                if y_label_orientation == "Vertical":
                    # 创建一个临时图像来旋转文字
                    txt_img = Image.new('L', (i_height, font_size + 10))
                    d = ImageDraw.Draw(txt_img)
                    d.text((i_height/2, (font_size+10)/2), Y_label[row], font=font, fill=255, anchor="mm")
                    w = txt_img.rotate(90, expand=1)
                    background.paste(ImageOps.colorize(w, (0,0,0), (0,0,0)), (int(x_offset_initial/2 - w.size[0]/2) , y_offset + int(i_height/2 - w.size[1]/2)),  w)
                else:
                    draw.text((x_offset_initial / 2, y_offset + i_height / 2), Y_label[row], font=font, fill="black", anchor="mm")
            y_offset += i_height + grid_spacing
        
        return (pil2tensor(background), torch.cat(image_tensor_list, dim=0))

# ======================================================================================================================
# XY Plot 设置节点
# ======================================================================================================================

class XYPlotSettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "grid_spacing": ("INT", {"default": 10, "min": 0, "max": 500, "step": 1}),
                "xy_flip": (["False", "True"],),
                "y_label_orientation": (["Horizontal", "Vertical"],),
            }
        }
    RETURN_TYPES = ("XY_PLOT_SETTINGS",)
    FUNCTION = "get_settings"
    CATEGORY = "🪐supernova/XY Plot"

    def get_settings(self, grid_spacing, xy_flip, y_label_orientation):
        settings_dict = {
            "grid_spacing": grid_spacing,
            "xy_flip": xy_flip,
            "y_label_orientation": y_label_orientation,
        }
        return (settings_dict,)

# ======================================================================================================================
# XY 输入节点
# ======================================================================================================================

class TSC_XYplot_LoRA_Plot:
    modes = ["X: LoRA Batch, Y: LoRA Weight", "X: LoRA Batch, Y: Model Strength", "X: LoRA Batch, Y: Clip Strength", "X: Model Strength, Y: Clip Strength"]
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
                "input_mode": (cls.modes,), "lora_name": (["None"] + folder_paths.get_filename_list("loras"),),
                "model_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "X_batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "X_batch_path": ("STRING", {"default": xy_batch_default_path}),
                "X_subdirectories": ("BOOLEAN", {"default": False}), "X_batch_sort": (["ascending", "descending"],),
                "X_first_value": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "X_last_value": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "Y_batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}),
                "Y_first_value": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "Y_last_value": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
        }}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY","XY",), ("X","Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def __init__(self): self.lora_batch = TSC_XYplot_LoRA_Batch()
    def xy_value(self, input_mode, lora_name, model_strength, clip_strength, X_batch_count, X_batch_path, X_subdirectories, X_batch_sort, X_first_value, X_last_value, Y_batch_count, Y_first_value, Y_last_value):
        x_tuple, y_tuple = None, None
        
        lora_identifier = folder_paths.get_full_path("loras", lora_name) if lora_name != 'None' else 'None'
        is_mstr_cstr_plot = "Model Strength" in input_mode and "Clip Strength" in input_mode
        
        if is_mstr_cstr_plot and lora_identifier == 'None':
            print("XY Plot 错误: 使用 'MStr/CStr' 模式时必须从下拉菜单选择一个LoRA。")
            return (None, None)

        if X_batch_count > 0:
            if "X: LoRA Batch" in input_mode:
                x_result = self.lora_batch.xy_value(X_batch_path, X_subdirectories, X_batch_sort, model_strength, clip_strength, X_batch_count)
                if x_result and x_result[0]: x_tuple = x_result[0]
            elif "X: Model Strength" in input_mode:
                x_floats = generate_floats(X_batch_count, X_first_value, X_last_value)
                if is_mstr_cstr_plot:
                    x_value = [[(lora_identifier, x, clip_strength)] for x in x_floats]
                else:
                    x_value = x_floats
                x_tuple = ("LoRA MStr", x_value)

        if Y_batch_count > 0:
            y_floats = generate_floats(Y_batch_count, Y_first_value, Y_last_value)
            if "Y: LoRA Weight" in input_mode: y_tuple = ("LoRA Wt", y_floats)
            elif "Y: Model Strength" in input_mode: y_tuple = ("LoRA MStr", y_floats)
            elif "Y: Clip Strength" in input_mode:
                if is_mstr_cstr_plot:
                    y_value = [[(lora_identifier, model_strength, y)] for y in y_floats]
                else:
                    y_value = y_floats
                y_tuple = ("LoRA CStr", y_value)
        
        return (x_tuple, y_tuple)

# ... (其他所有简单的 XY 输入节点) ...
class TSC_XYplot_SeedsBatch:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, batch_count): return (("Seeds++ Batch", list(range(batch_count))),) if batch_count > 0 else (None,)

class TSC_XYplot_Steps:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "first_step": ("INT", {"default": 10, "min": 1, "max": 10000}), "last_step": ("INT", {"default": 20, "min": 1, "max": 10000}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, batch_count, first_step, last_step): return (("Steps", generate_ints(batch_count, first_step, last_step)),)

class TSC_XYplot_CFG:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "first_cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 100.0}), "last_cfg": ("FLOAT", {"default": 9.0, "min": 0.0, "max": 100.0}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, batch_count, first_cfg, last_cfg): return (("CFG Scale", generate_floats(batch_count, first_cfg, last_cfg)),)

class TSC_XYplot_Sampler_Scheduler:
    parameters = ["sampler", "scheduler", "sampler & scheduler"]
    @classmethod
    def INPUT_TYPES(cls):
        samplers, schedulers = ["None"] + comfy.samplers.KSampler.SAMPLERS, ["None"] + comfy.samplers.KSampler.SCHEDULERS
        inputs = {"required": {"target_parameter": (cls.parameters,), "input_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"].update({f"sampler_{i}": (samplers,), f"scheduler_{i}": (schedulers,)})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, target_parameter, input_count, **kwargs):
        xy_value, xy_type = [], ""
        if target_parameter == "scheduler":
            xy_type, values = "Scheduler", [kwargs.get(f"scheduler_{i}") for i in range(1, input_count + 1)]
            xy_value = [v for v in values if v != "None"]
        else:
            xy_type, samplers = "Sampler", [kwargs.get(f"sampler_{i}") for i in range(1, input_count + 1)]
            if target_parameter == "sampler": xy_value = [(s, None) for s in samplers if s != "None"]
            else:
                schedulers = [kwargs.get(f"scheduler_{i}") for i in range(1, input_count + 1)]
                xy_value = [(s, sc if sc != "None" else None) for s, sc in zip(samplers, schedulers) if s != "None"]
        return ((xy_type, xy_value),) if xy_value else (None,)
    
class TSC_XYplot_Denoise:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "first_denoise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}), "last_denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, batch_count, first_denoise, last_denoise): return (("Denoise", generate_floats(batch_count, first_denoise, last_denoise)),)

class TSC_XYplot_LoRA_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
                "batch_path": ("STRING", {"default": xy_batch_default_path}), "subdirectories": ("BOOLEAN", {"default": False}),
                "batch_sort": (["ascending", "descending"],),
                "batch_max": ("INT",{"default": -1, "min": -1, "max": XYPLOT_LIM}),
                "model_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01})}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐supernova/XY Plot/Inputs"
    def xy_value(self, batch_path, subdirectories, batch_sort, model_strength, clip_strength, batch_max):
        if batch_max == 0: return (None,)
        loras = get_batch_files(batch_path, LORA_EXTENSIONS, include_subdirs=subdirectories)
        if not loras: return (None,)
        loras.sort(reverse=(batch_sort == "descending"))
        xy_value = [[(lora_path, model_strength, clip_strength)] for lora_path in loras]
        if batch_max != -1: xy_value = xy_value[:batch_max]
        return (("LoRA Batch", xy_value),) if xy_value else (None,)

# 全新的统一 Sampler/Scheduler 列表构建节点 -----------------------------------
class XY_Input_Sampler_Scheduler_Builder:
    """
    逐个构建一个 Sampler 与/或 Scheduler 的组合列表。
    可以通过模式选择器来决定输出类型，以避免XY轴类型冲突。
    每个节点既可以串联，也可以作为最后一个节点直接连接到 XY Plot。
    """
    # 关键修复点 1: 添加模式选择器
    MODES = ["Sampler & Scheduler", "Sampler Only", "Scheduler Only"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 将模式选择器添加到必需的输入中
                "mode": (cls.MODES,),
                
                "sampler_name": (["None"] + comfy.samplers.KSampler.SAMPLERS,),
                "scheduler_name": (["None"] + comfy.samplers.KSampler.SCHEDULERS,),
            },
            "optional": {
                "previous_list": ("SAMPLER_SCHEDULER_LIST",)
            }
        }

    RETURN_TYPES = ("SAMPLER_SCHEDULER_LIST", "XY")
    RETURN_NAMES = ("Chained List", "X or Y")
    FUNCTION = "build_list"
    CATEGORY = "🪐supernova/XY Plot/Inputs"

    # 关键修复点 2: 在函数中接收新的 mode 参数
    def build_list(self, mode, sampler_name, scheduler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        
        # 构建列表的逻辑保持不变，总是存储 (sampler, scheduler) 对
        # 只有在 sampler 或 scheduler 至少有一个被选择时才添加
        if sampler_name != "None" or scheduler_name != "None":
            sampler_val = sampler_name if sampler_name != "None" else "None" # 保留 "None" 作为占位符
            scheduler_val = scheduler_name if scheduler_name != "None" else None
            my_list.append((sampler_val, scheduler_val))
        
        # 关键修复点 3: 根据模式决定输出的 XY 类型和数据格式
        xy_output = None
        if my_list:
            if mode == "Sampler & Scheduler":
                # 过滤掉 sampler 为 "None" 的项
                valid_items = [item for item in my_list if item[0] != "None"]
                # 输出 ("Sampler", [(s1, sc1), (s2, sc2), ...])
                xy_output = ("Sampler", valid_items) if valid_items else None
            
            elif mode == "Sampler Only":
                # 只提取 sampler，并过滤掉 "None"
                samplers = [item[0] for item in my_list if item[0] != "None"]
                if samplers:
                    # 格式化为 XY Plot 需要的格式
                    xy_value = [(s, None) for s in samplers]
                    # 输出 ("Sampler", [(s1, None), (s2, None), ...])
                    xy_output = ("Sampler", xy_value)

            elif mode == "Scheduler Only":
                # 只提取 scheduler，并过滤掉 None
                schedulers = [item[1] for item in my_list if item[1] is not None]
                if schedulers:
                    # 输出 ("Scheduler", [sc1, sc2, ...])
                    xy_output = ("Scheduler", schedulers)

        # 返回更新后的列表和格式化好的 XY 数据
        return (my_list, xy_output)

class XY_Input_Sampler_List_Builder:
    """
    逐个构建一个 Sampler 列表。
    每个节点既可以串联，也可以作为最后一个节点直接连接到 XY Plot。
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sampler_name": (["None"] + comfy.samplers.KSampler.SAMPLERS,),
            },
            "optional": {
                # --- 修复 2: 规范化输入接口的 key ---
                "previous_list": ("SAMPLER_LIST",)
            }
        }

    # --- 修复 3: 优化输出接口的显示名称 ---
    RETURN_TYPES = ("SAMPLER_LIST", "XY")
    RETURN_NAMES = ("Chained List", "X or Y")
    
    FUNCTION = "build_list"
    CATEGORY = "🪐supernova/XY Plot/Inputs"

    # --- 修复 2: 函数参数名与上面的 key 保持一致 ---
    def build_list(self, sampler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        
        if sampler_name != "None":
            my_list.append(sampler_name)
        
        xy_output = None
        if my_list:
            xy_value = [(s, None) for s in my_list]
            xy_output = ("Sampler", xy_value)

        # --- 修复 1: 添加缺失的 return 语句 ---
        return (my_list, xy_output)
    
class XY_Input_Scheduler_List_Builder:
    """
    逐个构建一个 Scheduler 列表。
    每个节点既可以串联，也可以作为最后一个节点直接连接到 XY Plot。
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler_name": (["None"] + comfy.samplers.KSampler.SCHEDULERS,),
            },
            "optional": {
                # --- 修复 2: 规范化输入接口的 key ---
                "previous_list": ("SCHEDULER_LIST",)
            }
        }

    # --- 修复 3: 优化输出接口的显示名称 ---
    RETURN_TYPES = ("SCHEDULER_LIST", "XY")
    RETURN_NAMES = ("Chained List", "X or Y")
    
    FUNCTION = "build_list"
    CATEGORY = "🪐supernova/XY Plot/Inputs"

    # --- 修复 2: 函数参数名与上面的 key 保持一致 ---
    def build_list(self, scheduler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        
        if scheduler_name != "None":
            my_list.append(scheduler_name)

        xy_output = None
        if my_list:
            xy_output = ("Scheduler", my_list)

        # --- 修复 1: 添加缺失的 return 语句 ---
        return (my_list, xy_output)
#----------------------------------------------------------------------------
# 在你的 xy_plot.py 中，添加这个全新的 Class

class XY_Input_Dynamic_List_Builder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 唯一的永久控件：一个用于控制数量的整数输入框
                # 我们给它一个特殊的名字 "input_count" 以便在 JS 中识别
                "input_count": ("INT", {"default": 3, "min": 0, "max": 50, "step": 1}),
            }
        }

    RETURN_TYPES = ("XY",)
    RETURN_NAMES = ("X or Y",)
    FUNCTION = "build_list"
    CATEGORY = "🪐supernova/XY Plot/Inputs"

    def build_list(self, input_count, **kwargs):
        """
        这个函数会接收到 'input_count' 的值，
        以及一个 kwargs 字典，包含了所有动态生成的控件值，
        例如：{'sampler_1': 'euler', 'scheduler_1': 'normal', 'sampler_2': 'dpmpp_2m', ...}
        """
        my_list = []
        
        # 根据 input_count 的值，我们循环并从 kwargs 中提取数据
        for i in range(1, input_count + 1):
            sampler_key = f"sampler_{i}"
            scheduler_key = f"scheduler_{i}"

            # 从 kwargs 中获取值，如果不存在则使用默认值
            sampler_name = kwargs.get(sampler_key, "None")
            scheduler_name = kwargs.get(scheduler_key, "None")

            if sampler_name != "None":
                scheduler_val = scheduler_name if scheduler_name != "None" else None
                my_list.append((sampler_name, scheduler_val))
        
        # 格式化为 XY Plot 需要的最终输出
        xy_output = ("Sampler", my_list) if my_list else None
        
        return (xy_output,)
#----------------------------------------------------------------
# ======================================================================================================================
# 节点映射
# ======================================================================================================================
NODE_CLASS_MAPPINGS = {
    "XY Plot KSampler": StandaloneXYPlot,
    "XY Plot Settings": XYPlotSettings,
    "XY Input: Seeds": TSC_XYplot_SeedsBatch, 
    "XY Input: Steps": TSC_XYplot_Steps,
    "XY Input: CFG": TSC_XYplot_CFG, 
    "XY Input: Sampler/Scheduler": TSC_XYplot_Sampler_Scheduler,
    "XY Input: Denoise": TSC_XYplot_Denoise, 
    "XY Input: LoRA Batch": TSC_XYplot_LoRA_Batch,
    "XY Input: LoRA Plot": TSC_XYplot_LoRA_Plot,
    "XY_Input_Sampler_List_Builder": XY_Input_Sampler_List_Builder,
    "XY_Input_Scheduler_List_Builder": XY_Input_Scheduler_List_Builder,
    "XY_Input_Sampler_Scheduler_Builder": XY_Input_Sampler_Scheduler_Builder,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "XY Plot KSampler": "XY Plot with KSampler",
    "XY Plot Settings": "XY Plot Settings 📐",
    "XY Input: Seeds": "XY Input: Seeds ⚙️",
    "XY Input: Steps": "XY Input: Steps ⚙️",
    "XY Input: CFG": "XY Input: CFG ⚙️",
    "XY Input: Sampler/Scheduler": "XY Input: Sampler/Scheduler ⚙️",
    "XY Input: Denoise": "XY Input: Denoise ⚙️",
    "XY Input: LoRA Batch": "XY Input: LoRA Batch (from Path) ⚙️",
    "XY Input: LoRA Plot": "XY Input: LoRA Plot ⚙️",
    "XY_Input_Sampler_List_Builder": "XY Input: Add Sampler ⚙️",
    "XY_Input_Scheduler_List_Builder": "XY Input: Add Scheduler ⚙️",
    "XY_Input_Sampler_Scheduler_Builder": "XY Input: Add Sampler/Scheduler ⚙️",
}