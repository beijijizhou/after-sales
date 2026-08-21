from hashlib import sha256
from pathlib import Path

import pandas as pd
import streamlit as st

from automation.api.fangguo import (
    CATALOG_VERSION,
    build_latest_catalog_changes,
    fetch_fangguo_sku_prices,
    update_fangguo_sku_prices,
)
from automation.price_catalogs.haloopod import PRICE_CATALOG_ROWS
from ui.finance.haloopod_price_workbook import build_haloopod_price_workbook


STATE_PREVIEW = "finance_fangguo_sku_price_preview"
PRICE_ASSET_DIR = Path("assets/finance/halo_opod_2026_08")


def render_batch_price_editor(credentials, rows, on_refreshed):
    st.markdown("#### 批量价格调整")
    if (
        "sourcePayload" not in rows
        or not rows["sourcePayload"].map(lambda value: isinstance(value, dict)).all()
    ):
        st.warning(
            "当前页面仍是旧版缓存数据，不能安全提交价格。"
            "请点击上方“读取最新方果 SKU”后再进行批量调整。"
        )
        return
    st.warning(
        "这是方果线上价格写入操作。默认作用于当前筛选的全部 SKU；"
        "提交前必须核对涨价规则、SKU 范围、原价和新价。"
    )
    scope = st.segmented_control(
        "改价范围",
        ["当前筛选全部 SKU", "手动排除 / 选择"],
        default="当前筛选全部 SKU",
        key="fangguo_sku_price_scope",
    ) or "当前筛选全部 SKU"
    selected_ids = rows["skuId"].astype(int).tolist()
    if scope == "手动排除 / 选择":
        selected_ids = _render_manual_selection(rows)

    method_label = st.segmented_control(
        "涨价方式",
        ["按最新服装价目表", "每个 SKU 加固定金额", "按当前价格上涨百分比"],
        default="按最新服装价目表",
        key="fangguo_sku_price_method",
    ) or "每个 SKU 加固定金额"
    if method_label == "按最新服装价目表":
        method, value = "catalog", 0
        rule_text = CATALOG_VERSION
        st.caption("工艺为空或“背面”按单面价；只有“双面”按双面价。无法对应的材质、颜色或尺码不会修改。")
    elif method_label == "每个 SKU 加固定金额":
        method = "fixed"
        value = st.number_input(
            "每个 SKU 涨价金额",
            min_value=0.01,
            value=1.00,
            step=0.01,
            format="%.4f",
            key="fangguo_sku_fixed_increase",
        )
        rule_text = f"每个 SKU 当前价格 + ${float(value):.4f}"
    else:
        method = "percent"
        value = st.number_input(
            "上涨百分比",
            min_value=0.01,
            value=5.00,
            step=0.10,
            format="%.2f",
            key="fangguo_sku_percent_increase",
        )
        rule_text = f"每个 SKU 当前价格上涨 {float(value):.2f}%"

    st.info(
        f"当前规则：{rule_text}｜将作用于 {len(selected_ids):,} 个 SKU"
    )
    changes = build_latest_catalog_changes(rows, selected_ids) if method == "catalog" else build_bulk_price_changes(rows, selected_ids, method, value)
    signature = _changes_signature(changes)
    if st.button(
        "生成批量改价预览",
        type="primary",
        key="fangguo_sku_price_preview_button",
    ):
        if changes.empty:
            st.warning("当前没有需要调整价格的 SKU，请检查筛选范围和选择。")
        else:
            st.session_state[STATE_PREVIEW] = {
                "signature": signature,
                "changes": changes,
                "rule_text": rule_text,
            }

    preview = st.session_state.get(STATE_PREVIEW)
    if not preview or preview.get("signature") != signature:
        if preview:
            st.session_state.pop(STATE_PREVIEW, None)
            st.info("选择或价格已变化，请重新生成预览。")
        return
    _render_preview(
        credentials,
        preview["changes"],
        preview["rule_text"],
        on_refreshed,
    )


