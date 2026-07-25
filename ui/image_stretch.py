from pathlib import Path

import streamlit as st

from utils.image_tools import (
    build_stretch_region_preview,
    image_to_png_bytes,
    load_image,
    stretch_image_middle,
)


def render_image_stretch_page():
    st.title("图片中段拉伸")
    uploaded_file = st.file_uploader(
        "上传图片",
        type=["png", "jpg", "jpeg", "webp"],
        help="支持 PNG、JPG、JPEG 和 WebP",
    )
    if uploaded_file is None:
        st.info("上传图片后，选择中间拉伸范围；顶部和底部保持不变。")
        return

    try:
        original = load_image(uploaded_file.getvalue())
    except Exception as error:
        st.error(f"图片读取失败：{error}")
        return

    region_col, factor_col = st.columns(2)
    stretch_start, stretch_end = region_col.slider(
        "中间拉伸范围",
        min_value=0,
        max_value=100,
        value=(35, 90),
        step=1,
        format="%d%%",
        help="红线与蓝线之间会被拉伸，两条线外的区域保持不变。",
    )
    stretch_factor = factor_col.slider(
        "中间拉伸倍数",
        min_value=1.0,
        max_value=4.0,
        value=1.5,
        step=0.05,
        format="%.2f 倍",
    )

    try:
        result = stretch_image_middle(
            original,
            stretch_start,
            stretch_end,
            stretch_factor,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    original_col, result_col = st.columns(2)
    with original_col:
        st.subheader("中间拉伸范围")
        st.image(
            build_stretch_region_preview(
                original,
                stretch_start,
                stretch_end,
            ),
            width="stretch",
        )
        st.caption(
            f"顶部固定 {stretch_start}% · "
            f"底部固定 {100 - stretch_end}%"
        )
        st.caption(f"原图：{original.width} × {original.height} px")
    with result_col:
        st.subheader("处理结果")
        st.image(result, width="stretch")
        st.caption(f"输出：{result.width} × {result.height} px")

    output_name = f"{Path(uploaded_file.name).stem}_中段拉伸.png"
    st.download_button(
        "下载 PNG",
        data=image_to_png_bytes(result),
        file_name=output_name,
        mime="image/png",
        width="stretch",
    )
