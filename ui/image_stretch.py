import streamlit as st

from ui.image_tools import render_dieline_composer, render_middle_stretch


def render_image_stretch_page():
    st.title("图片处理")
    stretch_tab, dieline_tab = st.tabs(["中段拉伸", "刀模套图"])
    with stretch_tab:
        render_middle_stretch()
    with dieline_tab:
        render_dieline_composer()
