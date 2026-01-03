import torch
import numpy as np
from nodes import PreviewImage

class MultiImageComparer:
    """
    A node that compares up to 4 images (1, 2, 3, 4) with click-to-slide interaction
    and dynamic resolution display.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
            },
            "hidden": {
                "prompt": "PROMPT", 
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    CATEGORY = "🪐supernova/Image"
    FUNCTION = "compare_images"

    def compare_images(self, image_1=None, image_2=None, image_3=None, image_4=None, 
                       filename_prefix="comparer", prompt=None, extra_pnginfo=None):
        
        # Simple helper to instantiate a PreviewImage class to reuse its save logic
        # We process each image individually to get the UI object
        previewer = PreviewImage()

        def get_ui_image(images, suffix):
            if images is None:
                return []
            saved = previewer.save_images(images, f"{filename_prefix}_{suffix}", prompt, extra_pnginfo)
            return saved['ui']['images']

        result = { 
            "ui": { 
                "images_1": get_ui_image(image_1, "1"),
                "images_2": get_ui_image(image_2, "2"),
                "images_3": get_ui_image(image_3, "3"),
                "images_4": get_ui_image(image_4, "4"),
            } 
        }
        return result

# Register the node
NODE_CLASS_MAPPINGS = {
    "MultiImageComparer": MultiImageComparer
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MultiImageComparer": "Mult Image Comparer 🪟"
}