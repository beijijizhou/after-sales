from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t
from ui.inventory.stock.table_editor import render_inventory_table_editor
from ui.inventory.stock.table_filters import render_inventory_table_filters


def render_inventory_view_mode(category, inventory_df):
    if category == "彩色短袖":
        return st.segmented_control(
            "彩色短袖库存显示规则",
            ["跨品牌合并", "按品牌查看"],
            default="跨品牌合并",
            key="inventory_stock_view_mode_colored",
        )
    has_black_white = (
        category == "黑白短袖"
        or (
            not category
            and "品类" in inventory_df.columns
            and (inventory_df["品类"] == "黑白短袖").any()
        )
    )
    if not has_black_white:
        return "品牌明细"

    return st.segmented_control(
        t("库存查看方式"),
        ["品牌明细", "整体黑白统计"],
        default="品牌明细",
        format_func=t,
        key="inventory_stock_view_mode",
    )


def render_inventory_table(
    supabase, department, category, inventory_df, inventory_date, editable,
    visible_sizes, filter_title, is_historical=False,
):
    st.subheader(f"{filter_title} {t('库存明细')}")
    current_date = datetime.now(ZoneInfo("America/New_York")).date()

    col1, col2 = st.columns(2)
    col1.metric(t("当前日期"), current_date.isoformat())
    date_context = build_inventory_date_context(
        current_date, inventory_date, is_historical
    )
    col2.metric(t(date_context["label"]), inventory_date.isoformat())
    if date_context["message"]:
        st.info(t(date_context["message"]).format(
            date=inventory_date.isoformat()
        ))
    if date_context["stale_days"]:
        days = date_context["stale_days"]
        st.warning(
            t("该部门库存账已经 {days} 天没有更新").format(days=days)
        )
    display_df = render_inventory_table_filters(inventory_df, visible_sizes)
    column_config = {
        "总库存": st.column_config.NumberColumn(
            t("总库存（全部尺码）"), format="%d"
        ),
        "品类": st.column_config.TextColumn(t("品类")),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质")),
        "颜色": st.column_config.TextColumn(t("颜色")),
        "型号": st.column_config.TextColumn(t("型号")),
        **{
            size: st.column_config.NumberColumn(size, format="%d")
            for size in SIZE_COLUMNS
        },
    }
    table_height = min(max((len(display_df) + 1) * 35 + 8, 220), 900)
    if editable:
        render_inventory_table_editor(
            supabase, department, category, display_df, column_config,
            table_height,
        )
    else:
        st.dataframe(
            display_df, hide_index=True, width="stretch",
            column_config=column_config, height=table_height,
        )


def render_sku_update_times(raw_df, department, visible_sizes=None):
    update_table = build_sku_update_time_table(
        raw_df, department, visible_sizes
    )
    if update_table.empty:
        return
    with st.expander(t("SKU 上次库存更新时间（纽约）"), expanded=False):
        st.caption(t("只记录成功写入库存的时间；失败提交不会更新时间。"))
        st.dataframe(
            update_table, hide_index=True, width="stretch",
            height=min(max((len(update_table) + 1) * 35 + 8, 180), 700),
        )


def build_sku_update_time_table(raw_df, department, visible_sizes=None):
    source = pd.DataFrame(raw_df).copy()
    identity = ["category", "brand", "material", "color"]
    required = {*identity, "size", "updated_at"}
    if source.empty or not required.issubset(source.columns):
        return pd.DataFrame()
    updated = pd.to_datetime(source["updated_at"], errors="coerce", utc=True)
    source["更新时间"] = updated.dt.tz_convert(
        ZoneInfo("America/New_York")
    ).dt.strftime("%Y-%m-%d %H:%M").fillna("—")
    source["size"] = source["size"].fillna("").astype(str)
    if str(department or "").strip().upper() != "DTF":
        return (
            source.groupby([*identity, "size"], dropna=False, as_index=False)
            .agg(更新时间=("更新时间", "max"))
            .rename(columns={
                "category": "品类", "brand": "品牌", "material": "材质",
                "color": "颜色", "size": "型号",
            })
        )
    table = source.pivot_table(
        index=identity, columns="size", values="更新时间",
        aggfunc="max", fill_value="—",
    ).reset_index().rename(columns={
        "category": "品类", "brand": "品牌", "material": "材质",
        "color": "颜色",
    })
    sizes = [
        size for size in (visible_sizes or SIZE_COLUMNS)
        if size in table.columns
    ]
    table["_material_order"] = table["材质"].map({
        "160g": 0, "180g": 1, "CVC": 2,
    }).fillna(99)
    table["_color_order"] = table["颜色"].map({
        "黑": 0, "白": 1,
    }).fillna(99)
    table = table.sort_values(
        ["_material_order", "材质", "品牌", "_color_order", "颜色"],
        kind="stable",
    )
    return table[["品类", "品牌", "材质", "颜色", *sizes]].reset_index(
        drop=True
    )


def build_inventory_date_context(
    current_date, inventory_date, is_historical=False,
):
    if is_historical:
        return {
            "label": "历史库存日期",
            "message": "正在查看 {date} 的历史库存快照，不代表库存账停止更新",
            "stale_days": 0,
        }
    stale_days = 0
    if inventory_date < current_date:
        days = (current_date - inventory_date).days
        stale_days = days
    return {
        "label": "库存账最后变动",
        "message": "",
        "stale_days": stale_days,
    }


def render_inventory_metrics(inventory_df):
    table_total = int(inventory_df["总库存"].sum())
    color_count = (
        inventory_df["颜色"].nunique() if "颜色" in inventory_df.columns else 0
    )
    col1, col2 = st.columns(2)
    col1.metric(t("当前表总库存"), table_total)
    col2.metric(t("当前表颜色数"), color_count)
