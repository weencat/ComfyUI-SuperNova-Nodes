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

def wrap_text_by_pixels(text: str, font, max_width: int) -> str:
    """基于像素宽度的智能换行函数，兼容多语言"""
    if not text:
        return ""
    dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    lines = []
    for paragraph in text.split('\n'):
        current_line = ""
        for char in paragraph:
            test_line = current_line + char
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
    return "\n".join(lines)

# ======================================================================================================================
# 核心 XY Plot 节点 
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
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("IMAGE", "IMAGE"), ("XY Plot Image", "Batched Images"), "plot", "🪐 Superova/XY Plot"

    def plot(self, model, clip, vae, positive_text, negative_text, latent_image, seed, steps, cfg, sampler_name, scheduler, denoise, X=None, Y=None, XY_PLOT_SETTINGS=None):
        # 1. 获取设置
        if XY_PLOT_SETTINGS:
            grid_spacing = XY_PLOT_SETTINGS.get("grid_spacing", 10)
            xy_flip = XY_PLOT_SETTINGS.get("xy_flip", "False")
            y_label_orientation = XY_PLOT_SETTINGS.get("y_label_orientation", "Horizontal")
            settings_font_size = XY_PLOT_SETTINGS.get("font_size", 0)
            settings_font_path = XY_PLOT_SETTINGS.get("font_path", "")
            text_wrap = XY_PLOT_SETTINGS.get("text_wrap", True)
        else:
            grid_spacing, xy_flip, y_label_orientation = 10, "False", "Horizontal"
            settings_font_size, settings_font_path, text_wrap = 0, "", True
        
        X_type, X_value = X if X else ("Nothing", [""])
        Y_type, Y_value = Y if Y else ("Nothing", [""])
        
        if xy_flip == "True":
            X_type, Y_type = Y_type, X_type
            X_value, Y_value = Y_value, X_value

        if X_type == Y_type and X_type != "Nothing":
            print("XY Plot 错误：X 和 Y 输入类型必须不同。")
            return (None, None)

        image_pil_list, image_tensor_list = [], []
        
        # 2. 生成循环
        for y_idx, y_val in enumerate(Y_value):
            for x_idx, x_val in enumerate(X_value):
                current_seed, current_steps, current_cfg = seed, steps, cfg
                current_sampler, current_scheduler, current_denoise = sampler_name, scheduler, denoise
                current_model, current_clip = model.clone(), clip.clone()
                current_vae = vae
                pos_prompt, neg_prompt = positive_text, negative_text
                
                lora_stack = []
                lora_types = ["LoRA Batch", "LoRA Wt", "LoRA MStr", "LoRA CStr"]
                
                temp_params = [(X_type, x_val), (Y_type, y_val)]
                
                is_mstr_cstr_plot = (X_type == "LoRA MStr" and Y_type == "LoRA CStr") or (X_type == "LoRA CStr" and Y_type == "LoRA MStr")
                if is_mstr_cstr_plot:
                    try:
                        lora_path = x_val[0][0] 
                        m_str = x_val[0][1] if X_type == "LoRA MStr" else y_val[0][1]
                        c_str = y_val[0][2] if Y_type == "LoRA CStr" else x_val[0][2]
                        lora_stack = [(lora_path, m_str, c_str)]
                    except: pass 
                elif X_type == "LoRA Batch" and Y_type in lora_types:
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
                    for param_type, param_val in temp_params:
                        if not param_val and param_val != 0: continue
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
                        elif param_type == "PromptSR":
                            search_txt, replace_txt = param_val
                            pos_prompt = pos_prompt.replace(search_txt, replace_txt)
                            neg_prompt = neg_prompt.replace(search_txt, replace_txt)
                        elif param_type == "Checkpoint":
                            ckpt_name = param_val
                            ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                            try:
                                out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))
                                current_model, current_clip, current_vae = out[:3]
                            except Exception as e: print(f"加载 Checkpoint '{ckpt_name}' 失败: {e}")
                        elif param_type == "VAE":
                            vae_name = param_val
                            vae_path = folder_paths.get_full_path("vae", vae_name)
                            try:
                                current_vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(vae_path))
                            except Exception as e: print(f"加载 VAE '{vae_name}' 失败: {e}")
                        elif param_type == "UNet":
                            unet_name = param_val
                            unet_path = folder_paths.get_full_path("diffusion_models", unet_name) or folder_paths.get_full_path("unet", unet_name)
                            if unet_path and os.path.exists(unet_path):
                                try:
                                    current_model = comfy.sd.load_diffusion_model(unet_path)
                                except Exception as e: print(f"加载 UNet '{unet_name}' 失败: {e}")
                            else:
                                print(f"未找到 UNet 文件: {unet_name}")
                        elif param_type == "CLIP":
                            clip_name = param_val
                            clip_path = folder_paths.get_full_path("clip", clip_name) or folder_paths.get_full_path("text_encoders", clip_name)
                            if clip_path and os.path.exists(clip_path):
                                try:
                                    current_clip = comfy.sd.load_clip(ckpt_paths=[clip_path], embedding_directory=folder_paths.get_folder_paths("embeddings"))
                                except Exception as e: print(f"加载 CLIP '{clip_name}' 失败: {e}")
                            else:
                                print(f"未找到 CLIP 文件: {clip_name}")
                
                # LoRA 加载执行：自动跳过空路径或 None
                if lora_stack:
                    for lora_path, model_str, clip_str in lora_stack:
                        if lora_path is None or str(lora_path).strip().lower() in ['none', '']: 
                            continue
                        if os.path.exists(lora_path) and os.path.isfile(lora_path):
                            try:
                                lora_data = comfy.utils.load_torch_file(lora_path)
                                lora_model, lora_clip = comfy.sd.load_lora_for_models(current_model, current_clip, lora_data, model_str, clip_str)
                                current_model, current_clip = lora_model, lora_clip
                            except Exception as e: 
                                print(f"加载 LoRA '{os.path.basename(lora_path)}' 失败: {e}")
                
                positive_cond, negative_cond = CLIPTextEncode().encode(current_clip, pos_prompt)[0], CLIPTextEncode().encode(current_clip, neg_prompt)[0]
                print(f"正在生成: X={x_idx}, Y={y_idx} | Seed={current_seed}")
                
                try:
                    latent_out = KSampler().sample(current_model, current_seed, current_steps, current_cfg, current_sampler, current_scheduler, positive_cond, negative_cond, latent_image, denoise=current_denoise)[0]
                    image = VAEDecode().decode(current_vae, latent_out)[0]
                    image_tensor_list.append(image)
                    image_pil_list.append(tensor2pil(image))
                except Exception as e:
                    print(f"生成失败 X={x_idx}, Y={y_idx}: {e}")
                    image_pil_list.append(Image.new('RGB', (512, 512), (0, 0, 0)))
                    image_tensor_list.append(torch.zeros((1, 512, 512, 3)))
                
        if not image_pil_list: return (None, None)

        # 3. 绘图逻辑
        num_cols, num_rows = len(X_value), len(Y_value)
        i_width, i_height = image_pil_list[0].size
        
        def format_label(val, type):
            try:
                if isinstance(val, (list, tuple)):
                    if len(val) > 0:
                        if type == "LoRA Batch":
                            try:
                                lora_path = val[0][0]
                                # 优化：空路径或 None 显式输出 "No LoRA"
                                if not lora_path or str(lora_path).strip().lower() in ["none", ""]: 
                                    return "No LoRA"
                                name = os.path.splitext(os.path.basename(str(lora_path)))[0]
                                return name if text_wrap else (name[:20] + "..." if len(name) > 23 else name)
                            except: 
                                return "LoRA"
                        if type in ["Prompt S/R", "PromptSR"] and len(val) > 1: return f"Prompt: {val[1]}"
                        value_str = str(val[0])
                    else: value_str = ""
                else:
                    value_str = str(val)

                if type == "Steps": return f"Steps: {value_str}"
                if type == "CFG Scale": return f"CFG: {value_str}"
                if type == "Denoise": return f"Denoise: {value_str}"
                if type == "Seeds++ Batch": return f"Seed: {value_str}"
                if type == "Sampler": return f"Sampler: {value_str}"
                if type == "Scheduler": return f"Sched: {value_str}"
                
                if type == "LoRA Wt": 
                    try: return f"Wt: {float(value_str):.2f}"
                    except: return f"Wt: {value_str}"

                if type in ["Checkpoint", "VAE", "UNet", "CLIP"]:
                    name = os.path.splitext(os.path.basename(value_str))[0]
                    return name if text_wrap else (name[:20] + "..." if len(name) > 23 else name)

                if type in ["Prompt S/R", "PromptSR"]: return f"Prompt: {value_str}"
                return value_str
            except Exception as e:
                print(f"Label Error: {e}")
                return str(val)

        X_label = [format_label(v, X_type) for v in X_value]
        Y_label = [format_label(v, Y_type) for v in Y_value]

        # --- 字体初始化 ---
        if settings_font_size > 0:
            final_font_size = settings_font_size
        else:
            final_font_size = max(12, int(min(i_width, i_height) * 0.04))
            
        chosen_font_path = font_path
        if settings_font_path and str(settings_font_path).strip():
            chosen_font_path = settings_font_path
            
        try:
            if chosen_font_path: font = ImageFont.truetype(chosen_font_path, final_font_size)
            else: font = ImageFont.load_default()
        except Exception as e:
            print(f"XYPlot: 加载字体失败 '{chosen_font_path}', 尝试回退。错误: {e}")
            try:
                if font_path and chosen_font_path != font_path: font = ImageFont.truetype(font_path, final_font_size)
                else: font = ImageFont.load_default()
            except: font = ImageFont.load_default()

        # --- 文本换行处理与边界计算 ---
        dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

        if text_wrap:
            X_label = [wrap_text_by_pixels(l, font, i_width - 20) for l in X_label]
            y_max_width = i_height - 20 if y_label_orientation == "Vertical" else max(300, i_width // 2)
            Y_label = [wrap_text_by_pixels(l, font, y_max_width) for l in Y_label]

        max_x_label_height = 0
        if X_type != "Nothing":
            for l in X_label:
                bbox = dummy_draw.multiline_textbbox((0, 0), l, font=font)
                max_x_label_height = max(max_x_label_height, bbox[3] - bbox[1])
                
        max_y_label_width = 0
        if Y_type != "Nothing":
            for l in Y_label:
                bbox = dummy_draw.multiline_textbbox((0, 0), l, font=font)
                if y_label_orientation == "Vertical":
                    max_y_label_width = max(max_y_label_width, bbox[3] - bbox[1])
                else:
                    max_y_label_width = max(max_y_label_width, bbox[2] - bbox[0])

        padding = 30
        x_offset_initial = (max_y_label_width + padding) if Y_type != "Nothing" else 0
        y_offset_initial = (max_x_label_height + padding) if X_type != "Nothing" else 0
        
        x_offset_initial = max(x_offset_initial, i_width // 15 * 4 if Y_type != "Nothing" else 0)
        y_offset_initial = max(y_offset_initial, i_height // 15 * 3 if X_type != "Nothing" else 0)

        bg_width = (num_cols * i_width) + ((num_cols - 1) * grid_spacing) + x_offset_initial
        bg_height = (num_rows * i_height) + ((num_rows - 1) * grid_spacing) + y_offset_initial
        background = Image.new('RGB', (bg_width, bg_height), color=(255, 255, 255))
        
        y_offset = y_offset_initial
        for row in range(num_rows):
            x_offset = x_offset_initial
            for col in range(num_cols):
                idx = row * num_cols + col
                if idx < len(image_pil_list):
                    background.paste(image_pil_list[idx], (x_offset, y_offset))
                if row == 0 and X_type != "Nothing":
                    draw = ImageDraw.Draw(background)
                    draw.multiline_text((x_offset + i_width / 2, y_offset_initial / 2), X_label[col], font=font, fill="black", anchor="mm", align="center")
                x_offset += i_width + grid_spacing
            
            if Y_type != "Nothing":
                if y_label_orientation == "Vertical":
                    bbox = dummy_draw.multiline_textbbox((0,0), Y_label[row], font=font)
                    t_w, t_h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                    txt_img = Image.new('L', (t_w + 20, t_h + 20)) 
                    d = ImageDraw.Draw(txt_img)
                    d.multiline_text(((t_w+20)/2, (t_h+20)/2), Y_label[row], font=font, fill=255, anchor="mm", align="center")
                    w = txt_img.rotate(90, expand=1)
                    background.paste(ImageOps.colorize(w, (0,0,0), (0,0,0)), (int(x_offset_initial/2 - w.size[0]/2) , y_offset + int(i_height/2 - w.size[1]/2)),  w)
                else:
                    draw = ImageDraw.Draw(background)
                    draw.multiline_text((x_offset_initial / 2, y_offset + i_height / 2), Y_label[row], font=font, fill="black", anchor="mm", align="center")
            y_offset += i_height + grid_spacing
        
        return (pil2tensor(background), torch.cat(image_tensor_list, dim=0))

# =================================================================================
# LoRA 路径串联节点 (新增)
# =================================================================================

class XY_Input_LoRA_Path_Chain:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_path": ("STRING", {
                    "default": "", 
                    "multiline": False, 
                    "placeholder": "LoRA 完整路径（留空则不加载并标记为 No LoRA）"
                }),
                "model_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            },
            "optional": {
                "lora_chain_list": ("LORA_CHAIN_LIST",)
            }
        }
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("LORA_CHAIN_LIST", "XY"), ("LoRA Chain List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/LoRA Inputs"

    def build_chain(self, lora_path, model_strength, clip_strength, lora_chain_list=None):
        my_list = lora_chain_list[:] if lora_chain_list is not None else []
        clean_path = lora_path.strip() if lora_path else ""
        # 以 [ (path, model_strength, clip_strength) ] 结构存储
        my_list.append([(clean_path, model_strength, clip_strength)])
        return (my_list, ("LoRA Batch", my_list))

# =================================================================================
# UNet & CLIP 输入节点 (Chain & Batch)
# =================================================================================

def get_unet_list():
    unets1 = folder_paths.get_filename_list("diffusion_models") or []
    unets2 = folder_paths.get_filename_list("unet") or []
    models = set(unets1 + unets2)
    return ["None"] + sorted(list(models))

def get_clip_list():
    clips1 = folder_paths.get_filename_list("clip") or []
    clips2 = folder_paths.get_filename_list("text_encoders") or []
    clips = set(clips1 + clips2)
    return ["None"] + sorted(list(clips))

class XY_Input_UNet_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"unet_name": (get_unet_list(),)}, "optional": {"unet_list": ("UNET_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("UNET_LIST", "XY"), ("UNet List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/Model Inputs"
    def build_chain(self, unet_name, unet_list=None):
        my_list = unet_list[:] if unet_list is not None else []
        if unet_name != "None": my_list.append(unet_name)
        return (my_list, ("UNet", my_list))

class XY_Input_UNet_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        unets = get_unet_list()
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"][f"unet_name_{i}"] = (unets,)
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/Model Inputs"
    def xy_value(self, input_count, **kwargs):
        unets = [kwargs.get(f"unet_name_{i}") for i in range(1, input_count + 1) if kwargs.get(f"unet_name_{i}", "None") != "None"]
        return (("UNet", unets),) if unets else (None,)

class XY_Input_CLIP_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"clip_name": (get_clip_list(),)}, "optional": {"clip_list": ("CLIP_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("CLIP_LIST", "XY"), ("CLIP List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/Model Inputs"
    def build_chain(self, clip_name, clip_list=None):
        my_list = clip_list[:] if clip_list is not None else []
        if clip_name != "None": my_list.append(clip_name)
        return (my_list, ("CLIP", my_list))

class XY_Input_CLIP_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        clips = get_clip_list()
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"][f"clip_name_{i}"] = (clips,)
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/Model Inputs"
    def xy_value(self, input_count, **kwargs):
        clips = [kwargs.get(f"clip_name_{i}") for i in range(1, input_count + 1) if kwargs.get(f"clip_name_{i}", "None") != "None"]
        return (("CLIP", clips),) if clips else (None,)

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
                "font_size": ("INT", {"default": 50, "min": 0, "max": 500, "step": 1, "label": "font_size (0=Auto)"}),
                "font_path": ("STRING", {"default": "", "multiline": False, "placeholder": "e.g. C:/Windows/Fonts/arial.ttf"}),
                "text_wrap": ("BOOLEAN", {"default": True, "tooltip": "开启后，X/Y轴的长文本会自动换行显示，而不是截断或溢出"}),
            }
        }
    RETURN_TYPES = ("XY_PLOT_SETTINGS",)
    FUNCTION = "get_settings"
    CATEGORY = "🪐 Superova/XY Plot"

