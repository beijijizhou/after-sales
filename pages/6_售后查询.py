from supabase import create_client
import streamlit as st

from utils.page_layout import configure_page


configure_page()

import pandas as pd

from after_sales_table import sales_table
from db.after_sale import enrich_after_sales_status
from db.barcode_operation_search import enrich_search_with_operation_history
from ui.after_sales_ui import render_after_sales_section
from ui.barcode_operations_ui import render_barcode_operation_section
from ui import search_ui
from utils.auth import can_access_page, render_navigation
from utils import exact_match, fuzzy_match


render_navigation()

if not can_access_page("app"):
    st.title("生产数据")
    st.info("请从左侧选择可以查看的页面。")
    st.stop()

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

st.title("批量生产订单/条码售后数据查询")

input_col, preview_col = st.columns([1, 2])

with input_col:
    input_text = st.text_area(
        search_ui.INPUT_COLUMN,
        height=260
    )

barcodes = search_ui.parse_barcodes(input_text)

if barcodes:
    with input_col:
        st.metric("输入数量", len(barcodes))

    with preview_col:
        search_ui.render_search_preview(
            "查询预览",
            search_ui.build_search_preview(barcodes)
        )

col1, col2 = st.columns(2)

exact_search = col1.button("精准匹配")
like_search = col2.button("模糊匹配")

if exact_search or like_search:
    if not barcodes:
        st.warning("未输入任何内容")
        st.stop()

    results = []
    found_inputs = set()

    with st.spinner("正在查询..."):
        if exact_search:
            results, found_inputs, _ = search_ui.normalize_search_response(
                exact_match.search(supabase, barcodes)
            )
        else:
            results, found_inputs, _ = search_ui.normalize_search_response(
                fuzzy_match.search(supabase, barcodes)
            )

    if results:
        df = pd.DataFrame(results).drop_duplicates()
        df = enrich_after_sales_status(df)
        df = enrich_search_with_operation_history(df)
        st.session_state["search_df"] = df

        st.success(f"找到 {len(df)} 条记录")
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "操作次数": st.column_config.NumberColumn("操作次数", format="%d"),
                "完整操作历史": st.column_config.TextColumn(
                    "完整操作历史",
                    width="large",
                ),
            },
        )

        missing_barcodes = [
            barcode
            for barcode in barcodes
            if barcode not in found_inputs
        ]
        if missing_barcodes:
            st.warning(f"{len(missing_barcodes)} 个条码未找到")
            st.text_area("未找到的条码", "\n".join(missing_barcodes), height=200)
    else:
        st.session_state.pop("search_df", None)
        st.warning("未找到匹配记录")
        st.text_area("未找到的条码", "\n".join(barcodes), height=200)


render_after_sales_section()
render_barcode_operation_section()

sales_table()
