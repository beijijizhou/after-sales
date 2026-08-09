import pandas as pd
import streamlit as st

from automation.production_period import load_period_production_model
from automation.sync.uv_daily_operation import (
    SYNCABLE_STATUSES,
    apply_daily_sync,
    build_daily_sync_preview,
)
from automation.sync.uv_sheet_inventory import load_daily_summary
from db.inventory.planning.consumption import (
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.planning.consumption_comparison import (
    build_period_model_comparison,
)
from db.inventory.planning.demand_anomaly import load_daily_outbound_history
from db.inventory.planning.uv_consumption import (
    UV_CONSUMPTION_LOOKBACK_DAYS,
    UV_GOOGLE_DRIVE_FOLDER_URL,
    build_uv_container_coverage,
    load_uv_consumption_history,
)
from db.inventory.container.repository import load_inventory_containers
from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.core.queries import load_inventory_items
from ui.inventory.i18n import t
from ui.inventory.planning.accuracy import (
    render_model_accuracy_summary,
)
from ui.inventory.planning.colored_consumption import (
    render_colored_consumption,
)
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)
from utils.auth.session import (
    get_current_operator_name,
    has_permission,
)


def render_model_comparison(
    model_df, outbound_df, current_date, category="黑白短袖"
):
    days = st.selectbox(
        t("统计周期"),
        [3, 7, 14, 28],
        index=2,
        format_func=lambda value: f"{value} {t('天')}",
        key="inventory_consumption_comparison_days",
    )
    production = load_period_production_model(
        current_date, days, category
    )
    comparison_df = build_period_model_comparison(
        model_df, outbound_df, production.data, current_date, days,
        production.effective_days,
    )
    render_model_comparison_result(
        comparison_df,
        production.effective_days,
        production.start_date,
        production.end_date,
        requested_days=days,
    )


def render_model_comparison_result(
    comparison_df, platform_days, start_date, end_date,
    key_prefix="inventory", requested_days=None,
):
    st.subheader(t("三种消耗模型对比"))
    st.caption(t(
        "15,000单是固定基准；仓库模型来自每日出库；平台模型只使用完整平台数据。"
    ))
    if comparison_df.empty:
        st.info(t("暂无周期对比数据"))
        return

    warehouse_intervals = int(comparison_df["仓库统计区间数"].max())
    st.caption(
        f"{t('仓库有效出库区间')}：{warehouse_intervals}｜"
        f"{t('平台有效天数')}：{platform_days}"
        + (
            f"（{start_date} 至 {end_date}）"
            if platform_days else ""
        )
    )
    if requested_days and platform_days < requested_days:
        st.warning(t("平台完整数据天数不足，平台模型仅供阶段性参考。"))
    render_model_accuracy_summary(comparison_df)

    view = st.selectbox(
        t("查看模型"),
        [
            t("三模型总览"),
            t("15,000模型"),
            t("仓库出库模型"),
            t("平台生产模型"),
        ],
        key=f"{key_prefix}_consumption_model_view",
    )
    if view != t("三模型总览"):
        field = {
            t("15,000模型"): "15,000模型日耗",
            t("仓库出库模型"): "仓库出库日均",
            t("平台生产模型"): "平台生产日均",
        }[view]
        _render_model_detail(comparison_df, field, view)
        return

    _render_totals(comparison_df)
    display_df = comparison_df.copy()
    display_df["颜色"] = display_df["颜色"].map(t)
    styled_df = display_df.style.apply(highlight_comparison, axis=1)
    st.dataframe(
        styled_df, hide_index=True, width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t("尺码")),
            "15,000模型日耗": st.column_config.NumberColumn(
                t("15,000模型日耗"), format="%.1f"
            ),
            "仓库出库日均": st.column_config.NumberColumn(
                t("仓库出库日均"), format="%.1f"
            ),
            "平台生产日均": st.column_config.NumberColumn(
                t("平台生产日均"), format="%.1f"
            ),
            "三模型平均日耗": st.column_config.NumberColumn(
                "三模型平均日耗", format="%.1f"
            ),
            "仓库/模型": st.column_config.NumberColumn(
                t("仓库/模型"), format="%.1f%%"
            ),
            "平台/模型": st.column_config.NumberColumn(
                t("平台/模型"), format="%.1f%%"
            ),
            "仓库有效区间数": st.column_config.NumberColumn(format="%d"),
            "仓库统计区间数": st.column_config.NumberColumn(format="%d"),
            "平台有效天数": st.column_config.NumberColumn(format="%d"),
        },
    )
