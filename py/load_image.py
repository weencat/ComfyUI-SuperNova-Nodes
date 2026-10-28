# 导入os模块，用于处理文件和目录路径
import os
import shutil
import time
import hashlib
import numpy as np
from aiohttp import web

# 导入Pillow库
from PIL import Image, ImageOps, ImageSequence
from PIL.PngImagePlugin import PngInfo

# 导入PyTorch
import torch

# 导入ComfyUI核心模块
import folder_paths
from server import PromptServer

# ============================================================================
# 全局常量与各目录专用扫描函数
# ============================================================================

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.tif'}

def get_input_images_with_subfolders():
    """
    【专为 LoadImageUnified 设计】
    仅扫描 input 目录及其所有多级子文件夹。
    【核心修复】：
    1. 彻底过滤所有以 clipspace 开头或包含 painted-masked 的遮罩临时文件，防止污染列表。
    2. 按最新修改时间排序。
    """
    input_dir = folder_paths.get_input_directory()
    if not input_dir or not os.path.isdir(input_dir):
        return []
    
    exclude_folders = {"clipspace"}
    records = []
    for root, dirs, files in os.walk(input_dir, followlinks=True):
        dirs[:] = [d for d in dirs if d not in exclude_folders]
        for file in files:
            # 彻底屏蔽遮罩编辑器产生的临时涂抹草稿与隐藏文件
            if file.startswith("clipspace") or "painted-masked" in file or file.startswith("."):
                continue

            if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, input_dir).replace("\\", "/")
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = 0
                records.append((mtime, rel_path))
                
    records.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in records]


def get_all_temp_images():
    """
    【专为 LoadImageFromTemp 设计】
    仅扫描 temp 临时缓存目录及子文件夹。
    """
    temp_dir = folder_paths.get_temp_directory()
    if not temp_dir or not os.path.isdir(temp_dir):
        return []
    
    records = []
    for root, _, files in os.walk(temp_dir, followlinks=True):
        for file in files:
            if file.startswith("."):
                continue
            if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, temp_dir).replace("\\", "/")
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = 0
                records.append((mtime, f"{rel_path} [temp]"))
                
    records.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in records]


# ============================================================================
# 后台 404 智能预览图救援中间件 (确保所有子目录缩略图正常显示)
# ============================================================================
@web.middleware
async def comfy_image_fallback_middleware(request, handler):
    try:
        response = await handler(request)
    except Exception:
        response = None

    if (response is None or response.status in (404, 400)) and request.path in ("/view", "/api/view"):
        filename = request.rel_url.query.get("filename", "")
        if filename:
            clean_name = filename
            for tag in [" [output]", " [input]", " [temp]"]:
                if clean_name.endswith(tag):
                    clean_name = clean_name[:-len(tag)]
                    break
            
            base_filename = os.path.basename(clean_name.replace("\\", "/"))
            found_path = None

            for base_dir in [folder_paths.get_input_directory(), 
                             folder_paths.get_output_directory(), 
                             folder_paths.get_temp_directory()]:
                if not base_dir or not os.path.exists(base_dir):
                    continue
                direct = os.path.join(base_dir, clean_name.replace("/", os.sep))
                if os.path.isfile(direct):
                    found_path = direct
                    break
                for root, _, files in os.walk(base_dir):
                    if base_filename in files:
                        found_path = os.path.join(root, base_filename)
                        break
                if found_path:
                    break

            if found_path and os.path.isfile(found_path):
                return web.FileResponse(found_path)

    return response

try:
    PromptServer.instance.app.middlewares.append(comfy_image_fallback_middleware)
except Exception:
    pass

# ============================================================================
# API 定义
# ============================================================================

@PromptServer.instance.routes.get("/mape/get_input_image_files")
async def get_input_image_files(request):
    return web.json_response(get_input_images_with_subfolders())

@PromptServer.instance.routes.get("/mape/get_temp_image_files")
async def get_temp_image_files(request):
    return web.json_response(get_all_temp_images())

@PromptServer.instance.routes.get("/mape/get_all_image_files")
async def get_all_image_files(request):
    return web.json_response(get_input_images_with_subfolders())

