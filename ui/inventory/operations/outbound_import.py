"""Optional spreadsheet import for a daily outbound batch."""

import pandas as pd
import streamlit as st

from db.inventory.operations.outbound import (
    apply_outbound_batch_date,
    build_outbound_package_template,
    convert_packages_to_adjustments,
    normalize_outbound_packages,
)
from ui.inventory.operations.outbound_i18n import COLUMNS, to_display_table, to_internal_table


def render_outbound_import(
    movement_date, language, version, text, title, outbound_specs,
    packaging_rules, sku_packaging_rules,
):
    """Return imported adjustments and whether file parsing failed."""
    with st.expander(title, expanded=False):
        date_column = COLUMNS[language]["日期"]
        template = to_display_table(
            build_outbound_package_template(outbound_specs), language
        ).drop(columns=[date_column])
        st.download_button(
            text["download"], data=template.to_csv(index=False).encode("utf-8-sig"),
            file_name=text["file"], mime="text/csv", width="stretch",
        )
        uploaded = st.file_uploader(
            text["upload"], type=["xlsx", "xls", "csv"],
            key=f"daily_outbound_upload_{language}_{version}_{movement_date.isoformat()}",
        )
        if uploaded is None:
            return pd.DataFrame(), False
        try:
            source = (
                pd.read_csv(uploaded)
                if uploaded.name.lower().endswith(".csv")
                else pd.read_excel(uploaded)
            )
            packages = normalize_outbound_packages(
                apply_outbound_batch_date(to_internal_table(source, language), movement_date),
                outbound_specs,
            )
            return convert_packages_to_adjustments(
                packages, packaging_rules, sku_packaging_rules, outbound_specs
            ), False
        except Exception as error:
            st.error(f"{text['read_error']}: {error}")
            return pd.DataFrame(), True