def render_consumption_models(
    supabase, department, category, order_quantity, current_date,
    visible_sizes=None, inventory_df=None,
):
    if department == "UV":
        render_uv_consumption_model(
            supabase, category, current_date, visible_sizes, inventory_df
        )
        return
    if category == "彩色短袖":
        render_colored_consumption(supabase, current_date, inventory_df)
        return
    if category != "黑白短袖":
        st.info(t("当前品类暂无消耗模型"))
        return
    try:
        model_df = scale_consumption_model(
            load_consumption_model(supabase, category), order_quantity
        )
        outbound_df = load_daily_outbound_history(
            supabase, department, category, current_date
        )
        if visible_sizes:
            model_df = model_df[model_df["size"].isin(visible_sizes)]
            outbound_df = outbound_df[
                outbound_df["尺码"].isin(visible_sizes)
            ]
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    render_model_comparison(
        model_df, outbound_df, current_date, category
    )


def render_uv_consumption_model(
    supabase, category, current_date, visible_sizes=None, inventory_df=None
):
    try:
        model_df = load_uv_consumption_history(supabase, current_date)
        if category:
            model_df = model_df[model_df["品类"] == category]
        if visible_sizes:
            model_df = model_df[model_df["型号"].isin(visible_sizes)]
        containers = load_inventory_containers(
            supabase,
            department="UV",
            category=category or None,
            statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
        )
        coverage_df = build_uv_container_coverage(
            model_df, inventory_df, containers
        )
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    st.subheader("UV 每日消耗与货柜")
    st.caption(
        f"每日消耗按 Google Sheets 最近 {UV_CONSUMPTION_LOOKBACK_DAYS} 天"
        "的有效数据日计算，并按品类、材质、颜色、型号连接当前库存和货柜。"
        "每日库存扣减请到“系统库存扣减”。"
    )
    if model_df.empty:
        st.info("最近 14 天暂无已同步的 UV 每日消耗数据")
        return
    daily_total = float(model_df["每日消耗"].sum())
    effective_days = int(model_df["有效数据天数"].max())
    daily_col, days_col = st.columns(2)
    daily_col.metric("一天消耗", f"{daily_total:,.1f} 件")
    days_col.metric("计算所用有效天数", f"{effective_days} 天")
    if effective_days < UV_CONSUMPTION_LOOKBACK_DAYS:
        st.warning(
            f"最近 14 天中只有 {effective_days} 天已同步；"
            "当前日均仅按这些有效日期计算。"
        )
    st.dataframe(
        coverage_df,
        hide_index=True,
        width="stretch",
        column_config={
            "每日消耗": st.column_config.NumberColumn(format="%.1f"),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "当前可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "预计到货日期": st.column_config.DateColumn(),
            "货柜数量": st.column_config.NumberColumn(format="%d"),
            "到货后可撑天数": st.column_config.NumberColumn(
                format="%.1f 天"
            ),
        },
    )


