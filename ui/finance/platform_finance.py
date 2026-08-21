from datetime import timedelta

import pandas as pd
import streamlit as st

from automation.api.fangguo import (
    apply_current_sku_prices,
    build_customer_bill_summary,
    build_customer_bill_table,
    build_price_rule_table,
    fetch_fangguo_finance_lines,
    fetch_fangguo_sku_prices,
    load_fangguo_credentials,
    recalculate_fangguo_finance,
)
from ui.finance.bill_workbook import build_bill_workbook
from ui.finance.fangguo_sku_catalog import render_fangguo_sku_catalog


STATE_LINES = "finance_fangguo_lines"
STATE_RULES = "finance_fangguo_price_rules"
STATE_SKU_PRICES = "finance_fangguo_sku_prices"


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_fangguo(
    start_date, end_date, tenant_id, group_ids, _credentials,
):
    return fetch_fangguo_finance_lines(
        start_date, end_date, _credentials, list(group_ids)
    )


def render_platform_finance(report_date):
    st.caption(
        "订单可复用一小时缓存；方果当前 SKU 价格每次点击都会实时同步。"
        "按同步价格重算并导出核对，不会回写平台。"
    )
    reconciliation_tab, sku_tab = st.tabs(["方果订单重算", "方果 SKU 当前价格"])
    with reconciliation_tab:
        _render_fangguo(report_date)
    with sku_tab:
        credentials = _credentials_or_error()
        if credentials is not None:
            render_fangguo_sku_catalog(credentials)


def _render_fangguo(report_date):
    credentials = _credentials_or_error()
    if credentials is None:
        return
    defaults = credentials.get("finance_group_ids") or []
    first, second = st.columns(2)
    with first:
        start_date = st.date_input(
            "计费开始日期", report_date - timedelta(days=30),
            key="fangguo_finance_start",
        )
    with second:
        end_date = st.date_input(
            "计费结束日期", report_date,
            key="fangguo_finance_end",
        )
    groups = _parse_group_ids(defaults)
    st.info("当前平台对账范围：隆丰、Haloo")
    query_signature = (
        "fixed-accounts-v2",
        str(credentials.get("tenant_id") or ""),
        str(start_date), str(end_date), tuple(groups),
    )
    saved_signature = st.session_state.get("fangguo_finance_query_signature")
    if isinstance(st.session_state.get(STATE_LINES), pd.DataFrame) and (
        saved_signature != query_signature
    ):
        _clear_fangguo_result_state()

    actions = st.columns(2)
    load_clicked = actions[0].button(
        "读取订单（优先使用缓存）",
        type="primary",
        key="fangguo_finance_fetch",
    )
    refresh_clicked = actions[1].button(
        "强制刷新方果数据",
        key="fangguo_finance_force_refresh",
    )
    if load_clicked or refresh_clicked:
        try:
            status = st.empty()
            if refresh_clicked:
                _cached_fetch_fangguo.clear()
            with st.spinner("正在读取方果平台财务..."):
                status.info(
                    "正在强制刷新方果数据"
                    if refresh_clicked else "正在读取订单缓存或方果数据"
                )
                lines = _cached_fetch_fangguo(
                    start_date,
                    end_date,
                    str(credentials.get("tenant_id") or ""),
                    tuple(groups),
                    credentials,
                )
                sku_prices = fetch_fangguo_sku_prices(
                    credentials,
                    material_ids=_configured_ids(
                        credentials, "finance_sku_material_ids"
                    ),
                    color_ids=_configured_ids(
                        credentials, "finance_sku_color_ids"
                    ),
                    report_progress=status.info,
                )
            st.session_state[STATE_LINES] = lines
            st.session_state[STATE_SKU_PRICES] = sku_prices
            st.session_state["fangguo_finance_query_signature"] = query_signature
            st.session_state[STATE_RULES] = apply_current_sku_prices(
                build_price_rule_table(lines), sku_prices
            )
            _clear_fangguo_calculation_state()
            status.success(
                f"已读取 {len(lines):,} 行平台订单；"
                f"实时同步 {len(sku_prices):,} 行方果当前 SKU 价格"
            )
        except Exception as error:
            st.error(f"方果平台财务读取失败：{error}")

    lines = st.session_state.get(STATE_LINES)
    if not isinstance(lines, pd.DataFrame):
        st.info("选择日期后读取隆丰和 Haloo 订单。")
        return
    if lines.empty:
        st.warning("当前范围没有找到订单。")
        return
    filtered = _render_account_filter(lines)
    filtered = _render_material_filter(filtered, credentials)
    if filtered.empty:
        st.warning("所选账户和商品范围没有订单。")
        return
    _render_source_summary(filtered)
    _render_source_orders(filtered)
    _render_recalculation(filtered)


