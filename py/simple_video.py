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
import scipy.io.wavfile
import re
import urllib.parse
from pathlib import Path

# 尝试安全导入第三方音频后端
try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import av
except ImportError:
    av = None


# ========================================================
# 辅助函数: 鲁棒性路径清洗与音频解码
# ========================================================
def sanitize_and_resolve_path(path_str: str) -> Path:
    if not path_str or not path_str.strip():
        raise ValueError("【LoadAudioFromPath】音频路径不能为空！")

    p = path_str.strip()

    if p.lower().startswith("file:///"):
        p = p[8:]
        p = urllib.parse.unquote(p)
        if re.match(r"^/[a-zA-Z]:", p):
            p = p[1:]
    elif p.lower().startswith("file://"):
        p = p[7:]
        p = urllib.parse.unquote(p)

    quote_chars = {'"', "'", "“", "”", "‘", "’", "`"}
    while len(p) >= 2 and (p[0] in quote_chars or p[-1] in quote_chars):
        if p[0] in quote_chars:
            p = p[1:]
        if p and p[-1] in quote_chars:
            p = p[:-1]
        p = p.strip()

    p = os.path.expanduser(p)
    p = os.path.expandvars(p)

    return Path(p).resolve()


def robust_read_audio(file_path: Path):
    path_str = str(file_path)

    if sf is not None:
        try:
            data, sample_rate = sf.read(path_str, dtype="float32")
            tensor = torch.from_numpy(data)
            if tensor.ndim == 1:
                waveform = tensor.unsqueeze(0)
            else:
                waveform = tensor.t()
            return waveform, sample_rate
        except Exception:
            pass

    if av is not None:
        try:
            with av.open(path_str) as container:
                stream = container.streams.audio[0]
                sample_rate = stream.rate
                frames = []
                for frame in container.decode(stream):
                    frames.append(frame.to_ndarray())
                if frames:
                    audio_data = np.concatenate(frames, axis=1)
                    waveform = torch.from_numpy(audio_data).to(torch.float32)
                    return waveform, sample_rate
        except Exception:
            pass

    try:
        waveform, sample_rate = torchaudio.load(path_str, backend="soundfile")
        return waveform, sample_rate
    except Exception:
        pass

    try:
        return torchaudio.load(path_str)
    except Exception:
        with open(file_path, "rb") as f:
            return torchaudio.load(f)


