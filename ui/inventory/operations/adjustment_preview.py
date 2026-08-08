import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t
from utils.sku_sorting import sort_sku_rows


COMPARISON_COLUMNS = [
    "品牌", "材质", "颜色", "数据口径", *SIZE_COLUMNS, "合计",
]


def build_adjustment_stock_comparison(inventory_df, edited_df, action):
    """Build current + change = resulting stock rows for edited DTF SKUs."""
    inventory = pd.DataFrame(inventory_df).copy()
    edited = pd.DataFrame(edited_df).copy()
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    identity = ["品牌", "材质", "颜色"]
    for frame in [inventory, edited]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
        for size in SIZE_COLUMNS:
            if size not in frame:
                frame[size] = 0
            frame[size] = pd.to_numeric(
                frame[size], errors="coerce"
            ).fillna(0).astype(int)

    edited = edited[
        (edited["材质"] != "")
        & (edited["颜色"] != "")
        & (edited[SIZE_COLUMNS].sum(axis=1) > 0)
    ]
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    current = inventory.groupby(
        identity, dropna=False, as_index=False
    )[SIZE_COLUMNS].sum()
    changes = edited.groupby(
        identity, dropna=False, as_index=False, sort=False
    )[SIZE_COLUMNS].sum()
    identities = sort_sku_rows(
        changes[identity], size="__wide_size_columns__"
    )
    current_by_key = current.set_index(identity)[SIZE_COLUMNS]
    changes_by_key = changes.set_index(identity)[SIZE_COLUMNS]
    direction = 1 if action == "增加" else -1
    operation_label = "本次入库 (+)" if direction > 0 else "本次出库 (-)"
    rows = []
    for item in identities.to_dict("records"):
        key = tuple(item[column] for column in identity)
        current_values = _wide_values(current_by_key, key)
        change_values = _wide_values(changes_by_key, key) * direction
        resulting_values = current_values + change_values
        for label, values in [
            ("当前库存", current_values),
            (operation_label, change_values),
            ("操作后库存", resulting_values),
        ]:
            rows.append({
                **item,
                "数据口径": label,
                **{size: int(values[size]) for size in SIZE_COLUMNS},
                "合计": int(values.sum()),
            })
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def render_adjustment_stock_comparison(inventory_df, edited_df, action):
    comparison = build_adjustment_stock_comparison(
        inventory_df, edited_df, action
    )
    if comparison.empty:
        return comparison
    st.markdown("#### 保存前库存核对")
    st.caption("当前库存 + 本次变动 = 操作后库存；仅显示本次涉及的 SKU。")
    resulting = comparison[comparison["数据口径"] == "操作后库存"]
    negative = resulting[SIZE_COLUMNS].lt(0)
    if negative.any(axis=None):
        affected = int(negative.any(axis=1).sum())
        st.error(
            f"有 {affected} 个 SKU 组合操作后会出现负库存，请调整本次数量。"
        )
    display = comparison.copy()
    change_mask = display["数据口径"].str.startswith("本次")
    for column in [*SIZE_COLUMNS, "合计"]:
        display[column] = display[column].map(lambda value: f"{int(value):,}")
        display.loc[change_mask, column] = comparison.loc[
            change_mask, column
        ].map(_format_signed)
    st.dataframe(display, hide_index=True, width="stretch")
    return comparison


def _wide_values(indexed, key):
    try:
        values = indexed.loc[key]
    except KeyError:
        return pd.Series(0, index=SIZE_COLUMNS, dtype="int64")
    if isinstance(values, pd.DataFrame):
        values = values.sum(axis=0)
    return pd.to_numeric(values, errors="coerce").fillna(0).astype(int)


def _format_signed(value):
    number = int(value)
    if number > 0:
        return f"+{number:,}"
    return f"{number:,}"


def build_adjustment_preview(adjustment_df):
    if adjustment_df.empty:
        return pd.DataFrame()

    preview_df = adjustment_df.copy()
    preview_df["日期"] = pd.to_datetime(
        preview_df["日期"], errors="coerce"
    ).dt.date
    for column in ["品牌", "材质", "颜色", "备注"]:
        preview_df[column] = preview_df[column].fillna("").astype(str)
    preview_df["数量"] = pd.to_numeric(
        preview_df["数量"], errors="coerce"
    ).fillna(0).astype(int)

    index_columns = ["日期", "操作", "品牌", "材质", "颜色", "备注"]
    wide_df = (
        preview_df
        .pivot_table(
            index=index_columns,
            columns="尺码",
            values="数量",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    for size in SIZE_COLUMNS:
        if size not in wide_df.columns:
            wide_df[size] = 0
        wide_df[size] = pd.to_numeric(wide_df[size], errors="coerce").fillna(0).astype(int)
    wide_df["合计"] = wide_df[SIZE_COLUMNS].sum(axis=1)
    return wide_df[[*index_columns[:-1], *SIZE_COLUMNS, "合计", "备注"]]


def render_adjustment_preview_editor(
    adjustment_df,
    key,
    lock_operation=False,
    lock_identity=False,
    allow_rows=True,
    disabled_columns=None,
    fixed_date=None,
):
    preview_df = build_adjustment_preview(adjustment_df).drop(columns=["合计"])
    if fixed_date is not None:
        preview_df = preview_df.drop(columns=["日期"])
    column_config = {
        "操作": st.column_config.SelectboxColumn(
            "操作", options=["增加", "扣减"], required=True
        ),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质"), required=True),
        "颜色": st.column_config.TextColumn(t("颜色"), required=True),
        "备注": st.column_config.TextColumn(t("备注")),
    }
    if fixed_date is None:
        column_config["日期"] = st.column_config.DateColumn(
            t("日期"), required=True
        )
    for size in SIZE_COLUMNS:
        column_config[size] = st.column_config.NumberColumn(
            size, min_value=0, step=1, format="%d"
        )
    disabled = ["操作"] if lock_operation else []
    if lock_identity:
        disabled.extend(["品牌", "材质", "颜色"])
        if fixed_date is None:
            disabled.append("日期")
    disabled.extend(disabled_columns or [])
    disabled = list(dict.fromkeys(disabled))
    edited_df = st.data_editor(
        preview_df,
        hide_index=True,
        num_rows="dynamic" if allow_rows else "fixed",
        width="stretch",
        disabled=disabled,
        column_config=column_config,
        key=key,
    )
    total = sum(
        pd.to_numeric(edited_df[size], errors="coerce").fillna(0).sum()
        for size in SIZE_COLUMNS
    )
    if fixed_date is not None:
        edited_df.insert(0, "日期", fixed_date)
    st.caption(f"{t('当前编辑总件数')}: {int(total):,}")
    return edited_df
