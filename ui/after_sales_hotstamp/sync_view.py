"""Preview-before-import UI for hotstamp film Google Sheets."""

import pandas as pd
import streamlit as st

from automation.sync.after_sales_hotstamp import load_hotstamp_film_previews
from automation.sync.google_sheets import GoogleSheetsClient
from db.after_sales_hotstamp import (
    import_hotstamp_film_batch,
    load_hotstamp_film_batches,
)
from utils.auth import get_current_operator_name


PREVIEW_STATE = "after_sales_hotstamp_film_previews"


def render_sync_view(supabase, folder_id):
    st.subheader("同步 Google 表格")
    st.caption(
        "先读取并预览每个周表；确认后按周表保存为独立同步批次。"
        "同一文件内容未变化时不会重复导入。"
    )
    if not folder_id:
        st.warning(
            "尚未配置 AFTER_SALES_HOTSTAMP_FOLDER_ID，"
            "请先在 Streamlit Secrets 中填写售后登记文件夹 ID。"
        )
        return

    if st.button("读取全部周表", type="primary", key="read_hotstamp_film"):
        _read_previews(folder_id)

    previews = st.session_state.get(PREVIEW_STATE)
    if not previews:
        st.info("点击“读取全部周表”后，这里会显示批次级导入预览。")
        return

    batches = _safe_batches(supabase)
    saved_hashes = set(batches.get("source_hash", pd.Series(dtype=str)).astype(str))
    preview_table = _preview_table(previews, saved_hashes)
    st.dataframe(preview_table, hide_index=True, width="stretch")

    pending = [
        item for item in previews if item["source_hash"] not in saved_hashes
    ]
    options = [item["source_file_name"] for item in pending]
    selected = st.multiselect(
        "选择要导入的周表",
        options,
        default=options,
        key="hotstamp_film_selected_batches",
    )
    _render_invalid_rows(previews)
    confirmed = st.checkbox(
        "我已核对来源范围、有效行数、膜总数和异常行",
        key="confirm_hotstamp_film_import",
    )
    if st.button(
        "确认导入所选批次",
        disabled=not selected or not confirmed,
        key="import_hotstamp_film_batches",
    ):
        _import_selected(supabase, pending, selected)


def _read_previews(folder_id):
    progress_bar = st.progress(0, text="正在读取文件目录...")

    def update(current, total, name):
        progress_bar.progress(
            current / max(total, 1), text=f"正在读取 {name}（{current}/{total}）"
        )

    try:
        client = GoogleSheetsClient.from_environment(st.secrets)
        previews = load_hotstamp_film_previews(client, folder_id, update)
    except Exception as exc:
        progress_bar.empty()
        st.error(f"Google 表格读取失败：{exc}")
        st.info("请确认售后文件夹已共享给系统 Google 服务账号。")
        return
    progress_bar.empty()
    st.session_state[PREVIEW_STATE] = previews
    st.success(
        f"已读取 {len(previews)} 个周表，"
        f"共 {sum(item['row_count'] for item in previews):,} 条有效登记。"
    )


def _preview_table(previews, saved_hashes):
    return pd.DataFrame([{
        "同步状态": "内容未变化" if item["source_hash"] in saved_hashes else "待同步",
        "周表": item["source_file_name"],
        "开始日期": item["start_date"],
        "结束日期": item["end_date"],
        "有效登记行": item["row_count"],
        "膜总数": item["total_film_quantity"],
        "异常行": item["invalid_row_count"],
        "来源最后修改": item.get("source_modified_at"),
    } for item in previews])


def _render_invalid_rows(previews):
    invalid = [row for item in previews for row in item["invalid_rows"]]
    if not invalid:
        return
    with st.expander(f"查看 {len(invalid)} 条未导入异常行"):
        st.dataframe(pd.DataFrame(invalid), hide_index=True, width="stretch")


def _import_selected(supabase, previews, selected):
    selected_set = set(selected)
    targets = [
        item for item in previews if item["source_file_name"] in selected_set
    ]
    progress = st.progress(0, text="正在导入...")
    results = []
    for index, item in enumerate(targets, start=1):
        result = import_hotstamp_film_batch(
            supabase, item, get_current_operator_name()
        )
        results.append(result)
        progress.progress(
            index / len(targets),
            text=f"已导入 {item['source_file_name']}（{index}/{len(targets)}）",
        )
    progress.empty()
    saved = sum(int(row.get("saved_rows") or 0) for row in results)
    quantity = sum(int(row.get("saved_quantity") or 0) for row in results)
    st.success(f"同步完成：{saved:,} 条登记，膜总数 {quantity:,}。")
    st.session_state.pop(PREVIEW_STATE, None)
    st.session_state.pop("confirm_hotstamp_film_import", None)
    st.rerun()


def _safe_batches(supabase):
    try:
        return load_hotstamp_film_batches(supabase, limit=500)
    except Exception:
        return pd.DataFrame()
