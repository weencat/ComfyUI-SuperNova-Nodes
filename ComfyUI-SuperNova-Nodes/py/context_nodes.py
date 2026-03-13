import comfy.samplers
import torch


# ==============================================================================
# 核心工具：万能类型 (AnyType)
# 作用：这是一个“作弊”类，它声称自己等于任何类型。
# 目的：解决 ComfyUI 前端严格的端口类型检查（例如 String 不能连到 Combo）。
# ==============================================================================
class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False  # 永远不“不等于” -> 永远相等
    def __eq__(self, __value: object) -> bool:
        return True   # 永远“等于”任何东西

# 实例化万能对象，用作 RETURN_TYPES 的占位符
any_combo = AnyType("*")

# ==============================================================================
# 2. 核心工具：动态获取列表的辅助函数
#    (定义在这里，但不在此时执行，而是在节点运行时执行)
# ==============================================================================
def get_latest_lists():
    try:
        # 总是获取内存中最新的列表
        s = comfy.samplers.KSampler.SAMPLERS
        c = comfy.samplers.KSampler.SCHEDULERS
    except:
        s = ["euler"]
        c = ["normal"]
    return s, c
#-------------------------------------基础节点 (无需修改)-------------------------------------

class ContextCreateBase:
    """
    基础版 Context 创建节点。
    不包含采样器/调度器等复杂参数，因此不需要 AnyType 修复。
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent": ("LATENT",)
            }
        }

    RETURN_TYPES = ("CONTEXT", "MODEL", "CLIP", "VAE", "CONDITIONING", "CONDITIONING", "LATENT")
    RETURN_NAMES = ("context", "model", "clip", "vae", "positive", "negative", "latent")
    FUNCTION = "create_context"
    CATEGORY = "🪐supernova/Context"

    def create_context(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        
        return (
            ctx, ctx.get("model"), ctx.get("clip"), ctx.get("vae"), 
            ctx.get("positive"), ctx.get("negative"), ctx.get("latent")
        )

class ContextUpdateBase:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional":{
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent": ("LATENT",)
            }
        }

    RETURN_TYPES = ("CONTEXT",)
    RETURN_NAMES = ("context",)
    FUNCTION = "update_context"
    CATEGORY = "🪐supernova/Context"

    def update_context(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        return (ctx,)

class ContextUnpackBase:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "context": ("CONTEXT",),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "CONDITIONING", "CONDITIONING", "LATENT")
    RETURN_NAMES = ("model", "clip", "vae", "positive", "negative", "latent")
    FUNCTION = "unpack_context"
    CATEGORY = "🪐supernova/Context"

    def unpack_context(self, context):
        if context is None:
            return (None, None, None, None, None, None, None, None, 0)
        return (
            context.get("model"), context.get("clip"), context.get("vae"),
            context.get("positive"), context.get("negative"), context.get("latent")
        )


#-------------------------------------高级节点 (已修复)-------------------------------------

class ContextCreateAdded:
    """
    Context Create (Advanced) - 修复版
    1. 动态读取采样器列表，防止列表过时。
    2. 使用 any_type 输出采样器名称，强制允许连接到 KSampler。
    """
    @classmethod
    def INPUT_TYPES(s):
        input_samplers, input_schedulers = get_latest_lists()

        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent": ("LATENT",),
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "seed": ("INT", {"forceInput": True}),
                "steps": ("INT", {"forceInput": True}),
                "cfg": ("FLOAT", {"forceInput": True}),
                
                # 使用动态获取的列表。forceInput: True 表示允许外部连线输入。
                "sampler_name": (input_samplers, {"forceInput": True}),
                "scheduler": (input_schedulers, {"forceInput": True}),
                
                "denoise": ("FLOAT", {"forceInput": True}),
                "pos_text": ("STRING", {"forceInput": True}),
                "neg_text": ("STRING", {"forceInput": True}),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "batch_size": ("INT", {"forceInput": True}),
            }
        }

    # 修复 2: 将 sampler_name 和 scheduler 的输出类型改为 any_type
    # 原来是 "STRING", "STRING"。
    # 改成 any_type 后，无论 KSampler 的输入要求是 COMBO 还是 STRING，都能连上。
    RETURN_TYPES = (
        "CONTEXT", "MODEL", "CLIP", "VAE", "CONDITIONING", "CONDITIONING", 
        "LATENT", "IMAGE", "MASK", "INT", "INT", "FLOAT", 
        any_combo, any_combo, "FLOAT", "STRING", "STRING", "INT", "INT", "INT"
    )
    
    RETURN_NAMES = (
        "context", "model", "clip", "vae", "positive", "negative", 
        "latent", "image", "mask", "seed", "steps", "cfg", 
        "sampler_name", "scheduler", "denoise", "pos_text", "neg_text", "width", "height", "batch_size"
    )
    
    FUNCTION = "execute"
    CATEGORY = "🪐supernova/Context"

    def execute(self, context=None, **kwargs):
        new_ctx = context.copy() if context is not None else {}

        all_keys = [
            "model", "clip", "vae", "positive", "negative", 
            "latent", "image", "mask", "seed", "steps", "cfg", 
            "sampler_name", "scheduler", "denoise", "pos_text", "neg_text", "width", "height", "batch_size"
        ]

        for key in all_keys:
            if key in kwargs and kwargs[key] is not None:
                new_ctx[key] = kwargs[key]

        return (
            new_ctx,
            new_ctx.get("model"),
            new_ctx.get("clip"),
            new_ctx.get("vae"),
            new_ctx.get("positive"),
            new_ctx.get("negative"),
            new_ctx.get("latent"),
            new_ctx.get("image"),
            new_ctx.get("mask"),
            new_ctx.get("seed", 0),
            new_ctx.get("steps", 25),
            new_ctx.get("cfg", 7.0),
            new_ctx.get("sampler_name", "euler"), # 这里实际返回的是字符串，但 any_type 允许它通过类型检查
            new_ctx.get("scheduler", "normal"),
            new_ctx.get("denoise", 1.0),
            new_ctx.get("pos_text", ""),
            new_ctx.get("neg_text", ""),
            new_ctx.get("width", 0),
            new_ctx.get("height", 0),
            new_ctx.get("batch_size", 1)
        )

class ContextUpdateAdded:
    """
    Context Update (Advanced) - 修复版
    主要是更新了 INPUT_TYPES 中的采样器列表获取逻辑。
    """
    @classmethod
    def INPUT_TYPES(s):
        input_samplers, input_schedulers = get_latest_lists()

        return {
            "required": {},
            "optional":{
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent": ("LATENT",),
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "seed": ("INT", {"forceInput": True}),
                "steps": ("INT", {"forceInput": True}),
                "cfg": ("FLOAT", {"forceInput": True}),
                # 使用动态列表
                "sampler_name": (input_samplers, {"forceInput": True}),
                "scheduler": (input_schedulers, {"forceInput": True}),
                "denoise": ("FLOAT", {"forceInput": True}),
                "pos_text": ("STRING", {"forceInput": True}),
                "neg_text": ("STRING", {"forceInput": True}),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "batch_size": ("INT", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("CONTEXT",)
    RETURN_NAMES = ("context",)
    FUNCTION = "update_context"
    CATEGORY = "🪐supernova/Context"

    def update_context(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        return (ctx,)

class ContextUnpackAdded:
    """
    Context Unpack (Advanced) - 修复版
    1. 使用 any_type 作为输出类型，确保解包出来的采样器名称能连入 KSampler。
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "context": ("CONTEXT",),
            }
        }

    # 修复 2: 将输出类型改为 any_type，解决连线变红/拒绝连接的问题
    RETURN_TYPES = (
        "MODEL", "CLIP", "VAE", "CONDITIONING", "CONDITIONING", 
        "LATENT", "IMAGE", "MASK", "INT", "INT", "FLOAT", 
        any_combo, any_combo, "FLOAT", "STRING", "STRING", "INT", "INT", "INT"
    )
    
    RETURN_NAMES = (
        "model", "clip", "vae", "positive", "negative", 
        "latent", "image", "mask", "seed", "steps", "cfg", 
        "sampler_name", "scheduler", "denoise", "pos_text", "neg_text", "width", "height", "batch_size"
    )
    FUNCTION = "unpack_context" 
    CATEGORY = "🪐supernova/Context"

    def unpack_context(self, context=None):
        if context is None:
            context = {}

        return (
            context.get("model"),
            context.get("clip"),
            context.get("vae"),
            context.get("positive"),
            context.get("negative"),
            context.get("latent"),
            context.get("image"),
            context.get("mask"),
            context.get("seed", 0),
            context.get("steps", 25),
            context.get("cfg", 7.0),
            context.get("sampler_name", "euler"), # 输出字符串
            context.get("scheduler", "normal"),   # 输出字符串
            context.get("denoise", 1.0),
            context.get("pos_text", ""),
            context.get("neg_text", ""),
            context.get("width", 0),
            context.get("height", 0),
            context.get("batch_size", 1)
        )

