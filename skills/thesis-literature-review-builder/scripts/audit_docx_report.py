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
REFERENCE_INDENT_MIN_TWIPS = 300
REFERENCE_INDENT_MAX_TWIPS = 540
TITLE_MIN_HALF_POINTS = 32
SAMPLE_PATTERNS = (
    "示例图片",
    "示例图",
    "样例图片",
    "样例图",
    "图题",
    "图片标题",
    "请在此",
    "此处插入",
    "模板示例",
    "样例内容",
)


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS))


def rpr_half_points(rpr: etree._Element | None) -> int | None:
    if rpr is None:
        return None
    values = []
    for tag in ("sz", "szCs"):
        node = rpr.find(f"w:{tag}", NS)
        val = node.get(qn("val")) if node is not None else None
        if val and val.isdigit():
            values.append(int(val))
    return max(values) if values else None


def style_context(styles_xml: bytes | None) -> dict:
    if not styles_xml:
        return {"styles": {}, "defaults": {}, "doc_default": None}
    root = etree.fromstring(styles_xml)
    styles = {}
    defaults = {}
    for style in root.findall("w:style", NS):
        style_id = style.get(qn("styleId"))
        style_type = style.get(qn("type"))
        if not style_id:
            continue
        based_on = style.find("w:basedOn", NS)
        styles[style_id] = {
            "type": style_type,
            "based_on": based_on.get(qn("val")) if based_on is not None else None,
            "size": rpr_half_points(style.find("w:rPr", NS)),
        }
        if style.get(qn("default")) in ("1", "true") and style_type:
            defaults[style_type] = style_id
    default_rpr = root.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    return {"styles": styles, "defaults": defaults, "doc_default": rpr_half_points(default_rpr)}


def resolved_style_size(context: dict, style_id: str | None) -> int | None:
    seen = set()
    while style_id and style_id not in seen:
        seen.add(style_id)
        style = context["styles"].get(style_id)
        if not style:
            return None
        if style["size"] is not None:
            return style["size"]
        style_id = style["based_on"]
    return None


def effective_run_half_points(r: etree._Element, p: etree._Element, context: dict) -> int | None:
    rpr = r.find("w:rPr", NS)
    direct = rpr_half_points(rpr)
    if direct is not None:
        return direct
    rstyle = rpr.find("w:rStyle", NS) if rpr is not None else None
    size = resolved_style_size(context, rstyle.get(qn("val")) if rstyle is not None else None)
    if size is not None:
        return size
    pstyle = p.find("w:pPr/w:pStyle", NS)
    paragraph_style_id = pstyle.get(qn("val")) if pstyle is not None else context["defaults"].get("paragraph")
    size = resolved_style_size(context, paragraph_style_id)
    return size if size is not None else context["doc_default"]


def instr_texts(root: etree._Element) -> list[str]:
    return ["".join(t.text or "" for t in p.findall(".//w:instrText", NS)) for p in root.findall(".//w:p", NS)]


def title_report(paras: list[etree._Element], title: str | None, styles: dict) -> dict:
    if not title:
        return {
            "title_checked": False,
            "title_on_cover": None,
            "title_max_half_points": None,
            "title_large_enough": None,
        }
    normalized = re.sub(r"\s+", "", title)
    for idx, p in enumerate(paras[:20], 1):
        text = re.sub(r"\s+", "", para_text(p))
        if normalized and normalized in text:
            text_runs = [r for r in p.findall(".//w:r", NS) if para_text(r).strip()]
            sizes = [effective_run_half_points(r, p, styles) for r in text_runs]
            known_sizes = [size for size in sizes if size is not None]
            unresolved = len(sizes) - len(known_sizes)
            return {
                "title_checked": True,
                "title_on_cover": True,
                "title_paragraph_index": idx,
                "title_max_half_points": max(known_sizes) if known_sizes else None,
                "title_min_half_points": min(known_sizes) if known_sizes else None,
                "title_unresolved_run_count": unresolved,
                "title_large_enough": bool(known_sizes) and unresolved == 0 and min(known_sizes) >= TITLE_MIN_HALF_POINTS,
            }
    return {
        "title_checked": True,
        "title_on_cover": False,
        "title_paragraph_index": None,
        "title_max_half_points": None,
        "title_large_enough": False,
    }


def field_report(root: etree._Element) -> tuple[int, int, int, set[int], set[str]]:
    ref_fields = 0
    superscript = 0
    non_superscript = 0
    cited_numbers: set[int] = set()
    targets: set[str] = set()
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
            instr_text = "".join(instr)
            m = re.search(r"\bREF\s+Ref_(\d+)", instr_text)
            if sep is not None and end is not None and m:
                ref_fields += 1
                cited_numbers.add(int(m.group(1)))
                targets.add(f"Ref_{m.group(1)}")
                result_runs = children[sep + 1 : end]
                is_sup = any(
                    (r.find("w:rPr/w:vertAlign", NS) is not None)
                    and r.find("w:rPr/w:vertAlign", NS).get(qn("val")) == "superscript"
                    for r in result_runs
                )
                superscript += int(is_sup)
                non_superscript += int(not is_sup)
            i = (end + 1) if end is not None else i + 1
    return ref_fields, superscript, non_superscript, cited_numbers, targets