@PromptServer.instance.routes.get("/mape/preview_absolute_path")
async def preview_absolute_path(request):
    path = request.rel_url.query.get("path", "")
    if not path: return web.json_response({"error": "No path"}, status=400)
    
    path = path.strip().strip('"').strip("'")
    if path.startswith("clipspace/"):
        clipspace_dir = os.path.join(folder_paths.get_input_directory(), "clipspace")
        filename = path.split("/")[-1]
        clip_path = os.path.join(clipspace_dir, filename)
        if os.path.exists(clip_path):
             return web.json_response({"filename": filename, "type": "clipspace", "subfolder": ""})

    if not os.path.exists(path): return web.json_response({"error": "Not found"}, status=404)

    filename = os.path.basename(path)
    file_hash = hashlib.md5(path.encode()).hexdigest()[:8]
    temp_filename = f"preview_{file_hash}_{filename}"
    temp_dir = folder_paths.get_temp_directory()
    temp_path = os.path.join(temp_dir, temp_filename)

    if not os.path.exists(temp_path):
        try:
            os.link(path, temp_path)
        except:
            try:
                shutil.copy(path, temp_path)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

    return web.json_response({"filename": temp_filename, "type": "temp"})

# ============================================================================
# 节点 1: LoadImageFromReload (reload文件夹内图片读取器)
# ============================================================================
class LoadImageFromReload:
    @classmethod
    def INPUT_TYPES(s):
        reload_path = "reload" 
        input_dir = folder_paths.get_input_directory()
        image_dir = os.path.join(input_dir, reload_path)

        if not os.path.exists(image_dir):
            file_list = []
        else:
            files_in_dir = os.listdir(image_dir)
            file_list = []
            for file in files_in_dir:
                if os.path.isfile(os.path.join(image_dir, file)):
                    file_path = os.path.join(reload_path, file).replace("\\", "/")
                    file_list.append(file_path)
        
        return {"required":
                    {"image": (sorted(file_list),
                               {"image_upload": True}
                               )},
                }
    
    CATEGORY = "🪐 Superova/ImageLoader"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def load_image(self, image):
        image_path = folder_paths.get_annotated_filepath(image)
        i = Image.open(image_path)
        i = ImageOps.exif_transpose(i)
        image = i.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        
        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
        
        return (image, mask.unsqueeze(0))

    @classmethod
    def IS_CHANGED(s, image):
        image_path = folder_paths.get_annotated_filepath(image)
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(s, image):
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid image file: {}".format(image)
        return True

# ============================================================================
# 节点 2: LoadImageWithSubfolders (读取输入图片包括子文件夹)
# ============================================================================
class LoadImageWithSubfolders:
    SUPPORTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']

    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        file_list = []

        for dirpath, dirnames, filenames in os.walk(input_dir, followlinks=True):
            for filename in filenames:
                if any(filename.lower().endswith(ext) for ext in s.SUPPORTED_EXTENSIONS):
                    relative_subdir = os.path.relpath(dirpath, input_dir)
                    if relative_subdir == ".":
                        file_path = filename
                    else:
                        file_path = os.path.join(relative_subdir, filename)
                    file_path = file_path.replace("\\", "/")
                    file_list.append(file_path)
        
        if not file_list:
            file_list.append("No images found in input folder or its subfolders")
            
        return {
            "required": {
                "image": (sorted(file_list), {"image_upload": True})
            }
        }

    CATEGORY = "🪐 Superova/ImageLoader"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def load_image(self, image):
        image_path = folder_paths.get_annotated_filepath(image)
        i = Image.open(image_path)
        i = ImageOps.exif_transpose(i)
        image = i.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]

        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")

        return (image, mask.unsqueeze(0))

    @classmethod
    def IS_CHANGED(s, image):
        image_path = folder_paths.get_annotated_filepath(image)
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(s, image):
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid image file: {}".format(image)
        return True