def _render_account_filter(lines):
    accounts = ["隆丰", "Haloo"]
    state_key = "fangguo_finance_accounts"
    if state_key not in st.session_state:
        st.session_state[state_key] = accounts
    else:
        st.session_state[state_key] = [
            value for value in st.session_state[state_key]
            if value in accounts
        ]
    selected = st.multiselect(
        "当前对账账户", accounts, key=state_key,
    )
    if not selected:
        return lines.iloc[0:0].copy()
    names = lines.get("shopName", pd.Series("", index=lines.index)).fillna("").astype(str)
    codes = lines.get("shopCode", pd.Series("", index=lines.index)).fillna("").astype(str)
    mask = pd.Series(False, index=lines.index)
    if "隆丰" in selected:
        mask |= names.str.startswith("隆丰")
    if "Haloo" in selected:
        mask |= (names == "海捞") | (codes.str.casefold() == "haloo")
    return lines[mask].copy()


def _clear_fangguo_result_state():
    st.session_state.pop(STATE_LINES, None)
    st.session_state.pop(STATE_RULES, None)
    st.session_state.pop(STATE_SKU_PRICES, None)
    st.session_state.pop("fangguo_finance_query_signature", None)
    _clear_fangguo_calculation_state()


def _clear_fangguo_calculation_state():
    st.session_state.pop("finance_fangguo_result", None)
    st.session_state.pop("fangguo_finance_materials", None)
    st.session_state.pop("fangguo_finance_rule_editor_material", None)
    st.session_state.pop("fangguo_finance_rule_editor_material_model", None)


def _render_source_summary(lines):
    order_count = lines.get("tid", pd.Series(dtype=str)).nunique()
    quantity = pd.to_numeric(lines.get("quantity"), errors="coerce").fillna(0).sum()
    material = pd.to_numeric(lines.get("caseAmount"), errors="coerce").fillna(0).sum()
    total = pd.to_numeric(lines.get("totalAmount"), errors="coerce").fillna(0).sum()
    columns = st.columns(4)
    columns[0].metric("订单数", f"{order_count:,}")
    columns[1].metric("商品数量", f"{quantity:,.0f}")
    columns[2].metric("原材料费", f"${material:,.4f}")
    columns[3].metric("平台原总金额", f"${total:,.4f}")


def _render_material_filter(lines, credentials):
    if "materialCode" not in lines:
        return lines
    materials = sorted(
        value for value in lines["materialCode"].dropna().astype(str).unique()
        if value.strip()
    )
    configured = credentials.get("finance_material_names") or []
    if isinstance(configured, str):
        configured = [configured]
    configured = [str(value).casefold() for value in configured]
    matched_defaults = [
        material for material in materials
        if any(term in material.casefold() for term in configured)
    ]
    state_key = "fangguo_finance_materials"
    if state_key not in st.session_state:
        st.session_state[state_key] = matched_defaults or materials
    else:
        st.session_state[state_key] = [
            value for value in st.session_state[state_key]
            if value in materials
        ]
    selected = st.multiselect(
        "商品 / 材质",
        materials,
        key=state_key,
    )
    if not selected:
        return lines.iloc[0:0].copy()
    return lines[lines["materialCode"].astype(str).isin(selected)].copy()


def _render_source_orders(lines):
    st.markdown("#### 平台订单明细")
    st.caption("订单读取完成后立即显示；无需先填写新价格或生成重算预览。")
    display = lines.copy()
    if "transactionTime" in display:
        display["transactionTime"] = pd.to_datetime(
            display["transactionTime"], unit="ms", errors="coerce", utc=True
        ).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M:%S")
    display = display.rename(columns={
        "transactionTime": "计费时间", "shopName": "客户",
        "shopCode": "客户编号", "tid": "订单号",
        "materialCode": "商品 / 材质", "colorCode": "颜色",
        "modelCode": "型号",
        "quantity": "商品数量", "caseAmount": "材料费",
        "totalAmount": "总金额", "dfStatusStr": "订单状态",
        "platform": "平台", "storeName": "店铺",
    })
    columns = [
        "计费时间", "客户", "客户编号", "订单号", "订单状态",
        "商品 / 材质", "颜色", "型号", "商品数量",
        "材料费", "总金额", "平台", "店铺",
    ]
    st.dataframe(
        display[[column for column in columns if column in display]],
        hide_index=True,
        use_container_width=True,
    )


