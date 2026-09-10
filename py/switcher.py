import time
import os
from aiohttp import web
from server import PromptServer

# --- 基础环境检查 ---
try:
    from comfy_execution.graph import ExecutionBlocker
except ImportError:
    ExecutionBlocker = None

# --- 音频挂载 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
audio_dir = os.path.join(base_dir, "audio")

if os.path.exists(audio_dir):
    has_route = False
    for route in PromptServer.instance.app.router.routes():
        if route.resource and route.resource.canonical == "/supernova/audio":
            has_route = True
            break
    if not has_route:
        PromptServer.instance.app.add_routes([
            web.static("/supernova/audio", audio_dir)
        ])

SELECTION_STATE = {}

@PromptServer.instance.routes.post("/supernova/select")
async def select_node(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        selection = data.get("selection")
        SELECTION_STATE[str(node_id)] = selection
        return web.json_response({"status": "success", "selection": selection})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

# ============================================================================
# 专门用于读取本地任意路径音频的代理接口
# ============================================================================
@PromptServer.instance.routes.get("/supernova/audio_stream")
async def stream_custom_audio(request):
    audio_path = request.query.get("path", "")
    if not audio_path:
        return web.Response(status=400, text="No path provided")
        
    # 1. 尝试判断是否是绝对路径且存在 (如 D:\music\1.mp3 或 /usr/sounds/1.wav)
    if os.path.isabs(audio_path) and os.path.exists(audio_path):
        return web.FileResponse(audio_path)
        
    # 2. 尝试作为相对路径，去插件自带的 audio 目录找
    ext_audio_path = os.path.join(audio_dir, audio_path)
    if os.path.exists(ext_audio_path):
        return web.FileResponse(ext_audio_path)
        
    # 3. 尝试去 ComfyUI 根目录找
    base_path = os.path.abspath(audio_path)
    if os.path.exists(base_path):
        return web.FileResponse(base_path)
        
    # 都没找到，报错打印
    print(f"[Supernova] ⚠️ Audio file not found: {audio_path}")
    return web.Response(status=404, text="Audio file not found")

# --- 辅助类 ---
class FlexibleOptionalInputType(dict):
    def __init__(self, type_name, input_dict):
        self.type_name = type_name
        self.input_dict = input_dict
        super().__init__(input_dict)
    def __contains__(self, key): return True
    def __getitem__(self, key):
        if key not in self.input_dict: return (self.type_name,)
        return self.input_dict[key]

class AnyType(str):
    def __ne__(self, __value: object) -> bool: return False
ANY = AnyType("*")

def wait_for_decision(unique_id, seed, node_type):
    node_id = str(unique_id)
    print(f"[{node_type}] Node {node_id} Paused (Seed: {seed})...")
    SELECTION_STATE[node_id] = "waiting"
    PromptServer.instance.send_sync("supernova_pause_alert", {"node_id": node_id})
    while True:
        if SELECTION_STATE.get(node_id, "waiting") != "waiting": break
        time.sleep(0.1)
    decision = SELECTION_STATE.pop(node_id)
    print(f"[{node_type}] Node {node_id} Resumed: {decision}")
    if decision == "stop": raise Exception("Workflow stopped by user.")
    return decision

# ==============================================================================
# 1. Switcher (1->2)
# ==============================================================================
class PauseAndSelectOutput:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "input_any": (ANY,), "seed": ("INT", {"default": 0, "min": 0, "max": 999})}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = (ANY, ANY)
    RETURN_NAMES = ("Output 1", "Output 2")
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"
    def run(self, input_any, seed, unique_id):
        decision = wait_for_decision(unique_id, seed, "Switcher")
        blocker = ExecutionBlocker(None) if ExecutionBlocker else None
        if decision == "1": return (input_any, blocker)
        elif decision == "2": return (blocker, input_any)
        return (None, None)

# ==============================================================================
# 2. Selector (2->1)
# ==============================================================================
class PauseAndSelectInput:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "input_1": (ANY,), "input_2": (ANY,), "seed": ("INT", {"default": 0, "min": 0, "max": 999})}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("Selected Output",)
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"
    def run(self, input_1, input_2, seed, unique_id):
        decision = wait_for_decision(unique_id, seed, "Selector")
        if decision == "1": return (input_1,)
        elif decision == "2": return (input_2,)
        return (None,)

# ==============================================================================
# 3. Matrix (2->2)
# ==============================================================================
class PauseAndMatrix:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "input_1": (ANY,), "input_2": (ANY,), "seed": ("INT", {"default": 0, "min": 0, "max": 999})}, "hidden": {"unique_id": "UNIQUE_ID"}}
    RETURN_TYPES = (ANY, ANY)
    RETURN_NAMES = ("Output 1", "Output 2")
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"
    def run(self, input_1, input_2, seed, unique_id):
        decision = wait_for_decision(unique_id, seed, "Matrix")
        blocker = ExecutionBlocker(None) if ExecutionBlocker else None
        if decision == "1-1": return (input_1, blocker)
        elif decision == "1-2": return (blocker, input_1)
        elif decision == "2-1": return (input_2, blocker)
        elif decision == "2-2": return (blocker, input_2)
        return (None, None)

