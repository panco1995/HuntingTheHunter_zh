from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy
from fontTools.ttLib import TTFont
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


VISIBLE_FIELDS = {"m_Text", "level1atext", "tooltipText"}
SCENE_FILE = "level0"
FONT_ASSET_FILE = "sharedassets0.assets"
FONT_PATH_ID = 90


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_text_catalog(path: Path) -> dict[tuple[int, str], str]:
    catalog: dict[tuple[int, str], str] = {}
    if not path.is_file():
        return catalog
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["asset_file"] == SCENE_FILE and row["field"] in VISIBLE_FIELDS and row["text"]:
                catalog[(int(row["path_id"]), row["field"])] = row["text"]
    return catalog


def apply_catalog_translations(
    value: Any,
    path_id: int,
    catalog: dict[tuple[int, str], str],
    translations: dict[str, str],
    replacements: Counter[str],
    field_path: str = "",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{field_path}.{key}" if field_path else str(key)
            if key in VISIBLE_FIELDS and isinstance(child, str):
                source = catalog.get((path_id, child_path))
                if source in translations:
                    value[key] = translations[source]
                    replacements[source] += 1
            else:
                apply_catalog_translations(
                    child, path_id, catalog, translations, replacements, child_path
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            apply_catalog_translations(
                child,
                path_id,
                catalog,
                translations,
                replacements,
                f"{field_path}[{index}]",
            )


def replace_visible_strings(
    value: Any, translations: dict[str, str], replacements: Counter[str]
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in VISIBLE_FIELDS and isinstance(child, str) and child in translations:
                value[key] = translations[child]
                replacements[child] += 1
            else:
                replace_visible_strings(child, translations, replacements)
    elif isinstance(value, list):
        for child in value:
            replace_visible_strings(child, translations, replacements)


def replace_serialized_strings(
    data: bytes, translations: dict[str, str], replacements: Counter[str]
) -> bytes:
    for source, target in translations.items():
        source_bytes = source.encode("utf-8")
        target_bytes = target.encode("utf-8")
        source_padding = b"\0" * (-len(source_bytes) % 4)
        target_padding = b"\0" * (-len(target_bytes) % 4)
        pattern = struct.pack("<I", len(source_bytes)) + source_bytes + source_padding
        replacement = struct.pack("<I", len(target_bytes)) + target_bytes + target_padding
        count = data.count(pattern)
        if count:
            data = data.replace(pattern, replacement)
            replacements[source] += count
    return data


def load_scene_layout(env: UnityPy.Environment) -> tuple[dict[int, str], dict[int, tuple[Any, dict[str, Any]]], dict[int, int]]:
    names: dict[int, str] = {}
    rects: dict[int, tuple[Any, dict[str, Any]]] = {}
    rect_owner_by_id: dict[int, int] = {}
    for obj in env.objects:
        if obj.assets_file.name != SCENE_FILE:
            continue
        if obj.type.name == "GameObject":
            names[obj.path_id] = str(obj.read_typetree().get("m_Name", ""))
        elif obj.type.name == "RectTransform":
            tree = obj.read_typetree()
            owner = int(tree["m_GameObject"]["m_PathID"])
            rects[owner] = (obj, tree)
            rect_owner_by_id[obj.path_id] = owner
    return names, rects, rect_owner_by_id


def fitted_height(
    owner: int,
    rects: dict[int, tuple[Any, dict[str, Any]]],
    rect_owner_by_id: dict[int, int],
) -> float:
    current = owner
    seen: set[int] = set()
    while current and current not in seen:
        seen.add(current)
        item = rects.get(current)
        if item is None:
            return 0
        tree = item[1]
        height = float(tree.get("m_SizeDelta", {}).get("y", 0) or 0)
        anchor_min = float(tree.get("m_AnchorMin", {}).get("y", 0) or 0)
        anchor_max = float(tree.get("m_AnchorMax", {}).get("y", 0) or 0)
        if abs(anchor_max - anchor_min) < 0.01 and height >= 30:
            return height
        current = rect_owner_by_id.get(int(tree.get("m_Father", {}).get("m_PathID", 0)), 0)
    return 0


def enlarge_text_settings(
    font_data: dict[str, Any], object_name: str, rect_height: float, parent_rect_height: float
) -> None:
    if object_name.startswith("storytext") and rect_height >= 180:
        font_data["m_FontSize"] = 32
        font_data["m_BestFit"] = 1
        font_data["m_MinSize"] = 28
        font_data["m_MaxSize"] = 40
        font_data["m_LineSpacing"] = 0.9
        return

    limit = parent_rect_height or rect_height
    if 0 < limit < 80:
        size = max(24, int(limit * 0.72))
    else:
        size = 42
    font_data["m_FontSize"] = size
    font_data["m_BestFit"] = 1
    font_data["m_MinSize"] = max(20, size - 6)
    font_data["m_MaxSize"] = size + 8


def enlarge_story_boxes(
    names: dict[int, str], rects: dict[int, tuple[Any, dict[str, Any]]]
) -> int:
    changed = 0
    for owner, (obj, tree) in rects.items():
        name = names.get(owner, "")
        size = tree.get("m_SizeDelta")
        position = tree.get("m_AnchoredPosition")
        if not isinstance(size, dict) or not isinstance(position, dict):
            continue
        width = float(size.get("x", 0) or 0)
        height = float(size.get("y", 0) or 0)
        if name == "storybox" and 760 <= width <= 820 and 320 <= height <= 360:
            growth = 620 - height
            size["y"] = 620
            position["y"] = float(position.get("y", 0) or 0) - growth / 2
            obj.save_typetree(tree)
            changed += 1
        elif name == "storytext" and height >= 180 and height < 540:
            size["y"] = 540
            obj.save_typetree(tree)
            changed += 1
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Hunting The Hunter Chinese patch.")
    parser.add_argument("data_dir", type=Path, help="Hunting The Hunter_Data directory")
    parser.add_argument("translations", type=Path, help="translations.zh-CN.json")
    parser.add_argument("output_dir", type=Path, help="Patch payload directory")
    parser.add_argument(
        "--font",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "font" / "HTH-Chinese.ttf",
        help="Simplified Chinese TrueType/OpenType font",
    )
    parser.add_argument(
        "--localized",
        action="store_true",
        help="Update an already translated game while preserving original file hashes",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "work" / "text_candidates.tsv",
        help="Original English text locations extracted from the game",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_data_dir = output_dir / "Hunting The Hunter_Data"
    output_data_dir.mkdir(parents=True, exist_ok=True)

    translation_doc = json.loads(args.translations.read_text(encoding="utf-8"))
    entries = translation_doc["entries"]
    translations = {entry["source"]: entry["target"] for entry in entries}
    if len(translations) != len(entries):
        raise ValueError("Translation file contains duplicate source entries")
    if any(not source or not target for source, target in translations.items()):
        raise ValueError("Translation entries must have non-empty source and target strings")
    if not args.font.is_file():
        raise FileNotFoundError(f"Chinese font not found: {args.font}")
    font_check = TTFont(args.font, lazy=True)
    font_codepoints = set(font_check.getBestCmap())
    required_codepoints = {
        ord(character)
        for target in translations.values()
        for character in target
        if not character.isspace()
    }
    missing_glyphs = sorted(required_codepoints - font_codepoints)
    font_check.close()
    if missing_glyphs:
        missing_text = "".join(chr(codepoint) for codepoint in missing_glyphs)
        raise ValueError(f"Patch font is missing translated glyphs: {missing_text}")

    env = UnityPy.load(str(data_dir))
    first_object = next(iter(env.objects))
    env.typetree_generator = TypeTreeGenerator(first_object.assets_file.unity_version)
    env.typetree_generator.load_local_dll_folder(str(data_dir / "Managed"))

    catalog = load_text_catalog(args.catalog.resolve())
    names, rects, rect_owner_by_id = load_scene_layout(env)
    replacements: Counter[str] = Counter()
    changed_objects = 0
    enlarged_text_objects = 0
    patched_raw_objects = 0
    parse_failures: list[dict[str, Any]] = []
    for obj in env.objects:
        if obj.assets_file.name != SCENE_FILE or obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            parse_failures.append(
                {"path_id": obj.path_id, "error": f"{type(exc).__name__}: {exc}"}
            )
            raw_data = obj.get_raw_data()
            patched_data = raw_data
            if not args.localized:
                patched_data = replace_serialized_strings(
                    raw_data, translations, replacements
                )
            if patched_data != raw_data:
                obj.set_raw_data(patched_data)
                changed_objects += 1
                patched_raw_objects += 1
            continue
        before = sum(replacements.values())
        apply_catalog_translations(
            tree, obj.path_id, catalog, translations, replacements
        )
        replace_visible_strings(tree, translations, replacements)
        if "m_FontData" in tree and isinstance(tree["m_FontData"], dict):
            owner = int(tree.get("m_GameObject", {}).get("m_PathID", 0))
            rect_tree = rects.get(owner, (None, {}))[1]
            enlarge_text_settings(
                tree["m_FontData"],
                names.get(owner, ""),
                float(rect_tree.get("m_SizeDelta", {}).get("y", 0) or 0),
                fitted_height(owner, rects, rect_owner_by_id),
            )
            enlarged_text_objects += 1
        if sum(replacements.values()) != before or "m_FontData" in tree:
            obj.save_typetree(tree)
            changed_objects += 1

    enlarged_boxes = enlarge_story_boxes(names, rects)
    scene_bytes = b"".join(
        obj.get_raw_data()
        for obj in env.objects
        if obj.assets_file.name == SCENE_FILE
    )
    missing_sources = [
        source
        for source, target in translations.items()
        if source not in replacements
        and struct.pack("<I", len(target.encode())) + target.encode() not in scene_bytes
    ]
    if missing_sources:
        raise ValueError(
            "Translations not found in supported visible fields: "
            + ", ".join(repr(value) for value in missing_sources)
        )

    font_object = next(
        (
            obj
            for obj in env.objects
            if obj.assets_file.name == FONT_ASSET_FILE
            and obj.type.name == "Font"
            and obj.path_id == FONT_PATH_ID
        ),
        None,
    )
    if font_object is None:
        raise RuntimeError("Expected Lilita One font asset was not found")
    font_tree = font_object.read_typetree()
    font_bytes = args.font.read_bytes()
    font_tree["m_Name"] = "HTH-ChinesePatch"
    font_tree["m_FontNames"] = ["HTH Chinese Patch"]
    font_tree["m_FontData"] = list(font_bytes)
    font_object.save_typetree(font_tree)

    source_files: dict[str, Any] = {}
    for asset_name in (SCENE_FILE, FONT_ASSET_FILE):
        asset_file = next(
            file
            for file in env.files.values()
            if getattr(file, "name", "") == asset_name
        )
        original_path = data_dir / asset_name
        patched_data = asset_file.save()
        output_path = output_data_dir / asset_name
        output_path.write_bytes(patched_data)
        source_data = original_path.read_bytes()
        source_hash = sha256(source_data)
        source_size = len(source_data)
        existing_manifest = output_dir / "manifest.json"
        if existing_manifest.is_file():
            previous = json.loads(existing_manifest.read_text(encoding="utf-8"))
            previous_file = previous.get("files", {}).get(asset_name, {})
            if previous_file.get("original_sha256"):
                source_hash = previous_file["original_sha256"]
                source_size = previous_file["original_size"]
        source_files[asset_name] = {
            "original_sha256": source_hash,
            "patched_sha256": sha256(patched_data),
            "original_size": source_size,
            "patched_size": len(patched_data),
        }

    manifest = {
        "game": "Hunting The Hunter",
        "locale": translation_doc.get("locale", "zh-CN"),
        "unity_version": first_object.assets_file.unity_version,
        "translation_entries": len(translations),
        "replacement_count": sum(replacements.values()),
        "changed_scene_objects": changed_objects,
        "enlarged_text_objects": enlarged_text_objects,
        "enlarged_story_boxes": enlarged_boxes,
        "replacement_counts": dict(replacements),
        "font": {
            "source": str(args.font.resolve()),
            "sha256": sha256(font_bytes),
            "size": len(font_bytes),
            "target_asset": FONT_ASSET_FILE,
            "target_path_id": FONT_PATH_ID,
        },
        "files": source_files,
        "parse_failure_count": len(parse_failures),
        "patched_parse_failure_count": patched_raw_objects,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
