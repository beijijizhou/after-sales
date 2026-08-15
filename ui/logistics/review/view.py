"""Carrier review table and user actions."""

import sys

import pandas as pd
import streamlit as st

from db.logistics import (
    ensure_tracking_context_shipments,
    save_reviewed_ocr_results,
)
from ui.logistics.review.model import (
    carrier_filter_name,
    database_error,
    label_ocr_candidates,
    review_selection_defaults,
)
from ui.logistics.review.ocr_format import resolve_ocr_workers
from ui.logistics.review.ocr_runner import apply_label_ocr
from ui.logistics.review.state import (
    render_label_archive_download,
    store_review_ocr_results,
)
from utils.auth import get_current_operator_name, has_permission


CARRIER_NAMES = (
    "USPS", "CBS", "CBT", "GOFO", "FedEx", "UPS", "UniUni", "SwiftX",
    "其他待确认",
)


def render_carrier_review(supabase, show_empty=False):
    rows = st.session_state.get(
        "logistics_carrier_review_rows",
        st.session_state.get("s2b_carrier_review_rows", []),
    )
    if not rows and not show_empty:
        return
    st.subheader("物流识别核对")
    notice = st.session_state.pop("logistics_review_ocr_notice", "")
    if notice:
        st.success(notice)
    selected_carriers = _render_carrier_filters()
    if not rows:
        st.info("点击“从ERP读取数据”后，这里会显示本次物流识别结果。")
        return
    _render_carrier_counts(rows)
    filtered = [
        row for row in rows
        if carrier_filter_name(row) in selected_carriers
    ]
    selected_rows = _render_selection_table(filtered, selected_carriers)
    if selected_rows is not None:
        _render_ocr_actions(supabase, rows, selected_rows)
    st.caption(
        "CBS（GOFO揽收）和CBT（TikTok指定物流商揽收）可单独筛选；"
        "它们不会进入普通USPS核查候选。"
    )


def _render_carrier_filters():
    columns = st.columns(4)
    return [
        name for index, name in enumerate(CARRIER_NAMES)
        if columns[index % len(columns)].checkbox(
            name, value=name == "USPS",
            key=f"logistics_carrier_checkbox_{name}",
        )
    ]


def _render_carrier_counts(rows):
    counts = pd.Series([carrier_filter_name(row) for row in rows]).value_counts()
    excluded = sum(row.get("USPS子类型") in {"CBS", "CBT"} for row in rows)
    st.caption(
        "｜".join(
            f"{name} {int(counts.get(name, 0)):,} 条"
            for name in CARRIER_NAMES
        ) + (f"｜CBS/CBT 独立分类 {excluded:,} 条" if excluded else "")
    )


def _render_selection_table(rows, selected_carriers):
    available_count = len(label_ocr_candidates(rows))
    version = int(st.session_state.get("logistics_review_data_version", 0))
    columns = st.columns([2, 1, 1])
    mode = columns[0].radio(
        "面单选择方式", ("手工勾选", "全选可下载", "随机抽查"),
        index=1, horizontal=True, key="logistics_review_selection_mode",
    )
    count = columns[1].number_input(
        "随机抽查数量", min_value=1, max_value=max(1, available_count),
        value=min(5, max(1, available_count)),
        disabled=mode != "随机抽查" or not available_count,
        key=f"logistics_review_random_count_{version}_{'_'.join(selected_carriers)}",
    )
    seed = int(st.session_state.get("logistics_review_random_seed", 0))
    if columns[2].button(
        "重新随机", width="stretch",
        disabled=mode != "随机抽查" or not available_count,
    ):
        seed += 1
        st.session_state["logistics_review_random_seed"] = seed
    defaults = review_selection_defaults(rows, mode, int(count), seed)
    display = pd.DataFrame([{
        "OCR选择": defaults[index],
        **{key: value for key, value in row.items() if key != "row"},
    } for index, row in enumerate(rows)])
    if not rows:
        st.info("当前没有勾选物流商的匹配记录。")
        return None
    edited = st.data_editor(
        display, hide_index=True, width="stretch", height=420,
        disabled=[column for column in display if column != "OCR选择"],
        column_config={
            "OCR选择": st.column_config.CheckboxColumn(
                "OCR选择", help="只勾选需要核查的可疑面单。"
            ),
            "面单": st.column_config.LinkColumn(display_text="打开面单"),
            "备用面单": st.column_config.LinkColumn(display_text="备用面单"),
        },
        key=(
            f"logistics_carrier_review_editor_{version}_{mode}_{seed}_"
            f"{'_'.join(selected_carriers)}"
        ),
    )
    return [
        rows[index]
        for index, selected in enumerate(edited["OCR选择"].tolist())
        if bool(selected)
    ]


def _render_ocr_actions(supabase, reviewed, selected_rows):
    available = label_ocr_candidates(selected_rows)
    missing_count = len(selected_rows) - len(available)
    columns = st.columns([2, 1, 2, 2])
    mode = columns[0].selectbox(
        "OCR速度模式", ("稳定模式（单线程）", "加速模式（双线程）"),
        help="双线程仅开放给最多20张的小批量测试，并使用更多云端内存。",
        key="logistics_review_ocr_mode",
    )
    columns[1].metric("已选可解析", f"{len(available):,} 张")
    requested = 2 if mode.startswith("加速") else 1
    workers, reason = resolve_ocr_workers(
        requested, sys.version_info[:2], False, len(available)
    )
    if columns[2].button(
        "OCR分析勾选面单", type="primary", width="stretch",
        disabled=not available,
    ):
        if not has_permission("can_manage_logistics"):
            st.error("当前账号没有面单OCR权限。")
            return
        summary = apply_label_ocr(
            available, "物流识别核对", max_labels=None,
            ocr_workers=workers, ordinary_usps_only=False,
        )
        try:
            reviewer = get_current_operator_name()
            shipments = ensure_tracking_context_shipments(
                supabase,
                [item.get("row", item) for item in selected_rows],
                reviewer,
            )
            saved = save_reviewed_ocr_results(
                supabase, selected_rows, shipments, reviewer
            )
            st.caption(f"OCR审计已保存 {saved:,} 条。")
        except Exception as error:
            st.error(database_error(error))
        store_review_ocr_results(reviewed, summary)
        st.rerun()
    render_label_archive_download(columns[3], reviewed)
    if missing_count:
        st.warning(f"已选记录中有 {missing_count:,} 条没有可下载面单，无法OCR。")
    if reason:
        st.warning(reason)
    elif workers == 2:
        st.warning("当前使用双线程OCR；建议先选择少量面单确认云端稳定性。")
