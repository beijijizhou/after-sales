import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = PROJECT_ROOT / "assets" / "dielines" / "phone_cases"
CATALOG_PATH = CATALOG_ROOT / "catalog.json"


def _load_catalog():
    if not CATALOG_PATH.exists():
        return {"materials": {}}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def get_dieline_materials():
    return list(_load_catalog()["materials"])


def get_dieline_models(material):
    details = _load_catalog()["materials"].get(material, {})
    return sorted(details.get("models", {}), key=model_sort_key)


def load_local_dieline_template(material, model):
    material_details = _load_catalog()["materials"].get(material)
    if material_details is None:
        raise ValueError(f"未找到刀模材质：{material}")
    model_details = material_details["models"].get(model)
    if model_details is None:
        raise ValueError(f"未找到刀模型号：{model}")

    path = CATALOG_ROOT / model_details["path"]
    if not path.exists():
        raise FileNotFoundError(f"刀模文件不存在：{path.name}")
    return path.read_bytes(), tuple(model_details["output_size"])


def match_dieline_template(path_text):
    normalized_path = _normalize_match_text(path_text)
    matches = []
    for material, material_details in _load_catalog()["materials"].items():
        material_scores = [
            len(_normalize_match_text(alias))
            for alias in material_details.get("aliases", [])
            if _normalize_match_text(alias) in normalized_path
        ]
        if not material_scores:
            continue
        for model, model_details in material_details["models"].items():
            model_scores = [
                len(_normalize_match_text(alias))
                for alias in model_details.get("aliases", [])
                if _normalize_match_text(alias) in normalized_path
            ]
            if model_scores:
                matches.append(
                    (
                        max(material_scores),
                        max(model_scores),
                        material,
                        model,
                    )
                )
    if not matches:
        return None
    best_score = max((row[0], row[1]) for row in matches)
    best = [
        (material, model)
        for material_score, model_score, material, model in matches
        if (material_score, model_score) == best_score
    ]
    return best[0] if len(best) == 1 else None


def _normalize_match_text(value):
    return "".join(
        character.lower()
        for character in str(value)
        if character.isalnum()
    )


def model_sort_key(model):
    match = re.fullmatch(
        r"iPhone (\d+)(?: (Mini|Plus|Pro|Pro Max|Air)|e)?",
        model,
    )
    if not match:
        return (999, 999, model)
    generation = int(match.group(1))
    suffix = model.removeprefix(f"iPhone {generation}")
    variant_order = {
        " Mini": 0,
        "": 1,
        "e": 2,
        " Plus": 3,
        " Air": 4,
        " Pro": 5,
        " Pro Max": 6,
    }
    return (generation, variant_order.get(suffix, 99), model)
