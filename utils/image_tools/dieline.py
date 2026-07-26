from io import BytesIO

import numpy as np
from PIL import Image, ImageChops, ImageOps

from utils.image_tools.stretch import load_image


def extract_colored_dieline_mask(template_bytes, rotate_to_portrait=True):
    with Image.open(BytesIO(template_bytes)) as source:
        template = ImageOps.exif_transpose(source).convert("RGB")

    pixels = np.asarray(template)
    highest = pixels.max(axis=2).astype(np.int16)
    lowest = pixels.min(axis=2).astype(np.int16)
    selected = (highest - lowest >= 18) & (lowest < 245)
    mask = Image.fromarray((selected * 255).astype(np.uint8), mode="L")
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("没有识别到彩色刀模区域")

    mask = mask.crop(bbox)
    if rotate_to_portrait and mask.width > mask.height:
        mask = mask.transpose(Image.Transpose.ROTATE_270)
    return mask


def extract_green_dieline_mask(template_bytes, rotate_to_portrait=True):
    return extract_colored_dieline_mask(
        template_bytes,
        rotate_to_portrait,
    )


def load_dieline_mask(mask_bytes):
    with Image.open(BytesIO(mask_bytes)) as source:
        return source.convert("L")


def compose_artwork_with_dieline(
    artwork,
    mask,
    output_size,
    zoom=1.0,
    horizontal_shift=0,
    vertical_shift=0,
):
    if zoom < 1:
        raise ValueError("缩放比例不能小于 1")
    output_width, output_height = map(int, output_size)
    if output_width <= 0 or output_height <= 0:
        raise ValueError("输出尺寸必须大于 0")

    artwork = artwork.convert("RGBA")
    base_scale = max(
        output_width / artwork.width,
        output_height / artwork.height,
    )
    scale = base_scale * zoom
    scaled_size = (
        max(round(artwork.width * scale), output_width),
        max(round(artwork.height * scale), output_height),
    )
    artwork = artwork.resize(scaled_size, Image.Resampling.LANCZOS)

    overflow_x = artwork.width - output_width
    overflow_y = artwork.height - output_height
    offset_x = round(
        -overflow_x / 2 + horizontal_shift / 100 * overflow_x / 2
    )
    offset_y = round(
        -overflow_y / 2 + vertical_shift / 100 * overflow_y / 2
    )
    canvas = Image.new("RGBA", (output_width, output_height))
    canvas.paste(artwork, (offset_x, offset_y), artwork)

    fitted_mask = mask.resize(
        (output_width, output_height),
        Image.Resampling.LANCZOS,
    )
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), fitted_mask))
    return canvas


def build_dieline_preview(mask, output_size):
    fitted_mask = mask.resize(output_size, Image.Resampling.LANCZOS)
    return ImageOps.colorize(
        fitted_mask,
        black="#FFFFFF",
        white="#12A72A",
    )


def load_artwork(image_bytes):
    return load_image(image_bytes).convert("RGBA")
