import time
import os
import nodes
from aiohttp import web
from server import PromptServer

# 全局状态
PAUSE_STATE = {}

# --- 1. 核心修复：正确挂载同级 audio 目录 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
audio_path = os.path.join(root_dir, "audio")

if os.path.exists(audio_path):
    has_route = False
    for route in PromptServer.instance.app.router.routes():
        if route.resource and route.resource.canonical == "/supernova/audio":
            has_route = True
            break
    
    if not has_route:
        PromptServer.instance.app.add_routes([
            web.static("/supernova/audio", audio_path)
        ])
    print(f"[Supernova] Audio mounted from: {audio_path}")
else:
    pass # 这里的 print 如果找不到可以忽略，避免刷屏

# --- API ---
@PromptServer.instance.routes.post("/supernova/preview_control")
async def preview_control(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        action = data.get("action")
        PAUSE_STATE[str(node_id)] = action
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

class PreviewAndPause:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": { "images": ("IMAGE",), },
            "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "🪐supernova/Image"
    OUTPUT_NODE = True
    
    def run(self, images, unique_id, prompt=None, extra_pnginfo=None):
        node_id = str(unique_id)
        
        # 调用原生预览保存图片
        previewer = nodes.PreviewImage()
        result = previewer.save_images(images, filename_prefix="Pause_Preview", prompt=prompt, extra_pnginfo=extra_pnginfo)
        ui_images = result['ui']['images']

        print(f"[PreviewPause] Pause at node {node_id}")
        
        # 重置状态为等待
        PAUSE_STATE[node_id] = "waiting"
        
        # 发送前端消息
        PromptServer.instance.send_sync("supernova_preview_data", {
            "node_id": node_id,
            "images": ui_images
        })

        # 阻塞循环
        while True:
            status = PAUSE_STATE.get(node_id, "waiting")
            if status == "continue": 
                break
            elif status == "stop": 
                PAUSE_STATE.pop(node_id, None)
                raise Exception("Workflow stopped by user.")
            time.sleep(0.1)
        
        # 清理状态
        PAUSE_STATE.pop(node_id, None)
        return {"ui": {"images": ui_images}, "result": (images,)}

NODE_CLASS_MAPPINGS = { "PreviewAndPause": PreviewAndPause }
NODE_DISPLAY_NAME_MAPPINGS = { "PreviewAndPause": "Preview & Pause ⏯️" }