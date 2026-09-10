# Lora Loader with Path (Stackable) Node
# Author: [Your Name/Alias]
# Version: 1.0

import os
import comfy.sd
import comfy.utils

# ======================================================================================================================
# LoRA 堆叠节点 (通过路径加载)
# ======================================================================================================================
class LoraLoaderWithPathStack:
    """
    一个可堆叠的 LoRA 加载器节点，它通过指定文件的绝对路径来加载 LoRA。
    可以像链条一样将多个此节点串联起来，按顺序应用多个 LoRA。
    这个版本能够智能处理带引号或不带引号的文件路径。
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_path": ("STRING", {"default": "C:\\path\\to\\your\\lora.safetensors"}),
                "strength_model": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_clip": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            }
        }
    
    RETURN_TYPES = ("MODEL", "CLIP")
    FUNCTION = "load_lora_stack"
    CATEGORY = "🪐 Superova/LoRALoader"

    def load_lora_stack(self, model, clip, lora_path, strength_model, strength_clip):
        
        # --- 新增：智能处理路径字符串 ---
        # 移除路径字符串开头和结尾可能存在的空格、单引号和双引号
        clean_lora_path = lora_path.strip().strip("'\"")
        # --------------------------------

        # 使用清洗后的路径进行后续所有检查和操作
        if not clean_lora_path or not os.path.isfile(clean_lora_path):
            print(f"LoraLoaderWithPathStack 警告: LoRA 路径无效或文件不存在 '{clean_lora_path}'。将跳过此 LoRA 并直接传递原始模型。")
            return (model, clip)

        try:
            model_lora = model.clone()
            clip_lora = clip.clone()

            print(f"正在从路径加载并堆叠 LoRA: {os.path.basename(clean_lora_path)}")
            
            # 使用清洗后的路径加载 LoRA 文件
            lora_data = comfy.utils.load_torch_file(clean_lora_path)

            model_lora, clip_lora = comfy.sd.load_lora_for_models(
                model_lora, clip_lora, lora_data, strength_model, strength_clip
            )
            
            return (model_lora, clip_lora)

        except Exception as e:
            print(f"LoraLoaderWithPathStack 加载 LoRA 时出错: {str(e)}")
            return (model, clip)

# ======================================================================================================================
# 节点映射
# ======================================================================================================================

# `NODE_CLASS_MAPPINGS` 告诉 ComfyUI 如何将一个字符串名称映射到实际的 Python 类。
NODE_CLASS_MAPPINGS = {
    "LoraLoaderWithPathStack": LoraLoaderWithPathStack
}

# `NODE_DISPLAY_NAME_MAPPINGS` 提供了在 ComfyUI 菜单中显示的、更友好的节点名称。
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraLoaderWithPathStack": "Load LoRA from Path 🔗"
}