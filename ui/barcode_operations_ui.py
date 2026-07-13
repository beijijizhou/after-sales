import pandas as pd
import streamlit as st

from db.barcode_operations import (
    load_platform_options,
    save_operation_rows,
)
from ui.search_ui import parse_barcodes
from utils.auth import get_current_user, has_permission


OPERATION_TYPES = [
    "无轨迹补发",
    "需要抠图面单已出",
    "断码",
    "质检表",
    "面单已出",
    "自定义",
]


def get_platform_options():
    return [""] + load_platform_options()


def required_label(label):
    st.markdown(f"{label} <span style='color:#d32f2f'>*</span>", unsafe_allow_html=True)


def render_direct_operation_entry():
    st.subheader("新增追踪单号")

    saved_count = st.session_state.pop("operation_saved_count", None)
    if saved_count:
        st.toast(f"已成功将 {saved_count} 个单号 / 条码加入数据库", icon="✅")

    user = get_current_user()
    if not user or not has_permission("can_mark_barcode_operations"):
        st.info("当前账号只能查看，不能新增追踪单号。")
        return

    input_col, setting_col = st.columns([2, 1])
    with input_col:
        input_version = st.session_state.get("direct_operation_input_version", 0)
        required_label("粘贴单号 / 条码（支持换行或逗号分隔）")
        input_text = st.text_area(
            "单号 / 条码",
            height=160,
            key=f"direct_operation_barcodes_{input_version}",
            label_visibility="collapsed",
        )
    barcodes = parse_barcodes(input_text)

    with setting_col:
        st.metric("输入数量", len(barcodes))
        required_label("操作类型")
        operation_type = st.selectbox(
            "操作类型", OPERATION_TYPES, label_visibility="collapsed"
        )
        custom_type = ""
        if operation_type == "自定义":
            required_label("自定义操作类型")
            custom_type = st.text_input(
                "自定义操作类型", label_visibility="collapsed"
            )
        try:
            platform_options = get_platform_options()
        except Exception:
            platform_options = [""]
        platform = st.selectbox(
            "平台（可选）",
            platform_options,
            format_func=lambda value: value or "未选择",
        )
        requires_rescan = st.checkbox("需要重新扫描", value=True)

    if barcodes:
        st.dataframe(
            pd.DataFrame({"单号 / 条码": barcodes}),
            hide_index=True,
            use_container_width=True,
            height=180,
        )

    if st.button("加入问题件追踪", use_container_width=True):
        if not barcodes:
            st.warning("请先输入单号或条码")
            return
        final_operation_type = custom_type.strip() if operation_type == "自定义" else operation_type
        if not final_operation_type:
            st.warning("请输入自定义操作类型")
            return

        rows = [
            {
                "barcode": barcode,
                "operation_type": final_operation_type,
                "platform": platform,
                "requires_rescan": requires_rescan,
            }
            for barcode in barcodes
        ]
        try:
            save_operation_rows(rows, user["username"])
        except Exception as e:
            st.error(f"保存失败：{e}")
            st.info("请先在 Supabase SQL Editor 运行 sql/barcode_operation_history.sql")
            return

        st.session_state["operation_saved_count"] = len(rows)
        st.session_state["direct_operation_input_version"] = input_version + 1
        st.rerun()


def render_barcode_operation_section():
    st.divider()
    st.subheader("订单操作标记")

    df = st.session_state.get("search_df")
    if df is None or df.empty:
        st.info("请先查询条码，再添加操作标记。")
        return

    user = get_current_user()
    if not user or not has_permission("can_mark_barcode_operations"):
        st.info("当前账号只能查看，不能添加订单操作标记。")
        return

    editor_df = build_operation_editor_df(df)
    try:
        platform_options = get_platform_options()
    except Exception:
        platform_options = [""]
    edited_df = st.data_editor(
        editor_df,
        hide_index=True,
        use_container_width=True,
        disabled=["barcode", "scanned_by", "scanned_at"],
        column_config={
            "保存": st.column_config.CheckboxColumn("保存"),
            "barcode": st.column_config.TextColumn("条码"),
            "scanned_by": st.column_config.TextColumn("质检人员"),
            "scanned_at": st.column_config.TextColumn("扫描时间"),
            "operation_type": st.column_config.SelectboxColumn("操作类型 *", options=OPERATION_TYPES),
            "custom_type": st.column_config.TextColumn("自定义操作类型 *"),
            "platform": st.column_config.SelectboxColumn("平台（可选）", options=platform_options),
            "requires_rescan": st.column_config.CheckboxColumn("需要重新扫描"),
        },
        key="barcode_operation_editor",
    )

    selected_df = pd.DataFrame(edited_df)
    selected_df = selected_df[selected_df["保存"]]
    if st.button("保存订单操作标记", use_container_width=True):
        if selected_df.empty:
            st.warning("请先勾选需要保存的条码")
            return

        custom_missing = (
            (selected_df["operation_type"] == "自定义")
            & (selected_df["custom_type"].fillna("").str.strip() == "")
        )
        if custom_missing.any():
            st.warning("自定义操作类型不能为空")
            return

        selected_df.loc[
            selected_df["operation_type"] == "自定义", "operation_type"
        ] = selected_df["custom_type"].fillna("").str.strip()
        try:
            save_operation_rows(selected_df.to_dict("records"), user["username"])
        except Exception as e:
            st.error(f"保存失败：{e}")
            st.info("请先在 Supabase SQL Editor 运行 sql/barcode_operation_history.sql")
            return

        st.toast(f"已成功将 {len(selected_df)} 条操作标记加入数据库", icon="✅")


def build_operation_editor_df(df):
    editor_df = df.copy()
    for column in ["barcode", "scanned_by", "scanned_at"]:
        if column not in editor_df.columns:
            editor_df[column] = ""

    editor_df = editor_df[["barcode", "scanned_by", "scanned_at"]].drop_duplicates()
    editor_df.insert(0, "保存", False)
    editor_df["operation_type"] = "无轨迹补发"
    editor_df["custom_type"] = ""
    editor_df["platform"] = ""
    editor_df["requires_rescan"] = True
    return editor_df
