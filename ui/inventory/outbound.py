import streamlit as st
import pandas as pd

from db.inventory import SIZE_COLUMNS, apply_adjustment_rows
from db.inventory.outbound import (
    OUTBOUND_SPECS,
    build_outbound_package_template,
    convert_packages_to_adjustments,
    normalize_outbound_packages,
)
from ui.inventory.adjustment_preview import build_adjustment_preview
from ui.inventory.i18n import get_language
from ui.inventory.outbound_i18n import (
    COLUMNS,
    COLORS,
    TEXT,
    to_display_table,
    to_internal_table,
    translate_package,
)
from utils.auth import get_current_user


def render_daily_outbound(supabase, department, category):
    language = get_language()
    text = TEXT[language]
    st.subheader(text["title"])
    st.warning(text["notice"])

    version = st.session_state.get("daily_outbound_version", 0)
    template_df = to_display_table(build_outbound_package_template(), language)
    st.download_button(
        text["download"],
        data=template_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=text["file"],
        mime="text/csv",
        use_container_width=True,
    )
    uploaded_file = st.file_uploader(
        text["upload"],
        type=["xlsx", "xls", "csv"],
        key=f"daily_outbound_upload_{language}_{version}",
    )
    if uploaded_file is not None:
        try:
            template_df = (
                pd.read_csv(uploaded_file)
                if uploaded_file.name.lower().endswith(".csv")
                else pd.read_excel(uploaded_file)
            )
            template_df = to_display_table(
                normalize_outbound_packages(to_internal_table(template_df, language)),
                language,
            )
        except Exception as error:
            st.error(f"{text['read_error']}: {error}")
            return

    st.caption(text["caption"])
    package_df = st.data_editor(
        template_df,
        hide_index=True,
        use_container_width=True,
        disabled=[COLUMNS[language]["包装规格"]],
        column_config=build_package_column_config(language),
        key=(
            f"daily_outbound_editor_{language}_{version}_"
            f"{getattr(uploaded_file, 'size', 0)}"
        ),
    )
    package_df = normalize_outbound_packages(to_internal_table(package_df, language))
    adjustment_df = convert_packages_to_adjustments(package_df)
    if adjustment_df.empty:
        st.info(text["empty"])
        return

    st.markdown(f"#### {text['preview']}")
    preview_df = translate_preview(build_adjustment_preview(adjustment_df), language)
    st.dataframe(preview_df, hide_index=True, use_container_width=True)
    total = int(adjustment_df["数量"].sum())
    st.metric(text["total"], f"{total:,}")
    if not st.button(text["confirm"], use_container_width=True):
        return

    try:
        username = (get_current_user() or {}).get("username", "system")
        apply_adjustment_rows(supabase, department, category, adjustment_df, username)
        st.session_state["inventory_saved_message"] = (
            f"{total:,} {text['saved']}"
        )
        st.session_state["daily_outbound_version"] = version + 1
        st.rerun()
    except Exception as error:
        st.error(f"{text['save_error']}: {error}")


def build_package_column_config(language):
    columns = COLUMNS[language]
    colors = list(COLORS[language].values())
    config = {
        columns["日期"]: st.column_config.DateColumn(columns["日期"], required=True),
        columns["包装规格"]: st.column_config.SelectboxColumn(
            columns["包装规格"],
            options=[translate_package(value, language) for value in OUTBOUND_SPECS],
            required=True,
        ),
        columns["颜色"]: st.column_config.SelectboxColumn(
            columns["颜色"], options=colors, required=True
        ),
        columns["备注"]: st.column_config.TextColumn(columns["备注"]),
    }
    for size in SIZE_COLUMNS:
        config[size] = st.column_config.NumberColumn(
            size, min_value=0, step=1, format="%d"
        )
    return config


def translate_preview(df, language):
    columns = COLUMNS[language]
    labels = {
        "日期": columns["日期"], "品牌": "Brand" if language == "en" else "Marca" if language == "es" else "品牌",
        "材质": "Material" if language != "zh" else "材质",
        "颜色": columns["颜色"], "合计": "Total" if language == "en" else "Total" if language == "es" else "合计",
        "备注": columns["备注"], "操作": "Action" if language == "en" else "Acción" if language == "es" else "操作",
    }
    result = df.copy()
    result["颜色"] = result["颜色"].map(COLORS[language]).fillna(result["颜色"])
    if language != "zh":
        result["操作"] = "Deduct" if language == "en" else "Descontar"
    return result.rename(columns=labels)
