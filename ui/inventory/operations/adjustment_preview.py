import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t
from ui.table_layout import fit_table_height
from utils.sku_sorting import sort_sku_rows


COMPARISON_COLUMNS = [
    "材质", "品牌", "颜色", "尺码", "当前库存", "本次变动", "调整后库存",
]


def build_inventory_change_comparison(inventory_df, adjustment_df):
    """Build a common before/change/after review from normalized SKU rows."""
    inventory = pd.DataFrame(inventory_df).rename(columns={
        "department": "部门", "category": "品类",
        "brand": "品牌", "material": "材质",
        "color": "颜色", "size": "尺码", "quantity": "当前库存",
        "总库存": "当前库存", "型号": "尺码",
    }).copy()
    changes = pd.DataFrame(adjustment_df).rename(columns={
        "department": "部门", "category": "品类",
        "brand": "品牌", "material": "材质",
        "color": "颜色", "size": "尺码", "quantity": "数量",
    }).copy()
    if changes.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    identity = [
        column for column in ["部门", "品类", "材质", "品牌", "颜色", "尺码"]
        if column in changes.columns
    ]
    required = {"材质", "品牌", "颜色", "尺码"}
    if not required.issubset(identity):
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    for frame in [inventory, changes]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
    changes["数量"] = pd.to_numeric(
        changes.get("数量", pd.Series(0, index=changes.index)), errors="coerce"
    ).fillna(0).astype(int)
    if "操作" in changes:
        direction = changes["操作"].map({"增加": 1, "扣减": -1}).fillna(0)
        changes["本次变动"] = changes["数量"] * direction.astype(int)
    elif "quantity_change" in changes:
        changes["本次变动"] = pd.to_numeric(
            changes["quantity_change"], errors="coerce"
        ).fillna(0).astype(int)
    else:
        changes["本次变动"] = changes["数量"]
    changes = changes[changes["本次变动"] != 0]
    if changes.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    inventory["当前库存"] = pd.to_numeric(
        inventory.get(
            "当前库存", pd.Series(0, index=inventory.index)
        ), errors="coerce"
    ).fillna(0).astype(int)
    current = inventory.groupby(identity, dropna=False)["当前库存"].sum()
    grouped = changes.groupby(identity, dropna=False, sort=False)["本次变动"].sum()
    rows = []
    for key, change in grouped.items():
        key = key if isinstance(key, tuple) else (key,)
        current_quantity = int(current.get(key, 0))
        row = dict(zip(identity, key))
        row.update({
            "当前库存": current_quantity,
            "本次变动": int(change),
            "调整后库存": current_quantity + int(change),
        })
        rows.append(row)
    columns = [
        *[column for column in ["部门", "品类"] if column in identity],
        *COMPARISON_COLUMNS,
    ]
    return sort_sku_rows(
        pd.DataFrame(rows, columns=columns),
        material="材质", color="颜色", size="尺码",
        leading=[
            column for column in ["部门", "品类", "材质", "品牌"]
            if column in columns
        ],
    )


def render_inventory_change_comparison(
    comparison, *, action=None, title="保存前库存核对", unit="件",
):
    """Render the ERP-wide three-stage stock review table."""
    comparison = pd.DataFrame(comparison).copy()
    if comparison.empty:
        return comparison
    if action is None:
        directions = set(
            "增加" if int(value) > 0 else "扣减"
            for value in comparison["本次变动"] if int(value) != 0
        )
        action = directions.pop() if len(directions) == 1 else "变动"
    operation_column = {
        "增加": "本次入库 (+)", "扣减": "本次出库 (-)",
    }.get(action, "本次变动 (+/-)")
    st.markdown(f"#### {title}")
    st.caption("每行代表一个 SKU；当前库存 + 本次变动 = 调整后库存。")
    negative = comparison["调整后库存"] < 0
    if negative.any():
        st.error(f"有 {int(negative.sum())} 个 SKU 调整后会出现负库存。")
    display = comparison.rename(columns={"本次变动": operation_column})
    display[operation_column] = display[operation_column].map(_format_signed)
    st.dataframe(
        display, hide_index=True, width="stretch",
        height=fit_table_height(display),
        column_config={
            "当前库存": st.column_config.NumberColumn(format=f"%d {unit}"),
            "调整后库存": st.column_config.NumberColumn(format=f"%d {unit}"),
        },
    )
    return comparison


def build_adjustment_stock_comparison(inventory_df, edited_df, action):
    """Build one review row per edited SKU: current + change = result."""
    inventory = pd.DataFrame(inventory_df).copy()
    edited = pd.DataFrame(edited_df).copy()
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    if {"型号", "数量"}.issubset(edited.columns):
        return _build_model_stock_comparison(inventory, edited, action)

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
    rows = []
    for item in identities.to_dict("records"):
        key = tuple(item[column] for column in identity)
        current_values = _wide_values(current_by_key, key)
        change_values = _wide_values(changes_by_key, key) * direction
        for size in SIZE_COLUMNS:
            change = int(change_values[size])
            if change == 0:
                continue
            current_quantity = int(current_values[size])
            rows.append({
                "材质": item["材质"],
                "品牌": item["品牌"],
                "颜色": item["颜色"],
                "尺码": size,
                "当前库存": current_quantity,
                "本次变动": change,
                "调整后库存": current_quantity + change,
            })
    return sort_sku_rows(
        pd.DataFrame(rows, columns=COMPARISON_COLUMNS),
        material="材质", color="颜色", size="尺码",
        leading=["材质", "品牌"],
    )


def render_adjustment_stock_comparison(inventory_df, edited_df, action):
    comparison = build_adjustment_stock_comparison(
        inventory_df, edited_df, action
    )
    if comparison.empty:
        return comparison
    return render_inventory_change_comparison(comparison, action=action)


def _build_model_stock_comparison(inventory, edited, action):
    identity = ["材质", "品牌", "颜色", "型号"]
    for frame in [inventory, edited]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
    edited["数量"] = pd.to_numeric(
        edited["数量"], errors="coerce"
    ).fillna(0).astype(int)
    edited = edited[edited["数量"] > 0]
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    current_column = next(
        (column for column in ["总库存", "数量", "quantity"] if column in inventory),
        None,
    )
    if current_column is None:
        inventory["_current_quantity"] = 0
        current_column = "_current_quantity"
    inventory[current_column] = pd.to_numeric(
        inventory[current_column], errors="coerce"
    ).fillna(0).astype(int)
    current = inventory.groupby(identity, dropna=False)[current_column].sum()
    changes = edited.groupby(identity, dropna=False, sort=False)["数量"].sum()
    direction = 1 if action == "增加" else -1
    rows = []
    for key, quantity in changes.items():
        key = key if isinstance(key, tuple) else (key,)
        current_quantity = int(current.get(key, 0))
        change = int(quantity) * direction
        rows.append({
            "材质": key[0], "品牌": key[1], "颜色": key[2],
            "尺码": key[3], "当前库存": current_quantity,
            "本次变动": change,
            "调整后库存": current_quantity + change,
        })
    return sort_sku_rows(
        pd.DataFrame(rows, columns=COMPARISON_COLUMNS),
        material="材质", color="颜色", size="尺码",
        leading=["材质", "品牌"],
    )


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
