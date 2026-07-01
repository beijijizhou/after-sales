from supabase import create_client
import streamlit as st

import pandas as pd
import re

from after_sales_table import sales_table
from ui.after_sales_ui import render_after_sales_section

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

st.title("批量生产订单/条码售后数据查询")


def is_fixed_barcode_pattern(value):
    return re.fullmatch(r"B[A-Z0-9]{6}-\d", value.strip().upper()) is not None


def build_fixed_barcode_candidates(value):
    value = value.strip().upper()

    if not value:
        return []

    if value.startswith("SCGD-"):
        base = value
    else:
        base = f"SCGD-{value}"

    if base.endswith("-A") or base.endswith("-B"):
        return [base]

    return [
        f"{base}-A",
        f"{base}-B",
    ]


def build_exact_search_candidates(values):
    candidate_to_input = {}

    for value in values:
        normalized_value = value.strip().upper()
        candidates = [normalized_value]

        if is_fixed_barcode_pattern(value):
            candidates = build_fixed_barcode_candidates(value)

        for candidate in candidates:
            candidate_to_input[candidate] = value

    return candidate_to_input


def chunk_list(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]

input_text = st.text_area(
    "粘贴生产订单 / 条码列表（每行一个）",
    height=200
)

col1, col2 = st.columns(2)

exact_search = col1.button("精准匹配")
like_search = col2.button("模糊匹配")

if exact_search or like_search:

    barcodes = list({
        x.strip()
        for x in input_text.split("\n")
        if x.strip()
    })

    if not barcodes:
        st.warning("未输入任何内容")
        st.stop()

    results = []
    found_inputs = set()

    with st.spinner("正在查询..."):

        if exact_search:

            candidate_to_input = build_exact_search_candidates(barcodes)

            for candidate_group in chunk_list(list(candidate_to_input.keys()), 100):

                response = (
                    supabase
                    .table("barcode_scans")
                    .select("barcode,scanned_by,scanned_at")
                    .in_("barcode", candidate_group)
                    .execute()
                )

                results.extend(response.data)

            found_inputs = {
                candidate_to_input[row["barcode"].upper()]
                for row in results
                if row["barcode"].upper() in candidate_to_input
            }

        else:

            fixed_barcodes = [
                barcode
                for barcode in barcodes
                if is_fixed_barcode_pattern(barcode)
            ]
            global_search_barcodes = [
                barcode
                for barcode in barcodes
                if not is_fixed_barcode_pattern(barcode)
            ]

            candidate_to_input = build_exact_search_candidates(fixed_barcodes)
            candidates = list(candidate_to_input.keys())

            for candidate_group in chunk_list(candidates, 100):

                response = (
                    supabase
                    .table("barcode_scans")
                    .select("barcode,scanned_by,scanned_at")
                    .in_("barcode", candidate_group)
                    .execute()
                )

                results.extend(response.data)

            for row in results:
                barcode = row["barcode"].upper()
                if barcode in candidate_to_input:
                    found_inputs.add(candidate_to_input[barcode])

            for barcode in global_search_barcodes:

                response = (
                    supabase
                    .table("barcode_scans")
                    .select("barcode,scanned_by,scanned_at")
                    .ilike("barcode", f"%{barcode}%")
                    .limit(20)
                    .execute()
                )

                if response.data:
                    found_inputs.add(barcode)
                    results.extend(response.data)

    if results:

        df = pd.DataFrame(results)
        st.session_state["search_df"] = df
        # remove duplicate rows
        df = df.drop_duplicates()

        st.success(f"找到 {len(df)} 条记录")

        st.dataframe(
            df,
            use_container_width=True
        )

        missing_barcodes = [
            barcode
            for barcode in barcodes
            if barcode not in found_inputs
        ]

        if missing_barcodes:

            st.warning(
                f"{len(missing_barcodes)} 个条码未找到"
            )

            st.text_area(
                "未找到的条码",
                "\n".join(missing_barcodes),
                height=200
            )

    else:

        st.warning("未找到匹配记录")

        st.text_area(
            "未找到的条码",
            "\n".join(barcodes),
            height=200
        )


render_after_sales_section()

sales_table()
