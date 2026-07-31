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
        "rule_material": "材质",
        "material_rules_title": "材质优先换算",
        "material_rules_help": "选择材质后，本次出库中该材质统一使用此换算单位，优先于 SKU 和普通规则。",
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
        "preview_check": "保存前整批核验",
        "detail_rows": "SKU 明细行数",
        "outbound_dates": "出库日期数",
        "submitted_total": "提交总件数",
        "database_total": "数据库入账总件数",
        "difference": "整批差额",
        "row_check": "SKU 明细核验",
        "row_match": "全部一致",
        "row_mismatch": "存在不一致",
        "audit_passed": "整批数据库核验通过",
        "audit_failed": "整批数据库核验未通过，请勿重复提交",
        "mismatch_details": "不一致明细",
        "inventory_issue": "当前出库包含缺失 SKU 或库存不足，无法保存。",
        "inventory_issue_help": "请先修正 SKU 或库存数量；系统已停止整批保存，其他正常行也不会被悄悄遗漏。",
        "inventory_check_error": "库存预检查失败",
        "outbound_quantity": "出库件数",
        "current_inventory": "当前库存",
        "shortage": "缺口",
        "unsaved": "当前内容只是预览，尚未保存到数据库。请核对后点击下方确认按钮。",
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
        "rule_material": "Material",
        "material_rules_title": "Material-priority Conversions",
        "material_rules_help": "For this outbound, the selected material uses one fixed conversion before SKU-specific and general rules.",
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
        "preview_check": "Pre-save batch check",
        "detail_rows": "SKU detail rows",
        "outbound_dates": "Outbound dates",
        "submitted_total": "Submitted pieces",
        "database_total": "Database pieces",
        "difference": "Batch difference",
        "row_check": "SKU detail check",
        "row_match": "All matched",
        "row_mismatch": "Mismatch found",
        "audit_passed": "Database batch verification passed",
        "audit_failed": "Database batch verification failed. Do not resubmit.",
        "mismatch_details": "Mismatch details",
        "inventory_issue": "This outbound contains a missing SKU or insufficient inventory and cannot be saved.",
        "inventory_issue_help": "Correct the SKU or inventory first. The entire batch has been stopped so valid rows are not silently omitted.",
        "inventory_check_error": "Inventory pre-check failed",
        "outbound_quantity": "Outbound quantity",
        "current_inventory": "Current inventory",
        "shortage": "Shortage",
        "unsaved": "This is only a preview and has not been saved. Review it, then confirm below.",
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
        "rule_material": "Material",
        "material_rules_title": "Conversión prioritaria por material",
        "material_rules_help": "Para esta salida, el material seleccionado usa una conversión fija antes que las reglas de SKU y generales.",
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
        "preview_check": "Verificación del lote antes de guardar",
        "detail_rows": "Filas de SKU",
        "outbound_dates": "Fechas de salida",
        "submitted_total": "Piezas enviadas",
        "database_total": "Piezas registradas",
        "difference": "Diferencia del lote",
        "row_check": "Verificación de SKU",
        "row_match": "Todo coincide",
        "row_mismatch": "Hay diferencias",
        "audit_passed": "Verificación del lote aprobada",
        "audit_failed": "La verificación falló. No vuelva a enviar.",
        "mismatch_details": "Detalles de diferencias",
        "inventory_issue": "Esta salida contiene un SKU inexistente o inventario insuficiente y no se puede guardar.",
        "inventory_issue_help": "Corrija primero el SKU o el inventario. Se detuvo todo el lote para evitar omitir filas válidas.",
        "inventory_check_error": "Falló la validación previa del inventario",
        "outbound_quantity": "Cantidad de salida",
        "current_inventory": "Inventario actual",
        "shortage": "Faltante",
        "unsaved": "Esto es solo una vista previa y todavía no se ha guardado. Revísela y confirme abajo.",
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


def untranslate_package(value, language):
    result = str(value)
    for source, target in PACKAGE_WORDS[language].items():
        result = result.replace(f"/{target}", f"/{source}")
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
    result["包装规格"] = result["包装规格"].map(
        lambda value: untranslate_package(value, language)
    )
    return result
