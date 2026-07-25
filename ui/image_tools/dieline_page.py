from hashlib import sha256
from pathlib import Path

import streamlit as st

from utils.image_tools import image_to_png_bytes
from utils.image_tools.dieline import (
    build_dieline_preview,
    compose_artwork_with_dieline,
    extract_green_dieline_mask,
    load_artwork,
)


@st.cache_data(show_spinner=False)
def _load_dieline_inputs(artwork_bytes, template_bytes):
    return (
        load_artwork(artwork_bytes),
        extract_green_dieline_mask(template_bytes),
    )


def render_dieline_composer():
    st.caption("绿色区域会作为可打印范围，白色区域自动变为透明。")
    artwork_col, template_col = st.columns(2)
    artwork_file = artwork_col.file_uploader(
        "上传原始图片",
        type=["png", "jpg", "jpeg", "webp"],
        key="dieline_artwork",
    )
    template_file = template_col.file_uploader(
        "上传刀模",
        type=["tif", "tiff", "png"],
        key="dieline_template",
    )
    if artwork_file is None or template_file is None:
        st.info("请同时上传未裁切的原始图片和绿色刀模文件。")
        return

    try:
        artwork_bytes = artwork_file.getvalue()
        template_bytes = template_file.getvalue()
        artwork, mask = _load_dieline_inputs(
            artwork_bytes, template_bytes
        )
    except Exception as error:
        st.error(f"刀模读取失败：{error}")
        return

    signature = sha256(artwork_bytes + template_bytes).hexdigest()[:10]
    size_col1, size_col2, zoom_col = st.columns(3)
    output_width = size_col1.number_input(
        "输出宽度",
        min_value=100,
        max_value=10000,
        value=artwork.width,
        step=1,
        key=f"dieline_width_{signature}",
    )
    output_height = size_col2.number_input(
        "输出高度",
        min_value=100,
        max_value=10000,
        value=artwork.height,
        step=1,
        key=f"dieline_height_{signature}",
    )
    zoom = zoom_col.slider(
        "图片缩放",
        min_value=1.0,
        max_value=2.5,
        value=1.1,
        step=0.01,
    )

    position_col1, position_col2 = st.columns(2)
    horizontal_shift = position_col1.slider(
        "主体左右位置",
        min_value=-100,
        max_value=100,
        value=0,
        help="负数向左，正数向右。",
    )
    vertical_shift = position_col2.slider(
        "主体上下位置",
        min_value=-100,
        max_value=100,
        value=35,
        help="负数向上，正数向下；猫头被摄像头缺口切到时向下调整。",
    )

    result = compose_artwork_with_dieline(
        artwork,
        mask,
        (output_width, output_height),
        zoom,
        horizontal_shift,
        vertical_shift,
    )
    mask_col, result_col = st.columns(2)
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
        "下载套图 PNG",
        data=image_to_png_bytes(result),
        file_name=f"{Path(artwork_file.name).stem}_套刀模.png",
        mime="image/png",
        width="stretch",
    )