def text_without_ref_fields(p: etree._Element) -> str:
    children = list(p)
    chunks: list[str] = []
    i = 0
    while i < len(children):
        fld = children[i].find("w:fldChar", NS)
        if fld is None or fld.get(qn("fldCharType")) != "begin":
            chunks.extend(t.text or "" for t in children[i].findall(".//w:t", NS))
            i += 1
            continue
        instr = []
        end = None
        j = i + 1
        while j < len(children):
            instr += [x.text or "" for x in children[j].findall(".//w:instrText", NS)]
            f = children[j].find("w:fldChar", NS)
            if f is not None and f.get(qn("fldCharType")) == "end":
                end = j
                break
            j += 1
        if end is not None and re.search(r"\bREF\s+Ref_", "".join(instr)):
            i = end + 1
        else:
            chunks.extend(t.text or "" for child in children[i : (end + 1 if end is not None else i + 1)] for t in child.findall(".//w:t", NS))
            i = (end + 1) if end is not None else i + 1
    return "".join(chunks)


def plain_citation_numbers(paras: list[etree._Element]) -> set[int]:
    nums: set[int] = set()
    pat = re.compile(r"\[(\d+(?:\s*[-,;，、]\s*\d+)*)\]")
    for p in paras:
        for match in pat.finditer(text_without_ref_fields(p)):
            for raw in re.findall(r"\d+", match.group(1)):
                nums.add(int(raw))
    return nums


def numbering_indent_map(numbering_xml: bytes | None) -> dict[str, tuple[int | None, int | None]]:
    if not numbering_xml:
        return {}
    root = etree.fromstring(numbering_xml)
    abstract_indent: dict[str, tuple[int | None, int | None]] = {}
    for abstract in root.findall("w:abstractNum", NS):
        abstract_id = abstract.get(qn("abstractNumId"))
        lvl = abstract.find("w:lvl[@w:ilvl='0']", NS)
        ind = lvl.find("w:pPr/w:ind", NS) if lvl is not None else None
        if abstract_id and ind is not None:
            abstract_indent[abstract_id] = (int(ind.get(qn("left"), "0")), int(ind.get(qn("hanging"), "0")))
    out: dict[str, tuple[int | None, int | None]] = {}
    for num in root.findall("w:num", NS):
        num_id = num.get(qn("numId"))
        abstract = num.find("w:abstractNumId", NS)
        abstract_id = abstract.get(qn("val")) if abstract is not None else None
        if num_id and abstract_id in abstract_indent:
            out[num_id] = abstract_indent[abstract_id]
    return out


def paragraph_indent(p: etree._Element, numbering: dict[str, tuple[int | None, int | None]]) -> tuple[int | None, int | None]:
    ind = p.find("w:pPr/w:ind", NS)
    if ind is not None and (ind.get(qn("left")) or ind.get(qn("hanging"))):
        left = int(ind.get(qn("left"), "0"))
        hanging = int(ind.get(qn("hanging"), "0"))
        return left, hanging
    num_id = p.find("w:pPr/w:numPr/w:numId", NS)
    if num_id is not None:
        return numbering.get(num_id.get(qn("val")) or "", (None, None))
    return None, None


def reference_indent_issues(ref_paras: list[etree._Element], numbering: dict[str, tuple[int | None, int | None]]) -> list[dict[str, int | str | None]]:
    issues = []
    for idx, p in enumerate(ref_paras, 1):
        left, hanging = paragraph_indent(p, numbering)
        ok = (
            left is not None
            and hanging is not None
            and REFERENCE_INDENT_MIN_TWIPS <= left <= REFERENCE_INDENT_MAX_TWIPS
            and REFERENCE_INDENT_MIN_TWIPS <= hanging <= REFERENCE_INDENT_MAX_TWIPS
            and abs(left - hanging) <= 160
        )
        if not ok:
            issues.append({"reference_index": idx, "left": left, "hanging": hanging, "text": para_text(p)[:120]})
    return issues[:20]


