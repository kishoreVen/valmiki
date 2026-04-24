
import base64
from dataclasses import dataclass
import io
from typing import List, Optional, Tuple, Union
import math
from PIL import Image


def image_to_base64_with_mime(image: Image.Image) -> Tuple[str, str]:
    """Convert PIL Image to base64 string with mime type.

    Args:
        image: PIL Image to convert

    Returns:
        Tuple of (base64 encoded string, mime type)
    """
    buffer = io.BytesIO()

    # Determine the best format to use based on the image
    # Preserve WebP format if it was WebP, otherwise use appropriate format
    format_to_use = "PNG"
    mime_type = "image/png"

    if hasattr(image, 'format') and image.format:
        if image.format.upper() == 'WEBP':
            format_to_use = "WEBP"
            mime_type = "image/webp"
        elif image.format.upper() in ['JPEG', 'JPG']:
            format_to_use = "JPEG"
            mime_type = "image/jpeg"
            # Convert RGBA to RGB for JPEG
            if image.mode == 'RGBA':
                # Create a white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3] if len(image.split()) > 3 else None)
                image = background
        elif image.format.upper() == 'PNG':
            format_to_use = "PNG"
            mime_type = "image/png"

    # Save in the determined format
    if format_to_use == "JPEG":
        image.save(buffer, format=format_to_use, quality=95)
    else:
        image.save(buffer, format=format_to_use)

    img_data = buffer.getvalue()
    base64_data = base64.b64encode(img_data).decode("utf-8")

    return base64_data, mime_type


def image_to_base64(image: Image.Image, include_data_uri_prefix: bool = False) -> str:
    """Convert PIL Image to base64 string.

    Args:
        image: PIL Image to convert
        include_data_uri_prefix: If True, prepend data URI prefix for web compatibility

    Returns:
        Base64 encoded string, optionally with data URI prefix
    """
    base64_data, mime_type = image_to_base64_with_mime(image)

    if include_data_uri_prefix:
        return f"data:{mime_type};base64,{base64_data}"
    return base64_data


def convert_query_images_to_base64_list(
    images: Union[str, Image.Image, List, dict], include_data_uri_prefix: bool = False
) -> List[str]:
    """Convert various image formats to a list of base64 strings.

    Args:
        images: Input images in various formats
        include_data_uri_prefix: If True, prepend data URI prefix for web compatibility

    Returns:
        List of base64 encoded strings
    """
    if isinstance(images, str):
        return [images]  # Assume already base64 or URL
    elif isinstance(images, Image.Image):
        return [image_to_base64(images, include_data_uri_prefix)]
    elif isinstance(images, list):
        return [
            (
                image_to_base64(img, include_data_uri_prefix)
                if isinstance(img, Image.Image)
                else img
            )
            for img in images
        ]
    elif isinstance(images, dict):
        converted_images = []

        for img in images.values():
            if isinstance(img, Image.Image):
                converted_images.append(image_to_base64(img, include_data_uri_prefix))
            elif isinstance(img, list):
                converted_images.extend(convert_query_images_to_base64_list(img))
            elif isinstance(img, str):
                converted_images.append(img)
            else:
                raise ValueError(f"Unsupported image type `{type(img)}` for conversion")

        return converted_images
    else:
        raise ValueError(f"Unsupported image format: {type(images)}")


def base64_to_image(base64_string: str) -> Image.Image:
    """Convert base64 string back to PIL Image."""
    # Remove data URL prefix if present
    if base64_string.startswith("data:"):
        base64_string = base64_string.split(",", 1)[1]

    # Decode base64 to bytes
    image_bytes = base64.b64decode(base64_string)

    # Convert bytes to PIL Image
    image_buffer = io.BytesIO(image_bytes)
    image = Image.open(image_buffer)

    return image


