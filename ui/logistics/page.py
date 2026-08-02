from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from time import perf_counter
from zoneinfo import ZoneInfo
import sys

import pandas as pd
import streamlit as st

from automation.logistics import (
    S2BAuthenticationError,
    S2BLocalLoginRequired,
    classify_carrier,
    classify_usps_subtype,
    fetch_diy19_shipments,
    fetch_s2b_pending_shipments,
    fetch_sds_pending_shipments,
    load_s2b_account,
    load_diy19_logistics_credentials,
    load_sds_account,
    local_login_available,
    parse_logistics_frame,
    refresh_local_s2b_token,
    usps_pickup_name,
)
from automation.production import (
    PLATFORMS_BY_DEPARTMENT,
    PRODUCTION_DEPARTMENTS,
)
from automation.logistics.label_cache import (
    cached_label_content as _cached_label_content,
    cached_label_fields as _cached_label_fields,
    get_cached_label_fields,
)
from automation.logistics.label_downloads import build_label_archive
from utils.auth import has_permission
from ui.logistics.tracking_lookup import render_tracking_lookup


LOGISTICS_CONNECTED_PLATFORMS = {
    "S2B", "SDS1", "SDS2", "七创", "一朵云",
}
ORDER_STAGES = {
    "待排产/未接单": 1,
    "生产中": 2,
    "已完成/已发货": 6,
}
LABEL_OCR_CACHE_VERSION = 4
def render_logistics_page(supabase):
    st.title("物流订单核查")
    st.caption(
        "从ERP实时获取物流关系，并通过USPS接口核查Tracking Events与始发地点。"
    )
    review_tab, rules_tab = st.tabs([
        "物流单号获取与USPS核查", "审核规则",
    ])
    with review_tab:
        _render_sync(supabase)
        st.divider()
        render_tracking_lookup(
            supabase,
            _database_error,
            st.session_state.get("logistics_usps_candidates", []),
        )
    with rules_tab:
        _render_rules()


def _render_sync(supabase):
    auto_tab, upload_tab = st.tabs([
        "从ERP自动读取", "复制粘贴订单物流",
    ])
    with auto_tab:
        _render_erp_sync(supabase)
    with upload_tab:
        _render_upload_sync()
    st.divider()
    _render_carrier_review(True)


