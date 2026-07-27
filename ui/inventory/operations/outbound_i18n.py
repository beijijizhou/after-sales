from db.inventory.operations.outbound import OUTBOUND_SPECS


LANGUAGES = {
    "中文": "zh",
    "English": "en",
    "Español": "es",
}

TEXT = {
    "zh": {
        "title": "仓库每日出货",
        "notice": "仓库每日出货（库存扣减）：登记仓库当天提供给生产部门的正常出货，确认后会从库存中扣除。",
        "download": "下载仓库每日出货模板",
        "upload": "上传仓库每日出货 Excel / CSV（可选）",
        "read_error": "文件读取失败",
        "caption": "尺码栏填写箱数或包数，系统会在确认前换算为件数。",
        "rules_title": "包装换算规则",
        "rules_help": "遇到尚未录入的新包装规格时，可以根据以上件数推算相应的箱数或包数。",
        "rule_scope": "修改立即用于本次出库换算，不会写入数据库。",
        "rule_package": "包装方式",
        "rule_scope_column": "适用范围",
        "rule_units": "每箱 / 每包件数",
        "rule_reset": "恢复默认",
        "rule_sku": "SKU",
        "sku_rules_title": "SKU 特殊换算",
        "sku_rules_help": "点击表格底部的加号新增一行，选择 SKU、包装方式和每箱 / 每包件数。",
        "rule_labels": {
            "standard_box": "普通 Box",
            "mens_box": "Men's Box",
            "bag_s_l": "Bag",
            "bag_xl_3xl": "Bag",
            "bag_4xl_5xl": "Bag",
        },
        "rule_scopes": {
            "standard_box": "普通 SKU",
            "mens_box": "Men's SKU",
            "bag_s_l": "S-L",
            "bag_xl_3xl": "XL-3XL",
            "bag_4xl_5xl": "4XL-5XL",
        },
        "empty": "填写箱数或包数后，这里会显示换算件数",
        "preview": "换算件数确认",
        "total": "本次仓库出货总件数",
        "confirm": "确认登记仓库每日出货",
        "saved": "件仓库每日出货，库存已刷新",
        "save_error": "仓库每日出货登记失败",
        "file": "仓库每日出货模板.csv",
    },
    "en": {
        "title": "Warehouse Daily Outbound",
        "notice": "Warehouse daily outbound (inventory deduction): record normal stock issued to production, then confirm the inventory deduction.",
        "download": "Download outbound template",
        "upload": "Upload outbound Excel / CSV (optional)",
        "read_error": "Unable to read file",
        "caption": "Enter box or bag counts by size. Pieces are calculated before confirmation.",
        "rules_title": "Package Conversion Rules",
        "rules_help": "For a new package not yet listed, use these quantities to estimate the equivalent boxes or bags.",
        "rule_scope": "Applies only to this page and is not saved to the database.",
        "rule_package": "Package type",
        "rule_scope_column": "Applies to",
        "rule_units": "Pieces per box / bag",
        "rule_reset": "Restore default",
        "rule_sku": "SKU",
        "sku_rules_title": "SKU-specific Conversions",
        "sku_rules_help": "Add a row, then select the SKU, package type, and pieces per box or bag.",
        "rule_labels": {
            "standard_box": "Standard Box",
            "mens_box": "Men's Box",
            "bag_s_l": "Bag",
            "bag_xl_3xl": "Bag",
            "bag_4xl_5xl": "Bag",
        },
        "rule_scopes": {
            "standard_box": "Standard SKU",
            "mens_box": "Men's SKU",
            "bag_s_l": "S-L",
            "bag_xl_3xl": "XL-3XL",
            "bag_4xl_5xl": "4XL-5XL",
        },
        "empty": "Enter box or bag counts to preview the converted pieces.",
        "preview": "Confirm Converted Pieces",
        "total": "Total outbound pieces",
        "confirm": "Confirm daily outbound",
        "saved": "outbound pieces saved. Inventory refreshed.",
        "save_error": "Unable to save daily outbound",
        "file": "daily_outbound_template.csv",
    },
    "es": {
        "title": "Salida diaria de almacén",
        "notice": "Salida diaria de almacén (descuento de inventario): registre el inventario entregado normalmente a producción y confirme el descuento.",
        "download": "Descargar plantilla de salida",
        "upload": "Subir Excel / CSV de salida (opcional)",
        "read_error": "No se pudo leer el archivo",
        "caption": "Ingrese cajas o bolsas por talla. Las piezas se calculan antes de confirmar.",
        "rules_title": "Reglas de conversión de empaque",
        "rules_help": "Si aparece un empaque nuevo que aún no está listado, use estas cantidades para calcular cajas o bolsas equivalentes.",
        "rule_scope": "Solo se aplica a esta página y no se guarda en la base de datos.",
        "rule_package": "Tipo de empaque",
        "rule_scope_column": "Se aplica a",
        "rule_units": "Piezas por caja / bolsa",
        "rule_reset": "Restaurar valor predeterminado",
        "rule_sku": "SKU",
        "sku_rules_title": "Conversiones específicas por SKU",
        "sku_rules_help": "Agregue una fila y seleccione el SKU, el empaque y las piezas por caja o bolsa.",
        "rule_labels": {
            "standard_box": "Caja estándar",
            "mens_box": "Caja Men's",
            "bag_s_l": "Bolsa",
            "bag_xl_3xl": "Bolsa",
            "bag_4xl_5xl": "Bolsa",
        },
        "rule_scopes": {
            "standard_box": "SKU estándar",
            "mens_box": "SKU Men's",
            "bag_s_l": "S-L",
            "bag_xl_3xl": "XL-3XL",
            "bag_4xl_5xl": "4XL-5XL",
        },
        "empty": "Ingrese cajas o bolsas para ver las piezas convertidas.",
        "preview": "Confirmar piezas convertidas",
        "total": "Total de piezas de salida",
        "confirm": "Confirmar salida diaria",
        "saved": "piezas de salida guardadas. Inventario actualizado.",
        "save_error": "No se pudo guardar la salida diaria",
        "file": "plantilla_salida_diaria.csv",
    },
}

