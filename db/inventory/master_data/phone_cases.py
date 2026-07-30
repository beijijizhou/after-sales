from utils.image_tools.templates import (
    get_dieline_materials,
    get_dieline_models,
)


def build_phone_case_sku_rows():
    return [
        {
            "SKU 名称": f"{material} {model}",
            "品牌": "",
            "材质": material,
            "颜色": "",
            "规格": model,
            "单位": "件",
        }
        for material in get_dieline_materials()
        for model in get_dieline_models(material)
    ]
