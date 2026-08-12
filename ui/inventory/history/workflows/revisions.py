import pandas as pd
import streamlit as st

from db.inventory.operations.daily_outbound_versions import (
    load_daily_outbound_revisions,
)
from utils.sku_sorting import sort_sku_rows


ACTION_LABELS = {
    "create": "首次登记",
    "edit": "修改并替换",
    "void": "撤销",
}


def render_daily_outbound_revision_history(
    supabase, department, category="黑白短袖",
):
    st.subheader("每日出库版本记录")
    st.caption(
        "普通库存流水只显示当前有效版本；这里保留每次登记、修改、"
        "撤销以及申报数量、实际扣减和缺口。"
    )
    try:
        batches = load_daily_outbound_revisions(
            supabase, department, category
        )
    except Exception:
        st.info(
            "请先运行 inventory_daily_outbound_versions.sql，"
            "启用每日出库版本记录。"
        )
        return
    summaries, revisions = _flatten_revisions(batches)
    if not summaries:
        st.info("暂无新版每日出库编辑记录")
        return
    summary = pd.DataFrame(summaries).sort_values(
        ["出库日期", "版本"], ascending=[False, False]
    )
    st.dataframe(summary, hide_index=True, width="stretch")
    options = summary["记录键"].tolist()
    labels = {
        row["记录键"]: (
            f"{row['出库日期']}｜第 {row['版本']} 版｜{row['操作']}｜"
            f"申报 {row['申报数量']:,} 件"
        )
        for row in summaries
    }
    selected = st.selectbox(
        "查看版本 SKU 明细",
        options,
        format_func=lambda value: labels[value],
        key="daily_outbound_revision_history_selected",
    )
    detail = pd.DataFrame(revisions[selected])
    detail = sort_sku_rows(
        detail, material="材质", color="颜色", size="尺码",
        leading=["品牌"],
    )
    st.dataframe(detail, hide_index=True, width="stretch")


def _flatten_revisions(batches):
    summaries = []
    details = {}
    for batch in batches:
        current = int(batch.get("current_revision") or 0)
        movement_date = pd.to_datetime(
            batch.get("movement_date"), errors="coerce"
        ).date()
        for revision in batch.get("inventory_daily_outbound_revisions", []):
            number = int(revision.get("revision_number") or 0)
            key = f"{batch['id']}|{number}"
            summaries.append({
                "记录键": key,
                "出库日期": movement_date,
                "版本": number,
                "状态": "当前有效" if number == current else "历史版本",
                "操作": ACTION_LABELS.get(revision.get("action"), "修改"),
                "申报数量": int(revision.get("requested_total") or 0),
                "实际扣减": int(revision.get("applied_total") or 0),
                "未扣差额": int(revision.get("shortage_total") or 0),
                "操作人": revision.get("created_by") or "",
                "操作时间": pd.to_datetime(
                    revision.get("created_at"), errors="coerce", utc=True
                ).tz_convert("America/New_York"),
                "备注": revision.get("note") or "",
            })
            details[key] = [
                {
                    "品牌": line.get("brand") or "",
                    "材质": line.get("material") or "",
                    "颜色": line.get("color") or "",
                    "尺码": line.get("size") or "",
                    "申报数量": int(line.get("requested_quantity") or 0),
                    "实际扣减": int(line.get("applied_quantity") or 0),
                    "未扣差额": int(line.get("shortage_quantity") or 0),
                }
                for line in revision.get("inventory_daily_outbound_lines", [])
            ]
    return summaries, details