    def get_settings(self, grid_spacing, xy_flip, y_label_orientation, font_size, font_path, text_wrap):
        settings_dict = {
            "grid_spacing": grid_spacing,
            "xy_flip": xy_flip,
            "y_label_orientation": y_label_orientation,
            "font_size": font_size,
            "font_path": font_path,
            "text_wrap": text_wrap,
        }
        return (settings_dict,)

# ======================================================================================================================
# XY 输入节点
# ======================================================================================================================

class TSC_XYplot_LoRA_Plot:
    MODES = [
        "X: LoRA Batch, Y: LoRA Weight",
        "X: LoRA Batch, Y: Model Strength",
        "X: LoRA Batch, Y: Clip Strength",
        "X: Model Strength, Y: Clip Strength"
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_mode": (cls.MODES,),
                "lora_name": (["None"] + folder_paths.get_filename_list("loras"),),
                "model_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "X_batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}),
                "include_no_lora": ("BOOLEAN", {
                    "default": False, 
                    "tooltip": "开启后，将在批处理列表的首位自动加入一组无 LoRA（No LoRA）项作为底模基准对照。"
                }),
                "X_batch_path": ("STRING", {"default": xy_batch_default_path, "placeholder": "扫描 LoRA 的文件夹路径"}),
                "X_subdirectories": ("BOOLEAN", {"default": False}),
                "X_batch_sort": (["ascending", "descending"],),
                "X_first_value": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "X_last_value": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "Y_batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}),
                "Y_first_value": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "Y_last_value": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("XY", "XY")
    RETURN_NAMES = ("X", "Y")
    FUNCTION = "xy_value"
    CATEGORY = "🪐 Superova/XY Plot/LoRA Inputs"

    def __init__(self):
        self.lora_batch = TSC_XYplot_LoRA_Batch()

    def xy_value(self, input_mode, lora_name, model_strength, clip_strength, include_no_lora,
                 X_batch_count, X_batch_path, X_subdirectories, X_batch_sort, X_first_value, X_last_value,
                 Y_batch_count, Y_first_value, Y_last_value):
        x_tuple, y_tuple = None, None
        lora_identifier = folder_paths.get_full_path("loras", lora_name) if lora_name != 'None' else 'None'
        is_mstr_cstr_plot = "Model Strength" in input_mode and "Clip Strength" in input_mode

        # 校验：单 LoRA 强度遍历模式下必须选择有效 LoRA
        if is_mstr_cstr_plot and lora_identifier == 'None':
            print("XY Plot 提示: 当前为 'MStr / CStr' 模式，请在下拉菜单中选择指定的 LoRA。")
            return (None, None)

        # -----------------------------------------------------------------------------------------
        # 处理 X 轴
        # -----------------------------------------------------------------------------------------
        if X_batch_count > 0:
            if "X: LoRA Batch" in input_mode:
                x_result = self.lora_batch.xy_value(
                    X_batch_path, X_subdirectories, X_batch_sort,
                    model_strength, clip_strength, X_batch_count
                )
                
                # 提取已加载的 LoRA 列表
                current_loras = x_result[0][1] if (x_result and x_result[0]) else []

                # 如果启用了 No LoRA 对照组，在首位插入空路径占位
                if include_no_lora:
                    no_lora_item = [("", model_strength, clip_strength)]
                    current_loras = [no_lora_item] + current_loras

                if current_loras:
                    x_tuple = ("LoRA Batch", current_loras)

            elif "X: Model Strength" in input_mode:
                x_floats = generate_floats(X_batch_count, X_first_value, X_last_value)
                if is_mstr_cstr_plot:
                    x_value = [[(lora_identifier, x, clip_strength)] for x in x_floats]
                else:
                    x_value = x_floats
                x_tuple = ("LoRA MStr", x_value)

        # -----------------------------------------------------------------------------------------
        # 处理 Y 轴
        # -----------------------------------------------------------------------------------------
        if Y_batch_count > 0:
            y_floats = generate_floats(Y_batch_count, Y_first_value, Y_last_value)
            
            if "Y: LoRA Weight" in input_mode:
                y_tuple = ("LoRA Wt", y_floats)
            elif "Y: Model Strength" in input_mode:
                y_tuple = ("LoRA MStr", y_floats)
            elif "Y: Clip Strength" in input_mode:
                if is_mstr_cstr_plot:
                    y_value = [[(lora_identifier, model_strength, y)] for y in y_floats]
                else:
                    y_value = y_floats
                y_tuple = ("LoRA CStr", y_value)

        return (x_tuple, y_tuple)
    
