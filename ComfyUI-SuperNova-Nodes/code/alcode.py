# 文件: myboys_core.py (合并了 JS 安装、日志、通用工具和 Context 功能的最终版)

# ======================================================================
#  第 1 部分: 核心应用功能 (JS安装, 日志, 配置)
# ======================================================================

import asyncio
import os
import shutil
import inspect
import aiohttp
from server import PromptServer
from tqdm import tqdm

# 【新增】: 导入 alcode.py 部分需要的库
import json
import re
from typing import Union
import comfy.samplers
import folder_paths


# --- 核心配置与日志 ---

config = None

def get_extension_config(reload=False):
    """获取扩展的配置，如果不存在则创建默认配置。"""
    global config
    if not reload and config is not None:
        return config

    config_path = os.path.join(os.path.dirname(__file__), "myboys_core.json")

    if not os.path.exists(config_path):
        print(f"(myboys) 配置文件 'myboys_core.json' 未找到，将创建默认配置。")
        default_config = {"name": "myboys", "logging": True}
        with open(config_path, "w", encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        config = default_config
    else:
        with open(config_path, "r", encoding='utf-8') as f:
            config = json.load(f)
    return config

def is_logging_enabled():
    """检查日志记录是否已启用。"""
    return get_extension_config().get("logging", False)

def log(message, type=None, always=False):
    """打印带前缀的日志信息。"""
    if not always and not is_logging_enabled():
        return
    
    name = get_extension_config().get("name", "myboys")
    if type:
        message = f"[{type.upper()}] {message}"
    print(f"({name}) {message}")


# --- JS 文件安装 ---

def get_ext_dir(subpath=None):
    """获取当前扩展所在的目录。"""
    dir_path = os.path.dirname(__file__)
    if subpath:
        dir_path = os.path.join(dir_path, subpath)
    return os.path.abspath(dir_path)

def get_comfy_dir(subpath=None):
    """获取 ComfyUI 的根目录。"""
    dir_path = os.path.dirname(inspect.getfile(PromptServer))
    if subpath:
        dir_path = os.path.join(dir_path, subpath)
    return os.path.abspath(dir_path)

# 文件：alcode.py (当 alcode.py 位于 My-node/ 根目录下时)

def install_js():
    """
    将 web/js 目录下的 JS 文件复制到 ComfyUI 的 web/extensions 目录。
    这个函数假定 alcode.py 文件的父目录就是扩展的根目录。
    """
    try:
        # 1. 计算源路径 (web/js)
        #    os.path.abspath(__file__) -> 获取 alcode.py 的绝对路径
        #    os.path.dirname(...)      -> 获取 alcode.py 所在的目录 (也就是 My-node/ 的路径)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.join(base_dir, "web", "js")
        
        # 添加调试打印，方便确认路径是否正确
        log(f"正在从源路径查找 JS 文件: {src_dir}")

        # 2. 检查源路径是否存在
        if not os.path.exists(src_dir):
            log(f"未找到 'web/js' 目录，跳过 JS 文件安装。")
            return

        # 3. 计算目标路径 (ComfyUI/web/extensions/myboys)
        ext_name = get_extension_config().get("name", "myboys")
        dst_dir = get_comfy_dir(f"web/extensions/{ext_name}")
        log(f"准备将 JS 文件安装到: {dst_dir}")

        # 4. 执行复制操作
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir) # 先删除旧的，确保全新安装
        
        shutil.copytree(src_dir, dst_dir)
        log("JS 文件已成功复制。")

    except Exception as e:
        log(f"安装 JS 文件时发生错误: {e}", type="error", always=True)

# --- 初始化函数 ---

def init():
    """初始化核心库，安装JS文件。"""
    log("核心库正在初始化...")
    install_js()
    log("核心库初始化完成。")
    return True


# ======================================================================
#  第 2 部分: 通用工具和 Context 功能 (来自 alcode.py)
# ======================================================================

class AnyType(str):
  """A special class that is always equal in not equal comparisons. Credit to pythongosssss"""
  def __ne__(self, __value: object) -> bool:
    return False

