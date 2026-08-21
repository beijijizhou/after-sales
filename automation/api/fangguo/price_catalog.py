import pandas as pd

from automation.price_catalogs.haloopod import CATALOG_VERSION
_SIZES = {"S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"}
_LARGE = {"4XL", "5XL"}


def latest_apparel_target_price(row):
    material = str(row.get("materialCode") or "").strip()
    color = str(row.get("colorCode") or "").strip()
    size = str(row.get("modelCode") or "").strip().upper()
    double = str(row.get("technologyName") or "").strip() == "双面"
    if material != "帆布袋" and size not in _SIZES:
        return None
    if material == "CVC_男T" and color in {"黑色", "白色"}:
        return (19.5 if size in _LARGE else 17.5) + (2 if double else 0)
    if material == "180g纯棉_男T":
        if color in {"黑色", "白色"}:
            price = 25 if size in _LARGE else 23
        elif color in {"深灰", "浅灰", "灰色", "黄色", "绿色", "红色", "橘色", "紫色", "蓝色", "粉色", "墨绿", "蓝绿"}:
            price = 27 if size in _LARGE else 25
        else:
            return None
        return price + (2 if double else 0)
    male = {
        "男连帽卫衣薄款": (40, 47), "男连帽卫衣薄款单面": (40, 40),
        "男连帽卫衣加绒": (50, 57), "男连帽卫衣加绒单面": (50, 50),
        "男圆领卫衣薄款": (35, 42), "男圆领卫衣薄款单面": (35, 35),
        "男圆领卫衣加绒": (45, 52), "男圆领卫衣加绒单面": (45, 45),
    }
    if material in male and color in {"黑色", "白色", "灰色", "红色"}:
        single, two_face = male[material]
        return (two_face if double else single) + (7 if size in _LARGE else 0)
    if material in {"女收腰短袖", "女收腰短袖单面"}:
        if color in {"黑色", "白色"}:
            price = 23
        elif color in {"粉色", "Pink", "卡其", "卡其色", "灰色"}:
            price = 25
        else:
            return None
        return price + (2 if double else 0)
    female = {
        "女连帽卫衣薄款": (40, 47), "女连帽卫衣薄款单面": (40, 40),
        "女连帽卫衣加绒": (47, 54), "女连帽卫衣加绒单面": (47, 47),
    }
    if material in female and color in {"黑色", "白色", "灰色", "海军蓝", "Navy"}:
        single, two_face = female[material]
        return two_face if double else single
    if material == "帆布袋":
        return 22 if double else 19
    return None

def build_latest_catalog_changes(source_rows, selected_ids):
    columns = ["skuId", "materialCode", "colorCode", "modelCode", "technologyName", "currentPrice", "increase", "newPrice", "sourcePayload"]
    if source_rows.empty or "sourcePayload" not in source_rows:
        return pd.DataFrame(columns=columns)
    selected = source_rows[source_rows["skuId"].astype(int).isin({int(v) for v in selected_ids})]
    changes = []
    for row in selected.to_dict("records"):
        target = latest_apparel_target_price(row)
        current = pd.to_numeric(row.get("currentSkuPrice"), errors="coerce")
        if target is None or pd.isna(current) or abs(float(target) - float(current)) <= 0.00005:
            continue
        changes.append({"skuId": int(row["skuId"]), "materialCode": row["materialCode"], "colorCode": row["colorCode"], "modelCode": row["modelCode"], "technologyName": row.get("technologyName", ""), "currentPrice": float(current), "increase": round(float(target) - float(current), 4), "newPrice": float(target), "sourcePayload": row["sourcePayload"]})
    return pd.DataFrame(changes, columns=columns)
