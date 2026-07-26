from hashlib import sha256
from io import BytesIO

from PIL import Image

from utils.image_tools.templates import (
    get_dieline_materials,
    get_dieline_models,
    load_local_dieline_template,
    model_sort_key,
)


def build_dieline_compatibility_groups():
    grouped = {}
    for material in get_dieline_materials():
        for model in get_dieline_models(material):
            mask_bytes, output_size = load_local_dieline_template(
                material,
                model,
            )
            with Image.open(BytesIO(mask_bytes)) as mask:
                pixels = mask.convert("L")
                printable_ratio = round(
                    sum(pixels.histogram()[128:])
                    / (pixels.width * pixels.height)
                    * 100,
                    1,
                )
                geometry_hash = sha256(pixels.tobytes()).hexdigest()
            key = (*output_size, geometry_hash)
            grouped.setdefault(key, []).append(
                {
                    "material": material,
                    "model": model,
                    "width": output_size[0],
                    "height": output_size[1],
                    "printable_ratio": printable_ratio,
                }
            )

    groups = []
    for index, (_, members) in enumerate(
        sorted(grouped.items(), key=_group_sort_key),
        start=1,
    ):
        materials = sorted({row["material"] for row in members})
        models = sorted({row["model"] for row in members})
        groups.append(
            {
                "group_id": f"P{index:02d}",
                "members": members,
                "materials": materials,
                "models": models,
                "width": members[0]["width"],
                "height": members[0]["height"],
                "printable_ratio": members[0]["printable_ratio"],
                "compatibility_type": _compatibility_type(
                    materials,
                    models,
                ),
            }
        )
    return groups


def find_compatibility_group(groups, material, model):
    return next(
        (
            group
            for group in groups
            if any(
                row["material"] == material and row["model"] == model
                for row in group["members"]
            )
        ),
        None,
    )


def build_full_report_rows(groups):
    rows = []
    for group in groups:
        for member in group["members"]:
            rows.append(
                {
                    "参数组": group["group_id"],
                    "材质": member["material"],
                    "型号": member["model"],
                    "目标宽度": member["width"],
                    "目标高度": member["height"],
                    "可打印面积": member["printable_ratio"],
                    "互用范围": group["compatibility_type"],
                    "互用数量": len(group["members"]),
                    "可互用刀模": _member_names(group),
                    "核对建议": _review_note(group),
                }
            )
    return rows


def build_material_family_details(groups):
    shared = {}
    independent = {}
    for group in groups:
        if len(group["members"]) == 1:
            member = group["members"][0]
            independent.setdefault(member["material"], []).append(
                member["model"]
            )
            continue
        if len(group["materials"]) <= 1:
            continue
        family = shared.setdefault(
            tuple(group["materials"]),
            {"common_models": [], "special_matches": []},
        )
        models = sorted(
            group["models"],
            key=model_sort_key,
            reverse=True,
        )
        models_by_material = [
            {
                member["model"]
                for member in group["members"]
                if member["material"] == material
            }
            for material in group["materials"]
        ]
        same_models = set.intersection(*models_by_material)
        family["common_models"].extend(same_models)
        if len(models) > 1:
            family["special_matches"].append(models)

    families = []
    for materials, details in shared.items():
        common_models = sorted(
            set(details["common_models"]),
            key=model_sort_key,
            reverse=True,
        )
        all_models_by_material = {
            material: {
                member["model"]
                for group in groups
                for member in group["members"]
                if member["material"] == material
            }
            for material in materials
        }
        families.append(
            {
                "materials": list(materials),
                "common_models": common_models,
                "special_matches": details["special_matches"],
                "remaining_by_material": {
                    material: sorted(
                        models - set(common_models),
                        key=model_sort_key,
                        reverse=True,
                    )
                    for material, models in all_models_by_material.items()
                },
            }
        )
    independent_details = [
        {
            "material": material,
            "models": sorted(
                set(models),
                key=model_sort_key,
                reverse=True,
            ),
        }
        for material, models in independent.items()
    ]
    return {
        "shared_families": families,
        "independent_materials": independent_details,
    }


def _compatibility_type(materials, models):
    if len(materials) > 1 and len(models) > 1:
        return "跨材质、跨型号"
    if len(models) > 1:
        return "跨型号"
    if len(materials) > 1:
        return "跨材质"
    return "无互用"


def _group_sort_key(item):
    width, height, geometry_hash = item[0]
    return (height, width, geometry_hash)


def _member_names(group):
    return "；".join(
        f"{row['material']} / {row['model']}"
        for row in group["members"]
    )


def _review_note(group):
    if len(group["models"]) > 1:
        return "跨型号，建议确认供应商命名"
    return ""
