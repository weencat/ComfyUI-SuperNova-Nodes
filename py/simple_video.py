import os
import folder_paths
import numpy as np
import torch
import imageio
from PIL import Image
from datetime import datetime
import hashlib
import shutil
from server import PromptServer
from aiohttp import web
import torchaudio

# ========================================================
# API: 统一预览接口
# ========================================================
@PromptServer.instance.routes.get("/simple_video/fetch_preview")
async def fetch_video_preview(request):
    # 1. 获取基础参数
    video_path = request.rel_url.query.get("path", "")
    frame_index = int(request.rel_url.query.get("index", -1))
    
    # 2. 获取处理参数 (用于 index=0 的情况)
    skip = int(request.rel_url.query.get("skip", 0))
    nth = int(request.rel_url.query.get("nth", 1))
    cap = int(request.rel_url.query.get("cap", 0))

    if not video_path: return web.json_response({"error": "No path"}, status=400)
    video_path = video_path.strip().strip('"').strip("'")
    if not os.path.exists(video_path): return web.json_response({"error": "Not found"}, status=404)

    # ------------------------------------------------
    # 模式 A: 原始视频预览 (Index = -1)
    # ------------------------------------------------
    if frame_index == -1:
        filename = os.path.basename(video_path)
        file_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
        temp_filename = f"preview_original_{file_hash}_{filename}"
        
        temp_dir = folder_paths.get_temp_directory()
        temp_path = os.path.join(temp_dir, temp_filename)

        if not os.path.exists(temp_path):
            try: os.link(video_path, temp_path)
            except:
                try: shutil.copy(video_path, temp_path)
                except: pass
        
        return web.json_response({"filename": temp_filename, "type": "temp", "format": "video"})

    # ------------------------------------------------
    # 模式 B: 处理后的视频预览 (Index = 0)
    # ------------------------------------------------
    elif frame_index == 0:
        # 生成唯一的哈希，包含所有参数，确保参数变了预览也会变
        param_str = f"{video_path}_{skip}_{nth}_{cap}"
        file_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        temp_filename = f"preview_processed_{file_hash}.mp4"
        
        temp_dir = folder_paths.get_temp_directory()
        temp_path = os.path.join(temp_dir, temp_filename)

        # 如果缓存存在，直接返回
        if os.path.exists(temp_path):
             return web.json_response({"filename": temp_filename, "type": "temp", "format": "video"})

        # 生成处理后的视频
        try:
            reader = imageio.get_reader(video_path)
            meta = reader.get_meta_data()
            fps = meta.get('fps', 24)
            
            frames_to_save = []
            count = 0
            for i, frame in enumerate(reader):
                if i < skip: continue
                if (i - skip) % nth != 0: continue
                frames_to_save.append(frame)
                count += 1
                if cap > 0 and count >= cap: break
            reader.close()

            if len(frames_to_save) == 0:
                return web.json_response({"error": "No frames found with current settings"}, status=400)

            # 保存为临时 MP4 (快速编码)
            imageio.mimsave(temp_path, frames_to_save, fps=fps, format="mp4", codec="libx264", quality=5)
            
            return web.json_response({"filename": temp_filename, "type": "temp", "format": "video"})
        except Exception as e:
             return web.json_response({"error": str(e)}, status=500)

    # ------------------------------------------------
    # 模式 C: 单帧预览 (Index > 0)
    # ------------------------------------------------
    else:
        # 用户输入 1 代表第 0 帧，输入 2 代表第 1 帧
        real_index = frame_index - 1
        
        file_hash = hashlib.md5(f"{video_path}_{real_index}".encode()).hexdigest()[:8]
        temp_filename = f"preview_frame_{file_hash}_{real_index}.png"
        temp_dir = folder_paths.get_temp_directory()
        temp_path = os.path.join(temp_dir, temp_filename)

        if os.path.exists(temp_path):
            return web.json_response({"filename": temp_filename, "type": "temp", "format": "image"})

        try:
            reader = imageio.get_reader(video_path)
            total = reader.count_frames()
            if total == 0: total = 999999
            
            target = min(real_index, total - 1)
            target = max(0, target)
            
            frame = reader.get_data(target)
            reader.close()
            
            imageio.imwrite(temp_path, frame)
            return web.json_response({"filename": temp_filename, "type": "temp", "format": "image"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


# ========================================================
# 节点 1: SimpleVideoSaver
# ========================================================
class SimpleVideoSaver:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE", ),
                "frame_rate": ("INT", {"default": 24, "min": 1, "max": 120, "step": 1}),
                "filename_prefix": ("STRING", {"default": "Video_{date}", "tooltip": "可用占位符：\n- {date}: 年-月-日\n- {time}: 时-分-秒"}),
                "format": ([
                    "video/h264-mp4", "video/h265-mp4", "video/webm", "video/avl-webm", 
                    "video/ProRes", "video/mkv", "image/apng", "image/gif", 
                    "image/webp", "video/16bit-png", "video/8bit-png", 
                    "video/nvenc_h264-mp4", "video/nvenc_hevc-mp4", "video/nvenc_av1-mp4",  
                ], {"default": "video/h264-mp4"}),
                "quality": (["high", "medium", "low"], {"default": "high"}),
            },
            "optional": {
                "audio": ("AUDIO", ),
                "sound_file": ("STRING", {"default": "sound.mp3", "tooltip": "ComfyUI/input/下的音频文件"}),
                "volume": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "save_video"
    OUTPUT_NODE = True
    CATEGORY = "🪐supernova/video"

    def save_video(self, image, frame_rate, filename_prefix, format, quality, audio=None, sound_file="sound.mp3", volume=1.0):
        now = datetime.now()
        filename_prefix = filename_prefix.replace("{date}", now.strftime("%Y-%m-%d"))
        filename_prefix = filename_prefix.replace("{time}", now.strftime("%H-%M-%S"))
        filename_prefix = filename_prefix.replace("{datetime}", now.strftime("%Y-%m-%d_%H-%M-%S"))

        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, image[0].shape[1], image[0].shape[0]
        )

        image_np = (255. * image.cpu().numpy()).astype(np.uint8)
        results = []
        audio_path_arg = None
        temp_audio_file = None
        
        if audio is not None:
            try:
                waveform = audio.get("waveform")
                sample_rate = audio.get("sample_rate")
                if waveform is not None:
                    temp_audio_file = os.path.join(folder_paths.get_temp_directory(), f"temp_audio_{counter}.wav")
                    if waveform.dim() == 3: waveform = waveform[0]
                    torchaudio.save(temp_audio_file, waveform, sample_rate)
                    audio_path_arg = temp_audio_file
            except: pass

        browser_friendly = False
        if "h264" in format or "webm" in format or "gif" in format or format == "image/webp" or format == "image/apng":
            browser_friendly = True
        
        is_image_sequence = format.startswith("image/") and format not in ["image/gif", "image/webp", "image/apng"]

        if is_image_sequence:
            ext = format.split("/")[-1]
            for i, img_np in enumerate(image_np):
                file_name = f"{filename}_{counter:05}_{i:04}.{ext}"
                full_path = os.path.join(full_output_folder, file_name)
                Image.fromarray(img_np).save(full_path, quality=95)
                results.append({"filename": file_name, "subfolder": subfolder, "type": self.type, "format": "image"})
            browser_friendly = True
        else:
            writer_kwargs = {}
            ext = "mp4"
            if "gif" in format: ext = "gif"; writer_kwargs["duration"] = 1000 / frame_rate; writer_kwargs["loop"] = 0
            elif "webp" in format: ext = "webp"; writer_kwargs["duration"] = 1000 / frame_rate; writer_kwargs["loop"] = 0
            elif "apng" in format: ext = "png"; writer_kwargs["duration"] = 1000 / frame_rate; writer_kwargs["loop"] = 0
            elif "webm" in format: ext = "webm"; writer_kwargs["codec"] = "libvpx-vp9"
            elif "mkv" in format: ext = "mkv"; writer_kwargs["codec"] = "ffv1"
            elif "ProRes" in format: ext = "mov"; writer_kwargs["codec"] = "prores_ks"; writer_kwargs["pixelformat"] = "yuv422p10le"
            elif "png" in format: ext = "mov"; writer_kwargs["codec"] = "png"
            elif "mp4" in format:
                ext = "mp4"; writer_kwargs["pixelformat"] = "yuv420p"
                if "h265" in format: writer_kwargs["codec"] = "libx265"
                elif "nvenc_h264" in format: writer_kwargs["codec"] = "h264_nvenc"
                elif "nvenc_hevc" in format: writer_kwargs["codec"] = "hevc_nvenc"
                elif "nvenc_av1" in format: writer_kwargs["codec"] = "av1_nvenc"
                else: writer_kwargs["codec"] = "libx264"

            if format not in ["image/gif", "image/webp", "image/apng"]:
                writer_kwargs["fps"] = frame_rate
                if audio_path_arg: writer_kwargs["audio"] = audio_path_arg

            if "libx" in writer_kwargs.get("codec", ""):
                crf = 19 if quality == "high" else 23 if quality == "medium" else 28
                writer_kwargs["ffmpeg_params"] = ["-crf", str(crf)]
            elif "nvenc" in writer_kwargs.get("codec", ""):
                writer_kwargs["ffmpeg_params"] = ["-rc", "vbr", "-cq", "19" if quality=="high" else "23"]

            file_name = f"{filename}_{counter:05}_{subfolder}" if subfolder else f"{filename}_{counter:05}"
            full_path = os.path.join(full_output_folder, file_name + f".{ext}")

            try:
                imageio.mimsave(full_path, image_np, format=ext, **writer_kwargs)
            except Exception as e:
                print(f"Save Error: {e}, fallback to cpu h264")
                if "audio" in writer_kwargs: del writer_kwargs["audio"]
                imageio.mimsave(full_path, image_np, format="mp4", fps=frame_rate)
                browser_friendly = True

            result_format_type = "video"
            if format in ["image/gif", "image/webp", "image/apng"]:
                result_format_type = "image"
            results.append({"filename": file_name + f".{ext}", "subfolder": subfolder, "type": self.type, "format": result_format_type})

        ui_results = results

        if not browser_friendly:
            try:
                preview_filename = f"preview_{filename}_{counter:05}.mp4"
                preview_path = os.path.join(folder_paths.get_temp_directory(), preview_filename)
                preview_kwargs = { "fps": frame_rate, "codec": "libx264", "pixelformat": "yuv420p", "ffmpeg_params": ["-preset", "ultrafast", "-crf", "26"] }
                if audio_path_arg: preview_kwargs["audio"] = audio_path_arg
                imageio.mimsave(preview_path, image_np, format="mp4", **preview_kwargs)
                ui_results = [{"filename": preview_filename, "type": "temp", "subfolder": "", "format": "video"}]
            except: pass

        if temp_audio_file and os.path.exists(temp_audio_file):
            try: os.remove(temp_audio_file)
            except: pass

        if sound_file and sound_file.strip() != "":
            PromptServer.instance.send_sync("play_sound_on_save", {"sound_file": sound_file, "volume": volume})

        return {"ui": {"video_preview": ui_results}, "result": ()}


# ========================================================
# 节点 2: SimpleLoadVideoPath (同步更新逻辑)
# ========================================================
class SimpleLoadVideoPath:
    def __init__(self): pass
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "X:/path/to/video.mp4", "multiline": False}),
                "frame_load_cap": ("INT", {"default": 0, "min": 0, "max": 10000, "step": 1}),
                "skip_first_frames": ("INT", {"default": 0, "min": 0, "step": 1}),
                "select_every_nth": ("INT", {"default": 1, "min": 1, "step": 1}),
                "select_frame_index": ("INT", {"default": -1, "min": -1, "max": 999999, "step": 1, "tooltip": "-1: 原始视频\n 0: 应用cap/skip/nth后的预览视频\n >0: 提取第n张图(1为第1帧)"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "INT", "INT", "AUDIO")
    RETURN_NAMES = ("image", "frame_count", "fps", "width", "height", "audio")
    FUNCTION = "load_video"
    CATEGORY = "🪐supernova/video"

    def load_video(self, video_path, frame_load_cap, skip_first_frames, select_every_nth, select_frame_index):
        video_path = video_path.strip('"')
        if not os.path.exists(video_path): raise FileNotFoundError(f"Video not found: {video_path}")

        reader = imageio.get_reader(video_path)
        meta = reader.get_meta_data()
        fps = meta.get('fps', 24)
        
        try: total_frames = reader.count_frames()
        except: total_frames = meta.get('nframes', 999999)

        # ==========================
        # 模式 A: 单帧提取 (>0)
        # ==========================
        if select_frame_index > 0:
            target_index = select_frame_index - 1 # 转换为 0-based 索引
            
            if total_frames > 0 and target_index >= total_frames:
                target_index = total_frames - 1

            try: frame = reader.get_data(target_index)
            except Exception as e:
                reader.close()
                raise RuntimeError(f"Error reading frame {target_index}: {e}")
            
            reader.close()

            frame_norm = frame.astype(np.float32) / 255.0
            video_tensor = torch.from_numpy(frame_norm).unsqueeze(0)
            
            # 预览图
            filename = os.path.basename(video_path)
            file_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
            preview_filename = f"preview_frame_{target_index}_{file_hash}.png"
            temp_dir = folder_paths.get_temp_directory()
            preview_path = os.path.join(temp_dir, preview_filename)
            imageio.imwrite(preview_path, frame)

            return {
                "ui": {"video_preview": [{"filename": preview_filename, "type": "temp", "format": "image"}]}, 
                "result": (video_tensor, 1, int(fps), video_tensor.shape[2], video_tensor.shape[1], None)
            }

        # ==========================
        # 模式 B: 视频加载 (<=0)
        # ==========================
        else:
            # 如果 index == -1，返回原始视频链接
            # 如果 index == 0，返回处理后的视频 (逻辑相同，只是预览不同，输出是一样的)
            
            frames = []
            count = 0
            try:
                for i, f in enumerate(reader):
                    if i < skip_first_frames: continue
                    if (i - skip_first_frames) % select_every_nth != 0: continue
                    frames.append(f.astype(np.float32) / 255.0)
                    count += 1
                    if frame_load_cap > 0 and count >= frame_load_cap: break
            finally:
                reader.close()
            
            if not frames: raise ValueError("No frames loaded")
            video_tensor = torch.from_numpy(np.array(frames))
            
            audio_output = None
            try:
                waveform, sample_rate = torchaudio.load(video_path)
                audio_output = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
            except: pass

            # 生成预览信息
            filename = os.path.basename(video_path)
            file_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
            
            if select_frame_index == 0:
                # 生成处理后的预览视频
                param_str = f"{video_path}_{skip_first_frames}_{select_every_nth}_{frame_load_cap}"
                mod_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
                temp_filename = f"preview_processed_{mod_hash}.mp4"
                temp_dir = folder_paths.get_temp_directory()
                temp_path = os.path.join(temp_dir, temp_filename)
                
                if not os.path.exists(temp_path):
                     frames_uint8 = (video_tensor.numpy() * 255).astype(np.uint8)
                     imageio.mimsave(temp_path, frames_uint8, fps=fps, format="mp4", codec="libx264", pixelformat="yuv420p", quality=5)
            else:
                # 原始视频链接 (-1)
                temp_filename = f"preview_original_{file_hash}_{filename}"
                temp_dir = folder_paths.get_temp_directory()
                temp_path = os.path.join(temp_dir, temp_filename)
                if not os.path.exists(temp_path):
                    try: os.link(video_path, temp_path)
                    except:
                         try: shutil.copy(video_path, temp_path)
                         except: pass

            return {
                "ui": {"video_preview": [{"filename": temp_filename, "type": "temp", "format": "video"}]}, 
                "result": (video_tensor, count, int(fps), video_tensor.shape[2], video_tensor.shape[1], audio_output)
            }

NODE_CLASS_MAPPINGS = { 
    "SimpleVideoCombine": SimpleVideoSaver, 
    "SimpleLoadVideoPath": SimpleLoadVideoPath 
}
NODE_DISPLAY_NAME_MAPPINGS = { 
    "SimpleVideoCombine": "Simple Video Saver 🔊🎞️", 
    "SimpleLoadVideoPath": "Simple Video Loader (with path) 🔗📼" 
}