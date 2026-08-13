"""Shared validation for consumable stock entry workflows."""

import streamlit as st

from ui.consumables.units import package_size


def validate_package_sizes(items):
    missing = items[items.apply(package_size, axis=1).isna()]
    if missing.empty:
        return True
    st.error(
        "以下耗材尚未设置每箱数量："
        + "、".join(missing["name"].astype(str))
    )
    return False
