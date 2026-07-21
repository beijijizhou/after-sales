import streamlit as st

from ui.inventory.i18n import t


def render_history_filters(batch_df, key):
    if batch_df.empty:
        return batch_df

    selected_types = st.multiselect(
        t("出入库类型"),
        _scalar_options(batch_df, "类型"),
        format_func=t,
        key=f"{key}_type_filter",
    )

    filtered_df = batch_df.copy()
    if selected_types:
        filtered_df = filtered_df[filtered_df["类型"].isin(selected_types)]
    return filtered_df


def _scalar_options(df, column):
    return sorted({
        str(value).strip()
        for value in df[column]
        if str(value).strip()
    })

