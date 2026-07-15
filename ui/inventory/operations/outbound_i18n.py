from db.inventory.operations.outbound import OUTBOUND_SPECS


LANGUAGES = {
    "中文": "zh",
    "English": "en",
    "Español": "es",
}

TEXT = {
    "zh": {
        "title": "每日正常出货",
        "notice": "每日正常出货（库存扣减）：登记当天已经完成的正常出货，确认后会从库存中扣除。",
        "download": "下载每日出货模板",
        "upload": "上传每日出货 Excel / CSV（可选）",
        "read_error": "文件读取失败",
        "caption": "尺码栏填写箱数或包数，系统会在确认前换算为件数。",
        "rules_title": "包装换算规则",
        "rules": (
            "- 普通 Box：每箱 **72 件**\n"
            "- Men's Box：每箱 **100 件**\n"
            "- Bag（S-L）：每包 **300 件**\n"
            "- Bag（XL-3XL）：每包 **250 件**\n"
            "- Bag（4XL-5XL）：每包 **200 件**"
        ),
        "rules_help": "遇到尚未录入的新包装规格时，可以根据以上件数推算相应的箱数或包数。",
        "empty": "填写箱数或包数后，这里会显示换算件数",
        "preview": "换算件数确认",
        "total": "本次正常出货总件数",
        "confirm": "确认登记每日出货",
        "saved": "件正常出货，库存已刷新",
        "save_error": "每日出货登记失败",
        "file": "每日正常出货模板.csv",
    },
    "en": {
        "title": "Daily Outbound",
        "notice": "Daily outbound (inventory deduction): confirm completed shipments before deducting inventory.",
        "download": "Download outbound template",
        "upload": "Upload outbound Excel / CSV (optional)",
        "read_error": "Unable to read file",
        "caption": "Enter box or bag counts by size. Pieces are calculated before confirmation.",
        "rules_title": "Package Conversion Rules",
        "rules": (
            "- Standard Box: **72 pieces per box**\n"
            "- Men's Box: **100 pieces per box**\n"
            "- Bag (S-L): **300 pieces per bag**\n"
            "- Bag (XL-3XL): **250 pieces per bag**\n"
            "- Bag (4XL-5XL): **200 pieces per bag**"
        ),
        "rules_help": "For a new package not yet listed, use these quantities to estimate the equivalent boxes or bags.",
        "empty": "Enter box or bag counts to preview the converted pieces.",
        "preview": "Confirm Converted Pieces",
        "total": "Total outbound pieces",
        "confirm": "Confirm daily outbound",
        "saved": "outbound pieces saved. Inventory refreshed.",
        "save_error": "Unable to save daily outbound",
        "file": "daily_outbound_template.csv",
    },
    "es": {
        "title": "Salida diaria",
        "notice": "Salida diaria (descuento de inventario): confirme los envíos terminados antes de descontar el inventario.",
        "download": "Descargar plantilla de salida",
        "upload": "Subir Excel / CSV de salida (opcional)",
        "read_error": "No se pudo leer el archivo",
        "caption": "Ingrese cajas o bolsas por talla. Las piezas se calculan antes de confirmar.",
        "rules_title": "Reglas de conversión de empaque",
        "rules": (
            "- Caja estándar: **72 piezas por caja**\n"
            "- Caja Men's: **100 piezas por caja**\n"
            "- Bolsa (S-L): **300 piezas por bolsa**\n"
            "- Bolsa (XL-3XL): **250 piezas por bolsa**\n"
            "- Bolsa (4XL-5XL): **200 piezas por bolsa**"
        ),
        "rules_help": "Si aparece un empaque nuevo que aún no está listado, use estas cantidades para calcular cajas o bolsas equivalentes.",
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
    "zh": "每日正常出货",
    "en": "Daily outbound",
    "es": "Salida diaria",
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