def audit(path: Path, ref_heading: str, title: str | None = None) -> dict:
    with zipfile.ZipFile(path) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
        styles = style_context(zf.read("word/styles.xml") if "word/styles.xml" in zf.namelist() else None)
        numbering = numbering_indent_map(zf.read("word/numbering.xml") if "word/numbering.xml" in zf.namelist() else None)
        todo_parts = []
        for name in zf.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                text = zf.read(name).decode("utf-8", errors="ignore")
                if "TODO:" in text or "待核验" in text:
                    todo_parts.append(name)
    paras = root.xpath(".//w:body//w:p", namespaces=NS)
    texts = [para_text(p).strip() for p in paras]
    field_instr = instr_texts(root)
    heading_idx = next((i for i, text in enumerate(texts) if text == ref_heading), None)
    refs = []
    ref_paras = []
    if heading_idx is not None:
        for p, text in zip(paras[heading_idx + 1 :], texts[heading_idx + 1 :]):
            if not text:
                continue
            refs.append(text)
            ref_paras.append(p)

    bookmarks = [
        b.get(qn("name"))
        for b in root.findall(".//w:bookmarkStart", NS)
        if (b.get(qn("name")) or "").startswith("Ref_")
    ]
    bookmark_set = set(bookmarks)
    ref_fields, sup, non_sup, ref_field_numbers, ref_field_targets = field_report(root)
    plain_citations = plain_citation_numbers(paras[: heading_idx if heading_idx is not None else len(paras)])
    cited_numbers = ref_field_numbers | plain_citations
    reference_numbers = set(range(1, len(refs) + 1))
    norm_refs = [re.sub(r"^\[\d+\]\s*", "", r).strip().lower() for r in refs]
    duplicates = sorted({r for r in norm_refs if norm_refs.count(r) > 1 and r})
    indent_issues = reference_indent_issues(ref_paras, numbering)
    sample_hits = [
        {"paragraph_index": idx + 1, "pattern": pat, "text": text[:160]}
        for idx, text in enumerate(texts)
        for pat in SAMPLE_PATTERNS
        if pat in text
    ][:20]
    title_info = title_report(paras, title, styles)
    expected_bookmarks = {f"Ref_{n:03d}" for n in reference_numbers}
    missing_reference_bookmarks = sorted(expected_bookmarks - bookmark_set)
    missing_field_bookmarks = sorted(ref_field_targets - bookmark_set)

    report = {
        "path": str(path),
        "paragraphs": len(paras),
        **title_info,
        "toc_field_count": sum(1 for instr in field_instr if re.search(r"\bTOC\b", instr)),
        "field_error_count": sum("Error!" in text or "错误!" in text or "找不到" in text for text in texts),
        "sample_content_hit_count": len(sample_hits),
        "sample_content_hits": sample_hits,
        "reference_heading_found": heading_idx is not None,
        "reference_count": len(refs),
        "ref_bookmark_count": len(bookmark_set),
        "missing_reference_bookmarks": missing_reference_bookmarks,
        "missing_field_bookmarks": missing_field_bookmarks,
        "ref_field_count": ref_fields,
        "superscript_ref_fields": sup,
        "non_superscript_ref_fields": non_sup,
        "plain_citation_count": len(plain_citations),
        "plain_citation_numbers": sorted(plain_citations),
        "in_text_citation_missing": bool(refs) and ref_fields == 0 and not plain_citations,
        "uncited_reference_numbers": sorted(reference_numbers - cited_numbers),
        "missing_reference_numbers": sorted(n for n in cited_numbers if n not in reference_numbers),
        "double_bracket_paragraphs": sum("[[" in t or "]]" in t for t in texts),
        "duplicate_reference_count": len(duplicates),
        "duplicate_references": duplicates[:20],
        "reference_indent_issue_count": len(indent_issues),
        "reference_indent_issues": indent_issues,
        "possible_collapsed_references": [
            r[:180] for r in refs if len(re.findall(r"\[\d+\]", r)) > 1
        ][:10],
        "todo_or_unverified_parts": todo_parts,
    }
    return report


def strict_failures(report: dict) -> list[str]:
    failures = []
    if not report["reference_heading_found"]:
        failures.append("reference_heading_found")
    if report.get("title_checked") and (not report.get("title_on_cover") or not report.get("title_large_enough")):
        failures.append("cover_title_format")
    if not report["toc_field_count"]:
        failures.append("toc_field_count")
    for key in (
        "field_error_count",
        "sample_content_hit_count",
        "double_bracket_paragraphs",
        "duplicate_reference_count",
        "possible_collapsed_references",
        "todo_or_unverified_parts",
        "non_superscript_ref_fields",
        "plain_citation_count",
        "uncited_reference_numbers",
        "missing_reference_numbers",
        "reference_indent_issue_count",
        "missing_reference_bookmarks",
        "missing_field_bookmarks",
        "in_text_citation_missing",
    ):
        if report[key]:
            failures.append(key)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a report DOCX for references and REF fields.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--ref-heading", default="参考文献")
    parser.add_argument("--title", help="Expected thesis title; checked near the cover using the larger title style.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on unresolved TODOs or citation-integrity findings.")
    args = parser.parse_args()

    report = audit(args.docx, args.ref_heading, args.title)
    failures = strict_failures(report)
    report["strict_failure_count"] = len(failures)
    report["strict_failures"] = failures
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    if args.strict and failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
