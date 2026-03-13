import sys  # 导入系统模块，用于获取系统最大整数值等
import comfy.samplers  # 导入 ComfyUI 的采样器模块，用于读取全局采样器列表
import random  # 导入随机数模块，用于生成随机种子
import torch  # 导入 PyTorch，用于处理 Tensor 数据（Latent 本质是 Tensor）

# ==============================================================================
# 核心工具：万能类型 (AnyType)
# 这是一个特殊的类，用于解决 ComfyUI 前端严格的类型检查问题。
# ==============================================================================
class AnyType(str):
    """
    一个继承自 str 的特殊类。
    它的作用是“欺骗” ComfyUI 的连接系统。
    """
    # 重写“不等于”方法
    def __ne__(self, __value: object) -> bool:
        return False  # 永远返回 False，意味着它永远不会“不等于”任何东西

    # 重写“等于”方法
    def __eq__(self, __value: object) -> bool:
        return True  # 永远返回 True，意味着它“等于”任何类型的端口（String, Combo, Any 等）

# 实例化一个万能对象，代表"任意类型"
# 在 RETURN_TYPES 中使用这个变量，就可以连接到任何输入端口
any_type = AnyType("*")


# ==============================================================================
# 节点 1: KSamplerSettings (KSampler 设置集线器)
# 作用：集中管理种子、步数、CFG、采样器等参数，并输出给 KSampler。
# ==============================================================================
class KSamplerSettings:
    
    # 定义节点在 ComfyUI 右键菜单中的分类路径
    CATEGORY = "🪐supernova/settings"

    # 定义节点的输出类型
    # 【关键修改】：sampler_name 和 scheduler 使用 any_type
    # 这样即使 KSampler 要求的是 COMBO 类型，这里也能强行连上去，不会被前端拒绝
    RETURN_TYPES = ("INT", "INT", "FLOAT", any_type, any_type, "FLOAT",)
    
    # 定义节点输出端口显示的名称
    RETURN_NAMES = ("seed", "steps", "cfg", "sampler_name", "scheduler", "denoise",)

    # 定义节点实际执行逻辑的函数名
    FUNCTION = "get_settings"

    @classmethod
    def INPUT_TYPES(cls):
        """
        定义节点的输入控件（UI界面）。
        【核心修复】：将采样器列表的获取逻辑放在这个函数内部。
        """
        # 尝试获取当前的完整列表
        try:
            # 这里的 comfy.samplers.KSampler.SAMPLERS 是实时的
            # 当用户刷新网页或加载工作流时，代码运行到这里，
            # 此时所有其他插件（如 RES4LYF）都已经加载完毕，所以能读到修改后的完整列表
            current_samplers = comfy.samplers.KSampler.SAMPLERS
            current_schedulers = comfy.samplers.KSampler.SCHEDULERS
        except:
            # 如果万一获取失败（极少情况），使用预设的默认列表防止崩溃
            current_samplers = ["euler", "euler_ancestral", "heun", "dpm_2", "lms", "dpmpp_2m"]
            current_schedulers = ["normal", "karras", "exponential", "simple", "sgm_uniform"]

        # 返回输入配置字典
        return {
            "required": {
                # 整数输入：种子
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                # 整数输入：步数
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                # 浮点输入：CFG Scale
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                
                # 下拉菜单：采样器（使用刚才动态获取的 current_samplers）
                "sampler_name": (current_samplers, ),
                # 下拉菜单：调度器（使用刚才动态获取的 current_schedulers）
                "scheduler": (current_schedulers, ),
                
                # 浮点输入：降噪强度
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    # 执行函数：简单地将输入的值原样返回
    def get_settings(self, seed, steps, cfg, sampler_name, scheduler, denoise):
        # 这里的 sampler_name 是用户选中的字符串（例如 "euler" 或 "beta57"）
        return (seed, steps, cfg, sampler_name, scheduler, denoise)


# ==============================================================================
# 节点 2: IntAndFloatHub (数字集线器)
# 作用：提供简单的整数和浮点数输入输出。
# ==============================================================================
class IntAndFloatHub:
    
    CATEGORY = "🪐supernova/settings"  # 分类
    RETURN_TYPES = ("INT", "FLOAT",)  # 输出类型：一个整数，一个浮点
    RETURN_NAMES = ("INT", "float",)  # 输出名称
    FUNCTION = "get_numbers"          # 执行函数

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 整数输入控件
                "INT": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "max": 0xffffffffffffffff, 
                    "step": 1,
                }),
                # 浮点数输入控件
                "float": ("FLOAT", {
                    "default": 1.0, 
                    "min": -sys.maxsize, # 使用系统允许的最小数
                    "max": sys.maxsize,  # 使用系统允许的最大数
                    "step": 0.01         # 调节步长
                }),
            }
        }

    # 简单透传数据
    def get_numbers(self, INT, float):
        return (INT, float)
    

