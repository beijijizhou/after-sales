import streamlit as st


def configure_page():
    st.set_page_config(layout="wide")
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"], .block-container {
            width: 80%;
            max-width: 2200px;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        @media (max-width: 768px) {
            [data-testid="stMainBlockContainer"], .block-container {
                width: 100%;
                padding-left: 1rem;
                padding-right: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
