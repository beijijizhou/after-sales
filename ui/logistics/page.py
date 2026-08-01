from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.logistics import (
    S2BAuthenticationError,
    S2BLocalLoginRequired,
    USPSClient,
    classify_carrier,
    classify_usps_subtype,
    classify_usps_response,
    fetch_s2b_pending_shipments,
    fetch_sds_pending_shipments,
    load_s2b_account,
    load_sds_account,
    load_usps_credentials,
    local_login_available,
    refresh_local_s2b_token,
    usps_pickup_name,
)
from db.logistics import (
    load_latest_tracking_checks,
    load_shipments,
    save_tracking_checks,
    upsert_shipments,
)
from utils.auth import get_current_operator_name, has_permission
from ui.logistics.tracking_lookup import render_tracking_lookup
from ui.logistics.reverse_lookup import render_reverse_lookup


SOURCES = ("SDS1", "SDS2", "S2B UV", "S2B DTF")
ORDER_STAGES = {
    "待排产/未接单": 1,
    "生产中": 2,
    "已完成/已发货": 6,
}


def render_logistics_page(supabase):
    st.title("物流订单核查")
    st.caption(
        "从ERP各订单阶段获取物流关系，支持订单正查、物流单号反查、"
        "USPS状态与面单OCR审核。"
    )
    sync_tab, lookup_tab, reverse_tab, search_tab, rules_tab = st.tabs([
        "ERP订单获取", "订单物流核查", "物流单号反查",
        "数据库查询", "审核规则",
    ])
    with sync_tab:
        _render_sync(supabase)
    with search_tab:
        _render_search(supabase)
    with lookup_tab:
        render_tracking_lookup(supabase, _database_error)
    with reverse_tab:
        render_reverse_lookup(supabase, _database_error)
    with rules_tab:
        _render_rules()


def _render_sync(supabase):
    st.subheader("从ERP读取订单与物流单号")
    refresh_cache = st.button(
        "刷新数据库缓存", key="logistics_refresh_database_cache"
    )
    cached = _load_cached_shipments(supabase, force=refresh_cache)
    _render_cache_status(cached)
    if cached is not None:
        cached_review = _classify_carrier_rows(cached.to_dict("records"))
        st.session_state["logistics_carrier_review_rows"] = cached_review
        _sync_tracking_lookup_from_cache(cached, cached_review)
    selected = st.multiselect("数据来源", SOURCES, default=["SDS2"])
    stage = st.selectbox("订单阶段", list(ORDER_STAGES))
    date_columns = st.columns(2)
    start_date = date_columns[0].date_input(
        "开始日期", value=date.today() - timedelta(days=1),
    )
    end_date = date_columns[1].date_input("结束日期", value=date.today())
    _render_s2b_connection_status(selected)
    show_carrier_review = bool(selected)
    if not st.button(
        "从ERP拉取并更新缓存", type="primary", disabled=not selected,
        width="stretch",
    ):
        _render_carrier_review(show_carrier_review)
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有同步物流数据的权限。")
        return
    all_rows, errors, carrier_review_rows = [], [], []
    progress = st.progress(0)
    for index, source in enumerate(selected, start=1):
        try:
            rows = _fetch_source(source, stage, start_date, end_date)
            for row in rows:
                row["local_acceptance_status"] = stage
            reviewed = _classify_carrier_rows(rows)
            carrier_review_rows.extend(reviewed)
            usps_rows = [
                item["row"] for item in reviewed
                if _is_target_usps_review(item)
            ]
            all_rows.extend(usps_rows)
            st.write(
                f"{source}：读取 {len(rows):,} 条｜"
                f"USPS {len(usps_rows):,} 条｜"
                f"已过滤 {len(rows) - len(usps_rows):,} 条"
            )
        except Exception as error:
            errors.append(f"{source}：{error}")
        progress.progress(index / len(selected))
    if all_rows:
        _queue_tracking_lookup_rows(all_rows)
        try:
            saved = upsert_shipments(supabase, all_rows)
            st.success(f"已保存/更新 {len(saved):,} 条订单面单关系。")
            cached = _load_cached_shipments(supabase, force=True)
            if cached is not None:
                st.session_state["logistics_carrier_review_rows"] = (
                    _classify_carrier_rows(cached.to_dict("records"))
                )
        except Exception as error:
            st.error(_database_error(error))
    if errors:
        st.warning("；".join(errors))
    _render_carrier_review(show_carrier_review)


