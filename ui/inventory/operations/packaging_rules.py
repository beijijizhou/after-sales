import pandas as pd
import streamlit as st

from db.inventory.core.packaging import (
    DEFAULT_PACKAGING_RULES,
    packaging_material_key,
    packaging_sku_key,
)
from db.inventory.master_data.repository import load_sku_catalog
from ui.inventory.operations.outbound_i18n import TEXT


RULE_ORDER = [
    "standard_box",
    "mens_box",
    "bag_s_l",
    "bag_xl_3xl",
    "bag_4xl_5xl",
]


def render_packaging_rule_editor(
    supabase,
    department,
    category,
    language,
    sku_df=None,
):
    text = TEXT[language]
    version_key = f"packaging_rule_table_version_{language}"
    version = st.session_state.get(version_key, 0)
    source = pd.DataFrame([
        {
            "_rule": rule,
            text["rule_package"]: text["rule_labels"][rule],
            text["rule_scope_column"]: text["rule_scopes"][rule],
            text["rule_units"]: DEFAULT_PACKAGING_RULES[rule],
        }
        for rule in RULE_ORDER
    ])
    edited = st.data_editor(
        source,
        hide_index=True,
        width="stretch",
        disabled=[
            text["rule_package"],
            text["rule_scope_column"],
        ],
        column_config={
            "_rule": None,
            text["rule_package"]: st.column_config.TextColumn(
                text["rule_package"]
            ),
            text["rule_scope_column"]: st.column_config.TextColumn(
                text["rule_scope_column"]
            ),
            text["rule_units"]: st.column_config.NumberColumn(
                text["rule_units"],
                min_value=1,
                step=1,
                format="%d",
                required=True,
            ),
        },
        key=f"packaging_rule_table_{language}_{version}",
    )
    special_rules = _render_sku_rule_table(
        supabase,
        department,
        category,
        language,
        version,
        sku_df,
    )
    st.caption(text["rule_scope"])
    if st.button(
        text["rule_reset"],
        key=f"packaging_rule_reset_{language}_{version}",
    ):
        st.session_state[version_key] = version + 1
        st.rerun()
    default_rules = {
        str(row["_rule"]): int(row[text["rule_units"]])
        for _, row in edited.iterrows()
    }
    return default_rules, special_rules


def _render_sku_rule_table(
    supabase,
    department,
    category,
    language,
    version,
    sku_df=None,
):
    text = TEXT[language]
    if sku_df is None:
        sku_df = load_sku_catalog(
            supabase, department, active_only=True
        )
    if category and not sku_df.empty:
        sku_df = sku_df[sku_df["category"] == category]
    if "is_active" in sku_df:
        sku_df = sku_df[sku_df["is_active"].fillna(True)]
    if sku_df.empty:
        return {}

    rules = _render_material_rule_table(sku_df, text, language, version)

    labels = {
        _sku_label(row): row
        for _, row in sku_df.iterrows()
    }
    sku_column = text["rule_sku"]
    package_column = text["rule_package"]
    units_column = text["rule_units"]
    st.markdown(f"**{text['sku_rules_title']}**")
    st.caption(text["sku_rules_help"])
    edited = st.data_editor(
        pd.DataFrame(columns=[sku_column, package_column, units_column]),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        column_config={
            sku_column: st.column_config.SelectboxColumn(
                sku_column,
                options=list(labels),
                required=True,
            ),
            package_column: st.column_config.SelectboxColumn(
                package_column,
                options=["Box", "Bag"],
                required=True,
            ),
            units_column: st.column_config.NumberColumn(
                units_column,
                min_value=1,
                step=1,
                format="%d",
                required=True,
            ),
        },
        key=f"packaging_sku_rule_table_{language}_{version}",
    )
    for _, source in edited.dropna().iterrows():
        sku = labels.get(source[sku_column])
        if sku is None:
            continue
        key = packaging_sku_key(
            sku.get("brand"),
            sku.get("material"),
            sku.get("color"),
            sku.get("size"),
            source[package_column],
        )
        rules[key] = int(source[units_column])
    return rules


def _render_material_rule_table(sku_df, text, language, version):
    materials = sorted({
        str(value).strip() for value in sku_df["material"].dropna()
        if str(value).strip()
    })
    if not materials:
        return {}
    material_column = text["rule_material"]
    package_column = text["rule_package"]
    units_column = text["rule_units"]
    st.markdown(f"**{text['material_rules_title']}**")
    st.caption(text["material_rules_help"])
    edited = st.data_editor(
        pd.DataFrame(columns=[
            material_column, package_column, units_column,
        ]),
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        column_config={
            material_column: st.column_config.SelectboxColumn(
                material_column, options=materials, required=True,
            ),
            package_column: st.column_config.SelectboxColumn(
                package_column, options=["Box", "Bag"], required=True,
            ),
            units_column: st.column_config.NumberColumn(
                units_column, min_value=1, step=1, format="%d",
                required=True,
            ),
        },
        key=f"packaging_material_rule_table_{language}_{version}",
    )
    return {
        packaging_material_key(
            source[material_column], source[package_column]
        ): int(source[units_column])
        for _, source in edited.dropna().iterrows()
    }


def _sku_label(row):
    details = " / ".join(
        str(row.get(column) or "").strip()
        for column in ["brand", "material", "color", "size"]
        if str(row.get(column) or "").strip()
    )
    return details or str(row.get("sku_name") or "").strip()