class FlexibleOptionalInputType(dict):
  """A special class to make flexible nodes that pass data to our python handlers."""
  def __init__(self, type, data: Union[dict, None] = None):
    super().__init__()
    self.type = type
    self.data = data
    if self.data is not None:
      for k, v in self.data.items():
        self[k] = v
  def __getitem__(self, key):
    if self.data is not None and key in self.data:
      val = self.data[key]
      return val
    return (self.type,)
  def __contains__(self, key):
    return True

any_type = AnyType("*")

def is_dict_value_falsy(data: dict, dict_key: str):
  """Checks if a dict value is falsy."""
  val = get_dict_value(data, dict_key)
  return not val

def get_dict_value(data: dict, dict_key: str, default=None):
  """Gets a deeply nested value given a dot-delimited key."""
  keys = dict_key.split('.')
  key = keys.pop(0) if len(keys) > 0 else None
  found = data.get(key)
  if found is not None and len(keys) > 0 and isinstance(found, dict):
    return get_dict_value(found, '.'.join(keys), default)
  return found if found is not None else default

def set_dict_value(data: dict, dict_key: str, value, create_missing_objects=True):
  """Sets a deeply nested value given a dot-delimited key."""
  keys = dict_key.split('.')
  key = keys.pop(0) if len(keys) > 0 else None
  if key not in data:
    if not create_missing_objects:
      return data
    data[key] = {}
  if len(keys) == 0:
    data[key] = value
  else:
    set_dict_value(data[key], '.'.join(keys), value, create_missing_objects)
  return data

def dict_has_key(data: dict, dict_key):
  """Checks if a dict has a deeply nested dot-delimited key."""
  keys = dict_key.split('.')
  key = keys.pop(0) if len(keys) > 0 else None
  if key is None or key not in data:
    return False
  if len(keys) == 0:
    return True
  return dict_has_key(data[key], '.'.join(keys))

def load_json_file(file: str, default=None):
  """Reads a json file and returns the json dict, stripping out "//" comments first."""
  if path_exists(file):
    with open(file, 'r', encoding='UTF-8') as f:
      content = f.read()
      try:
        return json.loads(content)
      except json.JSONDecodeError:
        try:
          # 尝试移除单行注释
          content_no_comments = re.sub(r"//.*", "", content)
          return json.loads(content_no_comments)
        except json.JSONDecodeError as e:
          log(f"解析JSON文件 '{file}' 失败: {e}", type="error", always=True)
  return default

def save_json_file(file_path: str, data: dict):
  """Saves a json file."""
  os.makedirs(os.path.dirname(file_path), exist_ok=True)
  with open(file_path, 'w', encoding='UTF-8') as file:
    json.dump(data, file, indent=2)

def path_exists(path):
  """Checks if a path exists, accepting None type."""
  return path is not None and os.path.exists(path)

def file_exists(path):
  """Checks if a file exists, accepting None type."""
  return path is not None and os.path.isfile(path)

def remove_path(path):
  """Removes a path, if it exists."""
  if path_exists(path):
    os.remove(path)
    return True
  return False

class ByPassTypeTuple(tuple):
  """A special class that will return additional "AnyType" strings beyond defined values."""
  def __getitem__(self, index):
    if index >= len(self):
      return AnyType("*")
    return super().__getitem__(index)

def install_js():
    """将 web/js 目录下的 JS 文件复制到 ComfyUI 的 web/extensions 目录。"""
    
    # 【新增调试代码】: 打印出它到底在哪个路径下寻找 web/js
    # -----------------------------------------------------------------
    ext_dir = get_ext_dir()
    js_source_dir_to_find = os.path.join(ext_dir, "web", "js")
    print(f"--- [DEBUG] Pysssss 正在尝试从此路径加载 JS: {js_source_dir_to_find} ---")
    # -----------------------------------------------------------------

    src_dir = get_ext_dir("web/js") # 这是原来的代码，我们保留它
    
    if not os.path.exists(src_dir):
        log("未找到 'web/js' 目录，跳过 JS 文件安装。")
        return

# --- Context 功能 ---