def _render_erp_sync(supabase):
    st.subheader("从ERP读取订单与物流单号")
    filter_columns = st.columns(2)
    department = filter_columns[0].selectbox(
        "部门", PRODUCTION_DEPARTMENTS, key="logistics_department"
    )
    platforms = tuple(PLATFORMS_BY_DEPARTMENT.get(department, ()))
    selected = filter_columns[1].multiselect(
        "生产平台",
        platforms,
        default=_default_logistics_platforms(platforms),
        key=f"logistics_platforms_{department}",
    )
    connected = [
        platform for platform in platforms
        if platform in LOGISTICS_CONNECTED_PLATFORMS
    ]
    st.caption(
        f"{department} 已配置平台：{'、'.join(platforms) or '暂无'}｜"
        f"已接入物流接口：{'、'.join(connected) or '暂无'}"
    )
    stage = st.selectbox("订单阶段", list(ORDER_STAGES))
    date_columns = st.columns(2)
    start_date = date_columns[0].date_input(
        "开始日期", value=date.today() - timedelta(days=1),
    )
    end_date = date_columns[1].date_input("结束日期", value=date.today())
    _render_s2b_connection_status(selected)
    if not st.button(
        "从ERP读取数据", type="primary", disabled=not selected,
        width="stretch",
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有同步物流数据的权限。")
        return
    all_rows, errors, carrier_review_rows = [], [], []
    progress = st.progress(0)
    for index, source in enumerate(selected, start=1):
        try:
            rows = _fetch_source(
                source, department, stage, start_date, end_date
            )
            for row in rows:
                row["local_acceptance_status"] = stage
                row["department"] = department
            reviewed = _classify_carrier_rows(rows)
            carrier_review_rows.extend(reviewed)
            usps_rows = [
                item["row"] for item in reviewed
                if _is_target_usps_review(item)
            ]
            all_rows.extend(usps_rows)
            label_count = len(_label_ocr_candidates(reviewed))
            status_text = (
                f"{source}：读取 {len(rows):,} 条｜"
                f"USPS {len(usps_rows):,} 条｜"
                f"可下载面单 {label_count:,} 张｜"
                f"已过滤 {len(rows) - len(usps_rows):,} 条"
            )
            st.write(status_text)
        except Exception as error:
            errors.append(f"{source}：{error}")
        progress.progress(index / len(selected))
    st.session_state["logistics_usps_candidates"] = _order_tracking_pairs(
        all_rows
    )
    if all_rows:
        st.success(f"本次读取到 {len(all_rows):,} 条普通 USPS；结果未写入数据库。")
    if errors:
        st.warning("；".join(errors))
    st.session_state["logistics_carrier_review_rows"] = carrier_review_rows
    _reset_review_selection()


def _render_upload_sync():
    st.subheader("复制粘贴订单与物流单号")
    st.caption(
        "在Excel里复制两列，点击下方第一格后直接粘贴；"
        "第一列订单号，第二列物流单号。"
    )
    entry = st.data_editor(
        pd.DataFrame([{"订单号": "", "物流单号": ""}]),
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "订单号": st.column_config.TextColumn("订单号", required=False),
            "物流单号": st.column_config.TextColumn(
                "物流单号", required=False
            ),
        },
        key="logistics_order_tracking_paste",
    )
    rows, issues = parse_logistics_frame(entry)
    if not rows and not issues:
        st.info("填写后会先校验并进入“物流识别核对”，不会直接查询USPS。")
    if issues:
        st.error("导入已停止：" + "；".join(issues[:20]))
        if len(issues) > 20:
            st.caption(f"另有 {len(issues) - 20:,} 行错误未显示。")
        return
    st.caption(f"校验通过：{len(rows):,} 条订单物流记录。")
    if not st.button(
        "进行物流识别", type="primary", width="stretch",
        disabled=not rows,
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有导入物流数据的权限。")
        return
    reviewed = _classify_carrier_rows(rows)
    st.session_state["logistics_carrier_review_rows"] = reviewed
    st.session_state["logistics_usps_candidates"] = _order_tracking_pairs([
        item["row"] for item in reviewed if _is_target_usps_review(item)
    ])
    _reset_review_selection()
    usps_count = sum(_is_target_usps_review(item) for item in reviewed)
    st.success(
        f"已导入 {len(rows):,} 条｜普通USPS {usps_count:,} 条｜"
        f"其他物流 {len(rows) - usps_count:,} 条"
    )


def _order_tracking_pairs(rows):
    pairs = []
    seen = set()
    for row in rows:
        pair = {
            "订单号": str(row.get("external_order_id") or "").strip(),
            "物流单号": str(row.get("tracking_number") or "").strip(),
        }
        optional = {
            "面单PDF": row.get("label_url"),
            "备用面单PDF": row.get("backup_label_url"),
            "ERP平台": row.get("erp_platform"),
            "面单OCR地址": row.get("ocr_address"),
            "重量（oz）": row.get("ocr_weight_oz"),
            "重量（lb）": row.get("ocr_weight_lb"),
            "OCR状态": row.get("ocr_status"),
        }
        pair.update({key: value for key, value in optional.items() if value})
        identity = (pair["订单号"], pair["物流单号"])
        if pair["物流单号"] and identity not in seen:
            pairs.append(pair)
            seen.add(identity)
    return pairs


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
            "OCR寄件地址": row.get("ocr_address", ""),
            "OCR重量（oz）": row.get("ocr_weight_oz"),
            "OCR重量（lb）": row.get("ocr_weight_lb"),
            "OCR状态": row.get("ocr_status", ""),
            "row": row,
        })
    return reviewed


def _label_ocr_candidates(reviewed):
    return [
        item for item in reviewed
        if item.get("row", {}).get("label_url")
        or item.get("row", {}).get("backup_label_url")
    ]