COLUMNS = {
    "zh": {"日期": "日期", "包装规格": "包装规格", "颜色": "颜色", "备注": "备注"},
    "en": {"日期": "Date", "包装规格": "Package", "颜色": "Color", "备注": "Note"},
    "es": {"日期": "Fecha", "包装规格": "Empaque", "颜色": "Color", "备注": "Nota"},
}

COLORS = {
    "zh": {"黑": "黑", "白": "白"},
    "en": {"黑": "Black", "白": "White"},
    "es": {"黑": "Negro", "白": "Blanco"},
}

PACKAGE_WORDS = {
    "zh": {"Box": "箱", "Bag": "包"},
    "en": {"Box": "Box", "Bag": "Bag"},
    "es": {"Box": "Caja", "Bag": "Bolsa"},
}

NOTES = {
    "zh": "仓库每日出货",
    "en": "Warehouse daily outbound",
    "es": "Salida diaria de almacén",
}


def translate_package(value, language):
    result = str(value)
    for source, target in PACKAGE_WORDS[language].items():
        result = result.replace(f"/{source}", f"/{target}")
    return result


def to_display_table(df, language):
    result = df.copy()
    result["包装规格"] = result["包装规格"].map(
        lambda value: translate_package(value, language)
    )
    result["颜色"] = result["颜色"].map(COLORS[language]).fillna(result["颜色"])
    result["备注"] = result["备注"].replace("每日正常出货", NOTES[language])
    return result.rename(columns=COLUMNS[language])


def to_internal_table(df, language):
    reverse_columns = {value: key for key, value in COLUMNS[language].items()}
    result = df.rename(columns=reverse_columns).copy()
    reverse_colors = {value: key for key, value in COLORS[language].items()}
    result["颜色"] = result["颜色"].map(reverse_colors).fillna(result["颜色"])
    result["备注"] = result["备注"].replace(NOTES[language], "每日正常出货")
    reverse_packages = {
        translate_package(value, language): value for value in OUTBOUND_SPECS
    }
    result["包装规格"] = result["包装规格"].map(reverse_packages).fillna(
        result["包装规格"]
    )
    return result