_all_context_input_output_data = {
  "base_ctx": ("base_ctx", "RGTHREE_CONTEXT", "CONTEXT"),
  "model": ("model", "MODEL", "MODEL"),
  "clip": ("clip", "CLIP", "CLIP"),
  "vae": ("vae", "VAE", "VAE"),
  "positive": ("positive", "CONDITIONING", "POSITIVE"),
  "negative": ("negative", "CONDITIONING", "NEGATIVE"),
  "latent": ("latent", "LATENT", "LATENT"),
  "images": ("images", "IMAGE", "IMAGE"),
  "seed": ("seed", "INT", "SEED"),
  "steps": ("steps", "INT", "STEPS"),
  "step_refiner": ("step_refiner", "INT", "STEP_REFINER"),
  "cfg": ("cfg", "FLOAT", "CFG"),
  "ckpt_name": ("ckpt_name", folder_paths.get_filename_list("checkpoints"), "CKPT_NAME"),
  "sampler": ("sampler", comfy.samplers.KSampler.SAMPLERS, "SAMPLER"),
  "scheduler": ("scheduler", comfy.samplers.KSampler.SCHEDULERS, "SCHEDULER"),
  "clip_width": ("clip_width", "INT", "CLIP_WIDTH"),
  "clip_height": ("clip_height", "INT", "CLIP_HEIGHT"),
  "text_pos_g": ("text_pos_g", "STRING", "TEXT_POS_G"),
  "text_pos_l": ("text_pos_l", "STRING", "TEXT_POS_L"),
  "text_neg_g": ("text_neg_g", "STRING", "TEXT_NEG_G"),
  "text_neg_l": ("text_neg_l", "STRING", "TEXT_NEG_L"),
  "mask": ("mask", "MASK", "MASK"),
  "control_net": ("control_net", "CONTROL_NET", "CONTROL_NET"),
}

force_input_types = ["INT", "STRING", "FLOAT"]
force_input_names = ["sampler", "scheduler", "ckpt_name"]

def _create_context_data(input_list=None):
  if input_list is None:
    input_list = _all_context_input_output_data.keys()
  list_ctx_return_types = []
  list_ctx_return_names = []
  ctx_optional_inputs = {}
  for inp in input_list:
    if inp not in _all_context_input_output_data: continue
    data = _all_context_input_output_data[inp]
    list_ctx_return_types.append(data[1])
    list_ctx_return_names.append(data[2])
    force_input = data[1] in force_input_types or data[0] in force_input_names
    ctx_optional_inputs[data[0]] = (data[1], {"forceInput": True} if force_input else {})

  ctx_return_types = tuple(list_ctx_return_types)
  ctx_return_names = tuple(list_ctx_return_names)
  return (ctx_optional_inputs, ctx_return_types, ctx_return_names)

ALL_CTX_OPTIONAL_INPUTS, ALL_CTX_RETURN_TYPES, ALL_CTX_RETURN_NAMES = _create_context_data()
_original_ctx_inputs_list = [
  "base_ctx", "model", "clip", "vae", "positive", "negative", "latent", "images", "seed"
]
ORIG_CTX_OPTIONAL_INPUTS, ORIG_CTX_RETURN_TYPES, ORIG_CTX_RETURN_NAMES = _create_context_data(
  _original_ctx_inputs_list)

def new_context(base_ctx, **kwargs):
  context = base_ctx if base_ctx else {}
  new_ctx = {}
  for key in _all_context_input_output_data:
    if key == "base_ctx": continue
    v = kwargs.get(key)
    new_ctx[key] = v if v is not None else context.get(key)
  return new_ctx

def merge_new_context(*args):
  new_ctx = {}
  for key in _all_context_input_output_data:
    if key == "base_ctx": continue
    v = None
    for ctx in reversed(args):
      if not is_context_empty(ctx):
        v = ctx.get(key)
        if v is not None:
          break
    new_ctx[key] = v
  return new_ctx

def get_context_return_tuple(ctx, inputs_list=None):
  if inputs_list is None:
    inputs_list = _all_context_input_output_data.keys()
  
  tup_list = [ctx]
  for key in inputs_list:
    if key == "base_ctx": continue
    tup_list.append(ctx.get(key) if ctx else None)
  return tuple(tup_list)

def get_orig_context_return_tuple(ctx):
  return get_context_return_tuple(ctx, _original_ctx_inputs_list)

def is_context_empty(ctx):
  return not ctx or all(v is None for v in ctx.values())