# ==============================================================================
# 节点 3: SamplerSchedulerHubv2 (采样/调度器集线器)
# 作用：单独提供采样器和调度器的选择。
# ==============================================================================
class SamplerSchedulerHubv2:
    
    CATEGORY = "🪐supernova/settings"
    
    # 【关键修改】：同样使用 any_type，确保能连上 KSampler
    RETURN_TYPES = (any_type, any_type,)
    RETURN_NAMES = ("sampler_name", "scheduler",)
    FUNCTION = "get_selections"

    @classmethod
    def INPUT_TYPES(cls):
        # 【核心修复】：同样在内部动态读取列表，确保同步其他插件的修改
        try:
            current_samplers = comfy.samplers.KSampler.SAMPLERS
            current_schedulers = comfy.samplers.KSampler.SCHEDULERS
        except:
            current_samplers = ["euler", "normal"] 
            current_schedulers = ["normal", "simple"]

        return {
            "required": {
                # 使用动态列表生成下拉菜单
                "sampler_name": (current_samplers, ),
                "scheduler": (current_schedulers, ),
            }
        }

    # 返回用户选中的字符串
    def get_selections(self, sampler_name, scheduler):
        return (sampler_name, scheduler)


# ==============================================================================
# 节点 4: SeedHub (种子集线器)
# 作用：提供更高级的随机种子控制。
# ==============================================================================
class SeedHub:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffffffffffff}),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("seed",)
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/settings"

    @classmethod
    def IS_CHANGED(cls, seed):
        if seed == -1: return random.random()
        return seed

    def execute(self, seed):
        if seed == -1:
            seed = random.randint(1, 0xffffffffffffffff)
        
        # 必须这样返回，前端才能收到数据
        return {
            "ui": {"seed": [seed]}, 
            "result": (seed,)
        }
    
# ==============================================================================
# 节点 5: VisualLatentNode (Latent 生成器)
# 作用：生成空的 Latent 图像，支持 8 像素对齐。
# ==============================================================================
class VisualLatentNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # 宽和高，step=1 允许任意尺寸
                "width": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 1}),
                "height": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 1}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 64}),
                # 开关：是否强制对齐到 8 的倍数（SDXL/SD1.5 推荐开启）
                "pixel_alignment": ("BOOLEAN", {"default": True}),
            },
        }

    # 定义 4 个输出
    RETURN_TYPES = ("LATENT", "INT", "INT", "INT")
    RETURN_NAMES = ("latent", "width", "height", "batch_size")
    FUNCTION = "generate"
    CATEGORY = "🪐supernova/settings"

    def generate(self, width, height, batch_size, pixel_alignment):
        # 如果开启对齐，将宽高强制调整为 8 的倍数
        # // 是整除，(513 // 8) * 8 = 64 * 8 = 512
        if pixel_alignment:
            width = (width // 8) * 8
            height = (height // 8) * 8
            
        # 创建一个全零的 Tensor，维度为 [批次, 通道数(4), 高度/8, 宽度/8]
        # 这是 Stable Diffusion Latent 的标准格式
        latent = torch.zeros([batch_size, 4, height // 8, width // 8])
        
        # 【重要修复】：返回值的数量必须和 RETURN_TYPES 里的数量一致（4个）
        # 之前的代码少返回了 batch_size，导致报错
        return ({"samples": latent}, width, height, batch_size)


# ==============================================================================
# 节点注册映射
# 这是告诉 ComfyUI 这个文件里有哪些节点，以及它们叫什么名字
# ==============================================================================
NODE_CLASS_MAPPINGS = {
    "IntAndFloatHub_Node": IntAndFloatHub,
    "KSamplerSettings_Standard": KSamplerSettings,
    "SamplerSchedulerHubv2": SamplerSchedulerHubv2,
    "SeedHub": SeedHub,
    "VisualLatentNode": VisualLatentNode,
}

# 显示名称映射（UI上看到的名字）
NODE_DISPLAY_NAME_MAPPINGS = {
    "IntAndFloatHub_Node": "Number Hub (Int & Float) 🔢",
    "KSamplerSettings_Standard": "KSampler Settings (Standard) ⚙️",
    "SamplerSchedulerHubv2": "Sampler & Scheduler Hub ⚙️",
    "SeedHub": "Seed Hub 🎲",
    "VisualLatentNode": "Empty Latent Image (Visual) ↔️"
}