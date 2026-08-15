"""Concurrent label download and OCR execution."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

import streamlit as st

from automation.logistics.label_cache import (
    cached_label_content,
    cached_label_fields,
    get_cached_label_fields,
)
from ui.logistics.review.model import (
    build_ocr_summary,
    empty_ocr_summary,
    is_target_usps_review,
    ocr_address,
    weight_lb,
)
from ui.logistics.review.ocr_format import (
    ocr_failure_reasons,
    ocr_progress_text,
    ocr_summary_text,
)


LABEL_OCR_CACHE_VERSION = 4


def apply_label_ocr(
    reviewed, source, max_labels=5, ocr_workers=1,
    ordinary_usps_only=True,
):
    started_at = perf_counter()
    targets = (
        [item for item in reviewed if is_target_usps_review(item)]
        if ordinary_usps_only else list(reviewed)
    )
    available = _mark_missing_labels(targets)
    candidates, skipped = _limit_candidates(available, max_labels)
    if not candidates:
        return empty_ocr_summary(targets, available, skipped)

    message = st.empty()
    target_name = "普通USPS" if ordinary_usps_only else "已选面单"
    message.info(
        f"{source}：{target_name} {len(targets):,} 张，"
        f"可下载面单 {len(available):,} 张，"
        f"本次OCR {len(candidates):,} 张。正在检查缓存……"
    )
    progress = st.progress(0)
    cache = _session_cache()
    pending = _load_server_cache(candidates, cache)
    downloaded, ocr_seconds = _process_pending(
        pending, cache, source, ocr_workers, message, progress
    )
    _apply_results(candidates, cache)
    progress.progress(1.0)
    st.session_state["logistics_label_ocr_cache"] = cache
    st.session_state["logistics_label_ocr_cache_version"] = (
        LABEL_OCR_CACHE_VERSION
    )
    progress.empty()
    summary = build_ocr_summary(
        targets, available, candidates, skipped, pending, downloaded,
        perf_counter() - started_at, ocr_seconds,
    )
    message.success(f"{source}：{ocr_summary_text(summary)}")
    reasons = ocr_failure_reasons(candidates, cache)
    if reasons:
        st.warning(
            f"{source} OCR失败原因：" + "；".join(
                f"{reason}（{count:,}张）" for reason, count in reasons
            )
        )
    return summary


def _mark_missing_labels(targets):
    available = []
    for item in targets:
        row = item["row"]
        if row.get("label_url") or row.get("backup_label_url"):
            available.append(item)
            continue
        _set_result(item, "", None, "平台未提供可下载面单")
    return available


def _limit_candidates(available, limit):
    candidates = available if limit is None else available[:limit]
    skipped = [] if limit is None else available[limit:]
    for item in skipped:
        _set_result(item, "", None, "本次未解析（超过测试数量）")
    return candidates, skipped


def _session_cache():
    if st.session_state.get("logistics_label_ocr_cache_version") == (
        LABEL_OCR_CACHE_VERSION
    ):
        return dict(st.session_state.get("logistics_label_ocr_cache", {}))
    return {}


def _load_server_cache(candidates, cache):
    pending = {}
    for item in candidates:
        url = _label_url(item)
        if url in cache:
            continue
        fields = get_cached_label_fields(url)
        if fields is None:
            pending[url] = item
        else:
            cache[url] = {"fields": fields, "error": "", "stage": ""}
    return pending


def _process_pending(pending, cache, source, workers, message, progress):
    if not pending:
        return 0, 0.0
    mode = "双线程加速模式" if workers == 2 else "单线程稳定模式"
    message.info(
        f"{source}：正在分批下载并识别 {len(pending):,} 张面单"
        f"（下载最多4线程，OCR{mode}）……"
    )
    completed = downloaded = 0
    ocr_seconds = 0.0
    started_at = perf_counter()
    urls = list(pending)
    with (
        ThreadPoolExecutor(max_workers=4) as downloader,
        ThreadPoolExecutor(max_workers=workers) as ocr,
    ):
        for start in range(0, len(urls), 8):
            batch = urls[start:start + 8]
            futures = {
                downloader.submit(cached_label_content, url): url
                for url in batch
            }
            contents = {}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    contents[url] = future.result()
                    downloaded += 1
                except Exception as error:
                    cache[url] = _failure("下载", error)
                    completed = _show_progress(
                        completed + 1, len(pending), source, started_at,
                        workers, message, progress,
                    )
            ocr_started = perf_counter()
            ocr_futures = {
                ocr.submit(cached_label_fields, url, content): url
                for url, content in contents.items()
            }
            for future in as_completed(ocr_futures):
                url = ocr_futures[future]
                try:
                    cache[url] = {
                        "fields": future.result(), "error": "", "stage": "",
                    }
                except Exception as error:
                    cache[url] = _failure("OCR", error)
                completed = _show_progress(
                    completed + 1, len(pending), source, started_at,
                    workers, message, progress,
                )
            ocr_seconds += perf_counter() - ocr_started
    return downloaded, ocr_seconds


def _show_progress(done, total, source, started, workers, message, progress):
    progress.progress(done / total)
    message.info(ocr_progress_text(source, done, total, started, workers))
    return done


def _apply_results(candidates, cache):
    for item in candidates:
        cached = cache.get(_label_url(item)) or _failure("OCR", "没有缓存结果")
        fields = cached.get("fields") or {}
        address = ocr_address(fields)
        status = "已识别" if address else (
            f"{cached.get('stage') or 'OCR'}失败："
            f"{cached.get('error') or '未找到寄件地址'}"
        )
        _set_result(
            item, address, fields.get("extracted_weight_oz"), status, fields
        )


def _set_result(item, address, weight_oz, status, fields=None):
    row = item["row"]
    row.update({
        "ocr_address": address, "ocr_weight_oz": weight_oz,
        "ocr_weight_lb": weight_lb(weight_oz), "ocr_status": status,
        "_ocr_fields": dict(fields or {}),
    })
    item.update({
        "OCR寄件地址": address, "OCR重量（oz）": weight_oz,
        "OCR重量（lb）": row["ocr_weight_lb"], "OCR状态": status,
    })


def _label_url(item):
    return item["row"].get("label_url") or item["row"].get("backup_label_url")


def _failure(stage, error):
    return {"fields": {}, "error": str(error), "stage": stage}
