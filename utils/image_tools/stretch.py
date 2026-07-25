from io import BytesIO

from PIL import Image, ImageDraw, ImageOps


MAX_OUTPUT_PIXELS = 100_000_000


def load_image(image_bytes):
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source)
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        target_mode = "RGBA" if has_alpha else "RGB"
        return image.convert(target_mode)


def stretch_image_bottom(image, fixed_top_percent, stretch_factor):
    if not 0 <= fixed_top_percent < 100:
        raise ValueError("顶部保留比例必须在 0% 到 99% 之间")
    if stretch_factor < 1:
        raise ValueError("底部拉伸倍数不能小于 1")

    width, height = image.size
    split_y = min(
        max(round(height * fixed_top_percent / 100), 0),
        height - 1,
    )
    top = image.crop((0, 0, width, split_y))
    bottom = image.crop((0, split_y, width, height))
    stretched_height = max(round(bottom.height * stretch_factor), 1)
    output_height = split_y + stretched_height
    if width * output_height > MAX_OUTPUT_PIXELS:
        raise ValueError("输出图片过大，请降低底部拉伸倍数")

    stretched_bottom = bottom.resize(
        (width, stretched_height),
        Image.Resampling.LANCZOS,
    )
    output = Image.new(image.mode, (width, output_height))
    if split_y:
        output.paste(top, (0, 0))
    output.paste(stretched_bottom, (0, split_y))
    return output


def build_boundary_preview(image, fixed_top_percent):
    preview = image.copy()
    split_y = min(
        max(round(preview.height * fixed_top_percent / 100), 0),
        preview.height - 1,
    )
    line_width = max(round(preview.width / 250), 3)
    draw = ImageDraw.Draw(preview)
    draw.line(
        [(0, split_y), (preview.width, split_y)],
        fill=(255, 61, 61, 255) if preview.mode == "RGBA" else (255, 61, 61),
        width=line_width,
    )
    return preview


def image_to_png_bytes(image):
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