def _apply_erp_label_ocr(
    reviewed,
    source,
    max_labels=5,
    ocr_workers=1,
    ordinary_usps_only=True,
):
    started_at = perf_counter()
    target_rows = (
        [item for item in reviewed if _is_target_usps_review(item)]
        if ordinary_usps_only else list(reviewed)
    )
    available_candidates = []
    for item in target_rows:
        row = item["row"]
        label_url = row.get("label_url") or row.get("backup_label_url")
        if label_url:
            available_candidates.append(item)
            continue
        row["ocr_address"] = ""
        row["ocr_weight_oz"] = None
        row["ocr_weight_lb"] = None
        row["ocr_status"] = "平台未提供可下载面单"
        item["OCR寄件地址"] = ""
        item["OCR重量（oz）"] = None
        item["OCR重量（lb）"] = None
        item["OCR状态"] = "平台未提供可下载面单"
    if max_labels is None:
        candidates = available_candidates
        skipped = []
    else:
        candidates = available_candidates[:max_labels]
        skipped = available_candidates[max_labels:]
    for item in skipped:
        row = item["row"]
        row["ocr_address"] = ""
        row["ocr_weight_oz"] = None
        row["ocr_weight_lb"] = None
        row["ocr_status"] = "本次未解析（超过测试数量）"
        item["OCR寄件地址"] = ""
        item["OCR重量（oz）"] = None
        item["OCR重量（lb）"] = None
        item["OCR状态"] = "本次未解析（超过测试数量）"
    if not candidates:
        return {
            "target": len(target_rows), "available": len(available_candidates),
            "processed": 0, "skipped": len(skipped),
            "missing": len(target_rows), "cache_hits": 0,
            "downloaded": 0, "address_ok": 0, "weight_ok": 0,
            "failed": 0,
        } if target_rows else None
    stage_message = st.empty()
    target_name = "普通USPS" if ordinary_usps_only else "已选面单"
    stage_message.info(
        f"{source}：{target_name} {len(target_rows):,} 张，"
        f"可下载面单 {len(available_candidates):,} 张，"
        f"本次OCR {len(candidates):,} 张。正在检查缓存……"
    )
    progress = st.progress(0)
    if st.session_state.get("logistics_label_ocr_cache_version") == (
        LABEL_OCR_CACHE_VERSION
    ):
        cache = dict(st.session_state.get("logistics_label_ocr_cache", {}))
    else:
        cache = {}
    pending = {}
    for item in candidates:
        row = item["row"]
        label_url = row.get("label_url") or row.get("backup_label_url")
        if label_url in cache:
            continue
        fields = get_cached_label_fields(label_url)
        if fields is not None:
            cache[label_url] = {"fields": fields, "error": "", "stage": ""}
        else:
            pending[label_url] = item
    completed = 0
    downloaded_count = 0
    ocr_seconds = 0.0
    if pending:
        mode_name = "双线程加速模式" if ocr_workers == 2 else "单线程稳定模式"
        stage_message.info(
            f"{source}：缓存命中 {len(candidates) - len(pending):,} 张；"
            f"正在分批下载并识别 {len(pending):,} 张面单"
            f"（下载最多4线程，OCR{mode_name}）……"
        )
        pending_urls = list(pending)
        batch_size = 8
        processing_started_at = perf_counter()
        with (
            ThreadPoolExecutor(max_workers=4) as download_executor,
            ThreadPoolExecutor(max_workers=ocr_workers) as ocr_executor,
        ):
            for start in range(0, len(pending_urls), batch_size):
                batch = pending_urls[start:start + batch_size]
                download_futures = {
                    download_executor.submit(
                        _cached_label_content, label_url
                    ): label_url
                    for label_url in batch
                }
                contents = {}
                for future in as_completed(download_futures):
                    label_url = download_futures[future]
                    try:
                        contents[label_url] = future.result()
                        downloaded_count += 1
                    except Exception as error:
                        cache[label_url] = {
                            "fields": {}, "error": str(error), "stage": "下载",
                        }
                        completed += 1
                        progress.progress(completed / len(pending))
                        stage_message.info(_ocr_progress_text(
                            source, completed, len(pending),
                            processing_started_at, ocr_workers,
                        ))
                if not contents:
                    continue
                ocr_batch_started_at = perf_counter()
                ocr_futures = {
                    ocr_executor.submit(
                        _cached_label_fields, label_url, content
                    ): label_url
                    for label_url, content in contents.items()
                }
                for future in as_completed(ocr_futures):
                    label_url = ocr_futures[future]
                    try:
                        cache[label_url] = {
                            "fields": future.result(),
                            "error": "", "stage": "",
                        }
                    except Exception as error:
                        cache[label_url] = {
                            "fields": {}, "error": str(error), "stage": "OCR",
                        }
                    completed += 1
                    progress.progress(completed / len(pending))
                    stage_message.info(_ocr_progress_text(
                        source, completed, len(pending),
                        processing_started_at, ocr_workers,
                    ))
                ocr_seconds += perf_counter() - ocr_batch_started_at
    for item in candidates:
        row = item["row"]
        label_url = row.get("label_url") or row.get("backup_label_url")
        cached = cache.get(label_url)
        if cached is None:
            try:
                cached = {
                    "fields": _cached_label_fields(
                        label_url, _cached_label_content(label_url)
                    ),
                    "error": "",
                    "stage": "",
                }
            except Exception as error:
                cached = {"fields": {}, "error": str(error), "stage": "OCR"}
            cache[label_url] = cached
        fields = cached.get("fields") or {}
        address = _ocr_address(fields)
        status = (
            "已识别"
            if address
            else f"{cached.get('stage') or 'OCR'}失败："
                 f"{cached.get('error') or '未找到寄件地址'}"
        )
        row["ocr_address"] = address
        row["ocr_weight_oz"] = fields.get("extracted_weight_oz")
        row["ocr_weight_lb"] = _weight_lb(fields.get("extracted_weight_oz"))
        row["ocr_status"] = status
        item["OCR寄件地址"] = address
        item["OCR重量（oz）"] = fields.get("extracted_weight_oz")
        item["OCR重量（lb）"] = row["ocr_weight_lb"]
        item["OCR状态"] = status
    progress.progress(1.0)
    st.session_state["logistics_label_ocr_cache"] = cache
    st.session_state["logistics_label_ocr_cache_version"] = (
        LABEL_OCR_CACHE_VERSION
    )
    progress.empty()
    address_ok = sum(bool(item["row"].get("ocr_address")) for item in candidates)
    weight_ok = sum(
        item["row"].get("ocr_weight_oz") is not None for item in candidates
    )
    failed = len(candidates) - address_ok
    summary = {
        "target": len(target_rows),
        "available": len(available_candidates),
        "processed": len(candidates),
        "skipped": len(skipped),
        "missing": len(target_rows) - len(available_candidates),
        "cache_hits": len(candidates) - len(pending),
        "downloaded": downloaded_count,
        "address_ok": address_ok,
        "weight_ok": weight_ok,
        "failed": failed,
        "total_seconds": perf_counter() - started_at,
        "ocr_seconds": ocr_seconds,
    }
    stage_message.success(f"{source}：{_ocr_summary_text(summary)}")
    reasons = _ocr_failure_reasons(candidates, cache)
    if reasons:
        st.warning(
            f"{source} OCR失败原因：" + "；".join(
                f"{reason}（{count:,}张）" for reason, count in reasons
            )
        )
    return summary