class TSC_XYplot_SeedsBatch:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"seed_offset": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),}, "optional": {"seed_list": ("SEED_CHAIN",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("SEED_CHAIN", "XY"), ("SEED List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_chain(self, seed_offset, seed_list=None):
        my_list = seed_list[:] if seed_list is not None else []
        my_list.append(seed_offset)
        return (my_list, ("Seeds++ Batch", my_list))

class TSC_XYplot_Steps:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "first_step": ("INT", {"default": 10, "min": 1, "max": 10000}), "last_step": ("INT", {"default": 20, "min": 1, "max": 10000}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/KSampler Inputs"
    def xy_value(self, batch_count, first_step, last_step): return (("Steps", generate_ints(batch_count, first_step, last_step)),)

class TSC_XYplot_CFG:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"batch_count": ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM}), "first_cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 100.0}), "last_cfg": ("FLOAT", {"default": 9.0, "min": 0.0, "max": 100.0}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/KSampler Inputs"
    def xy_value(self, batch_count, first_cfg, last_cfg): return (("CFG Scale", generate_floats(batch_count, first_cfg, last_cfg)),)

class TSC_XYplot_Sampler_Scheduler:
    parameters = ["sampler", "scheduler", "sampler & scheduler"]
    @classmethod
    def INPUT_TYPES(cls):
        samplers, schedulers = ["None"] + comfy.samplers.KSampler.SAMPLERS, ["None"] + comfy.samplers.KSampler.SCHEDULERS
        inputs = {"required": {"target_parameter": (cls.parameters,), }}
        for i in range(1, XYPLOT_LIM + 1):
            inputs["required"][f"sampler_{i}"] = (samplers,)
            inputs["required"][f"scheduler_{i}"] = (schedulers,)
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/KSampler Inputs"
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
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/KSampler Inputs"
    def xy_value(self, batch_count, first_denoise, last_denoise): return (("Denoise", generate_floats(batch_count, first_denoise, last_denoise)),)

class TSC_XYplot_LoRA_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
                "batch_path": ("STRING", {"default": xy_batch_default_path}), "subdirectories": ("BOOLEAN", {"default": False}),
                "batch_sort": (["ascending", "descending"],), "batch_max": ("INT",{"default": -1, "min": -1, "max": XYPLOT_LIM}),
                "model_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01})}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/LoRA Inputs"
    def xy_value(self, batch_path, subdirectories, batch_sort, model_strength, clip_strength, batch_max):
        if batch_max == 0: return (None,)
        loras = get_batch_files(batch_path, LORA_EXTENSIONS, include_subdirs=subdirectories)
        if not loras: return (None,)
        loras.sort(reverse=(batch_sort == "descending"))
        xy_value = [[(lora_path, model_strength, clip_strength)] for lora_path in loras]
        if batch_max != -1: xy_value = xy_value[:batch_max]
        return (("LoRA Batch", xy_value),) if xy_value else (None,)

class XY_Input_Sampler_Scheduler_Builder:
    MODES = ["Sampler & Scheduler", "Sampler Only", "Scheduler Only"]
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"mode": (cls.MODES,), "sampler_name": (["None"] + comfy.samplers.KSampler.SAMPLERS,), "scheduler_name": (["None"] + comfy.samplers.KSampler.SCHEDULERS,),}, "optional": {"previous_list": ("SAMPLER_SCHEDULER_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("SAMPLER_SCHEDULER_LIST", "XY"), ("Chained List", "X or Y"), "build_list", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_list(self, mode, sampler_name, scheduler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        if sampler_name != "None" or scheduler_name != "None":
            my_list.append((sampler_name if sampler_name != "None" else "None", scheduler_name if scheduler_name != "None" else None))
        xy_output = None
        if my_list:
            if mode == "Sampler & Scheduler":
                valid = [item for item in my_list if item[0] != "None"]
                xy_output = ("Sampler", valid) if valid else None
            elif mode == "Sampler Only":
                samplers = [item[0] for item in my_list if item[0] != "None"]
                if samplers: xy_output = ("Sampler", [(s, None) for s in samplers])
            elif mode == "Scheduler Only":
                schedulers = [item[1] for item in my_list if item[1] is not None]
                if schedulers: xy_output = ("Scheduler", schedulers)
        return (my_list, xy_output)

class XY_Input_Sampler_List_Builder:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"sampler_name": (["None"] + comfy.samplers.KSampler.SAMPLERS,),}, "optional": {"previous_list": ("SAMPLER_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("SAMPLER_LIST", "XY"), ("Chained List", "X or Y"), "build_list", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_list(self, sampler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        if sampler_name != "None": my_list.append(sampler_name)
        return (my_list, ("Sampler", [(s, None) for s in my_list]) if my_list else None)
    
class XY_Input_Scheduler_List_Builder:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"scheduler_name": (["None"] + comfy.samplers.KSampler.SCHEDULERS,),}, "optional": {"previous_list": ("SCHEDULER_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("SCHEDULER_LIST", "XY"), ("Chained List", "X or Y"), "build_list", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_list(self, scheduler_name, previous_list=None):
        my_list = previous_list[:] if previous_list is not None else []
        if scheduler_name != "None": my_list.append(scheduler_name)
        return (my_list, ("Scheduler", my_list) if my_list else None)

class XY_Input_Dynamic_List_Builder:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"input_count": ("INT", {"default": 3, "min": 0, "max": 50, "step": 1}),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "build_list", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_list(self, input_count, **kwargs):
        my_list = []
        for i in range(1, input_count + 1):
            s_name = kwargs.get(f"sampler_{i}", "None")
            sc_name = kwargs.get(f"scheduler_{i}", "None")
            if s_name != "None": my_list.append((s_name, sc_name if sc_name != "None" else None))
        return (("Sampler", my_list) if my_list else None,)

class XY_Input_PromptSR_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"search_txt": ("STRING", {"default": "", "multiline": False}), "replace_txt": ("STRING", {"default": "", "multiline": False}),}, "optional": {"prompt_s_r_list": ("PROMPT_SR_LIST",),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("PROMPT_SR_LIST", "XY"), ("PromptSR List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/Prompt Inputs"
    def build_chain(self, search_txt, replace_txt, prompt_s_r_list=None):
        my_list = prompt_s_r_list[:] if prompt_s_r_list is not None else []
        my_list.append((search_txt, replace_txt))
        return (my_list, ("PromptSR", my_list))

class XY_Input_Checkpoint_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"ckpt_name": (["None"] + folder_paths.get_filename_list("checkpoints"),),}, "optional": {"ckpt_list": ("CHECKPOINT_LIST",),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("CHECKPOINT_LIST", "XY"), ("ckpt List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/Model Inputs"
    def build_chain(self, ckpt_name, ckpt_list=None):
        my_list = ckpt_list[:] if ckpt_list is not None else []
        if ckpt_name != "None": my_list.append(ckpt_name)
        return (my_list, ("Checkpoint", my_list))

class XY_Input_VAE_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"vae_name": (["None"] + folder_paths.get_filename_list("vae"),),}, "optional": {"vae_s_list": ("VAE_LIST",),}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("VAE_LIST", "XY"), ("VAE List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/Model Inputs"
    def build_chain(self, vae_name, vae_s_list=None):
        my_list = vae_s_list[:] if vae_s_list is not None else []
        if vae_name != "None": my_list.append(vae_name)
        return (my_list, ("VAE", my_list))

class XY_Input_Denoise_Chain:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"denoise_value": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),}, "optional": {"denoise_s_list": ("DENOISE_LIST",)}}
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("DENOISE_LIST", "XY"), ("Denoise List", "X or Y"), "build_chain", "🪐 Superova/XY Plot/KSampler Inputs"
    def build_chain(self, denoise_value, denoise_s_list=None):
        my_list = denoise_s_list[:] if denoise_s_list is not None else []
        my_list.append(denoise_value)
        return (my_list, ("Denoise", my_list))

class XY_Input_Seeds_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"][f"seed_{i}"] = ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff})
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/KSampler Inputs"
    def xy_value(self, input_count, **kwargs):
        seeds = [kwargs.get(f"seed_{i}", 0) for i in range(1, input_count + 1)]
        return (("Seeds++ Batch", seeds),) if seeds else (None,)

class XY_Input_Checkpoint_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        ckpts = ["None"] + folder_paths.get_filename_list("checkpoints")
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"][f"ckpt_name_{i}"] = (ckpts,)
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/Model Inputs"
    def xy_value(self, input_count, **kwargs):
        ckpts = [kwargs.get(f"ckpt_name_{i}") for i in range(1, input_count + 1) if kwargs.get(f"ckpt_name_{i}", "None") != "None"]
        return (("Checkpoint", ckpts),) if ckpts else (None,)

class XY_Input_VAE_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        vaes = ["None"] + folder_paths.get_filename_list("vae")
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1): inputs["required"][f"vae_name_{i}"] = (vaes,)
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/Model Inputs"
    def xy_value(self, input_count, **kwargs):
        vaes = [kwargs.get(f"vae_name_{i}") for i in range(1, input_count + 1) if kwargs.get(f"vae_name_{i}", "None") != "None"]
        return (("VAE", vaes),) if vaes else (None,)

class XY_Input_PromptSR_Batch:
    @classmethod
    def INPUT_TYPES(cls):
        inputs = {"required": {}}
        for i in range(1, XYPLOT_LIM + 1):
            inputs["required"][f"search_txt_{i}"] = ("STRING", {"default": "", "multiline": False})
            inputs["required"][f"replace_txt_{i}"] = ("STRING", {"default": "", "multiline": False})
        inputs["required"]["input_count"] = ("INT", {"default": XYPLOT_DEF, "min": 0, "max": XYPLOT_LIM})
        return inputs
    RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("XY",), ("X or Y",), "xy_value", "🪐 Superova/XY Plot/Prompt Inputs"
    def xy_value(self, input_count, **kwargs):
        prompt_sr = [(kwargs.get(f"search_txt_{i}", ""), kwargs.get(f"replace_txt_{i}", "")) for i in range(1, input_count + 1) if kwargs.get(f"search_txt_{i}", "") != ""]
        return (("PromptSR", prompt_sr),) if prompt_sr else (None,)

# ======================================================================================================================
# 节点映射
# ======================================================================================================================
NODE_CLASS_MAPPINGS = {
    "XY_Plot_KSampler": StandaloneXYPlot,
    "XY_Plot_Settings": XYPlotSettings,
    "XY_Input_Seeds": TSC_XYplot_SeedsBatch, 
    "XY_Input_Steps": TSC_XYplot_Steps,
    "XY_Input_CFG": TSC_XYplot_CFG, 
    "XY_Input_Sampler_Scheduler_Batch": TSC_XYplot_Sampler_Scheduler,
    "XY_Input_Denoise": TSC_XYplot_Denoise, 
    "XY_Input_LoRA_Batch": TSC_XYplot_LoRA_Batch,
    "XY_Input_LoRA_Plot": TSC_XYplot_LoRA_Plot,
    "XY_Input_LoRA_Path_Chain": XY_Input_LoRA_Path_Chain, 
    "XY_Input_Sampler_List_Builder": XY_Input_Sampler_List_Builder,
    "XY_Input_Scheduler_List_Builder": XY_Input_Scheduler_List_Builder,
    "XY_Input_Sampler_Scheduler_Builder": XY_Input_Sampler_Scheduler_Builder,
    "XY_Input_PromptSR_Chain": XY_Input_PromptSR_Chain,
    "XY_Input_Checkpoint_Chain": XY_Input_Checkpoint_Chain,
    "XY_Input_VAE_Chain": XY_Input_VAE_Chain,
    "XY_Input_Denoise_Chain": XY_Input_Denoise_Chain,
    "XY_Input_Seeds_Batch": XY_Input_Seeds_Batch,
    "XY_Input_Checkpoint_Batch": XY_Input_Checkpoint_Batch,
    "XY_Input_VAE_Batch": XY_Input_VAE_Batch,
    "XY_Input_PromptSR_Batch": XY_Input_PromptSR_Batch,
    "XY_Input_UNet_Chain": XY_Input_UNet_Chain,
    "XY_Input_UNet_Batch": XY_Input_UNet_Batch,
    "XY_Input_CLIP_Chain": XY_Input_CLIP_Chain,
    "XY_Input_CLIP_Batch": XY_Input_CLIP_Batch,
    "XY_Input_Dynamic_List_Builder": XY_Input_Dynamic_List_Builder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XY_Plot_KSampler": "XY Plot with KSampler",
    "XY_Plot_Settings": "XY Plot Settings 📐",
    "XY_Input_Steps": "XY Input: Steps ⚙️",
    "XY_Input_CFG": "XY Input: CFG ⚙️",
    "XY_Input_Denoise": "XY Input: Denoise ⚙️",
    "XY_Input_LoRA_Batch": "XY Input: LoRA Batch (from Path) ⚙️",
    "XY_Input_LoRA_Plot": "XY Input: LoRA Plot ⚙️",
    "XY_Input_LoRA_Path_Chain": "XY Input: LoRA (Path) Chain🔗⚙️", 
    "XY_Input_Sampler_Scheduler_Batch": "XY Input: Sampler/Scheduler Batch🗒️⚙️",
    "XY_Input_Seeds_Batch": "XY Input: Seeds Batch🗒️⚙️",
    "XY_Input_Checkpoint_Batch": "XY Input: Checkpoint Batch🗒️⚙️",
    "XY_Input_VAE_Batch": "XY Input: VAE Batch🗒️⚙️",
    "XY_Input_PromptSR_Batch": "XY Input: Prompt S/R Batch🗒️⚙️",
    "XY_Input_Seeds": "XY Input: Seeds Chain🔗⚙️",
    "XY_Input_Scheduler_List_Builder": "XY Input: Add Scheduler Chain🔗⚙️",
    "XY_Input_Sampler_Scheduler_Builder": "XY Input: Add Sampler/Scheduler Chain🔗⚙️",
    "XY_Input_Sampler_List_Builder": "XY Input: Add Sampler Chain🔗⚙️",
    "XY_Input_PromptSR_Chain": "XY Input: Prompt S/R Chain🔗⚙️",
    "XY_Input_Checkpoint_Chain": "XY Input: Checkpoint Chain🔗⚙️",
    "XY_Input_VAE_Chain": "XY Input: VAE Chain🔗⚙️",
    "XY_Input_Denoise_Chain": "XY Input: Denoise Chain🔗⚙️",
    "XY_Input_UNet_Chain": "XY Input: UNet Chain🔗⚙️",
    "XY_Input_UNet_Batch": "XY Input: UNet Batch🗒️⚙️",
    "XY_Input_CLIP_Chain": "XY Input: CLIP Chain🔗⚙️",
    "XY_Input_CLIP_Batch": "XY Input: CLIP Batch🗒️⚙️",
    "XY_Input_Dynamic_List_Builder": "XY Input: Dynamic Sampler/Scheduler List Builder ⚙️",
}