def _render_recalculation(lines):
    st.markdown("#### 1. 核对并填写新价格")
    price_by_model = st.checkbox(
        "按型号分别定价",
        value=False,
        key="fangguo_finance_price_by_model",
        help="关闭时同一商品使用一个价格；开启后可为每个型号分别填写价格。",
    )
    rule_fields = ["materialCode", "modelCode"] if price_by_model else ["materialCode"]
    mode = "material_model" if price_by_model else "material"
    if st.session_state.get("fangguo_finance_price_mode") != mode:
        st.session_state["fangguo_finance_price_mode"] = mode
        st.session_state.pop("finance_fangguo_result", None)
    st.caption(
        "你可以决定型号是否参与定价；颜色和商品规格不参与价格规则。留空维持原材料费。"
    )
    st.info(
        "“订单历史单价”是订单发生时的材料费；“方果当前 SKU 价格”来自 SKU 管理页。"
        "同一规则只有一个当前价格时会自动填入；出现多个价格时保留为空，需人工确认。"
    )
    source_rules = st.session_state.get(STATE_RULES)
    source_rules = _normalize_price_rules(
        lines,
        source_rules,
        rule_fields,
        st.session_state.get(STATE_SKU_PRICES),
    )
    active_keys = lines[rule_fields].fillna("").astype(str).drop_duplicates()
    visible_rules = active_keys.merge(
        source_rules, how="left",
        on=rule_fields,
    )
    edited = st.data_editor(
        visible_rules,
        hide_index=True,
        use_container_width=True,
        disabled=[
            *rule_fields, "currentUnitPrice", "fangguoSkuPrice",
        ],
        column_config={
            "materialCode": "商品 / 材质",
            "modelCode": "型号",
            "currentUnitPrice": "订单历史单价（可能含错价）",
            "fangguoSkuPrice": "方果当前 SKU 价格",
            "newUnitPrice": st.column_config.NumberColumn(
                "新材料单价", min_value=0.0, format="$%.4f"
            ),
        },
        key=f"fangguo_finance_rule_editor_{mode}",
    )
    if st.button("生成重算预览", key="fangguo_finance_recalculate"):
        st.session_state[STATE_RULES] = _merge_rule_edits(
            source_rules, edited, rule_fields
        )
        st.session_state["finance_fangguo_result"] = recalculate_fangguo_finance(
            lines, edited, rule_fields
        )

    result = st.session_state.get("finance_fangguo_result")
    if not isinstance(result, pd.DataFrame):
        return
    result = _limit_result_to_lines(result, lines)
    _render_result(result, price_by_model)


def _render_result(result, price_by_model):
    st.markdown("#### 2. 重算差额预览")
    changed = result[result["difference"].abs() > 0.00005].copy()
    unapplied = int((~result["priceRuleApplied"]).sum())
    old_total = result["totalAmount"].sum()
    new_total = result["recalculatedTotalAmount"].sum()
    columns = st.columns(4)
    columns[0].metric("受影响订单行", f"{len(changed):,}")
    columns[1].metric("未填写新价", f"{unapplied:,}")
    columns[2].metric("重算后总金额", f"${new_total:,.4f}")
    columns[3].metric("应调整差额", f"${new_total - old_total:,.4f}")
    if unapplied:
        st.warning(f"仍有 {unapplied:,} 行未匹配新价格，将维持平台原材料费。")

    _render_customer_bills(result, price_by_model)

    st.caption("计算口径：重算后总金额 = 平台原总金额 - 原材料费 + 商品数量 × 新材料单价。")


def _render_customer_bills(result, price_by_model):
    st.markdown("#### Haloo / 隆丰对账单")
    summary = build_customer_bill_summary(result)
    if summary.empty:
        st.warning("当前订单中没有可生成的 Haloo 或隆丰账单。")
        return
    for account in ("Haloo", "隆丰"):
        account_summary = summary[summary["customerAccount"] == account]
        if account_summary.empty:
            continue
        st.markdown(f"##### {account} Bill")
        bill = build_customer_bill_table(
            result, account, include_model=price_by_model
        )
        bill_display = bill.rename(columns={
            "materialCode": "商品 / 材质", "modelCode": "型号",
            "orderCount": "订单数", "quantity": "商品数量",
            "newUnitPrice": "正确单价",
            "originalMaterialAmount": "原材料费",
            "originalAmount": "原账单金额",
            "recalculatedAmount": "重算后金额", "amountDue": "应补金额",
        })
        if not price_by_model:
            bill_display = bill_display.drop(columns="型号")
        st.dataframe(
            bill_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "原账单金额": st.column_config.NumberColumn(format="%.4f"),
                "重算后金额": st.column_config.NumberColumn(format="%.4f"),
                "应补金额": st.column_config.NumberColumn(format="%.4f"),
            },
        )
        detail = _bill_detail(result, account)
        workbook = build_bill_workbook(account, bill_display, detail)
        st.download_button(
            f"下载 {account} Bill Excel",
            data=workbook,
            file_name=f"{account}_Bill.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=f"fangguo_bill_download_{account}",
        )
        st.caption("Excel 第1页为 Bill汇总，第2页为平台订单明细。")


