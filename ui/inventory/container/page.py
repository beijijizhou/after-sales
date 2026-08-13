from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_container_dimensions,
)
from ui.inventory.container.events import (
    render_container_history,
)
from ui.inventory.container.filters import (
    render_container_inventory_filters,
)
from ui.inventory.container.form import render_container_form
from ui.inventory.container.history_view import (
    render_arrival_date_range,
    render_arrival_history_table,
)
from ui.inventory.container.posting import (
    load_pending_containers,
    render_pending_container_posting,
)
from ui.inventory.container.search import render_container_search
from ui.inventory.container.transit_view import render_in_transit_table
from ui.inventory.container.today import (
    container_tab_names,
    load_today_arrivals,
    render_today_arrival_posting,
    render_today_arrivals,
)
from ui.inventory.container.week import render_week_selector
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_inventory_container_page(supabase):
    st.title("货柜安排")
    saved_message = st.session_state.pop("container_saved_message", None)
    if saved_message:
        st.success(saved_message)
    render_container_search(supabase)
    st.divider()
    try:
        dimensions = load_container_dimensions(supabase)
    except Exception:
        dimensions = pd.DataFrame(columns=["department", "category"])
    filters = render_container_inventory_filters(
        dimensions, key="container_shared"
    )
    department, category, brands, materials, colors, sizes = filters
    today = datetime.now(NY_TIMEZONE).date()
    try:
        today_arrivals_df = load_today_arrivals(
            supabase, today, *filters
        )
        today_arrivals_error = None
    except Exception as error:
        today_arrivals_df = pd.DataFrame()
        today_arrivals_error = error
    try:
        pending_df = load_pending_containers(supabase, *filters)
        pending_error = None
    except Exception as error:
        pending_df = pd.DataFrame()
        pending_error = error
    tab_names = container_tab_names(
        not today_arrivals_df.empty,
        not pending_df.empty,
    )
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["在途货柜"]:
        week_start, week_end = render_week_selector(
            today,
            show_weekdays=False,
        )
        render_in_transit_table(
            supabase, week_start, week_end, *filters
        )
    with tabs["今日到柜"]:
        render_today_arrivals(
            today_arrivals_df,
            load_error=today_arrivals_error,
        )
        if today_arrivals_error is None:
            render_today_arrival_posting(
                supabase,
                today_arrivals_df,
            )
    with tabs["待确认入库"]:
        if pending_error is not None:
            st.error(f"待入库货柜加载失败：{pending_error}")
        else:
            render_pending_container_posting(supabase, pending_df)
    with tabs["新增货柜"]:
        if has_permission("can_edit_container"):
            render_container_form(supabase, department, category)
        else:
            st.info("当前账号只能查看货柜安排，不能新增或修改")
    with tabs["到柜及入库历史"]:
        arrival_start, arrival_end = render_arrival_date_range(today)
        arrived_df = render_arrival_history_table(
            supabase, arrival_start, arrival_end, *filters
        )
        render_container_history(supabase, arrived_df)
