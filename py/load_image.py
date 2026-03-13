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
# 全局常量
# ============================================================================

# 定义支持的图像文件扩展名 (用于 API 和 LoadImageUnified)
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.tif'}

# ============================================================================
# API 定义
# ============================================================================

# API 1: 获取所有图片列表 (LoadImageUnified 用)
@PromptServer.instance.routes.get("/mape/get_all_image_files")
async def get_all_image_files(request):
    search_locations = {
        "output": folder_paths.get_output_directory(),
        "temp": folder_paths.get_temp_directory(),
        "input": folder_paths.get_input_directory(),
    }
    exclude_folders = {}
    
    files_with_meta = []
    for dir_type, base_path in search_locations.items():
        if not os.path.isdir(base_path): continue
        
        for root, dirs, files in os.walk(base_path, followlinks=True):
            dirs[:] = [d for d in dirs if d not in exclude_folders]
            for file in files:
                if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, start=base_path)
                    annotated_filename = f"{dir_type}/{relative_path.replace('\\', '/')}"
                    files_with_meta.append({
                        'filename': annotated_filename,
                        'mtime': os.path.getmtime(full_path)
                    })
    
    files_with_meta.sort(key=lambda x: x['mtime'], reverse=True)
    sorted_file_list = [item['filename'] for item in files_with_meta]
    return web.json_response(sorted_file_list)

# API 2: 绝对路径图片预览接口 (load_image_by_path 用)
@PromptServer.instance.routes.get("/mape/preview_absolute_path")
async def preview_absolute_path(request):
    path = request.rel_url.query.get("path", "")
    if not path: return web.json_response({"error": "No path"}, status=400)
    
    path = path.strip().strip('"').strip("'")
    
    # 如果已经是 clipspace 路径，尝试解析真实路径
    if path.startswith("clipspace/"):
        clipspace_dir = os.path.join(folder_paths.get_input_directory(), "clipspace")
        filename = path.split("/")[-1]
        # 检查 clipspace 文件是否存在
        clip_path = os.path.join(clipspace_dir, filename)
        if os.path.exists(clip_path):
             # 如果是 clipspace 文件，我们不需要复制，直接返回让前端通过 view API 读取
             return web.json_response({"filename": filename, "type": "clipspace", "subfolder": ""})

    if not os.path.exists(path): return web.json_response({"error": "Not found"}, status=404)

    # 创建临时预览文件
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
        # 1. 在这里设置你想要读取的文件夹名称
        reload_path = "reload" 

        # 获取 ComfyUI 的主 `input` 文件夹路径
        input_dir = folder_paths.get_input_directory()
        # 拼接成你指定的文件夹的完整路径
        image_dir = os.path.join(input_dir, reload_path)

        # 检查指定的文件夹是否存在，如果不存在则返回空列表以防出错
        if not os.path.exists(image_dir):
            print(f"Warning: The specified folder '{reload_path}' does not exist in the input directory.",
                  f"警告：指定的文件夹“{reload_path}”在输入目录中不存在。")
            file_list = []
        else:
            # 只列出指定文件夹下的所有文件
            files_in_dir = os.listdir(image_dir)
            file_list = []
            for file in files_in_dir:
                # 确保我们只添加文件，而不是子文件夹
                if os.path.isfile(os.path.join(image_dir, file)):
                    # 构建相对于 `input` 目录的路径
                    file_path = os.path.join(reload_path, file).replace("\\", "/")
                    file_list.append(file_path)
        
        return {"required":
                    {"image": (sorted(file_list),
                               {"image_upload": True,}
                               )},
                }
    
    CATEGORY = "🪐supernova/ImageLoader"
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
            mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
        
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
# 节点 2: LoadImageWithSubfolders (读取输出图片包括子文件夹)
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

    CATEGORY = "🪐supernova/ImageLoader"
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
# 节点 3: LoadImageUnified (读取全图片:output,input,temp)
# ============================================================================
class LoadImageUnified:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("COMBO", {
                    "image_upload": True, 
                    "remote": {
                        "route": "/mape/get_all_image_files",
                        "refresh_button": True, 
                        "control_after_refresh": "first", 
                    },
                }),
            }
        }

    CATEGORY = "🪐supernova/ImageLoader"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def get_full_path(self, annotated_path):
        try:
            if "/" in annotated_path:
                dir_type, subpath = annotated_path.split('/', 1)
            else:
                dir_type = "input"
                subpath = annotated_path
        except ValueError:
            dir_type, subpath = 'input', annotated_path

        base_path = folder_paths.get_input_directory()
        
        if dir_type == 'output': 
            base_path = folder_paths.get_output_directory()
        elif dir_type == 'temp': 
            base_path = folder_paths.get_temp_directory()
        elif dir_type == 'clipspace':
            # 【核心修复】支持 clipspace 目录
            base_path = os.path.join(folder_paths.get_input_directory(), "clipspace")
        
        return os.path.join(base_path, subpath)

    def load_image(self, image):
        image_path = self.get_full_path(image)
        
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"文件未找到: {image_path}")

        i = Image.open(image_path)
        i = ImageOps.exif_transpose(i)
        image_tensor = i.convert("RGB")
        image_tensor = np.array(image_tensor).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_tensor)[None,]
        
        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(mask)
        else:
            mask = torch.zeros((image_tensor.shape[1], image_tensor.shape[2]), dtype=torch.float32, device="cpu")
            
        return (image_tensor, mask.unsqueeze(0))

    @classmethod
    def IS_CHANGED(cls, image):
        instance = cls()
        image_path = instance.get_full_path(image)
        if not os.path.exists(image_path): return time.time() 
        m = hashlib.sha256()
        with open(image_path, 'rb') as f: m.update(f.read())
        return m.digest().hex()
    
    @classmethod
    def VALIDATE_INPUTS(cls, image):
        # 强制返回 True，允许加载不在列表中的路径（尤其是临时文件）
        return True

