"""Batch selector rendering and dependent-state synchronization."""

import streamlit as st

from ui.inventory.i18n import t


def render_batch_selector(
    batch_df, key="inventory_history_batch", sku_import=False
):
    if batch_df.empty:
        synchronize_batch_selector_state(st.session_state, key, [])
        st.info(t("暂无相关记录"))
        return None
    options = batch_df["batch_key"].tolist()
    synchronize_batch_selector_state(st.session_state, key, options)
    labels = _batch_labels(batch_df, sku_import)
    selected = st.selectbox(
        t("选择 SKU 导入记录") if sku_import else t("选择库存表格记录"),
        options, format_func=lambda value: labels.get(value, value), key=key,
    )
    latest = options[0]
    if selected != latest:
        st.warning(f"当前查看的是历史记录。最新记录：{labels.get(latest, latest)}")
        if st.button("查看最新记录", key=f"{key}_view_latest"):
            st.session_state[key] = latest
            st.rerun()
    caption = (
        "输入时间｜导入日期｜部门/品类｜总计｜操作人"
        if sku_import
        else "输入时间｜类型｜出入库日期｜部门/品类｜来源｜总计｜操作人"
    )
    st.caption(t(caption))
    return selected


def _batch_labels(batch_df, sku_import):
    if sku_import:
        return {
            row["batch_key"]: (
                f"{row['记录时间']}｜{row['表格日期']}｜"
                f"{row['部门']} {row['品类']}｜{row['数量']}｜{row['操作人']}"
            ) for row in batch_df.to_dict("records")
        }
    return {
        row["batch_key"]: (
            f"{row['记录时间']}｜{t(row['类型'])}｜{row['表格日期']}｜"
            f"{row['部门']} {row['品类']}｜"
            f"{t(row.get('消耗来源') or '其他出入库')}｜"
            f"{row['数量']}｜{row['操作人']}"
        ) for row in batch_df.to_dict("records")
    }


def synchronize_batch_selector_state(state, key, options):
    """Reset a child batch selector whenever its filtered options change."""
    options = list(options)
    signature_key = f"{key}__options_signature"
    signature = tuple(str(value) for value in options)
    if state.get(signature_key) != signature:
        if options:
            state[key] = options[0]
        else:
            state.pop(key, None)
        state[signature_key] = signature
        return True
    if key in state and state[key] not in options:
        state[key] = options[0] if options else None
        if not options:
            state.pop(key, None)
        return True
    return False
