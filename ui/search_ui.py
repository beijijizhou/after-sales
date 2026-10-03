import re

import pandas as pd
import streamlit as st

from utils.barcode_patterns import (
    build_candidate_to_input,
    build_prefix_to_inputs,
    build_exact_search_preview,
    build_fuzzy_search_preview,
)


INPUT_COLUMN = "粘贴生产订单 / 条码列表（支持换行或逗号分隔）"
QUERY_COLUMN = "实际查询内容"


def normalize_search_response(response):
    if len(response) == 3:
        return response

    results, found_inputs = response
    return results, found_inputs, []


def parse_barcodes(value):
    return list(dict.fromkeys(
        x.strip()
        for x in re.split(r"[\n,，]+", value)
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
    return build_exact_search_preview(barcodes)


def build_fuzzy_preview(barcodes):
    return build_fuzzy_search_preview(barcodes)


def build_search_preview(barcodes):
    rows = []
    for barcode in barcodes:
        rows.append({
            INPUT_COLUMN: barcode,
            "精准匹配": _candidate_summary(barcode),
            "模糊匹配": _candidate_summary(barcode, fuzzy=True),
        })
    return rows


def _candidate_summary(barcode, fuzzy=False):
    candidates = list(build_candidate_to_input([barcode]))
    prefixes = [
        f"{prefix}*"
        for prefix in build_prefix_to_inputs([barcode], fuzzy=fuzzy)
    ]
    return " / ".join([*candidates, *prefixes])


def render_search_preview(title, search_values):
    preview_rows = normalize_search_preview(search_values)
    if not preview_rows:
        return

    st.write(title)
    st.dataframe(
        pd.DataFrame(preview_rows),
        hide_index=True,
        width="stretch"
    )
