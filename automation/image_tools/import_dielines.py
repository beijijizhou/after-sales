import argparse
import json
from pathlib import Path
import re

from utils.image_tools.dieline import extract_colored_dieline_mask


MATERIALS = {
    "亚克力TPU": (
        "亚克力 TPU",
        "acrylic_tpu",
        ["亚克力", "透明手机壳"],
    ),
    "硅胶手机壳": ("硅胶手机壳", "silicone", ["硅胶"]),
    "磨砂TPU": ("磨砂 TPU", "matte_tpu", ["磨砂"]),
    "PC大孔TPU": (
        "PC 大孔 TPU",
        "pc_large_hole_tpu",
        ["PC大孔", "大孔TPU"],
    ),
    "PC精孔TPU": (
        "PC 精孔 TPU",
        "pc_precision_hole_tpu",
        ["PC精孔", "精孔TPU"],
    ),
}


def format_model_name(value):
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    match = re.fullmatch(
        r"iphone(\d+)(promax|pro|plus|mini|min|air|e)?",
        normalized,
    )
    if not match:
        return value
    generation, variant = match.groups()
    variant_names = {
        None: "",
        "e": "e",
        "min": " Mini",
        "mini": " Mini",
        "plus": " Plus",
        "pro": " Pro",
        "promax": " Pro Max",
        "air": " Air",
    }
    return f"iPhone {generation}{variant_names[variant]}"


def model_slug(model):
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def import_dielines(source_root, output_root):
    source_root = Path(source_root)
    output_root = Path(output_root)
    catalog = {"materials": {}}
    imported = []
    failed = []

    for source_name, details in MATERIALS.items():
        display_name, slug, aliases = details
        source_directory = source_root / source_name
        if not source_directory.exists():
            continue
        material = {
            "slug": slug,
            "aliases": [source_name, display_name, *aliases],
            "models": {},
        }
        for source_path in sorted(source_directory.glob("*.tif")):
            model = format_model_name(source_path.stem)
            target_path = output_root / slug / f"{model_slug(model)}.png"
            try:
                mask = extract_colored_dieline_mask(source_path.read_bytes())
                target_path.parent.mkdir(parents=True, exist_ok=True)
                mask.save(target_path, format="PNG", optimize=True)
                material["models"][model] = {
                    "path": str(target_path.relative_to(output_root)),
                    "output_size": list(mask.size),
                    "aliases": [source_path.stem, model],
                }
                imported.append((display_name, model, target_path))
            except (OSError, ValueError) as error:
                failed.append((source_path, str(error)))
        catalog["materials"][display_name] = material

    catalog_path = output_root / "catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return imported, failed, catalog_path


def main():
    parser = argparse.ArgumentParser(
        description="将按材质分类的 TIFF 刀模转换为项目内轻量蒙版。"
    )
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/dielines/phone_cases"),
    )
    arguments = parser.parse_args()
    imported, failed, catalog_path = import_dielines(
        arguments.source_root,
        arguments.output,
    )
    print(f"刀模目录：{catalog_path.parent.resolve()}")
    print(f"成功：{len(imported)}")
    print(f"失败：{len(failed)}")
    for path, error in failed:
        print(f"[失败] {path}: {error}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