def render_uv_daily_deduction(supabase, current_date):
    st.subheader("UV 系统库存扣减")
    st.caption(
        "先读取今天的 Google Sheets 数据并核对表格；"
        "确认后才会扣减库存，重复操作不会重复扣减。"
    )
    spreadsheet = render_uv_spreadsheet_selector()
    st.link_button("打开当前 Google 表格", spreadsheet["webViewLink"])
    st.link_button("打开 UV 数据文件夹", UV_GOOGLE_DRIVE_FOLDER_URL)
    spreadsheet_id = spreadsheet["id"]
    result = st.session_state.pop("uv_daily_deduction_result", None)
    if result:
        st.success(result)
    state_key = "uv_daily_deduction_preview"
    date_key = "uv_daily_deduction_date"
    if st.button(
        "读取今日消耗并生成表格",
        key="uv_load_daily_deduction",
        type="secondary",
    ):
        try:
            summary = load_daily_summary(
                google_sheets_client(),
                spreadsheet_id,
                current_date,
            )
            if not summary:
                st.session_state.pop(state_key, None)
                st.session_state.pop(date_key, None)
                st.warning(
                    f"{current_date:%m/%d} 暂无可扣减的 SKU 消耗数据。"
                )
            else:
                inventory = load_inventory_items(supabase, "UV", "")
                st.session_state[state_key] = build_daily_sync_preview(
                    supabase, summary, current_date, inventory
                )
                st.session_state[date_key] = current_date
        except Exception as error:
            st.error(f"读取今日消耗失败：{error}")

    preview = st.session_state.get(state_key)
    preview_date = st.session_state.get(date_key)
    if preview is None or preview_date != current_date:
        return
    st.caption(f"扣减日期：{current_date:%Y-%m-%d}")
    display_preview = preview.rename(columns={
        "预计扣减": "本次出库 (-)",
        "扣减后库存": "调整后库存",
    }).copy()
    display_preview["本次出库 (-)"] = -pd.to_numeric(
        display_preview["本次出库 (-)"], errors="coerce"
    ).fillna(0).abs().astype(int)
    st.dataframe(
        display_preview,
        hide_index=True,
        width="stretch",
        column_config={
            "当日消耗": st.column_config.NumberColumn(format="%d"),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "本次出库 (-)": st.column_config.NumberColumn(format="%d"),
            "调整后库存": st.column_config.NumberColumn(format="%d"),
        },
    )
    pending = preview[
        preview["状态"] == "可扣减"
    ]
    blocking = preview[
        ~preview["状态"].isin(SYNCABLE_STATUSES)
    ]
    st.caption(
        f"本次预计扣减：{int(pending['预计扣减'].sum()):,} 件｜"
        f"已同步：{int((preview['状态'] == '已同步').sum())} 个 SKU"
    )
    if not blocking.empty:
        details = "；".join(
            f"{row['表格产品']}：{row['状态']}"
            for row in blocking.to_dict("records")
        )
        st.error(f"暂不能扣减，请先处理：{details}")
        return
    deferred = preview[
        preview["状态"] == "待分配 SKU（本次不扣）"
    ]
    if not deferred.empty:
        details = "；".join(
            f"{row['表格产品']} {int(row['当日消耗'])} 件"
            for row in deferred.to_dict("records")
        )
        st.warning(
            f"{details} 缺少可确认的具体 SKU，本次不会扣减；"
            "其余 SKU 可以继续确认。"
        )
    if pending.empty:
        st.success("今天的消耗已经全部同步，无需再次扣减。")
        return
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能确认扣减库存。")
        return
    confirmed = st.checkbox(
        "我已核对以上 SKU、当日消耗和扣减后库存",
        key="uv_confirm_daily_deduction",
    )
    if st.button(
        "确认扣减今日库存",
        key="uv_apply_daily_deduction",
        type="primary",
        disabled=not confirmed,
    ):
        try:
            imported, skipped = apply_daily_sync(
                supabase,
                preview,
                current_date,
                get_current_operator_name(),
            )
            st.session_state.pop(state_key, None)
            st.session_state.pop(date_key, None)
            st.session_state["uv_daily_deduction_result"] = (
                f"今日库存已扣减 {imported:,} 件"
                + (f"，另有 {skipped:,} 件此前已同步" if skipped else "")
            )
            st.rerun()
        except Exception as error:
            st.error(f"扣减失败：{error}")


def _render_totals(df):
    columns = st.columns(4)
    values = [
        ("15,000模型日耗", "15,000模型"),
        ("仓库出库日均", "仓库出库模型"),
        ("平台生产日均", "平台生产模型"),
        ("三模型平均日耗", "三模型平均"),
    ]
    for column, (field, label) in zip(columns, values):
        value = pd.to_numeric(df[field], errors="coerce").sum(min_count=1)
        column.metric(t(label), f"{value:,.0f}" if pd.notna(value) else "—")


def _render_model_detail(df, field, title):
    values = df[["颜色", "尺码", field]].copy()
    wide = values.pivot(index="颜色", columns="尺码", values=field)
    wide = wide.reindex(index=["黑", "白"], columns=SIZE_COLUMNS)
    wide = wide.reset_index()
    wide["颜色"] = wide["颜色"].map(t)
    total = pd.to_numeric(values[field], errors="coerce").sum(min_count=1)
    st.metric(
        f"{title} {t('日均合计')}",
        f"{total:,.1f}" if pd.notna(total) else "—",
    )
    st.dataframe(
        wide, hide_index=True, width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            **{
                size: st.column_config.NumberColumn(size, format="%.1f")
                for size in SIZE_COLUMNS
            },
        },
    )


def highlight_comparison(row):
    styles = []
    for column in row.index:
        ratio_field = {
            "仓库出库日均": "仓库/模型",
            "仓库/模型": "仓库/模型",
            "平台生产日均": "平台/模型",
            "平台/模型": "平台/模型",
        }.get(column)
        ratio = pd.to_numeric(row.get(ratio_field), errors="coerce")
        if pd.notna(ratio) and abs(float(ratio) - 100) >= 30:
            styles.append(
                "background-color: #ffd6d6; color: #8a0000; font-weight: 700;"
            )
        elif pd.notna(ratio) and abs(float(ratio) - 100) >= 15:
            styles.append(
                "background-color: #fff1cc; color: #7a4a00; font-weight: 700;"
            )
        else:
            styles.append("")
    return styles
