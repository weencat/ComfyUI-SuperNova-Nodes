from ..code.alcode import is_context_empty
from ..code.alcode import FlexibleOptionalInputType, any_type

def is_none(value):
  """
  检查一个值是否为 "None"。
  这个函数扩展了传统意义上的 None，使其能处理 ComfyUI 中特定的数据结构。
  """
  # 如果值不是 Python 的 None
  if value is not None:
    # 特殊情况处理：如果值是一个字典，并且同时包含 'model' 和 'clip' 键，
    # 那么它可能是一个 "Context" 对象。在这种情况下，调用 is_context_empty 来判断这个 context 是否为空。
    # Context 是 rgthree-comfy 扩展中的一个核心概念，用于捆绑和传递多个数据流（如模型、CLIP、VAE等）。[1, 7]
    if isinstance(value, dict) and 'model' in value and 'clip' in value:
      return is_context_empty(value)
  # 如果以上条件都不满足，或者 value 本身就是 None，则返回常规的 None 判断结果
  return value is None

class AnyMultiSwitchScalable:
    """
    一个稳定、可配置的多路通用切换节点。
    它会根据下面设置的数量，显示固定数量的输入接口。
    它会按顺序查找，并输出第一个被连接的有效输入。
    """
    # ==================================================================
    # 在这里轻松修改你想要的固定输入接口数量
    # 默认设置为 5，你可以根据需要改成 3, 8, 10 或任何数字。
    N_INPUTS = 2
    # ==================================================================

    @classmethod
    def INPUT_TYPES(cls):
        """
        根据上面设置的 N_INPUTS，一次性定义好所有可选的输入接口。
        这是 ComfyUI 的标准做法，保证能正确显示。
        """
        # 使用 '*' 代表任意类型 (ANY)
        #any_type = "*"
        
        optional_inputs = {}
        # 循环动态生成名为 input1, input2, ... 的输入
        for i in range(1, cls.N_INPUTS + 1):
            optional_inputs[f"input{i}"] = (any_type,)

        return {
            "required": {},
            # 正确地实例化我们自己的工具类
            "optional": FlexibleOptionalInputType(any_type, optional_inputs)
        }

    # 返回类型也必须是 '*'，以确保它可以将数据传递给任何后续节点。
    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output",)
    CATEGORY = "🪐supernova/Switches"
    FUNCTION = "switch"

    def switch(self, **kwargs):
        """
        核心逻辑：遍历所有传入的参数（kwargs），并返回第一个有效（非 None）的值。
        这种方法非常灵活，因为它不关心输入的具体名称。
        """
        # kwargs 包含了所有连接到可选输入的参数
        for key, value in kwargs.items():
            # 找到第一个被连接且有数据的值
            if value is not None:
                # 立即返回，实现 "Switch" 功能
                return (value,)
        
        # 如果所有输入都为空或未连接，则安全地返回 None
        return (None,)

# --- 节点注册信息 ---

NODE_CLASS_MAPPINGS = {
   "AnyMultiSwitchScalable": AnyMultiSwitchScalable,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AnyMultiSwitchScalable": "AnyMultiSwitchScalable 🎚️",
}