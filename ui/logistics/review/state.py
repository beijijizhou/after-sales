"""Review session state and label-archive actions."""

from datetime import date

import streamlit as st

from automation.logistics.label_cache import cached_label_content
from automation.logistics.label_downloads import build_label_archive
from ui.logistics.review.model import (
    is_target_usps_review,
    label_documents,
    order_tracking_pairs,
)
from ui.logistics.review.ocr_format import ocr_summary_text
from utils.auth import has_permission


def render_label_archive_download(container, reviewed):
    documents = label_documents(reviewed)
    fingerprint = tuple(document["url"] for document in documents)
    if st.session_state.get("logistics_label_archive_fingerprint") != fingerprint:
        st.session_state.pop("logistics_label_archive", None)
        st.session_state.pop("logistics_label_archive_errors", None)
    if container.button(
        "打包全部面单", width="stretch", disabled=not documents,
        help="打包本次物流识别数据中的全部可下载面单，不受物流商筛选影响。",
    ):
        if not has_permission("can_manage_logistics"):
            st.error("当前账号没有批量下载面单的权限。")
            return
        with st.spinner(f"正在下载并打包 {len(documents):,} 张面单……"):
            archive, errors, downloaded = build_label_archive(
                documents, cached_label_content, max_workers=4
            )
        st.session_state["logistics_label_archive"] = archive
        st.session_state["logistics_label_archive_errors"] = errors
        st.session_state["logistics_label_archive_fingerprint"] = fingerprint
        st.success(
            f"面单包已生成：成功 {downloaded:,} 张｜失败 {len(errors):,} 张"
        )
    archive = st.session_state.get("logistics_label_archive")
    if archive:
        container.download_button(
            "下载全部面单 ZIP", data=archive,
            file_name=f"shipping_labels_{date.today():%Y%m%d}.zip",
            mime="application/zip", width="stretch",
        )
    errors = st.session_state.get("logistics_label_archive_errors") or []
    if errors:
        st.warning(f"有 {len(errors):,} 张面单下载失败，可稍后重新打包。")


def reset_review_selection():
    st.session_state["logistics_review_data_version"] = (
        int(st.session_state.get("logistics_review_data_version", 0)) + 1
    )
    st.session_state.pop("logistics_label_archive", None)
    st.session_state.pop("logistics_label_archive_errors", None)
    st.session_state.pop("logistics_label_archive_fingerprint", None)


def store_review_ocr_results(reviewed, summary):
    st.session_state["logistics_carrier_review_rows"] = reviewed
    st.session_state["logistics_usps_candidates"] = order_tracking_pairs([
        item["row"] for item in reviewed if is_target_usps_review(item)
    ])
    reset_review_selection()
    st.session_state["logistics_review_ocr_notice"] = (
        "OCR结果已回填到本表和下方普通USPS核查数据。"
        + (f" {ocr_summary_text(summary)}" if summary else "")
    )
