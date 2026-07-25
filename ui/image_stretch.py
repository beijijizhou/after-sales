from pathlib import Path

import streamlit as st

from utils.image_tools import (
    build_boundary_preview,
    image_to_png_bytes,
    load_image,
    stretch_image_bottom,
)


def render_image_stretch_page():
    st.title("图片底部拉伸")
    uploaded_file = st.file_uploader(
        "上传图片",
        type=["png", "jpg", "jpeg", "webp"],
        help="支持 PNG、JPG、JPEG 和 WebP",
    )
    if uploaded_file is None:
        st.info("上传图片后即可调整顶部固定范围和底部拉伸比例。")
        return

    try:
        original = load_image(uploaded_file.getvalue())
    except Exception as error:
        st.error(f"图片读取失败：{error}")
        return

    control_col, factor_col = st.columns(2)
    fixed_top_percent = control_col.slider(
        "顶部保持不变范围",
        min_value=0,
        max_value=95,
        value=35,
        step=1,
        format="%d%%",
        help="红线以上保持原始像素和尺寸不变。",
    )
    stretch_factor = factor_col.slider(
        "底部拉伸倍数",
        min_value=1.0,
        max_value=4.0,
        value=1.5,
        step=0.05,
        format="%.2f 倍",
    )

    try:
        result = stretch_image_bottom(
            original,
            fixed_top_percent,
            stretch_factor,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    original_col, result_col = st.columns(2)
    with original_col:
        st.subheader("拉伸分界线")
        st.image(
            build_boundary_preview(original, fixed_top_percent),
            width="stretch",
        )
        st.caption(f"原图：{original.width} × {original.height} px")
    with result_col:
        st.subheader("处理结果")
        st.image(result, width="stretch")
        st.caption(f"输出：{result.width} × {result.height} px")

    output_name = f"{Path(uploaded_file.name).stem}_底部拉伸.png"
    st.download_button(
        "下载 PNG",
        data=image_to_png_bytes(result),
        file_name=output_name,
        mime="image/png",
        width="stretch",
    )