def _load_cached_shipments(supabase, force=False):
    key = "logistics_saved_shipments"
    if not force and key in st.session_state:
        return st.session_state[key]
    try:
        frame = load_shipments(supabase)
    except Exception as error:
        st.info(_database_error(error))
        return None
    st.session_state[key] = frame
    return frame


def _cache_status(frame):
    if frame is None or frame.empty or "last_seen_at" not in frame:
        return {"count": 0, "stored_at": "暂无缓存"}
    timestamps = pd.to_datetime(frame["last_seen_at"], errors="coerce", utc=True)
    latest = timestamps.max()
    if pd.isna(latest):
        stored_at = "时间未知"
    else:
        stored_at = latest.tz_convert(ZoneInfo("America/New_York")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return {"count": len(frame), "stored_at": stored_at}


def _render_cache_status(frame):
    status = _cache_status(frame)
    columns = st.columns(2)
    columns[0].metric("数据库缓存订单", f"{status['count']:,} 条")
    columns[1].metric("最近存储时间（纽约）", status["stored_at"])
    st.caption(
        "下方物流识别核对表直接使用数据库缓存；仅在需要更新时再从ERP拉取。"
    )


def _classify_carrier_rows(rows):
    reviewed = []
    for row in rows:
        carrier_family = classify_carrier(
            row.get("carrier"), row.get("tracking_number")
        )
        usps_subtype = classify_usps_subtype(
            row.get("carrier"), row.get("tracking_number"),
            row.get("source_payload"),
        )
        reviewed.append({
            "平台": row.get("erp_platform", ""),
            "账号": row.get("erp_account", ""),
            "Order ID": row.get("external_order_id", ""),
            "Tracking Number": row.get("tracking_number", ""),
            "平台物流方式": row.get("carrier", ""),
            "系统判断": carrier_family,
            "USPS子类型": usps_subtype,
            "实际揽收方": usps_pickup_name(usps_subtype),
            "面单": row.get("label_url"),
            "备用面单": row.get("backup_label_url"),
            "row": row,
        })
    return reviewed


def _is_target_usps_review(item):
    return (
        item.get("系统判断") == "USPS"
        and item.get("USPS子类型") == "普通USPS"
    )


def _queue_tracking_lookup_rows(rows):
    imported = _tracking_lookup_import_rows(rows)
    st.session_state["logistics_tracking_lookup_import_rows"] = imported
    st.session_state["logistics_tracking_lookup_editor_revision"] = (
        int(st.session_state.get(
            "logistics_tracking_lookup_editor_revision", 0
        )) + 1
    )


def _sync_tracking_lookup_from_cache(frame, reviewed=None):
    signature = _shipment_cache_signature(frame)
    if st.session_state.get("logistics_tracking_lookup_cache_signature") == signature:
        return
    reviewed = reviewed or _classify_carrier_rows(frame.to_dict("records"))
    target_rows = [item["row"] for item in reviewed if _is_target_usps_review(item)]
    _queue_tracking_lookup_rows(target_rows)
    st.session_state["logistics_tracking_lookup_cache_signature"] = signature


def _shipment_cache_signature(frame):
    if frame is None or frame.empty:
        return "empty"
    latest = ""
    if "last_seen_at" in frame:
        timestamps = pd.to_datetime(frame["last_seen_at"], errors="coerce", utc=True)
        if not timestamps.dropna().empty:
            latest = timestamps.max().isoformat()
    return f"{len(frame)}:{latest}"


def _tracking_lookup_import_rows(rows):
    imported = []
    seen = set()
    for row in rows:
        item = {
            "ERP": str(row.get("erp_platform") or "").strip(),
            "账号": str(row.get("erp_account") or "").strip(),
            "部门": str(row.get("department") or "").strip(),
            "订单号": str(row.get("external_order_id") or "").strip(),
            "物流单号": str(row.get("tracking_number") or "").strip(),
            "ERP状态": str(row.get("erp_status") or "").strip(),
            "订单阶段": str(
                row.get("local_acceptance_status") or ""
            ).strip(),
        }
        identity = (
            item["ERP"], item["账号"], item["订单号"], item["物流单号"],
        )
        if item["物流单号"] and identity not in seen:
            imported.append(item)
            seen.add(identity)
    return imported


def _render_carrier_review(show_empty=False):
    rows = st.session_state.get(
        "logistics_carrier_review_rows",
        st.session_state.get("s2b_carrier_review_rows", []),
    )
    if not rows and not show_empty:
        return
    st.subheader("物流识别核对")
    carrier_names = (
        "USPS", "GOFO", "FedEx", "UPS", "UniUni", "SwiftX",
        "其他待确认",
    )
    filter_columns = st.columns(4)
    selected_carriers = []
    for index, name in enumerate(carrier_names):
        if filter_columns[index % len(filter_columns)].checkbox(
            name, value=name == "USPS",
            key=f"logistics_carrier_checkbox_{name}"
        ):
            selected_carriers.append(name)
    if not rows:
        st.info("数据库缓存为空；可从ERP拉取数据后更新核对表。")
        return
    counts = pd.Series([
        row["系统判断"] for row in rows
        if row["系统判断"] != "USPS" or _is_target_usps_review(row)
    ]).value_counts()
    excluded_usps = sum(
        row.get("USPS子类型") in {"CBS", "CBT"} for row in rows
    )
    st.caption(
        "｜".join(
            f"{name} {int(counts.get(name, 0)):,} 条"
            for name in carrier_names
        )
        + (f"｜已排除 CBS/CBT {excluded_usps:,} 条" if excluded_usps else "")
    )
    display = pd.DataFrame([
        {key: value for key, value in row.items() if key != "row"}
        for row in rows
        if row["系统判断"] in selected_carriers
        and (row["系统判断"] != "USPS" or _is_target_usps_review(row))
    ])
    if display.empty:
        st.info("当前没有勾选物流商的匹配记录。")
    else:
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config={
                "面单": st.column_config.LinkColumn(display_text="打开面单"),
                "备用面单": st.column_config.LinkColumn(
                    display_text="备用面单"
                ),
            },
        )
    st.caption(
        "只有普通 USPS 会写入物流数据库；CBS（GOFO揽收）和"
        "CBT（TikTok指定物流商揽收）会自动排除。"
    )


