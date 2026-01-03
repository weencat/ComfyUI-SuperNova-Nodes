import torch
import numpy as np
import os
from PIL import Image, ImageDraw, ImageFont, ImageColor

class ImageAddText:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "text": ("STRING", {"multiline": True, "default": "TEXT"}),
                "direction": (["top", "bottom", "left", "right"], {"default": "top"}),
                "font_path": ("STRING", {"default": "","tooltip":"If empty, the default file used is local.ttf from Fonts."}), 
                "font_size": ("INT", {"default": 50, "min": 1, "max": 2048, "step": 1}),
                "text_color": ("STRING", {"default": "#000000"}),
                "bg_color": ("STRING", {"default": "#FFFFFF"}),
                "bg_mode": (["inside", "outside"], {"default": "outside"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "add_text"
    CATEGORY = "🪐supernova/Image"

    def add_text(self, image, text, direction, font_path, font_size, text_color, bg_color, bg_mode):
        if not font_path.strip():
            current_dir = os.path.dirname(__file__)
            font_path = os.path.abspath(os.path.join(current_dir, "..", "Fonts", "local.ttf"))

        padding = int(font_size + 2)
        img_batches = []
        
        for i in range(image.shape[0]):
            img_np = (image[i].cpu().numpy() * 255).astype(np.uint8)
            pil_img = Image.fromarray(img_np)
            orig_w, orig_h = pil_img.size
            
            try:
                font = ImageFont.truetype(font_path, font_size) if os.path.exists(font_path) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            def get_color(hex_str, default):
                try: return ImageColor.getrgb(hex_str)
                except: return default
            txt_col = get_color(text_color, (0, 0, 0))
            bg_col = get_color(bg_color, (255, 255, 255))

            draw_tasks = [] # 存储 (文字内容, x_offset, y_offset)
            final_text_w = 0
            final_text_h = 0

            # ---------------------------------------------------------
            # 核心排版引擎
            # ---------------------------------------------------------
            if direction in ["top", "bottom"]:
                # --- 水平换行模式 ---
                max_w = orig_w - (padding * 2)
                lines = []
                current_line = ""
                for char in text:
                    if char == '\n':
                        lines.append(current_line)
                        current_line = ""
                        continue
                    test_line = current_line + char
                    if font.getlength(test_line) <= max_w:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = char
                lines.append(current_line)
                
                processed_text = "\n".join(lines)
                temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                bbox = temp_draw.textbbox((0, 0), processed_text, font=font, align="center")
                final_text_w, final_text_h = int(bbox[2]-bbox[0]), int(bbox[3]-bbox[1])
                draw_tasks.append((processed_text, 0, 0))
            
            else:
                # --- 垂直多列模式 ---
                max_h = orig_h - (padding * 2)
                columns = [] # 存储每一列的字符串
                current_col_chars = []
                current_col_h = 0
                
                # 过滤并处理文字
                for char in text.replace('\n', ' '):
                    bbox = font.getbbox(char)
                    char_h = (bbox[3] - bbox[1]) + (font_size // 5)
                    if current_col_h + char_h > max_h and current_col_chars:
                        columns.append("\n".join(current_col_chars))
                        current_col_chars = [char]
                        current_col_h = char_h
                    else:
                        current_col_chars.append(char)
                        current_col_h += char_h
                columns.append("\n".join(current_col_chars))
                
                # 计算每一列的宽度和总宽度
                col_widths = []
                temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                for col_txt in columns:
                    c_bbox = temp_draw.textbbox((0, 0), col_txt, font=font)
                    col_widths.append(int(c_bbox[2] - c_bbox[0]))
                
                column_gap = int(font_size // 2)
                final_text_w = sum(col_widths) + (len(columns) - 1) * column_gap
                
                # 获取文字块最大高度
                max_actual_h = 0
                curr_x = 0
                for idx, col_txt in enumerate(columns):
                    c_bbox = temp_draw.textbbox((0, 0), col_txt, font=font)
                    c_h = int(c_bbox[3] - c_bbox[1])
                    max_actual_h = max(max_actual_h, c_h)
                    # 记录每一列相对于文字块左上角的偏移
                    draw_tasks.append((col_txt, curr_x, 0))
                    curr_x += col_widths[idx] + column_gap
                final_text_h = max_actual_h

            # ---------------------------------------------------------
            # 画布与位置计算
            # ---------------------------------------------------------
            if bg_mode == "outside":
                if direction in ["top", "bottom"]:
                    new_w, new_h = orig_w, orig_h + final_text_h + (padding * 2)
                    res_img = Image.new("RGB", (int(new_w), int(new_h)), bg_col)
                    paste_pos = (0, final_text_h + padding * 2) if direction == "top" else (0, 0)
                    base_txt_x, base_txt_y = (new_w - final_text_w) // 2, (padding if direction == "top" else orig_h + padding)
                else:
                    new_w, new_h = orig_w + final_text_w + (padding * 2), orig_h
                    res_img = Image.new("RGB", (int(new_w), int(new_h)), bg_col)
                    paste_pos = (final_text_w + padding * 2, 0) if direction == "left" else (0, 0)
                    base_txt_x, base_txt_y = (padding if direction == "left" else orig_w + padding), (orig_h - final_text_h) // 2
                res_img.paste(pil_img, [int(i) for i in paste_pos])
            else:
                res_img = pil_img.copy()
                if direction == "top": base_txt_x, base_txt_y = (orig_w - final_text_w) // 2, padding
                elif direction == "bottom": base_txt_x, base_txt_y = (orig_w - final_text_w) // 2, orig_h - final_text_h - padding
                elif direction == "left": base_txt_x, base_txt_y = padding, (orig_h - final_text_h) // 2
                else: base_txt_x, base_txt_y = orig_w - final_text_w - padding, (orig_h - final_text_h) // 2

            # 绘制文字
            draw = ImageDraw.Draw(res_img)
            for content, off_x, off_y in draw_tasks:
                draw.text((int(base_txt_x + off_x), int(base_txt_y + off_y)), content, font=font, fill=txt_col, align="center", spacing=4)

            # 输出
            img_batches.append(torch.from_numpy(np.array(res_img).astype(np.float32) / 255.0).unsqueeze(0))

        return (torch.cat(img_batches, dim=0),)

NODE_CLASS_MAPPINGS = {"ImageAddText": ImageAddText}
NODE_DISPLAY_NAME_MAPPINGS = {"ImageAddText": "Image Add Text ✍️"}