# ============================================================================
# 节点 3: LoadImageUnified (锁定用户选择，杜绝乱跳)
# ============================================================================
class LoadImageUnified:
    @classmethod
    def INPUT_TYPES(cls):
        files = get_input_images_with_subfolders()
        if not files:
            files = ["none"]
        return {
            "required": {
                "image": (files, {
                    "image_upload": True,
                    "remote": {
                        "route": "/mape/get_input_image_files",
                        "refresh_button": True,
                        # 【核心修复】：改为 "keep"，刷新时严格保持当前选中项，绝不擅自跳到第一张新图
                        "control_after_refresh": "keep",
                    }
                }),
            }
        }

    CATEGORY = "🪐 Superova/ImageLoader"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def get_full_path(self, annotated_path):
        if not annotated_path or annotated_path == "none":
            return None
            
        annotated_path = annotated_path.strip().strip('"').strip("'")
        
        # 1. 优先调用原生解析
        try:
            resolved = folder_paths.get_annotated_filepath(annotated_path)
            if resolved and os.path.exists(resolved):
                return resolved
        except Exception:
            pass

        # 2. 遮罩编辑器 clipspace 解析
        if "clipspace" in annotated_path:
            clean_name = annotated_path
            for tag in [" [output]", " [input]"]:
                if clean_name.endswith(tag):
                    clean_name = clean_name[:-len(tag)]
            if clean_name.startswith("clipspace/"):
                clean_name = clean_name.split("clipspace/", 1)[1]
            clip_path = os.path.join(folder_paths.get_input_directory(), "clipspace", clean_name)
            if os.path.exists(clip_path):
                return clip_path

        # 3. 递归兜底匹配
        clean_file = annotated_path
        target_dir = folder_paths.get_input_directory()
        if clean_file.endswith(" [output]"):
            clean_file = clean_file[:-9]
            target_dir = folder_paths.get_output_directory()

        direct_cand = os.path.join(target_dir, clean_file.replace("/", os.sep))
        if os.path.exists(direct_cand):
            return direct_cand

        filename_only = os.path.basename(clean_file)
        if target_dir and os.path.exists(target_dir):
            for r, _, fs in os.walk(target_dir):
                if filename_only in fs:
                    return os.path.join(r, filename_only)

        return None

    def load_image(self, image):
        image_path = self.get_full_path(image)
        if not image_path or not os.path.exists(image_path):
            raise FileNotFoundError(f"LoadImageUnified 图像文件未找到: {image}")

        img = Image.open(image_path)
        output_images = []
        output_masks = []
        w, h = None, None
        excluded_formats = ['MPO']

        for i in ImageSequence.Iterator(img):
            i = ImageOps.exif_transpose(i)
            if i.mode == 'I':
                i = i.point(lambda val: val * (1 / 255))
            image_rgb = i.convert("RGB")

            if len(output_images) == 0:
                w, h = image_rgb.size[0], image_rgb.size[1]
            if image_rgb.size[0] != w or image_rgb.size[1] != h:
                continue

            image_tensor = np.array(image_rgb).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_tensor)[None,]

            if 'A' in i.getbands():
                mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1.0 - torch.from_numpy(mask)
            else:
                mask = torch.zeros((image_tensor.shape[1], image_tensor.shape[2]), dtype=torch.float32, device="cpu")

            output_images.append(image_tensor)
            output_masks.append(mask.unsqueeze(0))

        if len(output_images) > 1 and img.format not in excluded_formats:
            return (torch.cat(output_images, dim=0), torch.cat(output_masks, dim=0))
        else:
            return (output_images[0], output_masks[0])

    @classmethod
    def IS_CHANGED(cls, image):
        instance = cls()
        image_path = instance.get_full_path(image)
        if not image_path or not os.path.exists(image_path): 
            return time.time() 
        m = hashlib.sha256()
        with open(image_path, 'rb') as f: 
            m.update(f.read())
        return m.digest().hex()
    
    @classmethod
    def VALIDATE_INPUTS(cls, image):
        return True

