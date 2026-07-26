import argparse
from pathlib import Path
import sys

from PIL import Image

from utils.image_tools.dieline import (
    DIELINE_DPI,
    compose_artwork_with_dieline,
    load_artwork,
    load_dieline_mask,
    orient_artwork_to_output,
)
from utils.image_tools.templates import (
    load_local_dieline_template,
    match_dieline_template,
)


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def process_batch(
    input_directory,
    output_directory,
    zoom=1.1,
    horizontal_shift=0,
    vertical_shift=35,
    overwrite=False,
):
    input_directory = Path(input_directory).resolve()
    output_directory = Path(output_directory).resolve()
    results = {"processed": [], "skipped": [], "unmatched": [], "failed": []}
    mask_cache = {}

    for source_path in sorted(input_directory.rglob("*")):
        if (
            not source_path.is_file()
            or source_path.suffix.lower() not in SUPPORTED_SUFFIXES
        ):
            continue
        relative_path = source_path.relative_to(input_directory)
        template_key = match_dieline_template(str(relative_path))
        if template_key is None:
            results["unmatched"].append(relative_path)
            continue

        target_path = (output_directory / relative_path).with_suffix(".png")
        if target_path.exists() and not overwrite:
            results["skipped"].append(relative_path)
            continue

        try:
            if template_key not in mask_cache:
                material, model = template_key
                mask_bytes, output_size = load_local_dieline_template(
                    material,
                    model,
                )
                mask_cache[template_key] = (
                    load_dieline_mask(mask_bytes),
                    output_size,
                )
            mask, output_size = mask_cache[template_key]
            artwork = load_artwork(source_path.read_bytes())
            artwork = orient_artwork_to_output(artwork, output_size)
            result = compose_artwork_with_dieline(
                artwork,
                mask,
                output_size,
                zoom,
                horizontal_shift,
                vertical_shift,
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(
                target_path,
                format="PNG",
                optimize=True,
                dpi=DIELINE_DPI,
            )
            results["processed"].append(relative_path)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            results["failed"].append((relative_path, str(error)))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="按材质和型号批量匹配本地刀模并生成透明 PNG。"
    )
    parser.add_argument("input_directory", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="输出目录；默认在输入目录旁创建“原目录名_套刀模”。",
    )
    parser.add_argument("--zoom", type=float, default=1.1)
    parser.add_argument("--horizontal-shift", type=int, default=0)
    parser.add_argument("--vertical-shift", type=int, default=35)
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()

    output = arguments.output or arguments.input_directory.with_name(
        f"{arguments.input_directory.name}_套刀模"
    )
    results = process_batch(
        arguments.input_directory,
        output,
        arguments.zoom,
        arguments.horizontal_shift,
        arguments.vertical_shift,
        arguments.overwrite,
    )
    print(f"输出目录：{output.resolve()}")
    for key, label in [
        ("processed", "已处理"),
        ("skipped", "已存在跳过"),
        ("unmatched", "未匹配"),
        ("failed", "失败"),
    ]:
        print(f"{label}：{len(results[key])}")
    for path in results["unmatched"]:
        print(f"[未匹配] {path}")
    for path, error in results["failed"]:
        print(f"[失败] {path}: {error}")
    return 1 if results["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