def _ocr_summary_text(summary):
    text = (
        f"面单可下载 {summary['available']:,}｜"
        f"本次OCR {summary.get('processed', summary['available']):,}｜"
        f"未解析 {summary.get('skipped', 0):,}｜"
        f"无面单 {summary['missing']:,}｜"
        f"缓存命中 {summary['cache_hits']:,}｜"
        f"新下载 {summary['downloaded']:,}｜"
        f"OCR地址成功 {summary['address_ok']:,}｜"
        f"重量成功 {summary['weight_ok']:,}｜"
        f"失败 {summary['failed']:,}"
    )
    if "total_seconds" not in summary:
        return text
    total_seconds = float(summary.get("total_seconds") or 0)
    ocr_seconds = float(summary.get("ocr_seconds") or 0)
    network_seconds = max(0.0, total_seconds - ocr_seconds)
    processed = int(summary.get("downloaded") or 0)
    average_seconds = total_seconds / processed if processed else 0
    return (
        text
        + f"｜总耗时 {_format_duration(total_seconds)}"
        + f"｜OCR耗时 {_format_duration(ocr_seconds)}"
        + f"｜下载及等待 {_format_duration(network_seconds)}"
        + (
            f"｜新面单平均 {average_seconds:.1f}秒/张"
            if processed else ""
        )
    )


