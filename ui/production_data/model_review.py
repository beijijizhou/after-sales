import pandas as pd
import streamlit as st

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.planning.consumption import (
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.planning.consumption_comparison import (
    build_period_model_comparison,
)
from db.inventory.planning.demand_anomaly import (
    load_daily_outbound_history,
)
from ui.inventory.planning.comparison import (
    render_model_comparison_result,
)
from utils.erp.inventory_mapping import (
    normalize_production_for_inventory,
)


def render_black_white_model_review(
    supabase, production_df, start_date, end_date
):
    st.subheader("黑白短袖整体生产数据")
    st.caption(
        "已合并全部平台和品牌，仅按黑/白与尺码统计；当前仅核对，"
        "不会修改库存。"
    )
    platform_daily, production_wide = _build_platform_model(
        production_df, start_date, end_date
    )
    if production_wide.empty:
        st.info("本次完整生产数据中没有黑白短袖")
        return

    st.dataframe(
        production_wide,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.NumberColumn(column, format="%d")
            for column in [*SIZE_COLUMNS, "总件数"]
        },
    )

    days = (end_date - start_date).days + 1
    try:
        model = scale_consumption_model(
            load_consumption_model(supabase, "黑白短袖"),
            15000,
        )
        outbound = load_daily_outbound_history(
            supabase, "DTF", "黑白短袖", end_date,
            lookback_days=days,
        )
        comparison = build_period_model_comparison(
            model, outbound, platform_daily, end_date, days, days
        )
    except Exception as error:
        st.error(f"黑白短袖模型加载失败：{error}")
        return

    render_model_comparison_result(
        comparison,
        days,
        start_date,
        end_date,
        key_prefix="production_review",
    )


def _build_platform_model(production_df, start_date, end_date):
    normalized = normalize_production_for_inventory(production_df)
    source = normalized[
        (normalized["department"] == "DTF")
        & (normalized["category"] == "黑白短袖")
    ].copy()
    if "生产项状态" in source:
        source = source[
            ~source["生产项状态"].astype(str).str.contains(
                "取消", na=False
            )
        ]
    source = source[
        source["color"].isin(["黑", "白"])
        & source["size"].isin(SIZE_COLUMNS)
    ]
    if source.empty:
        return pd.DataFrame(), pd.DataFrame()

    source["quantity"] = pd.to_numeric(
        source["quantity"], errors="coerce"
    ).fillna(0)
    grouped = (
        source.groupby(["color", "size"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"color": "颜色", "size": "尺码"})
    )
    days = max((end_date - start_date).days + 1, 1)
    daily = grouped.copy()
    daily["平台生产日均"] = daily["quantity"] / days

    wide = grouped.pivot(
        index="颜色", columns="尺码", values="quantity"
    ).reindex(index=["黑", "白"], columns=SIZE_COLUMNS).fillna(0)
    wide = wide.astype(int)
    wide["总件数"] = wide.sum(axis=1)
    return (
        daily[["颜色", "尺码", "平台生产日均"]],
        wide.reset_index(),
    )
