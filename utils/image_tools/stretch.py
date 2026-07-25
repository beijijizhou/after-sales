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


def stretch_image_middle(
    image,
    stretch_start_percent,
    stretch_end_percent,
    stretch_factor,
):
    if not 0 <= stretch_start_percent < stretch_end_percent <= 100:
        raise ValueError("中间拉伸范围必须从上到下正确排列")
    if stretch_factor < 1:
        raise ValueError("中间拉伸倍数不能小于 1")

    width, height = image.size
    start_y = min(
        max(round(height * stretch_start_percent / 100), 0),
        height - 1,
    )
    end_y = min(
        max(round(height * stretch_end_percent / 100), start_y + 1),
        height,
    )
    top = image.crop((0, 0, width, start_y))
    middle = image.crop((0, start_y, width, end_y))
    bottom = image.crop((0, end_y, width, height))
    stretched_height = max(round(middle.height * stretch_factor), 1)
    output_height = top.height + stretched_height + bottom.height
    if width * output_height > MAX_OUTPUT_PIXELS:
        raise ValueError("输出图片过大，请降低中间拉伸倍数")

    stretched_middle = middle.resize(
        (width, stretched_height),
        Image.Resampling.LANCZOS,
    )
    output = Image.new(image.mode, (width, output_height))
    if top.height:
        output.paste(top, (0, 0))
    output.paste(stretched_middle, (0, top.height))
    if bottom.height:
        output.paste(bottom, (0, top.height + stretched_height))
    return output


def build_stretch_region_preview(
    image,
    stretch_start_percent,
    stretch_end_percent,
):
    preview = image.copy()
    start_y = min(
        max(round(preview.height * stretch_start_percent / 100), 0),
        preview.height - 1,
    )
    end_y = min(
        max(round(preview.height * stretch_end_percent / 100), start_y + 1),
        preview.height - 1,
    )
    line_width = max(round(preview.width / 250), 3)
    draw = ImageDraw.Draw(preview)
    colors = (
        ((255, 61, 61, 255), (31, 191, 255, 255))
        if preview.mode == "RGBA"
        else ((255, 61, 61), (31, 191, 255))
    )
    for y, color in ((start_y, colors[0]), (end_y, colors[1])):
        draw.line(
            [(0, y), (preview.width, y)],
            fill=color,
            width=line_width,
        )
    return preview


def image_to_png_bytes(image):
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