# ============================================================================
# 节点 4: LoadImageFromTemp (独立纯净 Temp 节点 + 保持选中)
# ============================================================================
class LoadImageFromTemp:
    @classmethod
    def INPUT_TYPES(cls):
        files = get_all_temp_images()
        if not files:
            files = ["none"]
        return {
            "required": {
                "image": (files, {
                    "remote": {
                        "route": "/mape/get_temp_image_files",
                        "refresh_button": True,
                        # 同样设为 "keep"，手动刷新时如果有选中的图依然保留
                        "control_after_refresh": "keep",
                    },
                }),
            }
        }

    CATEGORY = "🪐 Superova/ImageLoader"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def get_full_path(self, annotated_path):
        if not annotated_path or annotated_path == "none":
            return None
        
        annotated_path = annotated_path.strip().strip('"').strip("'")
        
        if "clipspace" in annotated_path:
            clean_name = annotated_path
            for tag in [" [temp]", " [output]", " [input]"]:
                if clean_name.endswith(tag):
                    clean_name = clean_name[:-len(tag)]
            if clean_name.startswith("clipspace/"):
                clean_name = clean_name.split("clipspace/", 1)[1]
            clip_path = os.path.join(folder_paths.get_input_directory(), "clipspace", clean_name)
            if os.path.exists(clip_path):
                return clip_path

        try:
            resolved = folder_paths.get_annotated_filepath(annotated_path)
            if resolved and os.path.exists(resolved):
                return resolved
        except Exception:
            pass

        temp_dir = folder_paths.get_temp_directory()
        clean_file = annotated_path
        if clean_file.endswith(" [temp]"):
            clean_file = clean_file[:-7]

        direct = os.path.join(temp_dir, clean_file.replace("/", os.sep))
        if os.path.exists(direct):
            return direct

        filename_only = os.path.basename(clean_file)
        if temp_dir and os.path.exists(temp_dir):
            for r, _, fs in os.walk(temp_dir):
                if filename_only in fs:
                    return os.path.join(r, filename_only)
        return None

    def load_image(self, image):
        image_path = self.get_full_path(image)
        if not image_path or not os.path.exists(image_path):
            raise FileNotFoundError(f"LoadImageFromTemp 缓存文件未找到: {image}")

        img = Image.open(image_path)
        output_images = []
        output_masks = []
        w, h = None, None
        excluded_formats = ['MPO']

        for i in ImageSequence.Iterator(img):
            i = ImageOps.exif_transpose(i)
            if i.mode == 'I':
                i = i.point(lambda val: val * (1 / 255))
            image_rgb = i.convert("RGB")

            if len(output_images) == 0:
                w, h = image_rgb.size[0], image_rgb.size[1]
            if image_rgb.size[0] != w or image_rgb.size[1] != h:
                continue

            image_tensor = np.array(image_rgb).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_tensor)[None,]

            if 'A' in i.getbands():
                mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1.0 - torch.from_numpy(mask)
            else:
                mask = torch.zeros((image_tensor.shape[1], image_tensor.shape[2]), dtype=torch.float32, device="cpu")

            output_images.append(image_tensor)
            output_masks.append(mask.unsqueeze(0))

        if len(output_images) > 1 and img.format not in excluded_formats:
            return (torch.cat(output_images, dim=0), torch.cat(output_masks, dim=0))
        else:
            return (output_images[0], output_masks[0])

    @classmethod
    def IS_CHANGED(cls, image):
        instance = cls()
        image_path = instance.get_full_path(image)
        if not image_path or not os.path.exists(image_path): 
            return time.time() 
        m = hashlib.sha256()
        with open(image_path, 'rb') as f: 
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        return True

# ============================================================================
# 节点 5: load_image_by_path
# ============================================================================
class load_image_by_path:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "img_path": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "load_all"
    CATEGORY = "🪐 Superova/ImageLoader"

    def load_all(self, img_path):
        if img_path is None: img_path = ""
        if not isinstance(img_path, str): img_path = str(img_path)
        img_path = img_path.strip().strip('"').strip("'")

        if img_path.startswith("clipspace/"):
            clean_filename = img_path.split("/")[-1]
            clip_path = os.path.join(folder_paths.get_input_directory(), "clipspace", clean_filename)
            if os.path.exists(clip_path):
                img_path = clip_path

        elif img_path and not os.path.exists(img_path):
            if img_path.startswith("temp/"):
                filename = img_path.split("/")[-1]
                temp_dir = folder_paths.get_temp_directory()
                temp_path = os.path.join(temp_dir, filename)
                if os.path.exists(temp_path):
                    img_path = temp_path

        output_images = []
        output_masks = []
        w, h = None, None

        def process_pil_image(img):
            nonlocal w, h
            if img.format == 'MPO': return 

            for i in ImageSequence.Iterator(img):
                i = ImageOps.exif_transpose(i)
                if i.mode == 'I':
                    i = i.point(lambda i: i * (1 / 255))
                image = i.convert("RGB")

                if len(output_images) == 0:
                    w = image.size[0]
                    h = image.size[1]
                
                if image.size[0] != w or image.size[1] != h:
                    continue

                image = np.array(image).astype(np.float32) / 255.0
                image = torch.from_numpy(image)[None,]

                if 'A' in i.getbands():
                    mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                    mask = 1. - torch.from_numpy(mask)
                elif i.mode == 'P' and 'transparency' in i.info:
                    try:
                        mask = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
                        mask = 1. - torch.from_numpy(mask)
                    except:
                        mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
                else:
                    mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")

                output_images.append(image)
                output_masks.append(mask.unsqueeze(0))

        if img_path and os.path.exists(img_path):
            if os.path.isdir(img_path):
                for filename in sorted(os.listdir(img_path)):
                    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp")):
                        try:
                            full_path = os.path.join(img_path, filename)
                            img = Image.open(full_path)
                            process_pil_image(img)
                        except: pass
            else:
                try:
                    img = Image.open(img_path)
                    process_pil_image(img)
                except Exception as e:
                    print(f"Failed to load: {img_path}, {e}")

        if not output_images:
            return (torch.zeros((1, 64, 64, 3), dtype=torch.float32), torch.zeros((1, 64, 64), dtype=torch.float32))

        if len(output_images) > 1:
            return (torch.cat(output_images, dim=0), torch.cat(output_masks, dim=0))
        else:
            return (output_images[0], output_masks[0])

