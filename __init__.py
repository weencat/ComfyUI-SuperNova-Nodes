# 文件: 🪐supernova/__init__.py (已升级为支持子目录扫描的最终版)

import os
import sys
import importlib
from server import PromptServer
from aiohttp import web

# =================================================================================
# 1. 首先定义所有全局变量和路径
# =================================================================================
NODE_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIRECTORY = "js"
# --- [关键] PY_FOLDER 路径保持不变 ---
PY_FOLDER = os.path.join(NODE_ROOT, "py")
# 创建一个全局的 API 函数注册表
API_FUNCTION_REGISTRY = {}
# --- [关键] 我们不仅要添加 py 根目录，还需要添加所有子目录到 sys.path ---
# 这样可以确保子目录间的相互导入 (e.g., from .utils import ...) 能够正常工作
print("正在扫描并添加 'py' 及其子目录到系统路径...")
for root, dirs, files in os.walk(PY_FOLDER):
    if root not in sys.path:
        sys.path.insert(0, root)
        print(f"  - 已添加路径: {os.path.relpath(root, NODE_ROOT)}")


# =================================================================================
# 2. 注册所有需要 Web 访问的 API 端点 (此部分保持您原有的逻辑)
# =================================================================================
# <<<--- 接入点/API 端点定义 --- START --->>>
@PromptServer.instance.routes.get("/audio/{filename}")
async def get_audio_file(request):
    filename = request.match_info.get("filename", None)
    if not filename: return web.Response(status=404)
    audio_folder = os.path.join(NODE_ROOT, "audio")
    audio_path = os.path.join(audio_folder, filename)
    if not os.path.normpath(audio_path).startswith(os.path.normpath(audio_folder)):
        return web.Response(status=403)
    if os.path.isfile(audio_path): return web.FileResponse(audio_path)
    else: return web.Response(status=404)

# 假设这个函数在某个子目录的节点文件中定义
# 我们在这里先做一个临时的定义，以防加载顺序导致问题
def get_image_file_list():
    print("警告: 'get_image_file_list' 函数尚未被实际节点模块覆盖。")
    return []

@PromptServer.instance.routes.get("/my-nodes/refresh-files")
async def refresh_file_list_endpoint(request):
    try:
        # 从注册表中动态获取最新版本的函数
        refresh_func = API_FUNCTION_REGISTRY.get("get_image_file_list")
        if not refresh_func:
            return web.json_response({"error": "Function not registered"}, status=404)
        
        file_list = refresh_func()
        return web.json_response(file_list)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
# <<<--- 接入点/API 端点定义 --- END --->>>

# =================================================================================
# 3. 自动扫描并加载所有节点 (*** 这是修改的核心部分 ***)
# =================================================================================
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

print("正在递归扫描 'py' 文件夹下的所有自定义节点...")

# --- [修改开始] ---
# 使用 os.walk 来遍历 py 目录及其所有子目录
for root, dirs, files in os.walk(PY_FOLDER):
    for filename in files:
        if filename.endswith(".py") and not filename.startswith("__"):
            # 构造模块的 Python 导入路径
            # 例如: .../🪐supernova/py/utils/helpers.py -> .py.utils.helpers
            relative_path = os.path.relpath(root, NODE_ROOT)
            module_name_path = os.path.join(relative_path, filename[:-3]).replace(os.sep, '.')
            
            try:
                # 动态导入模块
                module = importlib.import_module(f".{module_name_path}", __name__)
                
                # 更新 MAPPINGS
                if hasattr(module, "NODE_CLASS_MAPPINGS"):
                    NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)
                if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
                    NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)
                
                print(f"  - 已加载模块: {module_name_path}")

            except Exception as e:
                print(f"  - 无法加载模块 {module_name_path}: {e}")
# --- [修改结束] ---


# =================================================================================
# 4. 导出最终的 MAPPINGS
# =================================================================================
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

print(f"✅ 超新星已完成变星。共加载 {len(NODE_CLASS_MAPPINGS)} 个节点，并已注册 API 接入点。")