
import base64
import io
from PIL import Image


def compress_for_reference(
    images: list,
    max_px: int = 1024,
    jpeg_quality: int = 85,
) -> list[str]:
    """Downscale and JPEG-compress PIL images for WebSocket-friendly payloads.

    Returns data-URI base64 strings. Strings are passed through unchanged.
    """
    result = []
    for img in images:
        if isinstance(img, Image.Image):
            w, h = img.size
            if max(w, h) > max_px:
                scale = max_px / max(w, h)
                img = img.resize(
                    (int(w * scale), int(h * scale)), Image.LANCZOS
                )
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=jpeg_quality)
            b64 = base64.b64encode(buf.getvalue()).decode()
            result.append(f"data:image/jpeg;base64,{b64}")
        elif isinstance(img, str):
            result.append(img)
    return result
