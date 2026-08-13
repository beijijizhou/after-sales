"""Consumable SKU administration page."""

import streamlit as st

from ui.consumables.sku_catalog import render_catalog
from ui.consumables.sku_create import render_create_form
from ui.consumables.sku_models import copy_defaults

# Backward-compatible test/helper name.
_copy_defaults = copy_defaults


def render_sku_management(supabase, department_id, items_df, can_manage):
    st.subheader("SKU 管理")
    create_tab, catalog_tab = st.tabs(["新增 SKU", "现有 SKU"])
    with create_tab:
        render_create_form(supabase, department_id, items_df, can_manage)
    with catalog_tab:
        render_catalog(supabase, items_df, can_manage)
