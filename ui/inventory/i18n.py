"""Runtime inventory localization API.

Keep Streamlit state and rendering concerns here while the large, static
translation catalog remains framework-independent.
"""

import streamlit as st

from ui.inventory.i18n_catalog import LANGUAGES, TRANSLATIONS

__all__ = [
    "LANGUAGES",
    "TRANSLATIONS",
    "column_config_labels",
    "get_language",
    "render_language_selector",
    "t",
]


def get_language():
    return LANGUAGES.get(
        st.session_state.get("inventory_language_name", "中文"),
        "zh",
    )


def t(text):
    return TRANSLATIONS.get(get_language(), {}).get(text, text)


def render_language_selector():
    return st.radio(
        "Language / Idioma / 语言",
        list(LANGUAGES),
        horizontal=True,
        key="inventory_language_name",
    )


def column_config_labels(columns):
    return {
        column: st.column_config.TextColumn(t(column))
        for column in columns
    }