# ==============================================================================
# 4. Multi Input Selector (固定 5 In -> 1 Out)
# ==============================================================================
class MultiInputSelector:
    @classmethod
    def INPUT_TYPES(cls):
        # 固定定义5个输入
        inputs = {
            "input_1": (ANY,), "input_2": (ANY,), "input_3": (ANY,), "input_4": (ANY,), "input_5": (ANY,)
        }
        return {
            "required": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 999}),
            },
            "optional": FlexibleOptionalInputType(ANY, inputs),
            "hidden": {"unique_id": "UNIQUE_ID"},
        }
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("Selected Output",)
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"

    def run(self, seed, unique_id=None, **kwargs):
        decision = wait_for_decision(unique_id, seed, "MultiInput")
        # decision 格式: "input_1"
        return (kwargs.get(decision),)

# ==============================================================================
# 5. Multi Output Splitter (固定 1 In -> 5 Out)
# ==============================================================================
class MultiOutputSplitter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_data": (ANY,),
                "seed": ("INT", {"default": 0, "min": 0, "max": 999}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }
    # 固定5个输出
    RETURN_TYPES = (ANY,) * 5
    RETURN_NAMES = tuple(f"Output {i+1}" for i in range(5))
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"

    def run(self, input_data, seed, unique_id=None):
        decision = wait_for_decision(unique_id, seed, "MultiOutput")
        blocker = ExecutionBlocker(None) if ExecutionBlocker else None
        outputs = [blocker] * 5
        try:
            # decision 格式: "output_1"
            if decision and decision.startswith("output_"):
                idx = int(decision.split('_')[1]) - 1
                if 0 <= idx < 5: outputs[idx] = input_data
        except: pass
        return tuple(outputs)

# ==============================================================================
# 6. Play Sound Alert (节点经过时播放音效)
# ==============================================================================
class PlaySoundAlert:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "any_input": (ANY,),
                # 改为布尔开关
                "use_custom_path": ("BOOLEAN", {"default": False, "label_on": "Custom Path", "label_off": "Settings Sound"}),
                "audio_path": ("STRING", {"default": "1.mp3"}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"}
        }
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("Output",)
    FUNCTION = "run"
    CATEGORY = "🪐 Superova/Flow"

    def _clean_path(self, raw_path):
        """鲁棒性清理：去除两端引号、处理带有 path: 的字符串等"""
        if not isinstance(raw_path, str):
            return ""
        p = raw_path.strip()
        # 1. 去除包裹的引号 " 或 '
        if p.startswith('"') and p.endswith('"'): p = p[1:-1].strip()
        if p.startswith("'") and p.endswith("'"): p = p[1:-1].strip()
        
        # 2. 如果前缀是 path: (不区分大小写)
        if p.lower().startswith("path:"):
            p = p[5:].strip() # 截断前5个字符
            # 再次去引号 (防止诸如 path:"1.mp3" 的情况)
            if p.startswith('"') and p.endswith('"'): p = p[1:-1].strip()
            if p.startswith("'") and p.endswith("'"): p = p[1:-1].strip()
            
        return p

    def run(self, any_input, use_custom_path, audio_path, unique_id):
        # 提取并清理最终路径
        final_path = self._clean_path(audio_path)
        
        # 向前端发送播放指令 (支持各种原生浏览器音频扩展名: mp3, wav, ogg 等)
        PromptServer.instance.send_sync("supernova_play_sound_node", {
            "node_id": str(unique_id),
            "use_custom_path": use_custom_path,
            "audio_path": final_path
        })
        # 原样返回数据
        return (any_input,)

# --- 映射 ---
NODE_CLASS_MAPPINGS = {
    "PauseAndSelectOutput": PauseAndSelectOutput,
    "PauseAndSelectInput": PauseAndSelectInput,
    "PauseAndMatrix": PauseAndMatrix,
    "MultiInputSelector": MultiInputSelector,
    "MultiOutputSplitter": MultiOutputSplitter,
    "PlaySoundAlert": PlaySoundAlert
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PauseAndSelectOutput": "Switcher ➡️",
    "PauseAndSelectInput": "Selector ➡️",
    "PauseAndMatrix": "Matrix 🔀",
    "MultiInputSelector": "Multi Selector 🔢",
    "MultiOutputSplitter": "Multi Splitter 🔢",
    "PlaySoundAlert": "Play Sound 🎵"
}