def _bill_detail(result, account):
    names = result.get("shopName", pd.Series(dtype=str)).fillna("").astype(str)
    codes = result.get("shopCode", pd.Series("", index=result.index)).fillna("").astype(str)
    if account == "Haloo":
        selected = result[(names == "海捞") | (codes.str.casefold() == "haloo")]
    else:
        selected = result[names.str.startswith("隆丰")]
    return selected.rename(columns={
        "transactionTime": "计费时间", "shopName": "客户", "tid": "订单号",
        "materialCode": "商品 / 材质", "quantity": "数量",
        "caseAmount": "原材料费", "newUnitPrice": "新单价",
        "recalculatedCaseAmount": "重算材料费",
        "totalAmount": "原账单金额", "difference": "还应付给我",
        "recalculatedTotalAmount": "重算后金额",
    })[[
        "计费时间", "客户", "订单号", "商品 / 材质", "数量", "原材料费",
        "新单价", "重算材料费", "原账单金额", "还应付给我", "重算后金额",
    ]]


def _credentials_or_error():
    try:
        credentials = load_fangguo_credentials(st.secrets)
        defaults = credentials.get("finance_customer_names") or []
        if isinstance(defaults, str):
            defaults = [defaults]
        st.session_state["fangguo_finance_default_customers"] = [
            str(value) for value in defaults
        ]
        return credentials
    except Exception as error:
        st.error(f"方果凭据未配置：{error}")
        return None


def _parse_group_ids(value):
    if isinstance(value, (list, tuple, set)):
        pieces = list(value)
    else:
        normalized = str(value).strip().removeprefix("[").removesuffix("]")
        pieces = normalized.replace("，", ",").split(",")
    groups = [str(piece).strip() for piece in pieces if str(piece).strip()]
    if not groups:
        return []
    if any(not piece.isdigit() for piece in groups):
        raise ValueError("客户分组 ID 必须是数字，多个 ID 用逗号分隔")
    return [int(piece) for piece in groups]


def _merge_rule_edits(source, edits, rule_fields):
    remaining = source.merge(
        edits[rule_fields], on=rule_fields, how="left", indicator=True
    )
    remaining = remaining[remaining["_merge"] == "left_only"].drop(columns="_merge")
    return pd.concat([remaining, edits], ignore_index=True)


def _normalize_price_rules(lines, saved_rules, rule_fields, sku_prices=None):
    fresh = build_price_rule_table(lines, rule_fields)
    if isinstance(sku_prices, pd.DataFrame):
        fresh = apply_current_sku_prices(fresh, sku_prices, rule_fields)
    if not isinstance(saved_rules, pd.DataFrame):
        return fresh
    if any(field not in saved_rules for field in rule_fields):
        return fresh
    if "newUnitPrice" not in saved_rules:
        return fresh
    saved = saved_rules[[*rule_fields, "newUnitPrice"]].copy()
    for field in rule_fields:
        saved[field] = saved[field].fillna("").astype(str)
    saved["newUnitPrice"] = pd.to_numeric(saved["newUnitPrice"], errors="coerce")
    saved = saved.dropna(subset=["newUnitPrice"]).drop_duplicates(
        subset=rule_fields, keep="last"
    )
    return fresh.drop(columns="newUnitPrice").merge(
        saved, on=rule_fields, how="left", validate="one_to_one"
    )[[
        *rule_fields, "currentUnitPrice",
        *(["fangguoSkuPrice"] if "fangguoSkuPrice" in fresh else []),
        "newUnitPrice",
    ]]


def _configured_ids(credentials, key):
    return _parse_group_ids(credentials.get(key) or [])


def _limit_result_to_lines(result, lines):
    order_ids = set(lines.get("tid", pd.Series(dtype=str)).astype(str))
    return result[result.get("tid", pd.Series(dtype=str)).astype(str).isin(order_ids)]