# ========================================================
# API: 统一视频预览接口
# ========================================================
@PromptServer.instance.routes.get("/simple_video/fetch_preview")
async def fetch_video_preview(request):
    video_path = request.rel_url.query.get("path", "")
    frame_index = int(request.rel_url.query.get("index", -1))
    
    skip = int(request.rel_url.query.get("skip", 0))
    nth = int(request.rel_url.query.get("nth", 1))
    cap = int(request.rel_url.query.get("cap", 0))

    if not video_path: return web.json_response({"error": "No path"}, status=400)
    video_path = video_path.strip().strip('"').strip("'")
    if not os.path.exists(video_path): return web.json_response({"error": "Not found"}, status=404)

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

    elif frame_index == 0:
        param_str = f"{video_path}_{skip}_{nth}_{cap}"
        file_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        temp_filename = f"preview_processed_{file_hash}.mp4"
        
        temp_dir = folder_paths.get_temp_directory()
        temp_path = os.path.join(temp_dir, temp_filename)

        if os.path.exists(temp_path):
             return web.json_response({"filename": temp_filename, "type": "temp", "format": "video"})

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

            imageio.mimsave(temp_path, frames_to_save, fps=fps, format="mp4", codec="libx264", quality=5)
            return web.json_response({"filename": temp_filename, "type": "temp", "format": "video"})
        except Exception as e:
             return web.json_response({"error": str(e)}, status=500)

    else:
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
# API: 音频实时输入预览接口（仅保留单份定义，严禁重复）
# ========================================================
@PromptServer.instance.routes.get("/simple_video/fetch_audio_preview")
async def fetch_audio_preview(request):
    audio_path = request.rel_url.query.get("path", "")
    if not audio_path:
        return web.json_response({"error": "No path"}, status=400)
    
    try:
        resolved_path = sanitize_and_resolve_path(audio_path)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

    if not resolved_path.exists() or not resolved_path.is_file():
        return web.json_response({"error": "File not found"}, status=404)

    path_str = str(resolved_path)
    try:
        temp_dir = folder_paths.get_temp_directory()
        mtime = os.path.getmtime(path_str)
        hash_str = hashlib.md5(f"{path_str}_{mtime}".encode()).hexdigest()[:10]
        preview_filename = f"audio_preview_{hash_str}.wav"
        preview_path = os.path.join(temp_dir, preview_filename)

        if not os.path.exists(preview_path):
            waveform, sample_rate = robust_read_audio(resolved_path)
            preview_np = waveform[0].detach().cpu().numpy()
            if preview_np.ndim == 2:
                preview_np = preview_np.T
            scipy.io.wavfile.write(preview_path, int(sample_rate), preview_np)

        return web.json_response({"filename": preview_filename, "type": "temp"})
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
                "frame_rate": ("FLOAT", {"default": 24, "min": 1, "max": 120, "step": 1}),
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
    CATEGORY = "🪐 Superova/video"

    def save_video(self, image, frame_rate, filename_prefix, format, quality, audio=None, sound_file="sound.mp3", volume=1.0):
        now = datetime.now()
        filename_prefix = filename_prefix.replace("{date}", now.strftime("%Y-%m-%d"))
        filename_prefix = filename_prefix.replace("{time}", now.strftime("%H-%M-%S"))
        filename_prefix = filename_prefix.replace("{datetime}", now.strftime("%Y-%m-%d_%H-%M-%S"))

        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix, self.output_dir, image[0].shape[1], image[0].shape[0]
        )

        if not os.path.exists(full_output_folder):
            try:
                os.makedirs(full_output_folder, exist_ok=True)
            except Exception as e:
                print(f"[SimpleVideoSaver] Failed to create directory {full_output_folder}: {e}")

        image_np = (255. * image.cpu().numpy()).astype(np.uint8)
        results = []
        audio_path_arg = None
        temp_audio_file = None
        
        if audio is not None:
            try:
                waveform = audio.get("waveform")
                sample_rate = audio.get("sample_rate")
                if waveform is not None:
                    temp_audio_file = os.path.join(folder_paths.get_temp_directory(), f"temp_audio_{filename}_{counter}.wav")
                    if waveform.dim() == 3: waveform = waveform[0]
                    audio_data = waveform.detach().cpu().numpy()
                    if audio_data.ndim == 2:
                        audio_data = audio_data.T
                    scipy.io.wavfile.write(temp_audio_file, int(sample_rate), audio_data)
                    audio_path_arg = temp_audio_file
            except Exception as e:
                print(f"[SimpleVideoSaver] Audio processing error: {e}")

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
                writer_kwargs["macro_block_size"] = 1 
                if audio_path_arg: 
                    writer_kwargs["audio_path"] = audio_path_arg
                    writer_kwargs["audio_codec"] = "aac" 

            if "libx" in writer_kwargs.get("codec", ""):
                crf = 19 if quality == "high" else 23 if quality == "medium" else 28
                writer_kwargs["ffmpeg_params"] = ["-crf", str(crf)]
            elif "nvenc" in writer_kwargs.get("codec", ""):
                writer_kwargs["ffmpeg_params"] = ["-rc", "vbr", "-cq", "19" if quality=="high" else "23"]

            file_name = f"{filename}_{counter:05}"
            full_path = os.path.join(full_output_folder, file_name + f".{ext}")

            try:
                imageio.mimsave(full_path, image_np, format=ext, **writer_kwargs)
            except Exception as e:
                print(f"[SimpleVideoSaver] Save Error: {e}, fallback to cpu h264")
                if "audio" in writer_kwargs: del writer_kwargs["audio"]
                writer_kwargs.pop("codec", None)
                writer_kwargs.pop("ffmpeg_params", None)
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
# 节点 2: SimpleLoadVideoPath
# ========================================================
class SimpleLoadVideoPath:
    def __init__(self): pass
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "X:/path/to/video.mp4", "multiline": False}),
                "frame_load_cap": ("FLOAT", {"default": 0, "min": 0, "max": 10000, "step": 1}),
                "skip_first_frames": ("FLOAT", {"default": 0, "min": 0, "step": 1}),
                "select_every_nth": ("INT", {"default": 1, "min": 1, "step": 1}),
                "select_frame_index": ("INT", {"default": -1, "min": -1, "max": 999999, "step": 1, "tooltip": "-1: 原始视频\n 0: 应用cap/skip/nth后的预览视频\n >0: 提取第n张图(1为第1帧)"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "FLOAT", "FLOAT", "INT", "INT", "AUDIO")
    RETURN_NAMES = ("image", "frame_count", "fps", "width", "height", "audio")
    FUNCTION = "load_video"
    CATEGORY = "🪐 Superova/video"

    def load_video(self, video_path, frame_load_cap, skip_first_frames, select_every_nth, select_frame_index):
        video_path = video_path.strip('"')
        if not os.path.exists(video_path): raise FileNotFoundError(f"Video not found: {video_path}")

        reader = imageio.get_reader(video_path)
        meta = reader.get_meta_data()
        fps = meta.get('fps', 24)
        
        try: total_frames = reader.count_frames()
        except: total_frames = meta.get('nframes', 999999)

        if select_frame_index > 0:
            target_index = select_frame_index - 1
            if total_frames > 0 and target_index >= total_frames:
                target_index = total_frames - 1

            try: frame = reader.get_data(target_index)
            except Exception as e:
                reader.close()
                raise RuntimeError(f"Error reading frame {target_index}: {e}")
            
            reader.close()

            frame_norm = frame.astype(np.float32) / 255.0
            video_tensor = torch.from_numpy(frame_norm).unsqueeze(0)
            
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

        else:
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

            filename = os.path.basename(video_path)
            file_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
            
            if select_frame_index == 0:
                param_str = f"{video_path}_{skip_first_frames}_{select_every_nth}_{frame_load_cap}"
                mod_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
                temp_filename = f"preview_processed_{mod_hash}.mp4"
                temp_dir = folder_paths.get_temp_directory()
                temp_path = os.path.join(temp_dir, temp_filename)
                
                if not os.path.exists(temp_path):
                     frames_uint8 = (video_tensor.numpy() * 255).astype(np.uint8)
                     imageio.mimsave(temp_path, frames_uint8, fps=fps, format="mp4", codec="libx264", pixelformat="yuv420p", quality=5)
            else:
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


# ========================================================
# 节点 3: LoadAudioFromPath
# ========================================================
class LoadAudioFromPath:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "audio_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "粘贴音频文件绝对路径或相对路径（支持带引号、空格、中文）",
                    },
                ),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "cleaned_path")
    FUNCTION = "load_audio"
    CATEGORY = "🪐 Superova/video"
    OUTPUT_NODE = True

    def load_audio(self, audio_path: str):
        resolved_path = sanitize_and_resolve_path(audio_path)
        path_str = str(resolved_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"【LoadAudioFromPath】未找到文件，请检查路径：\n{path_str}")

        if not resolved_path.is_file():
            raise IsADirectoryError(f"【LoadAudioFromPath】指定的路径是一个目录：\n{path_str}")

        try:
            waveform, sample_rate = robust_read_audio(resolved_path)
        except Exception as e:
            raise RuntimeError(
                f"【LoadAudioFromPath】无法解码音频文件：{path_str}\n"
                f"错误详情: {str(e)}"
            )

        if waveform.ndim == 2:
            waveform = waveform.unsqueeze(0)
        elif waveform.ndim == 1:
            waveform = waveform.unsqueeze(0).unsqueeze(0)

        waveform = waveform.to(torch.float32)

        audio_dict = {
            "waveform": waveform,
            "sample_rate": int(sample_rate),
        }

        temp_dir = folder_paths.get_temp_directory()
        mtime = os.path.getmtime(path_str)
        hash_str = hashlib.md5(f"{path_str}_{mtime}".encode()).hexdigest()[:10]
        preview_filename = f"audio_preview_{hash_str}.wav"
        preview_path = os.path.join(temp_dir, preview_filename)

        if not os.path.exists(preview_path):
            try:
                preview_np = waveform[0].detach().cpu().numpy()
                if preview_np.ndim == 2:
                    preview_np = preview_np.T
                scipy.io.wavfile.write(preview_path, int(sample_rate), preview_np)
            except Exception as e:
                print(f"[LoadAudioFromPath] 生成试听临时文件失败: {e}")

        return {
            "ui": {
                "audio": [
                    {
                        "filename": preview_filename,
                        "subfolder": "",
                        "type": "temp"
                    }
                ]
            },
            "result": (audio_dict, path_str)
        }


NODE_CLASS_MAPPINGS = { 
    "SimpleVideoCombine": SimpleVideoSaver, 
    "SimpleLoadVideoPath": SimpleLoadVideoPath, 
    "LoadAudioFromPath": LoadAudioFromPath
}
NODE_DISPLAY_NAME_MAPPINGS = { 
    "SimpleVideoCombine": "Simple Video Saver 🔊🎞️", 
    "SimpleLoadVideoPath": "Simple Video Loader (with path) 🔗📼",
    "LoadAudioFromPath": "Load Audio (with Path) 🎧" 
}