# ============================================================================
# 节点 4: load_image_by_path (改为支持 temp 路径)
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
    CATEGORY = "🪐supernova/ImageLoader"

    def load_all(self, img_path):
        # 1. 基础清理
        if img_path is None: img_path = ""
        if not isinstance(img_path, str): img_path = str(img_path)
        img_path = img_path.strip().strip('"').strip("'")

        # 2. 路径解析逻辑 (支持 temp/ 前缀)
        # 如果路径不存在，且以 temp/ 开头，说明是遮罩编辑器生成的临时文件
        if img_path and not os.path.exists(img_path):
            if img_path.startswith("temp/"):
                # 提取文件名 (例如 temp/mask.png -> mask.png)
                filename = img_path.split("/")[-1]
                # 获取 ComfyUI 真实的 temp 目录路径
                temp_dir = folder_paths.get_temp_directory()
                temp_path = os.path.join(temp_dir, filename)
                
                # 如果文件存在，就使用这个绝对路径
                if os.path.exists(temp_path):
                    img_path = temp_path

        # 3. 初始化输出
        output_images = []
        output_masks = []
        w, h = None, None

        # 4. 图像处理内部函数
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

                # Mask 处理
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

        # 5. 执行加载
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

        # 6. 返回结果
        if not output_images:
            return (torch.zeros((1, 64, 64, 3), dtype=torch.float32), torch.zeros((1, 64, 64), dtype=torch.float32))

        if len(output_images) > 1:
            return (torch.cat(output_images, dim=0), torch.cat(output_masks, dim=0))
        else:
            return (output_images[0], output_masks[0])

# ============================================================================
# 节点映射注册
# ============================================================================
NODE_CLASS_MAPPINGS = {
    "LoadImageFromReload": LoadImageFromReload,
    "LoadImageWithSubfolders": LoadImageWithSubfolders,
    "LoadImageUnified": LoadImageUnified,
    "load_image_by_path": load_image_by_path,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageFromReload": "Load Image From Reload Folder 🗃️",
    "LoadImageWithSubfolders": "Load Image (Subfolders) 📂",
    "LoadImageUnified": "Load Image (image_folder) 🗄️",
    "load_image_by_path": "load image by path 🔗📁",
}