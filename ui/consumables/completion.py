from datetime import timedelta

import streamlit as st

from db.inventory.dashboard_completion import (
    DAILY_COMPLETION_START_DATE,
    active_consumable_issue_dates,
)

def build_consumable_missing_dates(
    batches, today, start_date=DAILY_COMPLETION_START_DATE,
):
    """Return only ended business dates missing an active issue batch."""
    recorded = active_consumable_issue_dates(batches)
    expected = {
        start_date + timedelta(days=offset)
        for offset in range(max((today - start_date).days, 0))
    }
    return sorted(expected - recorded)


def render_consumable_completion(batches, today, can_report):
    missing = build_consumable_missing_dates(batches, today)
    state_key = "consumable_makeup_date"
    active_date = st.session_state.get(state_key)
    if active_date not in missing:
        st.session_state.pop(state_key, None)
        active_date = None
    if missing:
        st.warning(
            f"耗材库存有 {len(missing)} 天尚未扣减。"
        )
        if can_report and active_date is None:
            controls = st.columns([2, 1])
            selected_date = controls[0].selectbox(
                "待补录日期",
                missing,
                format_func=lambda value: value.strftime("%m/%d"),
                key="consumable_makeup_date_selection",
            )
            if controls[1].button(
                "开始补录",
                type="primary",
                width="stretch",
                key="open_consumable_makeup",
                on_click=_open_makeup_date,
                args=(selected_date,),
            ):
                pass
        elif not can_report:
            st.caption("当前账号没有耗材出库登记权限。")
    else:
        st.success("截至昨日的耗材库存均已扣减。")
    return active_date


def _open_makeup_date(selected_date):
    st.session_state["consumable_makeup_date"] = selected_date
    st.session_state["daily_consumable_issue_date"] = selected_date
