from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.api.fangguo import fetch_fangguo_sku_prices
from db.inventory.core.constants import SIZE_COLUMNS
from utils.option_values import ordered_values
from utils.sku_sorting import sort_sku_rows
from ui.finance.fangguo_sku_pricing import (
    render_batch_price_editor,
    render_price_reference,
)


STATE_ROWS = "finance_fangguo_sku_catalog"
STATE_READ_AT = "finance_fangguo_sku_catalog_read_at"
NEW_YORK = ZoneInfo("America/New_York")


def render_fangguo_sku_catalog(credentials):
    render_price_reference()
    st.divider()
    st.caption(
        "实时读取方果 SKU 管理页；不会复用订单缓存，也不会修改方果数据。"
    )
    if st.button(
        "读取最新方果 SKU",
        type="primary",
        key="fangguo_sku_catalog_refresh",
        width="stretch",
    ):
        try:
            status = st.empty()
            with st.spinner("正在读取方果全部 SKU..."):
                rows = fetch_fangguo_sku_prices(
                    credentials,
                    report_progress=status.info,
                    include_inactive=True,
                )
            st.session_state[STATE_ROWS] = rows
            st.session_state[STATE_READ_AT] = datetime.now(NEW_YORK)
            status.success(f"已实时读取 {len(rows):,} 个方果 SKU")
        except Exception as error:
            st.error(f"方果 SKU 读取失败：{error}")

    rows = st.session_state.get(STATE_ROWS)
    if not isinstance(rows, pd.DataFrame):
        st.info("点击“读取最新方果 SKU”查看当前价格和启用状态。")
        return
    rows = _upgrade_cached_rows(rows)
    st.session_state[STATE_ROWS] = rows
    _render_summary(rows)
    filtered = _render_filters(rows)
    _render_table(filtered)
    _render_download(filtered)
    render_batch_price_editor(credentials, filtered, _save_refreshed_rows)


def _render_summary(rows):
    active = int(rows["skuActive"].sum()) if not rows.empty else 0
    priced = int(rows["currentSkuPrice"].notna().sum()) if not rows.empty else 0
    materials = rows["materialCode"].nunique() if not rows.empty else 0
    columns = st.columns(4)
    columns[0].metric("SKU 总数", f"{len(rows):,}")
    columns[1].metric("启用", f"{active:,}")
    columns[2].metric("停用", f"{len(rows) - active:,}")
    columns[3].metric("已配置价格", f"{priced:,}")
    read_at = st.session_state.get(STATE_READ_AT)
    if read_at:
        st.caption(
            f"本页读取时间：{read_at:%Y-%m-%d %H:%M:%S}（纽约）｜"
            f"材质 {materials:,} 种"
        )


def _render_filters(rows):
    status = st.segmented_control(
        "SKU 状态",
        ["启用", "停用", "全部"],
        default="启用",
        key="fangguo_sku_catalog_status",
    )
    scoped = rows.copy()
    if status == "启用":
        scoped = scoped[scoped["skuActive"]]
    elif status == "停用":
        scoped = scoped[~scoped["skuActive"]]

    material_options = ordered_values(scoped["materialCode"])
    selected_materials = st.multiselect(
        "材质 / 商品",
        material_options,
        key="fangguo_sku_catalog_materials",
    )
    if selected_materials:
        scoped = scoped[scoped["materialCode"].isin(selected_materials)]

    first, second = st.columns(2)
    colors = first.multiselect(
        "颜色",
        ordered_values(scoped["colorCode"]),
        key="fangguo_sku_catalog_colors",
    )
    if colors:
        scoped = scoped[scoped["colorCode"].isin(colors)]
    models = second.multiselect(
        "型号 / 尺码",
        ordered_values(scoped["modelCode"], SIZE_COLUMNS),
        key="fangguo_sku_catalog_models",
    )
    if models:
        scoped = scoped[scoped["modelCode"].isin(models)]
    technologies = st.multiselect(
        "印花面 / 工艺",
        ordered_values(scoped["technologyName"]),
        key="fangguo_sku_catalog_technologies",
    )
    if technologies:
        scoped = scoped[scoped["technologyName"].isin(technologies)]
    return scoped.reset_index(drop=True)


def _render_table(rows):
    st.markdown("#### 批量价格调整范围")
    st.caption(f"当前筛选显示 {len(rows):,} 个 SKU")
    display = rows.rename(columns={
        "skuId": "方果 SKU ID",
        "materialCode": "材质 / 商品",
        "colorCode": "颜色",
        "modelCode": "型号 / 尺码",
        "technologyName": "印花面 / 工艺",
        "itemCode": "方果商品编码",
        "currentSkuPrice": "当前价格",
        "skuActive": "状态",
        "skuUpdatedAt": "方果更新时间",
    }).copy()
    display["状态"] = display["状态"].map({True: "启用", False: "停用"})
    display["方果更新时间"] = pd.to_datetime(
        display["方果更新时间"], unit="ms", errors="coerce", utc=True
    ).dt.tz_convert(NEW_YORK).dt.strftime("%Y-%m-%d %H:%M:%S")
    display = sort_sku_rows(
        display,
        material="材质 / 商品",
        color="颜色",
        size="型号 / 尺码",
    )
    visible = [
        "方果 SKU ID", "材质 / 商品", "颜色", "型号 / 尺码",
        "印花面 / 工艺", "方果商品编码", "当前价格", "状态", "方果更新时间",
    ]
    st.dataframe(
        display[visible],
        hide_index=True,
        width="stretch",
        height=min(800, 38 * (len(display) + 1) + 4),
        column_config={
            "当前价格": st.column_config.NumberColumn(format="$%.4f"),
        },
    )


def _render_download(rows):
    export = rows.rename(columns={
        "skuId": "方果SKU ID", "materialCode": "材质/商品",
        "colorCode": "颜色", "modelCode": "型号/尺码",
        "technologyName": "印花面/工艺", "itemCode": "方果商品编码",
        "currentSkuPrice": "当前价格", "skuActive": "是否启用",
        "skuUpdatedAt": "方果更新时间毫秒",
    })
    export = export[[
        "方果SKU ID", "材质/商品", "颜色", "型号/尺码",
        "印花面/工艺", "方果商品编码", "当前价格", "是否启用",
        "方果更新时间毫秒",
    ]]
    st.download_button(
        "下载当前筛选 CSV",
        export.to_csv(index=False).encode("utf-8-sig"),
        file_name="方果SKU当前价格.csv",
        mime="text/csv",
        key="fangguo_sku_catalog_download",
    )


def _save_refreshed_rows(rows):
    st.session_state[STATE_ROWS] = rows
    st.session_state[STATE_READ_AT] = datetime.now(NEW_YORK)


def _upgrade_cached_rows(rows):
    """Keep an older Streamlit session cache compatible with new SKU fields."""
    result = rows.copy()
    for field in ("technologyName", "itemCode"):
        if field not in result:
            result[field] = ""
        result[field] = result[field].fillna("").astype(str)
    if "sourcePayload" not in result:
        result["sourcePayload"] = None
    return result
