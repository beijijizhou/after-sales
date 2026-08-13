import streamlit as st
from datetime import datetime
from hashlib import sha1
from zoneinfo import ZoneInfo

from db.inventory import SIZE_COLUMNS
from db.inventory.operations.outbound import (
    OUTBOUND_SPECS,
    build_outbound_sku_lookup,
    load_container_outbound_specs,
    load_sku_outbound_specs,
)
from db.inventory.master_data.repository import load_sku_catalog
from ui.inventory.i18n import get_language
from ui.inventory.operations.outbound_status import finish_daily_outbound_backfill
from ui.inventory.operations.outbound_entry import SKU_ENTRY_TEXT, render_sku_outbound_entry
from ui.inventory.operations.outbound_import import render_outbound_import
from ui.inventory.operations.outbound_review import render_outbound_review
from ui.inventory.operations.packaging_rules import (
    render_packaging_rule_editor,
)
from ui.inventory.operations.outbound_i18n import (
    COLUMNS,
    COLORS,
    TEXT,
    translate_package,
)


def render_daily_outbound(supabase, department, category):
    language = get_language()
    text = TEXT[language]
    st.subheader(text["title"])
    st.warning(text["notice"])
    temporary_saved_message = st.session_state.pop(
        "daily_outbound_temporary_saved_message", None
    )
    if temporary_saved_message:
        st.success(temporary_saved_message)

    if st.session_state.pop("daily_outbound_reset_date", False):
        st.session_state.pop("daily_outbound_batch_date", None)
    version = st.session_state.get("daily_outbound_version", 0)
    container_specs = load_container_outbound_specs(
        supabase, department, category
    )
    existing_specs = {**container_specs, **OUTBOUND_SPECS}
    sku_specs = load_sku_outbound_specs(
        supabase, department, category, existing_specs
    )
    outbound_specs = {**container_specs, **sku_specs, **OUTBOUND_SPECS}
    specs_signature = outbound_specs_signature(outbound_specs)
    sku_df = load_sku_catalog(supabase, department, active_only=True)
    if category and not sku_df.empty:
        sku_df = sku_df[sku_df["category"] == category]
    sku_lookup = build_outbound_sku_lookup(sku_df)
    movement_date = st.date_input(
        text["batch_date"],
        value=st.session_state.get(
            "inventory_today",
            datetime.now(ZoneInfo("America/New_York")).date(),
        ),
        key="daily_outbound_batch_date",
    )
    with st.expander(text["rules_title"], expanded=False):
        st.info(text["rules_help"])
        packaging_rules, sku_packaging_rules = render_packaging_rule_editor(
            supabase,
            department,
            category,
            language,
            sku_df=sku_df,
        )

    entry_text = SKU_ENTRY_TEXT[language]
    package_labels = entry_text["packages"]
    adjustment_df, package_preview_df = render_sku_outbound_entry(
        sku_lookup, movement_date, packaging_rules, sku_packaging_rules,
        entry_text, language, version, specs_signature,
    )

    imported, failed = render_outbound_import(
        movement_date, language, version, text, entry_text["import_title"],
        outbound_specs, packaging_rules, sku_packaging_rules,
    )
    if failed:
        return
    if not imported.empty:
        import pandas as pd
        adjustment_df = pd.concat([adjustment_df, imported], ignore_index=True)
    if adjustment_df.empty:
        st.info(text["empty"])
        return

    total = render_outbound_review(
        supabase, department, category, movement_date, adjustment_df,
        package_preview_df, entry_text, text,
    )
    if total is None:
        return
    st.session_state["inventory_saved_message"] = (
        f"{total:,} {text['saved']}"
    )
    st.session_state["daily_outbound_version"] = version + 1
    finish_daily_outbound_backfill()
    st.rerun()


def outbound_specs_signature(outbound_specs):
    source = "|".join(
        f"{key}:{tuple(value)}"
        for key, value in sorted(outbound_specs.items())
    )
    return sha1(source.encode()).hexdigest()[:10]


def build_package_column_config(language, outbound_specs=None):
    columns = COLUMNS[language]
    colors = list(COLORS[language].values())
    config = {
        columns["包装规格"]: st.column_config.SelectboxColumn(
            columns["包装规格"],
            options=[
                translate_package(value, language)
                for value in (outbound_specs or OUTBOUND_SPECS)
            ],
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