# ==============================================================================
# 节点：ContextBundle (Context 路由/集线器)
# 作用：单纯的数据中转站。输入什么，对应端口就输出什么。
# 场景：用于整理杂乱的连线，或者将多个独立的 Context 并行传输到工作流的另一端。
# ==============================================================================
class ContextBundle:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                # 定义 5 个可选输入，允许只接其中几个
                "context_1": ("CONTEXT",),
                "context_2": ("CONTEXT",),
                "context_3": ("CONTEXT",),
                "context_4": ("CONTEXT",),
                "context_5": ("CONTEXT",),
            }
        }

    # 对应 5 个输出
    RETURN_TYPES = ("CONTEXT", "CONTEXT", "CONTEXT", "CONTEXT", "CONTEXT")
    RETURN_NAMES = ("context_1", "context_2", "context_3", "context_4", "context_5")
    FUNCTION = "route_contexts"
    CATEGORY = "🪐supernova/Context"

    def route_contexts(self, context_1=None, context_2=None, context_3=None, context_4=None, context_5=None):
        # 逻辑非常简单：直进直出
        # 如果输入没接，就返回 None，避免报错
        return (context_1, context_2, context_3, context_4, context_5)
    
#==============================================================
#小型context
#==============================================================

#图片
class ContextImage:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "image": ("IMAGE",),
                "mask": ("MASK",),
            }
        }
    RETURN_TYPES = ("CONTEXT", "IMAGE", "MASK")
    RETURN_NAMES = ("context", "image", "mask")
    FUNCTION = "context_image"
    CATEGORY = "🪐supernova/Context"

    def context_image(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        
        # 【修复】：必须返回所有在 RETURN_TYPES 定义的值
        return (ctx, ctx.get("image"), ctx.get("mask"))
    
#k采样设置
class ContextKSampler:
    @classmethod
    def INPUT_TYPES(s):
        # 【修复1】：加上括号 () 才能真正执行函数获取列表
        input_samplers, input_schedulers = get_latest_lists() 
        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "seed": ("INT", {"forceInput": True}),
                "steps": ("INT", {"forceInput": True}),
                "cfg": ("FLOAT", {"forceInput": True}),
                "sampler_name": (input_samplers, {"forceInput": True}),
                "scheduler": (input_schedulers, {"forceInput": True}),
                "denoise": ("FLOAT", {"forceInput": True}),
            }
        }
    
    # 【修复2】："any_combo" 改为 any_type (变量)，解决连线类型检查
    # 【修复3】：RETURN_TYPES 数量要和 RETURN_NAMES 对应
    RETURN_TYPES = ("CONTEXT", "INT", "INT", "FLOAT", any_combo, any_combo, "FLOAT")
    # 【修复4】：补上漏掉的 "denoise"
    RETURN_NAMES = ("context", "seed", "steps", "cfg", "sampler_name", "scheduler", "denoise")
    
    FUNCTION = "context_KSampler"
    CATEGORY = "🪐supernova/Context"

    def context_KSampler(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        
        # 【修复5】：返回所有 unpacked 的值，并给默认值防止 None 报错
        return (
            ctx, 
            ctx.get("seed", 0), 
            ctx.get("steps", 20), 
            ctx.get("cfg", 8.0), 
            ctx.get("sampler_name", "euler"), 
            ctx.get("scheduler", "normal"), 
            ctx.get("denoise", 1.0)
        )

#提示词文本
class ContextPNText:
    @classmethod
    def INPUT_TYPES(s):
        # 【修复】：删除了无关的 get_latest_lists
        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "pos_text": ("STRING", {"forceInput": True}),
                "neg_text": ("STRING", {"forceInput": True}),
            }
        }
    RETURN_TYPES = ("CONTEXT", "STRING", "STRING")
    RETURN_NAMES = ("context", "pos_text", "neg_text")
    FUNCTION = "context_PNText"
    CATEGORY = "🪐supernova/Context"

    def context_PNText(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        
        # 【修复】：返回 unpack 的值
        return (ctx, ctx.get("pos_text", ""), ctx.get("neg_text", ""))

#Latent
class ContextLatent:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "context": ("CONTEXT",),
                "latent": ("LATENT",),
                "width": ("INT", {"forceInput": True}),
                "height": ("INT", {"forceInput": True}),
                "batch_size": ("INT", {"forceInput": True}),
            }
        }
    RETURN_TYPES = ("CONTEXT", "LATENT", "INT", "INT", "INT")
    RETURN_NAMES = ("context", "latent", "width", "height", "batch_size")
    FUNCTION = "context_latent"
    CATEGORY = "🪐supernova/Context"

    def context_latent(self, context=None, **kwargs):
        ctx = context.copy() if context is not None else {}
        for key, value in kwargs.items():
            if value is not None:
                ctx[key] = value
        
        # 【修复】：返回 unpack 的值
        return (
            ctx, 
            ctx.get("latent"), 
            ctx.get("width", 512), 
            ctx.get("height", 512), 
            ctx.get("batch_size", 1)
        )
