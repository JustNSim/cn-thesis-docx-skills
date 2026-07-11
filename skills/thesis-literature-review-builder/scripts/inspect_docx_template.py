#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


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


def rels_source_part(name: str) -> str:
    if name == "_rels/.rels":
        return ""
    prefix, marker, leaf = name.partition("/_rels/")
    if not marker or not leaf.endswith(".rels"):
        return ""
    return f"{prefix}/{leaf[:-len('.rels')]}"


def relationship_target(source: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target)).lstrip("./")


def strict_failures(report: dict) -> list[str]:
    fields = (
        "sensitive_hits",
        "comments_parts",
        "tracked_change_parts",
        "hidden_text_parts",
        "external_relationships",
        "embedded_object_parts",
        "macro_parts",
        "dangling_relationships",
        "errors",
    )
    return [field for field in fields if report.get(field)]


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
        "media_parts": [],
        "macro_parts": [],
        "dangling_relationships": [],
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

            text_parts = [n for n in names if n.endswith(".xml") or n.endswith(".rels")]
            for name in text_parts:
                text = read_text_part(zf, name)
                for pat in patterns:
                    if pat and pat in text:
                        report["sensitive_hits"].append({"part": name, "pattern": pat})
                if name.startswith("word/") and re.search(r"<w:(ins|del|moveFrom|moveTo)\b", text):
                    report["tracked_change_parts"].append(name)
                if name.startswith("word/") and "<w:vanish" in text:
                    report["hidden_text_parts"].append(name)
                if name.startswith("word/") and "comments" in name.lower():
                    report["comments_parts"].append(name)

            for name in names:
                lname = name.lower()
                if lname.startswith("word/embeddings/") or lname.startswith("word/activex/"):
                    report["embedded_object_parts"].append(name)
                if lname.startswith("word/media/"):
                    report["media_parts"].append(name)
                if lname.endswith("vbaproject.bin") or lname.endswith("vbaprojectsignature.bin"):
                    report["macro_parts"].append(name)
                if name.endswith(".rels"):
                    try:
                        rels = ET.fromstring(zf.read(name))
                    except ET.ParseError:
                        report["errors"].append(f"Invalid relationships XML: {name}")
                        continue
                    source = rels_source_part(name)
                    for rel in rels.findall(f"{{{REL_NS}}}Relationship"):
                        target = rel.get("Target") or ""
                        if (rel.get("TargetMode") or "").lower() == "external":
                            report["external_relationships"].append({"part": name, "target": target})
                        elif target and relationship_target(source, target) not in names:
                            report["dangling_relationships"].append({"part": name, "target": target})
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
    print(f"  embedded object parts: {report['embedded_object_parts'] or 'none'}")
    print(f"  media parts: {len(report['media_parts'])}")
    print(f"  macro parts: {report['macro_parts'] or 'none'}")
    print(f"  dangling relationships: {report['dangling_relationships'] or 'none'}")
    if report["errors"]:
        print(f"  errors: {report['errors']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit DOCX templates for metadata and privacy residue.")
    parser.add_argument("docx", nargs="+", type=Path)
    parser.add_argument("--pattern", action="append", default=[], help="Sensitive text pattern to search for.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human-readable text.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if privacy or package-integrity residue remains.")
    args = parser.parse_args()

    reports = [inspect_docx(path, args.pattern) for path in args.docx]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for i, report in enumerate(reports):
            if i:
                print()
            print_human(report)
    if args.strict and any(strict_failures(report) for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
