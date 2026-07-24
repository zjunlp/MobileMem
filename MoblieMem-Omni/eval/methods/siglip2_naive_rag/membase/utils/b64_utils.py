import os
import base64
from importlib import import_module

try:
    Image = import_module("PIL.Image")
    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

def get_image_mime_type(file_path: str) -> str:
    """根据文件扩展名返回 MIME 类型。"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.png', '.apng']:
        return "image/png"
    elif ext in ['.jpg', '.jpeg', '.jpe', '.jfif']:
        return "image/jpeg"
    elif ext in ['.gif']:
        return "image/gif"
    elif ext in ['.bmp', '.dib']:
        return "image/bmp"
    elif ext in ['.tiff', '.tif']:
        return "image/tiff"
    elif ext in ['.webp']:
        return "image/webp"
    else:
        return "image/jpeg"

def convert_image_to_base64(file_path: str, target_size: tuple[int, int] | None = None) -> str:
    """读取本地图片文件，可选调整大小，转换为 base64 data URI。

    Args:
        file_path: 图片文件路径
        target_size: 目标尺寸 (宽，高)，为 None 时不缩放，保持原图大小

    Returns:
        base64 data URI 字符串，或空字符串
    """
    if not HAS_PIL:
        print("警告：Pillow 库未安装，无法转换图片为 base64")
        return ""
    file_path = file_path.replace("data/image", "/home/xueyida/lxj/SimpleMem/data/image")
    try:
        img = Image.open(file_path)
        
        # ====================== 关键修改 ======================
        # 只有传入 target_size 才执行 resize
        if target_size is not None:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        # ======================================================

        if img.mode != 'RGB':
            img = img.convert('RGB')

        from io import BytesIO
        buffered = BytesIO()

        mime_type = get_image_mime_type(file_path)
        if mime_type == "image/png":
            img.save(buffered, format="PNG")
        else:
            img.save(buffered, format="JPEG")

        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        data_uri = f"data:{mime_type};base64,{img_base64}"

        return data_uri

    except Exception as e:
        print(f"图片转换失败 {file_path}: {e}")
        return ""