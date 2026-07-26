from hashlib import sha256
from pathlib import Path

import streamlit as st

from utils.image_tools import image_to_png_bytes
from utils.image_tools.dieline import (
    DIELINE_DPI,
    build_dieline_preview,
    compose_artwork_with_dieline,
    extract_green_dieline_mask,
    load_dieline_mask,
    load_artwork,
    orient_artwork_to_output,
)
from utils.image_tools.templates import (
    get_dieline_materials,
    get_dieline_models,
    load_local_dieline_template,
)


@st.cache_data(show_spinner=False)
def _load_dieline_inputs(
    artwork_bytes,
    template_bytes,
    template_is_mask,
):
    return (
        load_artwork(artwork_bytes),
        (
            load_dieline_mask(template_bytes)
            if template_is_mask
            else extract_green_dieline_mask(template_bytes)
        ),
    )


def render_dieline_composer():
    st.caption("先选择材质和型号，再上传原图生成对应的目标文件。")
    material_options = [*get_dieline_materials(), "自定义上传"]
    material = st.selectbox("手机壳材质", material_options)
    template_is_mask = material != "自定义上传"
    model = None
    if template_is_mask:
        model = st.selectbox(
            "手机型号",
            get_dieline_models(material),
        )
    artwork_file = st.file_uploader(
        "上传原始图片",
        type=["png", "jpg", "jpeg", "webp"],
        key="dieline_artwork",
    )
    template_file = None
    if template_is_mask:
        try:
            template_bytes, _ = (
                load_local_dieline_template(material, model)
            )
        except Exception as error:
            st.error(f"内置刀模读取失败：{error}")
            return
    else:
        template_file = st.file_uploader(
            "上传彩色刀模",
            type=["tif", "tiff", "png"],
            key="dieline_template",
        )
        template_bytes = (
            template_file.getvalue() if template_file is not None else None
        )

    if artwork_file is None:
        st.info("请上传未裁切的原始图片。")
        return
    if template_bytes is None:
        st.info("请上传绿色刀模文件。")
        return

    try:
        artwork_bytes = artwork_file.getvalue()
        artwork, mask = _load_dieline_inputs(
            artwork_bytes,
            template_bytes,
            template_is_mask,
        )
    except Exception as error:
        st.error(f"刀模读取失败：{error}")
        return

    output_width, output_height = mask.size
    mask_bbox = mask.getbbox()
    if mask_bbox is None:
        st.error("刀模有效区域为空")
        return
    print_width = mask_bbox[2] - mask_bbox[0]
    print_height = mask_bbox[3] - mask_bbox[1]
    print_width_cm = print_width / DIELINE_DPI[0] * 2.54
    print_height_cm = print_height / DIELINE_DPI[1] * 2.54
    st.caption(
        f"刀模画布：{output_width} × {output_height} px"
        "（18 × 9 cm，500 DPI，尺寸固定）｜"
        f"实际印刷区域：{print_width_cm:.2f} × {print_height_cm:.2f} cm"
    )
    control_key = sha256(
        f"{material}|{model or 'custom'}".encode("utf-8")
    ).hexdigest()[:12]
    use_reference_layout = model == "iPhone 17 Pro Max"
    artwork = orient_artwork_to_output(
        artwork,
        (output_width, output_height),
    )
    zoom = st.slider(
        "图片缩放",
        min_value=1.0,
        max_value=2.5,
        value=1.0 if use_reference_layout else 1.1,
        step=0.01,
        key=f"dieline_zoom_{control_key}",
    )

    position_col1, position_col2 = st.columns(2)
    horizontal_shift = position_col1.slider(
        "主体左右位置",
        min_value=-100,
        max_value=100,
        value=0,
        help="负数向左，正数向右。",
        key=f"dieline_horizontal_{control_key}",
    )
    vertical_shift = position_col2.slider(
        "主体上下位置",
        min_value=-100,
        max_value=100,
        value=0 if use_reference_layout else 35,
        help="负数向上，正数向下；猫头被摄像头缺口切到时向下调整。",
        key=f"dieline_vertical_{control_key}",
    )

    result = compose_artwork_with_dieline(
        artwork,
        mask,
        (output_width, output_height),
        zoom,
        horizontal_shift,
        vertical_shift,
        trim_transparent_artwork=use_reference_layout,
    )
    original_col, mask_col, result_col = st.columns(3)
    with original_col:
        st.subheader("原图（摄像头朝左）")
        st.image(artwork, width="stretch")
    with mask_col:
        st.subheader("刀模识别")
        st.image(
            build_dieline_preview(
                mask, (output_width, output_height)
            ),
            width="stretch",
        )
    with result_col:
        st.subheader("主体安全预览")
        st.image(result, width="stretch")
        st.caption("确认猫头等主体没有进入顶部摄像头缺口。")

    st.download_button(
        "下载目标 PNG",
        data=image_to_png_bytes(result, dpi=DIELINE_DPI),
        file_name=(
            f"{Path(artwork_file.name).stem}_"
            f"{material}_{model or '自定义'}_套图.png"
        ),
        mime="image/png",
        width="stretch",
    )
