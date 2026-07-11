#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def read_text_part(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8", errors="ignore")


def xml_text(data: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return [{"tag": "parse_error", "text": ""}]
    rows = []
    for el in root.iter():
        text = "".join(el.itertext()).strip()
        if text:
            rows.append({"tag": el.tag.split("}", 1)[-1], "text": text})
    return rows


def inspect_docx(path: Path, patterns: list[str]) -> dict:
    report: dict = {
        "path": str(path),
        "exists": path.exists(),
        "properties": {},
        "sensitive_hits": [],
        "comments_parts": [],
        "tracked_change_parts": [],
        "hidden_text_parts": [],
        "external_relationships": [],
        "embedded_object_parts": [],
        "errors": [],
    }
    if not path.exists():
        return report

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for prop in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
                if prop in names:
                    report["properties"][prop] = xml_text(zf.read(prop))

            xml_parts = [n for n in names if n.startswith("word/") and n.endswith(".xml")]
            for name in xml_parts:
                text = read_text_part(zf, name)
                for pat in patterns:
                    if pat and pat in text:
                        report["sensitive_hits"].append({"part": name, "pattern": pat})
                if re.search(r"<w:(ins|del|moveFrom|moveTo)\b", text):
                    report["tracked_change_parts"].append(name)
                if "<w:vanish" in text:
                    report["hidden_text_parts"].append(name)
                if "comments" in name.lower():
                    report["comments_parts"].append(name)

            for name in names:
                lname = name.lower()
                if lname.startswith("word/embeddings/") or lname.startswith("word/media/"):
                    report["embedded_object_parts"].append(name)
                if name.endswith(".rels"):
                    rels = read_text_part(zf, name)
                    for m in re.finditer(r'Target="([^"]+)"[^>]*?(?:TargetMode="External")', rels):
                        report["external_relationships"].append({"part": name, "target": m.group(1)})
    except Exception as exc:  # pragma: no cover - CLI guard
        report["errors"].append(str(exc))
    return report


def print_human(report: dict) -> None:
    print(f"FILE: {report['path']}")
    if not report["exists"]:
        print("  missing")
        return
    print(f"  properties parts: {', '.join(report['properties']) or 'none'}")
    print(f"  sensitive hits: {len(report['sensitive_hits'])}")
    for hit in report["sensitive_hits"][:20]:
        print(f"    - {hit['part']}: {hit['pattern']}")
    print(f"  comments parts: {report['comments_parts'] or 'none'}")
    print(f"  tracked changes: {report['tracked_change_parts'] or 'none'}")
    print(f"  hidden text: {report['hidden_text_parts'] or 'none'}")
    print(f"  external relationships: {report['external_relationships'] or 'none'}")
    print(f"  embedded/media parts: {len(report['embedded_object_parts'])}")
    if report["errors"]:
        print(f"  errors: {report['errors']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit DOCX templates for metadata and privacy residue.")
    parser.add_argument("docx", nargs="+", type=Path)
    parser.add_argument("--pattern", action="append", default=[], help="Sensitive text pattern to search for.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human-readable text.")
    args = parser.parse_args()

    reports = [inspect_docx(path, args.pattern) for path in args.docx]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for i, report in enumerate(reports):
            if i:
                print()
            print_human(report)


if __name__ == "__main__":
    main()
