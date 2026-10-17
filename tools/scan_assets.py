from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


TECHNICAL_VALUE = re.compile(
    r"^(?:"
    r"[A-Za-z0-9_./\\-]+\.(?:png|jpg|wav|mp3|ogg|prefab|asset|controller|anim)"
    r"|[0-9a-fA-F]{16,}"
    r"|(?:Assets|Library|Packages)[/\\]"
    r")"
)


def walk_strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from walk_strings(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_strings(child, f"{path}[{index}]")


def script_name(tree: dict[str, Any]) -> str:
    script = tree.get("m_Script")
    if not isinstance(script, dict):
        return ""
    try:
        target = script.get("m_PathID")
        if not target:
            return ""
        # The object lookup is filled by the caller because PPtr resolution differs
        # between UnityPy versions.
        return str(target)
    except Exception:
        return ""


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: scan_assets.py <Game_Data directory> <output directory>")
        return 2

    data_dir = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env = UnityPy.load(str(data_dir))
    first_object = next(iter(env.objects))
    env.typetree_generator = TypeTreeGenerator(first_object.assets_file.unity_version)
    env.typetree_generator.load_local_dll_folder(str(data_dir / "Managed"))
    type_counts = Counter(obj.type.name for obj in env.objects)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for obj in env.objects:
        if obj.type.name not in {"MonoBehaviour", "TextAsset"}:
            continue
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            failures.append(
                {
                    "asset_file": obj.assets_file.name,
                    "path_id": obj.path_id,
                    "type": obj.type.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        component_name = str(tree.get("m_Name", ""))
        script_path_id = script_name(tree)
        resolved_script_name = ""
        script = tree.get("m_Script")
        if isinstance(script, dict):
            try:
                script_obj = obj.assets_file.get_object(script.get("m_PathID", 0))
                script_tree = script_obj.read_typetree()
                resolved_script_name = str(script_tree.get("m_ClassName", ""))
            except Exception:
                pass

        for field_path, value in walk_strings(tree):
            text = value.strip()
            if not text or field_path == "m_Name":
                continue
            if TECHNICAL_VALUE.match(text):
                continue
            rows.append(
                {
                    "asset_file": obj.assets_file.name,
                    "path_id": obj.path_id,
                    "object_type": obj.type.name,
                    "component_name": component_name,
                    "script": resolved_script_name,
                    "script_path_id": script_path_id,
                    "field": field_path,
                    "text": value,
                }
            )

    with (output_dir / "text_candidates.tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "asset_file",
                "path_id",
                "object_type",
                "component_name",
                "script",
                "script_path_id",
                "field",
                "text",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "data_dir": str(data_dir),
        "asset_file_count": len(env.files),
        "object_count": len(env.objects),
        "type_counts": dict(type_counts.most_common()),
        "candidate_count": len(rows),
        "typetree_failures": failures,
    }
    (output_dir / "scan_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