# ==============================================================================
# 节点注册映射
# 这是告诉 ComfyUI 这个文件里有哪些节点，以及它们叫什么名字
# ==============================================================================
NODE_CLASS_MAPPINGS = {
    "ContextCreateBase": ContextCreateBase,
    "ContextUpdateBase": ContextUpdateBase,
    "ContextUnpackBase": ContextUnpackBase,
    "ContextCreateAdded": ContextCreateAdded,
    "ContextUpdateAdded": ContextUpdateAdded,
    "ContextUnpackAdded": ContextUnpackAdded,
    "ContextImage": ContextImage,
    "ContextKSampler": ContextKSampler,
    "ContextPNText": ContextPNText,
    "ContextLatent": ContextLatent,
    "ContextBundle": ContextBundle,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ContextCreateBase": "Context Create (Base)🖇️",
    "ContextUpdateBase": "Context Update (Base)🖇️",
    "ContextUnpackBase": "Context Unpack (Base)🖇️",
    "ContextCreateAdded": "Context Create (Advanced) 🖇️",
    "ContextUpdateAdded": "Context Update (Advanced) 🖇️",
    "ContextUnpackAdded": "Context Unpack (Advanced) 🖇️",
    "ContextImage": "Context Image 🖇️",
    "ContextKSampler": "Context KSampler 🖇️",
    "ContextPNText": "Context PNText 🖇️",
    "ContextLatent": "Context Latent🖇️",
    "ContextBundle": "Context Bundle (Router) 🚥",
}