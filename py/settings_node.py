import sys
import comfy.samplers

class KSamplerSettings:
    """
    一个用于集中管理 KSampler 设置的节点 (传统兼容版)。
    它使用 ComfyUI 标准的 NODE_CLASS_MAPPINGS 注册方法，确保能被正确加载。
    通过直接从 `comfy.samplers` 读取列表来动态获取所有可用的采样器和调度器，
    这确保了它能与任何添加了自定义采样器/调度器的其他节点包完美兼容。
    """
    
    # 1. 定义节点的类别，用于在右键菜单中分类
    CATEGORY = "🪐supernova/settings"

    # 2. 定义节点的输出类型和名称
    # 顺序必须和 execute 方法的 return 语句中的顺序完全一致
    RETURN_TYPES = ("INT", "INT", "FLOAT", comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS, "FLOAT",)
    RETURN_NAMES = ("seed", "steps", "cfg", "sampler_name", "scheduler", "denoise",)

    # 3. 定义节点执行的函数名
    FUNCTION = "get_settings"

    # 4. 定义节点的输入类型和参数
    @classmethod
    def INPUT_TYPES(cls):
        # 动态获取当前 ComfyUI 环境中所有可用的采样器和调度器
        # 这是解决您之前遇到的 `Return type mismatch` 错误的关键！
        available_samplers = comfy.samplers.KSampler.SAMPLERS
        available_schedulers = comfy.samplers.KSampler.SCHEDULERS

        return {
            "required": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                # 直接将动态列表作为下拉菜单的选项
                "sampler_name": (available_samplers, ),
                "scheduler": (available_schedulers, ),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    # 5. 节点的执行逻辑
    def get_settings(self, seed, steps, cfg, sampler_name, scheduler, denoise):
        # 将所有接收到的输入值，按照 RETURN_TYPES/RETURN_NAMES 定义的顺序打包返回
        return (seed, steps, cfg, sampler_name, scheduler, denoise)
#-------------------------------------------------------------------------
class IntAndFloatHub:
    """
    一个简洁的数字集线器节点。
    它提供一个整数输入和一个浮点数输入，并分别从独立的输出端口输出。
    非常适合用作工作流中种子(Seed)、步数(Steps)、CFG 或 Denoise 等参数的中央控制器。
    """
    
    # 1. 定义节点的分类，方便在菜单中查找
    CATEGORY = "🪐supernova/settings"

    # 2. 定义节点的输出类型和名称
    #    第一个输出是整数，第二个是浮点数
    RETURN_TYPES = ("INT", "FLOAT",)
    RETURN_NAMES = ("INT", "float",)

    # 3. 定义节点要执行的函数名
    FUNCTION = "get_numbers"

    # 4. 定义节点的输入界面
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 整数输入
                "INT": ("INT", {
                    "default": 0, 
                    "min": 0, # 通常用于 Seed，所以最小值为 0
                    "max": 0xffffffffffffffff, 
                    "step": 1,
                    #"control_after_generate": True # 关键特性：允许在批量生成时自动递增/随机化
                }),

                # 浮点数输入
                "float": ("FLOAT", {
                    "default": 1.0, 
                    "min": -sys.maxsize, 
                    "max": sys.maxsize,
                    "step": 0.01 # 步长为 0.01，适合微调
                }),
            }
        }

    # 5. 节点的执行逻辑
    def get_numbers(self, INT, float):
        # 将接收到的输入值，按顺序打包成一个元组返回
        # 第一个值对应第一个 RETURN_TYPE，第二个值对应第二个 RETURN_TYPE
        return (INT, float)


# --- 【关键部分】节点注册 ---
# 这两段代码是 ComfyUI 能够识别并加载这个节点的关键

# --- 新版本节点 (已修复兼容性问题) ----------------------------------------
class SamplerSchedulerHubv2:
    """
    【最终修正版】一个专门提供采样器和调度器的集线器节点。
    根据错误报告，KSampler 的输入端口需要明确的 STRING 类型，而不是通用 COMBO(*)。
    此版本将输出类型修正为 STRING，确保 100% 兼容。
    """
    
    # 节点的分类
    CATEGORY = "🪐supernova/settings"

    # 【最终修正】: 将输出类型从"*"改回"STRING"。这是解决报错的关键。
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("sampler_name", "scheduler",)
    
    # 执行函数
    FUNCTION = "get_selections"

    @classmethod
    def INPUT_TYPES(cls):
        # 节点UI上依然使用列表来生成下拉菜单
        return {
            "required": {
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, ),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, ),
            }
        }

    def get_selections(self, sampler_name, scheduler):
        # 将用户从下拉菜单中选择的字符串值直接返回。
        # 这个 STRING 类型可以被 KSampler 节点正确接收。
        return (sampler_name, scheduler)

#--------------------------------------------------------------------
NODE_CLASS_MAPPINGS = {
    "IntAndFloatHub_Node": IntAndFloatHub,
    "KSamplerSettings_Standard": KSamplerSettings,
    "SamplerSchedulerHubv2": SamplerSchedulerHubv2,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "IntAndFloatHub_Node": "Number Hub (Int & Float) 🔢",
    "KSamplerSettings_Standard": "KSampler Settings (Standard) ⚙️",
    "SamplerSchedulerHubv2": "Sampler & Scheduler Hub ⚙️",
}