def _ocr_progress_text(source, completed, total, started_at, ocr_workers):
    elapsed = max(0.0, perf_counter() - started_at)
    average = elapsed / completed if completed else 0
    remaining_count = max(0, total - completed)
    remaining_seconds = average * remaining_count
    finish_at = datetime.now(ZoneInfo("America/New_York")) + timedelta(
        seconds=remaining_seconds
    )
    mode = "双线程加速" if ocr_workers == 2 else "单线程稳定"
    return (
        f"{source}：已处理 {completed:,}/{total:,} 张｜"
        f"剩余 {remaining_count:,} 张｜已用 {_format_duration(elapsed)}｜"
        f"平均 {average:.1f}秒/张｜预计还需 "
        f"{_format_duration(remaining_seconds)}｜"
        f"预计完成 {finish_at:%H:%M:%S}（纽约）｜"
        f"下载4线程｜OCR{mode}模式"
    )


def _resolve_ocr_workers(requested, python_version, ocr_all, ocr_limit):
    if requested != 2:
        return 1, ""
    if tuple(python_version) >= (3, 14):
        return 1, (
            "当前部署使用Python 3.14；为避免ONNX原生库再次导致进程崩溃，"
            "已自动切换到单线程。请使用Python 3.12重新部署后再测试双线程。"
        )
    if ocr_all or ocr_limit > 20:
        return 1, (
            "双线程OCR仅用于最多20张的小批测试；当前范围较大，"
            "已自动切换到单线程稳定模式。"
        )
    return 2, ""


def _format_duration(seconds):
    seconds = max(0, int(round(float(seconds or 0))))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def _ocr_failure_reasons(candidates, cache):
    counts = {}
    for item in candidates:
        row = item["row"]
        label_url = row.get("label_url") or row.get("backup_label_url")
        cached = cache.get(label_url) or {}
        if row.get("ocr_address"):
            continue
        stage = cached.get("stage") or "OCR"
        detail = str(cached.get("error") or "未找到寄件地址").strip()
        reason = f"{stage}失败：{detail}"[:180]
        counts[reason] = counts.get(reason, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]


def _ocr_address(fields):
    return " ".join(str(fields.get(field) or "").strip() for field in (
        "extracted_street", "extracted_city", "extracted_state",
        "extracted_postal_code",
    )).strip()


def _weight_lb(weight_oz):
    if weight_oz is None:
        return None
    return round(float(weight_oz) / 16, 4)


def _is_target_usps_review(item):
    return (
        item.get("系统判断") == "USPS"
        and item.get("USPS子类型") == "普通USPS"
    )


