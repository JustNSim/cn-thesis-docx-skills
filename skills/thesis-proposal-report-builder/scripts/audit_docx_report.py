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


def para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS))


def field_report(root: etree._Element) -> tuple[int, int, int]:
    ref_fields = 0
    superscript = 0
    non_superscript = 0
    for p in root.findall(".//w:p", NS):
        children = list(p)
        i = 0
        while i < len(children):
            fld = children[i].find("w:fldChar", NS)
            if fld is None or fld.get(qn("fldCharType")) != "begin":
                i += 1
                continue
            sep = None
            end = None
            instr = []
            j = i + 1
            while j < len(children):
                instr += [x.text or "" for x in children[j].findall(".//w:instrText", NS)]
                f = children[j].find("w:fldChar", NS)
                if f is not None and f.get(qn("fldCharType")) == "separate":
                    sep = j
                if f is not None and f.get(qn("fldCharType")) == "end":
                    end = j
                    break
                j += 1
            if sep is not None and end is not None and re.search(r"\bREF\s+Ref_", "".join(instr)):
                ref_fields += 1
                result_runs = children[sep + 1 : end]
                is_sup = any(
                    (r.find("w:rPr/w:vertAlign", NS) is not None)
                    and r.find("w:rPr/w:vertAlign", NS).get(qn("val")) == "superscript"
                    for r in result_runs
                )
                superscript += int(is_sup)
                non_superscript += int(not is_sup)
            i = (end + 1) if end is not None else i + 1
    return ref_fields, superscript, non_superscript


def audit(path: Path, ref_heading: str) -> dict:
    with zipfile.ZipFile(path) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    paras = root.findall(".//w:body/w:p", NS)
    texts = [para_text(p).strip() for p in paras]
    heading_idx = next((i for i, text in enumerate(texts) if text == ref_heading), None)
    refs = []
    if heading_idx is not None:
        for text in texts[heading_idx + 1 :]:
            if not text:
                continue
            refs.append(text)

    bookmarks = [
        b.get(qn("name"))
        for b in root.findall(".//w:bookmarkStart", NS)
        if (b.get(qn("name")) or "").startswith("Ref_")
    ]
    ref_fields, sup, non_sup = field_report(root)
    norm_refs = [re.sub(r"^\[\d+\]\s*", "", r).strip().lower() for r in refs]
    duplicates = sorted({r for r in norm_refs if norm_refs.count(r) > 1 and r})

    return {
        "path": str(path),
        "paragraphs": len(paras),
        "reference_heading_found": heading_idx is not None,
        "reference_count": len(refs),
        "ref_bookmark_count": len(bookmarks),
        "ref_field_count": ref_fields,
        "superscript_ref_fields": sup,
        "non_superscript_ref_fields": non_sup,
        "double_bracket_paragraphs": sum("[[" in t or "]]" in t for t in texts),
        "duplicate_reference_count": len(duplicates),
        "duplicate_references": duplicates[:20],
        "possible_collapsed_references": [
            r[:180] for r in refs if len(re.findall(r"\[\d+\]", r)) > 1
        ][:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a report DOCX for references and REF fields.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--ref-heading", default="参考文献")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit(args.docx, args.ref_heading)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
