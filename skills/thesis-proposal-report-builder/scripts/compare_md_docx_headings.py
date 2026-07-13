#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = NS["w"]


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def normalize_heading(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^[#]+", "", text)
    text = re.sub(r"^\*+|\*+$", "", text)
    text = re.sub(r"^(?:第[一二三四五六七八九十百千万0-9]+[章节篇]|[一二三四五六七八九十]+[、.．]|[0-9]+(?:\.[0-9]+)*[、.．]?)", "", text)
    return text


def markdown_headings(path: Path) -> list[dict[str, int | str]]:
    headings = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        raw = match.group(2).strip()
        headings.append(
            {
                "source": "markdown",
                "line": line_no,
                "level": len(match.group(1)),
                "text": raw,
                "normalized": normalize_heading(raw),
            }
        )
    return headings


def paragraph_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS)).strip()


def style_levels(styles_xml: bytes | None) -> dict[str, int]:
    if not styles_xml:
        return {}
    root = etree.fromstring(styles_xml)
    raw: dict[str, int | None] = {}
    based_on: dict[str, str | None] = {}
    for style in root.findall("w:style", NS):
        style_id = style.get(qn("styleId"))
        if not style_id or style.get(qn("type")) != "paragraph":
            continue
        outline = style.find("w:pPr/w:outlineLvl", NS)
        level = int(outline.get(qn("val"))) + 1 if outline is not None and outline.get(qn("val"), "").isdigit() else None
        name = style.find("w:name", NS)
        name_val = name.get(qn("val")) if name is not None else ""
        for value in (style_id, name_val):
            m = re.search(r"(?:heading|标题)\s*([1-6])", value or "", re.I)
            if m:
                level = int(m.group(1))
                break
        raw[style_id] = level
        parent = style.find("w:basedOn", NS)
        based_on[style_id] = parent.get(qn("val")) if parent is not None else None

    resolved: dict[str, int] = {}

    def resolve(style_id: str | None, seen: set[str] | None = None) -> int | None:
        if not style_id:
            return None
        if style_id in resolved:
            return resolved[style_id]
        if seen is None:
            seen = set()
        if style_id in seen:
            return None
        seen.add(style_id)
        level = raw.get(style_id)
        if level is None:
            level = resolve(based_on.get(style_id), seen)
        if level is not None:
            resolved[style_id] = level
        return level

    for style_id in raw:
        resolve(style_id)
    return resolved


def docx_headings(path: Path) -> list[dict[str, int | str]]:
    with zipfile.ZipFile(path) as zf:
        document = etree.fromstring(zf.read("word/document.xml"))
        levels = style_levels(zf.read("word/styles.xml") if "word/styles.xml" in zf.namelist() else None)

    headings = []
    for idx, p in enumerate(document.xpath(".//w:body//w:p", namespaces=NS), 1):
        text = paragraph_text(p)
        if not text:
            continue
        outline = p.find("w:pPr/w:outlineLvl", NS)
        level = int(outline.get(qn("val"))) + 1 if outline is not None and outline.get(qn("val"), "").isdigit() else None
        pstyle = p.find("w:pPr/w:pStyle", NS)
        if level is None and pstyle is not None:
            level = levels.get(pstyle.get(qn("val")) or "")
        if level is None:
            continue
        headings.append(
            {
                "source": "docx",
                "paragraph": idx,
                "level": level,
                "text": text,
                "normalized": normalize_heading(text),
            }
        )
    return headings


def compare(markdown_path: Path, docx_path: Path) -> dict:
    md = markdown_headings(markdown_path)
    dx = docx_headings(docx_path)
    mismatches = []
    max_len = max(len(md), len(dx))
    for idx in range(max_len):
        md_item = md[idx] if idx < len(md) else None
        dx_item = dx[idx] if idx < len(dx) else None
        if md_item is None or dx_item is None:
            mismatches.append({"index": idx + 1, "markdown": md_item, "docx": dx_item, "reason": "missing_heading"})
            continue
        if md_item["level"] != dx_item["level"] or md_item["normalized"] != dx_item["normalized"]:
            mismatches.append({"index": idx + 1, "markdown": md_item, "docx": dx_item, "reason": "level_or_text_mismatch"})
    return {
        "markdown": str(markdown_path),
        "docx": str(docx_path),
        "markdown_heading_count": len(md),
        "docx_heading_count": len(dx),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Markdown headings with DOCX heading names and levels.")
    parser.add_argument("markdown", type=Path)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = compare(args.markdown, args.docx)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    if args.strict and report["mismatch_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