def _render_carrier_review(show_empty=False):
    rows = st.session_state.get(
        "logistics_carrier_review_rows",
        st.session_state.get("s2b_carrier_review_rows", []),
    )
    if not rows and not show_empty:
        return
    st.subheader("物流识别核对")
    ocr_notice = st.session_state.pop("logistics_review_ocr_notice", "")
    if ocr_notice:
        st.success(ocr_notice)
    carrier_names = (
        "USPS", "CBS", "CBT", "GOFO", "FedEx", "UPS", "UniUni", "SwiftX",
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
        st.info("点击“从ERP读取数据”后，这里会显示本次物流识别结果。")
        return
    counts = pd.Series([
        _carrier_filter_name(row) for row in rows
    ]).value_counts()
    excluded_usps = sum(
        row.get("USPS子类型") in {"CBS", "CBT"} for row in rows
    )
    st.caption(
        "｜".join(
            f"{name} {int(counts.get(name, 0)):,} 条"
            for name in carrier_names
        )
        + (f"｜CBS/CBT 独立分类 {excluded_usps:,} 条" if excluded_usps else "")
    )
    filtered_rows = [
        row for row in rows
        if _carrier_filter_name(row) in selected_carriers
    ]
    selectable_count = len(_label_ocr_candidates(filtered_rows))
    review_version = int(st.session_state.get("logistics_review_data_version", 0))
    selection_columns = st.columns([2, 1, 1])
    selection_mode = selection_columns[0].radio(
        "面单选择方式",
        ("手工勾选", "全选可下载", "随机抽查"),
        horizontal=True,
        key="logistics_review_selection_mode",
    )
    random_count = selection_columns[1].number_input(
        "随机抽查数量",
        min_value=1,
        max_value=max(1, selectable_count),
        value=min(5, max(1, selectable_count)),
        disabled=selection_mode != "随机抽查" or not selectable_count,
        key=(
            f"logistics_review_random_count_{review_version}_"
            f"{'_'.join(selected_carriers)}"
        ),
    )
    random_seed = int(st.session_state.get("logistics_review_random_seed", 0))
    if selection_columns[2].button(
        "重新随机",
        width="stretch",
        disabled=selection_mode != "随机抽查" or not selectable_count,
    ):
        random_seed += 1
        st.session_state["logistics_review_random_seed"] = random_seed
    defaults = _review_selection_defaults(
        filtered_rows, selection_mode, int(random_count), random_seed
    )
    display = pd.DataFrame([{
        "OCR选择": defaults[index],
        **{key: value for key, value in row.items() if key != "row"},
    } for index, row in enumerate(filtered_rows)])
    if not filtered_rows:
        st.info("当前没有勾选物流商的匹配记录。")
    else:
        edited = st.data_editor(
            display,
            hide_index=True,
            width="stretch",
            height=420,
            disabled=[
                column for column in display.columns
                if column != "OCR选择"
            ],
            column_config={
                "OCR选择": st.column_config.CheckboxColumn(
                    "OCR选择", help="只勾选需要核查的可疑面单。"
                ),
                "面单": st.column_config.LinkColumn(display_text="打开面单"),
                "备用面单": st.column_config.LinkColumn(
                    display_text="备用面单"
                ),
            },
            key=(
                "logistics_carrier_review_editor_"
                f"{review_version}_"
                f"{selection_mode}_{random_seed}_{'_'.join(selected_carriers)}"
            ),
        )
        selected_rows = [
            filtered_rows[index]
            for index, selected in enumerate(edited["OCR选择"].tolist())
            if bool(selected)
        ]
        _render_review_ocr_actions(rows, selected_rows)
    st.caption(
        "CBS（GOFO揽收）和CBT（TikTok指定物流商揽收）可单独筛选；"
        "它们不会进入普通USPS核查候选。"
    )


def _render_review_ocr_actions(reviewed, selected_rows):
    available_rows = _label_ocr_candidates(selected_rows)
    missing_count = len(selected_rows) - len(available_rows)
    action_columns = st.columns([2, 1, 2, 2])
    ocr_mode = action_columns[0].selectbox(
        "OCR速度模式",
        ("稳定模式（单线程）", "加速模式（双线程）"),
        help="双线程仅开放给最多20张的小批量测试，并使用更多云端内存。",
        key="logistics_review_ocr_mode",
    )
    action_columns[1].metric("已选可解析", f"{len(available_rows):,} 张")
    requested_workers = 2 if ocr_mode.startswith("加速") else 1
    ocr_workers, safety_reason = _resolve_ocr_workers(
        requested_workers,
        sys.version_info[:2],
        False,
        len(available_rows),
    )
    if action_columns[2].button(
        "OCR分析勾选面单",
        type="primary",
        width="stretch",
        disabled=not available_rows,
    ):
        if not has_permission("can_manage_logistics"):
            st.error("当前账号没有面单OCR权限。")
            return
        summary = _apply_erp_label_ocr(
            available_rows,
            "物流识别核对",
            max_labels=None,
            ocr_workers=ocr_workers,
            ordinary_usps_only=False,
        )
        _store_review_ocr_results(reviewed, summary)
        st.rerun()
    _render_label_archive_download(action_columns[3], reviewed)
    if missing_count:
        st.warning(f"已选记录中有 {missing_count:,} 条没有可下载面单，无法OCR。")
    if safety_reason:
        st.warning(safety_reason)
    elif ocr_workers == 2:
        st.warning("当前使用双线程OCR；建议先选择少量面单确认云端稳定性。")


def _review_selection_defaults(rows, mode, random_count, random_seed):
    available_indices = [
        index for index, item in enumerate(rows)
        if _label_ocr_candidates([item])
    ]
    if mode == "全选可下载":
        selected = set(available_indices)
    elif mode == "随机抽查" and available_indices:
        sample_size = min(max(0, random_count), len(available_indices))
        selected = set(random.Random(random_seed).sample(
            available_indices, sample_size
        ))
    else:
        selected = set()
    return [index in selected for index in range(len(rows))]


def _render_label_archive_download(container, reviewed):
    documents = _label_documents(reviewed)
    fingerprint = tuple(document["url"] for document in documents)
    if st.session_state.get("logistics_label_archive_fingerprint") != fingerprint:
        st.session_state.pop("logistics_label_archive", None)
        st.session_state.pop("logistics_label_archive_errors", None)
    if container.button(
        "打包全部面单",
        width="stretch",
        disabled=not documents,
        help="打包本次物流识别数据中的全部可下载面单，不受物流商筛选影响。",
    ):
        if not has_permission("can_manage_logistics"):
            st.error("当前账号没有批量下载面单的权限。")
            return
        with st.spinner(f"正在下载并打包 {len(documents):,} 张面单……"):
            archive, errors, downloaded = build_label_archive(
                documents, _cached_label_content, max_workers=4
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
            "下载全部面单 ZIP",
            data=archive,
            file_name=f"shipping_labels_{date.today():%Y%m%d}.zip",
            mime="application/zip",
            width="stretch",
        )
    errors = st.session_state.get("logistics_label_archive_errors") or []
    if errors:
        st.warning(f"有 {len(errors):,} 张面单下载失败，可稍后重新打包。")


def _label_documents(reviewed):
    return [{
        "url": item["row"].get("label_url")
        or item["row"].get("backup_label_url"),
        "platform": item.get("平台"),
        "order_id": item.get("Order ID"),
        "tracking_number": item.get("Tracking Number"),
    } for item in _label_ocr_candidates(reviewed)]


def _reset_review_selection():
    st.session_state["logistics_review_data_version"] = (
        int(st.session_state.get("logistics_review_data_version", 0)) + 1
    )
    st.session_state.pop("logistics_label_archive", None)
    st.session_state.pop("logistics_label_archive_errors", None)
    st.session_state.pop("logistics_label_archive_fingerprint", None)


def _store_review_ocr_results(reviewed, summary):
    st.session_state["logistics_carrier_review_rows"] = reviewed
    st.session_state["logistics_usps_candidates"] = _order_tracking_pairs([
        item["row"] for item in reviewed if _is_target_usps_review(item)
    ])
    _reset_review_selection()
    st.session_state["logistics_review_ocr_notice"] = (
        "OCR结果已回填到本表和下方普通USPS核查数据。"
        + (f" {_ocr_summary_text(summary)}" if summary else "")
    )


def _carrier_filter_name(row):
    subtype = row.get("USPS子类型")
    if subtype in {"CBS", "CBT"}:
        return subtype
    return row.get("系统判断", "其他待确认")


def _default_logistics_platforms(platforms):
    if "S2B" in platforms:
        return ["S2B"]
    return [
        platform for platform in platforms
        if platform in LOGISTICS_CONNECTED_PLATFORMS
    ][:1]


def _fetch_source(source, department, stage, start_date, end_date):
    status = ORDER_STAGES[stage]
    if source in {"七创", "一朵云"}:
        return fetch_diy19_shipments(
            source,
            load_diy19_logistics_credentials(st.secrets, source),
            start_date,
            end_date,
            stage=status,
        )
    if source.startswith("SDS"):
        profile = "1号线" if source == "SDS1" else "2号线"
        return fetch_sds_pending_shipments(
            profile, load_sds_account(st.secrets, profile), 100,
            status=status,
            time_range=_erp_time_range(start_date, end_date),
        )
    if source != "S2B":
        raise ValueError(
            f"{source} 已存在于生产数据平台目录，但尚未接入订单物流接口"
        )
    account = "UV" if department == "UV" else "DTF"
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
        "S2B" for source in selected if source == "S2B"
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


def _render_rules():
    st.subheader("当前面单审核规则")
    st.write("寄件街道：25 Ranic Road")
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