def build_bulk_price_changes(source_rows, selected_ids, method, value):
    columns = [
        "skuId", "materialCode", "colorCode", "modelCode", "technologyName",
        "currentPrice", "increase", "newPrice", "sourcePayload",
    ]
    if source_rows.empty or not selected_ids or "sourcePayload" not in source_rows:
        return pd.DataFrame(columns=columns)
    adjustment = float(value)
    if adjustment <= 0 or method not in {"fixed", "percent"}:
        return pd.DataFrame(columns=columns)
    selected = source_rows[
        source_rows["skuId"].astype(int).isin({int(value) for value in selected_ids})
    ].copy()
    changes = []
    for row in selected.to_dict("records"):
        current = float(row["currentSkuPrice"])
        new_price = (
            current + adjustment
            if method == "fixed"
            else current * (1 + adjustment / 100)
        )
        new_price = round(new_price, 4)
        changes.append({
            "skuId": int(row["skuId"]),
            "materialCode": row["materialCode"],
            "colorCode": row["colorCode"],
            "modelCode": row["modelCode"],
            "technologyName": row.get("technologyName", ""),
            "currentPrice": current,
            "increase": round(new_price - current, 4),
            "newPrice": new_price,
            "sourcePayload": row["sourcePayload"],
        })
    return pd.DataFrame(changes, columns=columns)


def build_sku_price_changes(source_rows, edited):
    columns = [
        "skuId", "materialCode", "colorCode", "modelCode", "technologyName",
        "currentPrice", "increase", "newPrice", "sourcePayload",
    ]
    if source_rows.empty or edited.empty or "选择" not in edited:
        return pd.DataFrame(columns=columns)
    selected = edited[edited["选择"].fillna(False)].copy()
    if selected.empty:
        return pd.DataFrame(columns=columns)
    source = source_rows.set_index("skuId", drop=False)
    changes = []
    for row in selected.to_dict("records"):
        sku_id = int(row["方果 SKU ID"])
        new_price = pd.to_numeric(row.get("新价格"), errors="coerce")
        if pd.isna(new_price) or float(new_price) <= 0 or sku_id not in source.index:
            continue
        original = source.loc[sku_id]
        current = float(original["currentSkuPrice"])
        if abs(float(new_price) - current) <= 0.00005:
            continue
        changes.append({
            "skuId": sku_id,
            "materialCode": original["materialCode"],
            "colorCode": original["colorCode"],
            "modelCode": original["modelCode"],
            "technologyName": original.get("technologyName", ""),
            "currentPrice": current,
            "increase": round(float(new_price) - current, 4),
            "newPrice": round(float(new_price), 4),
            "sourcePayload": original["sourcePayload"],
        })
    return pd.DataFrame(changes, columns=columns)


def _selection_rows(rows):
    result = rows.rename(columns={
        "skuId": "方果 SKU ID", "materialCode": "材质 / 商品",
        "colorCode": "颜色", "modelCode": "型号 / 尺码",
        "technologyName": "印花面 / 工艺",
        "currentSkuPrice": "当前价格",
    })[[
        "方果 SKU ID", "材质 / 商品", "颜色", "型号 / 尺码",
        "印花面 / 工艺", "当前价格",
    ]].copy()
    result.insert(0, "选择", False)
    return result


def _render_manual_selection(rows):
    editor = _selection_rows(rows)
    editor_version = _editor_signature(rows)
    edited = pd.DataFrame(st.data_editor(
        editor,
        hide_index=True,
        width="stretch",
        height=min(600, 38 * (len(editor) + 1) + 4),
        disabled=[
            "方果 SKU ID", "材质 / 商品", "颜色", "型号 / 尺码", "当前价格",
            "印花面 / 工艺",
        ],
        column_config={
            "选择": st.column_config.CheckboxColumn(default=False),
            "当前价格": st.column_config.NumberColumn(format="$%.4f"),
        },
        key=f"fangguo_sku_batch_selection_{editor_version}",
    ))
    return edited.loc[
        edited["选择"].fillna(False), "方果 SKU ID"
    ].astype(int).tolist()


