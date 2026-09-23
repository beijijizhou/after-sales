"""Build audited quantity-delta corrections for an existing inventory batch."""

import pandas as pd

from utils.sku_sorting import sort_sku_rows


IDENTITY_COLUMNS = ["brand", "material", "color", "size"]
EDITOR_IDENTITY_COLUMNS = ["品牌", "材质", "颜色", "尺码"]


def build_batch_correction_editor(movements):
    """Return one editable row per SKU with the original absolute quantity."""
    source = pd.DataFrame(movements).copy()
    columns = [
        "品牌", "材质", "颜色", "尺码", "原批次数量", "校准后数量",
        "原单位成本",
    ]
    if source.empty:
        return pd.DataFrame(columns=columns)
    quantities = pd.to_numeric(
        source.get("quantity_change"), errors="coerce"
    ).fillna(0).astype(int)
    nonzero = quantities[quantities.ne(0)]
    if nonzero.empty:
        return pd.DataFrame(columns=columns)
    if nonzero.gt(0).any() and nonzero.lt(0).any():
        raise ValueError("混合增减批次暂不支持数量校准")
    source["quantity_change"] = quantities
    for column in IDENTITY_COLUMNS:
        if column not in source:
            source[column] = ""
        source[column] = source[column].fillna("").astype(str).str.strip()
    source["size"] = source["size"].str.upper()
    source["unit_cost"] = pd.to_numeric(
        source.get("unit_cost"), errors="coerce"
    )
    grouped = source.groupby(
        IDENTITY_COLUMNS, as_index=False, sort=False, dropna=False
    ).agg(quantity_change=("quantity_change", "sum"), unit_cost=("unit_cost", "last"))
    grouped["原批次数量"] = grouped["quantity_change"].abs().astype(int)
    grouped["校准后数量"] = grouped["原批次数量"]
    grouped = grouped.rename(columns={
        "brand": "品牌", "material": "材质", "color": "颜色", "size": "尺码",
        "unit_cost": "原单位成本",
    })
    return sort_sku_rows(
        grouped[columns], material="材质", color="颜色", size="尺码",
        leading=["材质", "品牌"],
    ).reset_index(drop=True)


def build_batch_correction_adjustments(
    movements, edited, original_batch_id, reason_prefix="批次数量校准",
):
    """Translate corrected absolute quantities into signed inventory deltas."""
    source = pd.DataFrame(movements).copy()
    editor = pd.DataFrame(edited).copy()
    if source.empty or editor.empty:
        return pd.DataFrame()
    quantities = pd.to_numeric(
        source.get("quantity_change"), errors="coerce"
    ).fillna(0).astype(int)
    nonzero = quantities[quantities.ne(0)]
    if nonzero.empty:
        return pd.DataFrame()
    if nonzero.gt(0).any() and nonzero.lt(0).any():
        raise ValueError("混合增减批次暂不支持数量校准")
    direction = 1 if nonzero.iloc[0] > 0 else -1
    movement_dates = pd.to_datetime(
        source.get("movement_date"), errors="coerce"
    ).dt.date.dropna().unique()
    if len(movement_dates) != 1:
        raise ValueError("批次必须只有一个业务日期")
    editor["原批次数量"] = pd.to_numeric(
        editor["原批次数量"], errors="coerce"
    ).fillna(0).astype(int)
    editor["校准后数量"] = pd.to_numeric(
        editor["校准后数量"], errors="coerce"
    ).fillna(0).astype(int)
    if "校准后成本" in editor:
        editor["校准后成本"] = pd.to_numeric(
            editor["校准后成本"], errors="coerce"
        )
    if editor["校准后数量"].lt(0).any():
        raise ValueError("校准后数量不能小于 0")
    editor["差额"] = (
        editor["校准后数量"] - editor["原批次数量"]
    ) * direction
    rows = []
    for row in editor[editor["差额"].ne(0)].to_dict("records"):
        delta = int(row["差额"])
        rows.append({
            "日期": movement_dates[0],
            "操作": "增加" if delta > 0 else "扣减",
            "品牌": str(row.get("品牌") or "").strip(),
            "材质": str(row.get("材质") or "").strip(),
            "颜色": str(row.get("颜色") or "").strip(),
            "尺码": str(row.get("尺码") or "").strip().upper(),
            "数量": abs(delta),
            "成本": row.get("校准后成本", row.get("原单位成本", pd.NA)),
            "备注": (
                f"{reason_prefix}｜原批次 {original_batch_id}｜"
                f"{int(row['原批次数量'])}→{int(row['校准后数量'])}"
            ),
        })
    return pd.DataFrame(rows)


def attach_batch_cost_lots(editor, cost_lots):
    """Attach the current active cost-lot identity to an inbound editor."""
    result = pd.DataFrame(editor).copy()
    lots = pd.DataFrame(cost_lots).copy()
    result["成本批次ID"] = ""
    result["校准后成本"] = pd.to_numeric(
        result.get("原单位成本"), errors="coerce"
    )
    if result.empty or lots.empty:
        return result
    lots = lots.rename(columns={
        "record_id": "成本批次ID", "unit_cost": "当前批次成本",
        "brand": "品牌", "material": "材质", "color": "颜色",
        "size": "尺码",
    })
    for column in EDITOR_IDENTITY_COLUMNS:
        result[column] = result[column].fillna("").astype(str).str.strip()
        lots[column] = lots[column].fillna("").astype(str).str.strip()
    result["尺码"] = result["尺码"].str.upper()
    lots["尺码"] = lots["尺码"].str.upper()
    if lots.duplicated(EDITOR_IDENTITY_COLUMNS, keep=False).any():
        raise ValueError("同一批次的相同 SKU 存在多个成本记录，暂不能直接修改")
    lookup = lots.set_index(EDITOR_IDENTITY_COLUMNS)[
        ["成本批次ID", "当前批次成本"]
    ]
    for index, row in result.iterrows():
        identity = tuple(row[column] for column in EDITOR_IDENTITY_COLUMNS)
        if identity not in lookup.index:
            continue
        match = lookup.loc[identity]
        result.at[index, "成本批次ID"] = str(match["成本批次ID"])
        result.at[index, "原单位成本"] = match["当前批次成本"]
        result.at[index, "校准后成本"] = match["当前批次成本"]
    return result


def find_batch_cost_changes(original, edited):
    """Return validated ``(cost_lot_id, unit_cost)`` edits."""
    before = pd.DataFrame(original).copy()
    after = pd.DataFrame(edited).copy()
    if "成本批次ID" not in after or "校准后成本" not in after:
        return []
    before_costs = before.set_index("成本批次ID")["原单位成本"]
    changes = []
    for row in after.to_dict("records"):
        cost_lot_id = str(row.get("成本批次ID") or "").strip()
        if not cost_lot_id:
            continue
        new_cost = pd.to_numeric(row.get("校准后成本"), errors="coerce")
        if pd.isna(new_cost) or float(new_cost) <= 0:
            raise ValueError("校准后成本必须大于 0")
        old_cost = pd.to_numeric(before_costs.get(cost_lot_id), errors="coerce")
        if pd.isna(old_cost) or abs(float(new_cost) - float(old_cost)) > 0.00005:
            changes.append((cost_lot_id, round(float(new_cost), 4)))
    return changes
