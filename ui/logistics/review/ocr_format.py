"""Formatting and safety rules for label OCR operations."""

from datetime import datetime, timedelta
from time import perf_counter
from zoneinfo import ZoneInfo


def ocr_summary_text(summary):
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
    downloaded = int(summary.get("downloaded") or 0)
    average_seconds = total_seconds / downloaded if downloaded else 0
    return (
        text
        + f"｜总耗时 {format_duration(total_seconds)}"
        + f"｜OCR耗时 {format_duration(ocr_seconds)}"
        + f"｜下载及等待 {format_duration(network_seconds)}"
        + (
            f"｜新面单平均 {average_seconds:.1f}秒/张"
            if downloaded else ""
        )
    )


def ocr_progress_text(
    source, completed, total, started_at, ocr_workers, now=None,
):
    elapsed = max(0.0, perf_counter() - started_at)
    average = elapsed / completed if completed else 0
    remaining_count = max(0, total - completed)
    remaining_seconds = average * remaining_count
    current = now or datetime.now(ZoneInfo("America/New_York"))
    finish_at = current + timedelta(seconds=remaining_seconds)
    mode = "双线程加速" if ocr_workers == 2 else "单线程稳定"
    return (
        f"{source}：已处理 {completed:,}/{total:,} 张｜"
        f"剩余 {remaining_count:,} 张｜已用 {format_duration(elapsed)}｜"
        f"平均 {average:.1f}秒/张｜预计还需 "
        f"{format_duration(remaining_seconds)}｜"
        f"预计完成 {finish_at:%H:%M:%S}（纽约）｜"
        f"下载4线程｜OCR{mode}模式"
    )


def resolve_ocr_workers(requested, python_version, ocr_all, ocr_limit):
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


def format_duration(seconds):
    seconds = max(0, int(round(float(seconds or 0))))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def ocr_failure_reasons(candidates, cache):
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