def _fetch_source(source, stage, start_date, end_date):
    status = ORDER_STAGES[stage]
    if source.startswith("SDS"):
        profile = "1号线" if source == "SDS1" else "2号线"
        return fetch_sds_pending_shipments(
            profile, load_sds_account(st.secrets, profile), 100,
            status=status,
            time_range=_erp_time_range(start_date, end_date),
        )
    account = "UV" if source == "S2B UV" else "DTF"
    credentials = _s2b_credentials(account)
    try:
        return fetch_s2b_pending_shipments(
            account, credentials, status=status
        )
    except S2BAuthenticationError:
        return _refresh_and_fetch_s2b(account, status)


def _erp_time_range(start_date, end_date):
    return {
        "startTime": datetime.combine(
            start_date, datetime.min.time()
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": datetime.combine(
            end_date, datetime.max.time()
        ).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _s2b_credentials(account):
    token = st.session_state.get("logistics_s2b_tokens", {}).get(account)
    if token:
        return {"token": token}
    try:
        return load_s2b_account(st.secrets, account)
    except ValueError:
        if not local_login_available():
            raise
        return {"token": _refresh_s2b_session(account)}


def _refresh_and_fetch_s2b(account, status=1):
    token = _refresh_s2b_session(account)
    return fetch_s2b_pending_shipments(
        account, {"token": token}, status=status
    )


def _refresh_s2b_session(account):
    token = refresh_local_s2b_token(account)
    tokens = dict(st.session_state.get("logistics_s2b_tokens", {}))
    tokens[account] = token
    st.session_state["logistics_s2b_tokens"] = tokens
    return token


def _render_s2b_connection_status(selected):
    accounts = [
        "UV" if source == "S2B UV" else "DTF"
        for source in selected if source.startswith("S2B")
    ]
    if not accounts:
        return
    if local_login_available():
        st.caption(
            "本地模式：首次登录后会复用专用Chrome会话并直接调用API；"
            "只有登录状态失效时才需要重新登录或滑块验证。"
        )
    else:
        st.caption("云端模式：S2B账号由服务器Secrets或本地连接器提供。")


def _render_current_shipments(supabase):
    st.caption("数据库记录是同步后持久保存的数据；刷新页面不会重复新增。")
    if st.button(
        "加载数据库现有记录", key="logistics_load_saved_shipments"
    ):
        try:
            st.session_state["logistics_saved_shipments"] = load_shipments(
                supabase
            )
        except Exception as error:
            st.info(_database_error(error))
            return
    frame = st.session_state.get("logistics_saved_shipments")
    if frame is None:
        return
    if not frame.empty:
        st.caption(f"数据库已保存订单物流关系：{len(frame):,} 条")
        _render_rows(frame.head(200))
    else:
        st.info("数据库当前没有订单物流关系。")


def _render_search(supabase):
    st.subheader("按Order ID或Tracking Number查面单")
    query = st.text_area(
        "查询内容", placeholder="每行一个Order ID或Tracking Number"
    )
    try:
        frame = load_shipments(supabase)
    except Exception as error:
        st.info(_database_error(error))
        return
    terms = {line.strip() for line in query.replace(",", "\n").splitlines() if line.strip()}
    if terms:
        match = (
            frame["external_order_id"].astype(str).isin(terms)
            | frame["merchant_order_id"].astype(str).isin(terms)
            | frame["tracking_number"].astype(str).isin(terms)
        )
        frame = frame[match]
    _render_rows(frame)


def _render_usps(supabase):
    st.subheader("USPS预扫描合规检查")
    raw = st.text_area(
        "Tracking Number", placeholder="每行一个；优先使用数据库缓存"
    )
    numbers = list(dict.fromkeys(
        line.strip() for line in raw.replace(",", "\n").splitlines()
        if line.strip()
    ))
    force = st.checkbox("忽略缓存，强制向USPS重新查询")
    if not st.button("开始检查", disabled=not numbers, type="primary"):
        return
    try:
        latest = load_latest_tracking_checks(supabase, numbers)
    except Exception as error:
        st.error(_database_error(error))
        return
    cached, pending = _split_cache(numbers, latest, force)
    fresh_rows = []
    if pending:
        try:
            credentials = load_usps_credentials(st.secrets)
            client = USPSClient(
                credentials["client_id"], credentials["client_secret"]
            )
            for start in range(0, len(pending), 35):
                fresh_rows.extend(
                    classify_usps_response(item)
                    for item in client.track(pending[start:start + 35])
                )
            save_tracking_checks(
                supabase, fresh_rows, get_current_operator_name()
            )
        except Exception as error:
            st.error(f"USPS检查失败：{error}")
            return
    st.caption(
        f"数据库缓存 {len(cached):,} 个｜本次调用USPS {len(pending):,} 个"
    )
    display = pd.concat([cached, pd.DataFrame(fresh_rows)], ignore_index=True)
    if display.empty:
        st.info("没有可显示的USPS结果。")
        return
    display["审核判断"] = display["has_pre_scan"].map({
        True: "不合规：已有USPS记录/预扫描", False: "未发现USPS记录",
    })
    st.dataframe(
        display[[
            "tracking_number", "provider_status", "has_pre_scan", "审核判断"
        ]], hide_index=True, width="stretch",
    )


def _split_cache(numbers, latest, force):
    if force or latest.empty:
        return pd.DataFrame(), numbers
    frame = latest.copy()
    expiry = pd.to_datetime(frame["cache_expires_at"], errors="coerce", utc=True)
    fresh = frame[expiry > datetime.now(timezone.utc)]
    cached_numbers = set(fresh["tracking_number"].astype(str))
    return fresh, [number for number in numbers if number not in cached_numbers]


def _render_rules():
    st.subheader("当前面单审核规则")
    st.write("寄件街道：25 Ryanic Road")
    st.write("寄件州：New York")
    st.write("USPS状态：不能已有Pre-Shipment、Pre-Scan或后续记录")
    st.write("单件衣服参考重量：3–4 oz或略高；明显达到磅级进入调查")
    st.info(
        "地址和重量来自平台面单PDF OCR；平台未提供面单下载时会明确标记无法获取。"
    )


def _render_rows(frame):
    if frame.empty:
        st.info("当前没有匹配的面单记录。")
        return
    display = frame.rename(columns={
        "erp_platform": "ERP", "erp_account": "账号",
        "department": "部门", "external_order_id": "Order ID",
        "merchant_order_id": "销售订单号", "tracking_number": "Tracking Number",
        "carrier": "物流商", "erp_status": "ERP状态",
        "label_url": "面单PDF", "backup_label_url": "备用面单PDF",
        "local_acceptance_status": "接单状态",
    })
    columns = [
        "ERP", "账号", "部门", "Order ID", "销售订单号",
        "Tracking Number", "物流商", "ERP状态", "接单状态",
        "面单PDF", "备用面单PDF",
    ]
    st.dataframe(
        display[[column for column in columns if column in display]],
        hide_index=True, width="stretch",
        column_config={
            "面单PDF": st.column_config.LinkColumn(display_text="打开面单"),
            "备用面单PDF": st.column_config.LinkColumn(display_text="备用面单"),
        },
    )


def _database_error(error):
    if "logistics_" in str(error) and (
        "does not exist" in str(error) or "schema cache" in str(error)
    ):
        return "物流数据库尚未初始化，请先运行 sql/logistics/01_shipping_label_review.sql。"
    return f"物流数据库操作失败：{error}"