def _render_preview(credentials, changes, rule_text, on_refreshed):
    st.markdown("#### 改价确认")
    metrics = st.columns(3)
    metrics[0].metric("将修改 SKU", f"{len(changes):,}")
    metrics[1].metric("最低新价格", f"${changes['newPrice'].min():,.4f}")
    metrics[2].metric("最高新价格", f"${changes['newPrice'].max():,.4f}")
    st.info(f"本次规则：{rule_text}")
    preview = changes.drop(columns="sourcePayload").rename(columns={
        "skuId": "方果 SKU ID", "materialCode": "材质 / 商品",
        "colorCode": "颜色", "modelCode": "型号 / 尺码",
        "technologyName": "印花面 / 工艺",
        "currentPrice": "当前价格", "increase": "本次调整",
        "newPrice": "修改后价格",
    })
    st.dataframe(preview, hide_index=True, width="stretch")
    confirmed = st.checkbox(
        "我已核对以上 SKU 和价格，确认写入方果",
        key="fangguo_sku_price_confirmed",
    )
    if not st.button(
        "确认批量修改方果价格",
        type="primary",
        disabled=not confirmed,
        key="fangguo_sku_price_apply",
    ):
        return
    status = st.empty()
    result = update_fangguo_sku_prices(
        credentials,
        changes.to_dict("records"),
        report_progress=status.info,
    )
    failures = result[~result["success"]]
    if not failures.empty:
        st.error(f"{len(failures):,} 个 SKU 修改失败，请核对结果。")
        st.dataframe(result, hide_index=True, width="stretch")
        return
    with st.spinner("正在回读方果价格核验..."):
        refreshed = fetch_fangguo_sku_prices(
            credentials, include_inactive=True
        )
    expected = changes.set_index("skuId")["newPrice"].to_dict()
    actual = refreshed.set_index("skuId")["currentSkuPrice"].to_dict()
    mismatches = [
        sku_id for sku_id, price in expected.items()
        if sku_id not in actual or abs(float(actual[sku_id]) - float(price)) > 0.00005
    ]
    if mismatches:
        st.error(f"写入后有 {len(mismatches):,} 个 SKU 的回读价格不一致。")
        return
    st.session_state.pop(STATE_PREVIEW, None)
    on_refreshed(refreshed)
    status.success(f"已修改并核验 {len(changes):,} 个方果 SKU 价格")
    st.rerun()


def render_price_reference():
    st.markdown("### 最新价格表")
    st.caption("这是方果批量调整使用的结构化价格表。单面包含空工艺和“背面”；只有“双面”使用双面价。")
    table = pd.DataFrame(PRICE_CATALOG_ROWS, columns=["材质", "颜色范围", "尺码", "单面 / 背面", "双面"])
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("下载价格表 Excel", build_haloopod_price_workbook(), file_name="HalooPOD白墨烫画价格表2026.08.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="haloopod_price_excel")
    with st.expander("查看原始 PDF 图片", expanded=False):
        st.caption("批量调整使用结构化价格规则；以下保留 PDF 原图用于逐页核对。")
        images = sorted(PRICE_ASSET_DIR.glob("page-*.png"))
        for index, image_path in enumerate(images, start=1):
            st.markdown(f"**第 {index} 页**")
            st.image(str(image_path), width="stretch")
        pdf_path = PRICE_ASSET_DIR / "HalooPOD白墨烫画货盘2026.08.pdf"
        if pdf_path.exists():
            st.download_button(
                "下载原始价格 PDF",
                pdf_path.read_bytes(),
                file_name=pdf_path.name,
                mime="application/pdf",
                key="fangguo_price_reference_pdf",
            )


def _changes_signature(changes):
    if changes.empty:
        return ""
    values = [
        f"{row.skuId}:{row.currentPrice:.4f}:{row.newPrice:.4f}"
        for row in changes.itertuples()
    ]
    return sha256("|".join(values).encode()).hexdigest()


def _editor_signature(rows):
    if rows.empty:
        return "empty"
    values = [
        f"{row.skuId}:{float(row.currentSkuPrice):.4f}"
        for row in rows.itertuples()
    ]
    return sha256("|".join(values).encode()).hexdigest()[:12]
