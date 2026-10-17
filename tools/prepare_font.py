from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the Chinese patch font subset.")
    parser.add_argument("source_font", type=Path)
    parser.add_argument("translations", type=Path)
    parser.add_argument("text_candidates", type=Path)
    parser.add_argument("output_font", type=Path)
    args = parser.parse_args()

    translation_doc = json.loads(args.translations.read_text(encoding="utf-8"))
    characters = set(chr(codepoint) for codepoint in range(0x20, 0x100))
    for entry in translation_doc["entries"]:
        characters.update(entry["source"])
        characters.update(entry["target"])
    with args.text_candidates.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["asset_file"] == "level0":
                characters.update(row["text"])

    font = TTFont(args.source_font)
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.layout_features = ["*"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(characters)))
    subsetter.subset(font)
    font = instantiateVariableFont(font, {"wght": 800}, inplace=False)

    family = "HTH Chinese Patch"
    for record in font["name"].names:
        if record.nameID in {1, 4, 6, 16, 21}:
            value = family.replace(" ", "") if record.nameID == 6 else family
            record.string = value.encode(record.getEncoding(), errors="replace")
        elif record.nameID in {2, 17, 22}:
            record.string = "ExtraBold".encode(record.getEncoding(), errors="replace")

    args.output_font.parent.mkdir(parents=True, exist_ok=True)
    font.save(args.output_font)
    print(f"Created {args.output_font} ({args.output_font.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