# ============================================================================
# 节点 6: LoadAllImagesFromPathAsList
# ============================================================================
class LoadAllImagesFromPathAsList:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "directory_path": ("STRING", {"default": "C:/path/to/your/images", "multiline": False}),
            },
            "optional": {
                "image_load_cap": ("INT", {"default": 0, "min": 0, "max": 10000, "step": 1}),
                "recursive": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "INT")
    RETURN_NAMES = ("images (List)", "masks (List)", "count")
    OUTPUT_IS_LIST = (True, True, False)
    
    FUNCTION = "load_images"
    CATEGORY = "🪐 Superova/ImageLoader"

    def load_images(self, directory_path, image_load_cap=0, recursive=False):
        directory_path = directory_path.strip().strip('"').strip("'")
        empty_img = [torch.zeros((1, 64, 64, 3), dtype=torch.float32)]
        empty_mask = [torch.zeros((1, 64, 64), dtype=torch.float32)]

        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            return (empty_img, empty_mask, 0)

        image_files = []
        if recursive:
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                        image_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(directory_path):
                if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                    file_path = os.path.join(directory_path, file)
                    if os.path.isfile(file_path):
                        image_files.append(file_path)
        
        image_files.sort()
        if not image_files:
            return (empty_img, empty_mask, 0)

        output_images = []
        output_masks = []
        loaded_count = 0

        for full_path in image_files:
            if image_load_cap > 0 and loaded_count >= image_load_cap:
                break
            try:
                i = Image.open(full_path)
                i = ImageOps.exif_transpose(i)
                if i.mode == 'I':
                    i = i.point(lambda p: p * (1 / 255))
                image = i.convert("RGB")
                image_np = np.array(image).astype(np.float32) / 255.0
                image_tensor = torch.from_numpy(image_np)[None,]

                if 'A' in i.getbands():
                    mask_np = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                    mask_tensor = 1. - torch.from_numpy(mask_np)
                else:
                    mask_tensor = torch.zeros((image.size[1], image.size[0]), dtype=torch.float32, device="cpu")

                output_images.append(image_tensor)
                output_masks.append(mask_tensor.unsqueeze(0))
                loaded_count += 1
            except Exception as e:
                print(f"Failed to load image {full_path}: {e}")

        if not output_images:
            return (empty_img, empty_mask, 0)

        return (output_images, output_masks, loaded_count)

    @classmethod
    def IS_CHANGED(s, directory_path, image_load_cap, recursive):
        directory_path = directory_path.strip().strip('"').strip("'")
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            return os.path.getmtime(directory_path)
        return float("NaN")

# ============================================================================
# 节点映射注册
# ============================================================================
NODE_CLASS_MAPPINGS = {
    "LoadImageFromReload": LoadImageFromReload,
    "LoadImageWithSubfolders": LoadImageWithSubfolders,
    "LoadImageUnified": LoadImageUnified,
    "LoadImageFromTemp": LoadImageFromTemp,
    "load_image_by_path": load_image_by_path,
    "LoadAllImagesFromPathAsList": LoadAllImagesFromPathAsList,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageFromReload": "Load Image From Reload Folder 🗃️",
    "LoadImageWithSubfolders": "Load Image (Subfolders) 📂",
    "LoadImageUnified": "Load Image (image_folder) 🗄️",
    "LoadImageFromTemp": "Load Image From Temp ⏳",
    "load_image_by_path": "load image by path 🔗📁",
    "LoadAllImagesFromPathAsList": "Load All Images From Path 📜",
}