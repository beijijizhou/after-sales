import pandas as pd
import streamlit as st

from utils.barcode_patterns import (
    build_candidate_to_input,
    is_exact_expansion_pattern,
)


INPUT_COLUMN = "粘贴生产订单 / 条码列表（每行一个）"
QUERY_COLUMN = "实际查询内容"


def normalize_search_response(response):
    if len(response) == 3:
        return response

    results, found_inputs = response
    return results, found_inputs, []


def parse_barcodes(value):
    return list(dict.fromkeys(
        x.strip()
        for x in value.split("\n")
        if x.strip()
    ))


def normalize_search_preview(search_values):
    if not search_values:
        return []

    if isinstance(search_values[0], dict):
        return search_values

    return [
        {
            INPUT_COLUMN: "",
            QUERY_COLUMN: value,
        }
        for value in search_values
    ]


def build_exact_preview(barcodes):
    candidate_to_input = build_candidate_to_input(barcodes)

    return [
        {
            INPUT_COLUMN: original_value,
            QUERY_COLUMN: candidate,
        }
        for candidate, original_value in candidate_to_input.items()
    ]


def build_fuzzy_preview(barcodes):
    exact_barcodes = [
        barcode
        for barcode in barcodes
        if is_exact_expansion_pattern(barcode)
    ]
    global_search_barcodes = [
        barcode
        for barcode in barcodes
        if not is_exact_expansion_pattern(barcode)
    ]

    return build_exact_preview(exact_barcodes) + [
        {
            INPUT_COLUMN: barcode,
            QUERY_COLUMN: f"%{barcode}%",
        }
        for barcode in global_search_barcodes
    ]


def build_search_preview(barcodes):
    rows = []

    for barcode in barcodes:
        exact_candidate_to_input = build_candidate_to_input([barcode])
        exact_values = list(exact_candidate_to_input.keys())

        if is_exact_expansion_pattern(barcode):
            fuzzy_values = exact_values
        else:
            fuzzy_values = [f"%{barcode}%"]

        rows.extend([
            {
                INPUT_COLUMN: barcode,
                "匹配方式": "精准匹配",
                QUERY_COLUMN: value,
            }
            for value in exact_values
        ])
        rows.extend([
            {
                INPUT_COLUMN: barcode,
                "匹配方式": "模糊匹配",
                QUERY_COLUMN: value,
            }
            for value in fuzzy_values
        ])

    return rows


def render_search_preview(title, search_values):
    preview_rows = normalize_search_preview(search_values)
    if not preview_rows:
        return

    st.write(title)
    st.dataframe(
        pd.DataFrame(preview_rows),
        hide_index=True,
        use_container_width=True
    )