def detect_image_mime_type(base64_string: str) -> str:
    """Detect image MIME type from base64-encoded data using magic bytes.

    Args:
        base64_string: Base64 encoded image data (with or without data URI prefix)

    Returns:
        MIME type string (e.g., 'image/png', 'image/jpeg', 'image/webp')
    """
    # Handle data URI prefix - extract mime type directly if present
    if base64_string.startswith("data:"):
        # Format: data:image/png;base64,AAAA...
        mime_part = base64_string.split(";")[0]
        if mime_part.startswith("data:"):
            return mime_part[5:]  # Remove "data:" prefix

    # Decode first few bytes to check magic numbers
    try:
        # Only need first 12 bytes to detect format
        partial_data = base64.b64decode(base64_string[:16])
    except Exception:
        return "image/png"  # Default fallback

    # Check magic bytes
    if partial_data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif partial_data[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif partial_data[:4] == b'RIFF' and partial_data[8:12] == b'WEBP':
        return "image/webp"
    elif partial_data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    else:
        return "image/png"  # Default fallback


def save_image_to_temp(image: Image.Image, prefix: str = "demo_image") -> str:
    """Save PIL Image to temporary file and return the path."""
    import tempfile
    import os

    # Create temp file with .png extension
    fd, temp_path = tempfile.mkstemp(suffix=".png", prefix=f"{prefix}_")
    os.close(fd)  # Close the file descriptor, we just need the path

    # Save image
    image.save(temp_path, "PNG")

    return temp_path


def audio_to_base64(audio_data: bytes) -> str:
    """Convert audio bytes to base64 string."""
    return base64.b64encode(audio_data).decode("utf-8")


def base64_to_audio(base64_string: str) -> bytes:
    """Convert base64 string back to audio bytes."""
    # Remove data URL prefix if present
    if base64_string.startswith("data:"):
        base64_string = base64_string.split(",", 1)[1]

    # Decode base64 to bytes
    audio_bytes = base64.b64decode(base64_string)

    return audio_bytes


def save_audio_to_temp(
    audio_data: bytes, format: str = "mp3", prefix: str = "demo_audio"
) -> str:
    """Save audio bytes to temporary file and return the path."""
    import tempfile
    import os

    # Determine file extension from format
    # Format might be like "mp3_44100_128" so extract just the codec
    if "_" in format:
        extension = format.split("_")[0]
    else:
        extension = format

    # Create temp file with appropriate extension
    fd, temp_path = tempfile.mkstemp(suffix=f".{extension}", prefix=f"{prefix}_")

    # Write audio data to file
    try:
        os.write(fd, audio_data)
    finally:
        os.close(fd)

    return temp_path


def save_video_to_temp(
    video_data: bytes, format: str = "mp4", prefix: str = "demo_video"
) -> str:
    """Save video bytes to temporary file and return the path."""
    import tempfile
    import os

    fd, temp_path = tempfile.mkstemp(suffix=f".{format}", prefix=f"{prefix}_")
    try:
        os.write(fd, video_data)
    finally:
        os.close(fd)

    return temp_path


@dataclass
class OutpaintingExtent:
    """Represents the extent of outpainting with support for sizes > 2048."""

    # Extents in working space (for model generation)
    top: int
    bottom: int
    left: int
    right: int

    # Original and target dimensions
    original_size: Tuple[int, int]
    target_size: Tuple[int, int]

    # Working dimensions (constrained to model limits)
    working_input_size: Tuple[int, int]
    scaled_output_size: Tuple[int, int]

    # Scaling factors for pre/post processing
    pre_scale: float  # Scale factor to apply before generation
    post_scale: float  # Scale factor to apply after generation

    @classmethod
    def from_image_sizes(
        cls,
        image_size: Tuple[int, int],
        target_image_size: Tuple[int, int],
        image_position: Optional[Tuple[int, int]] = None,
        max_dimension: int = 2048,
        divisibility: int = 64,
    ) -> "OutpaintingExtent":
        """
        Calculate extent of outpainting from image sizes, with automatic scaling
        for sizes beyond model limits.

        Args:
            image_size: input image resolution (width, height)
            target_image_size: desired output size (width, height) - can be > 2048
            image_position: where on the canvas the original image is positioned (x, y),
                           image is centered if left None
            max_dimension: maximum dimension supported by model (default: 2048)
            divisibility: required divisibility for dimensions (default: 64)

        Returns:
            OutpaintingExtent with automatic scaling for large images
        """
        orig_width, orig_height = image_size
        target_width, target_height = target_image_size

        # Calculate scale factor needed to fit within constraints
        scale_factor = 1.0
        if target_width > max_dimension or target_height > max_dimension:
            scale_factor = min(
                max_dimension / target_width, max_dimension / target_height
            )

        # Calculate working dimensions (scaled down if needed)
        working_target_width = int(target_width * scale_factor)
        working_target_height = int(target_height * scale_factor)

        # Round working dimensions to nearest divisibility
        working_target_width = cls._round_to_divisible(
            working_target_width, divisibility
        )
        working_target_height = cls._round_to_divisible(
            working_target_height, divisibility
        )

        # Scale the input image size proportionally
        working_input_width = int(orig_width * scale_factor)
        working_input_height = int(orig_height * scale_factor)

        # Calculate position in working space
        if image_position is None:
            # Center the image
            working_position = None
        else:
            x, y = image_position
            working_position = (int(x * scale_factor), int(y * scale_factor))

        # Calculate extents in working space
        extents = cls._calculate_extents(
            (working_input_width, working_input_height),
            (working_target_width, working_target_height),
            working_position,
            divisibility,
        )

        return cls(
            top=extents["top"],
            bottom=extents["bottom"],
            left=extents["left"],
            right=extents["right"],
            original_size=image_size,
            target_size=target_image_size,
            working_input_size=(working_input_width, working_input_height),
            scaled_output_size=(working_target_width, working_target_height),
            pre_scale=scale_factor,
            post_scale=1.0 / scale_factor if scale_factor > 0 else 1.0,
        )

    @staticmethod
    def _round_to_divisible(value: int, divisibility: int) -> int:
        """Round value to nearest multiple of divisibility."""
        return round(value / divisibility) * divisibility

    @staticmethod
    def _calculate_extents(
        image_size: Tuple[int, int],
        target_size: Tuple[int, int],
        image_position: Optional[Tuple[int, int]],
        divisibility: int,
    ) -> dict:
        """Calculate the actual extent values ensuring divisibility."""
        width, height = image_size
        target_width, target_height = target_size

        # Calculate total padding needed
        total_pad_x = max(0, target_width - width)
        total_pad_y = max(0, target_height - height)

        if image_position is None:
            # Center the image
            left = total_pad_x // 2
            right = total_pad_x - left
            top = total_pad_y // 2
            bottom = total_pad_y - top
        else:
            # Position image at specified location
            x, y = image_position

            # Clamp position to non-negative values first
            # This ensures the image is always within or at the edge of the canvas
            clamped_x = max(0, x)
            clamped_y = max(0, y)

            # Calculate padding based on clamped position
            left = clamped_x
            top = clamped_y
            right = max(0, target_width - width - clamped_x)
            bottom = max(0, target_height - height - clamped_y)

        # Round each extent up to nearest multiple of divisibility
        # This ensures we always generate enough pixels to fulfill the request
        left = math.ceil(left / divisibility) * divisibility
        right = math.ceil(right / divisibility) * divisibility
        top = math.ceil(top / divisibility) * divisibility
        bottom = math.ceil(bottom / divisibility) * divisibility

        return {"top": top, "bottom": bottom, "left": left, "right": right}

    @property
    def needs_preprocessing(self) -> bool:
        """Check if preprocessing (downscaling) is needed."""
        return self.pre_scale < 1.0

    @property
    def needs_postprocessing(self) -> bool:
        """Check if postprocessing (upscaling) is needed."""
        return self.post_scale > 1.0
