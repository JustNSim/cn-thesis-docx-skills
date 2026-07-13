#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = NS["w"]


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def clear_settings(settings_xml: bytes) -> tuple[bytes, bool]:
    root = etree.fromstring(settings_xml)
    changed = False
    for node in root.findall("w:updateFields", NS):
        root.remove(node)
        changed = True
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), changed


def clear_docx(input_path: Path, output_path: Path) -> dict:
    changed = False
    with zipfile.ZipFile(input_path, "r") as zin:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == "word/settings.xml":
                        data, changed = clear_settings(data)
                    zout.writestr(item, data)
            shutil.move(str(tmp_path), output_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    return {"input": str(input_path), "output": str(output_path), "changed": changed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove Word update-on-open field prompts after fields have already been updated and saved.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = clear_docx(args.input, args.output)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
