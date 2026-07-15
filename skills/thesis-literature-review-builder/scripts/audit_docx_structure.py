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

HEADING_STYLE_IDS = {
    1: {"1", "Heading1"},
    2: {"2", "Heading2"},
}
CHINESE_TOC = "\u76ee\u5f55"
CHINESE_FIGURE_LIST = "\u56fe\u76ee"
CHINESE_TABLE_LIST = "\u8868\u76ee"
CHINESE_REFERENCE = "\u53c2\u8003\u6587\u732e"
CHINESE_FIGURE = "\u56fe"
CHINESE_TABLE = "\u8868"


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS))


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def read_xml(zf: zipfile.ZipFile, name: str) -> etree._Element | None:
    if name not in zf.namelist():
        return None
    return etree.fromstring(zf.read(name))


def style_catalog(styles_root: etree._Element | None) -> dict:
    styles: dict[str, dict] = {}
    heading_by_level: dict[int, set[str]] = {1: set(HEADING_STYLE_IDS[1]), 2: set(HEADING_STYLE_IDS[2])}
    if styles_root is None:
        return {"styles": styles, "heading_by_level": heading_by_level}

    for style in styles_root.findall("w:style", NS):
        style_id = style.get(qn("styleId"))
        if not style_id:
            continue
        name_node = style.find("w:name", NS)
        name = name_node.get(qn("val")) if name_node is not None else ""
        based_on = style.find("w:basedOn", NS)
        num_pr = style.find("w:pPr/w:numPr", NS)
        num_id = num_pr.find("w:numId", NS).get(qn("val")) if num_pr is not None and num_pr.find("w:numId", NS) is not None else None
        ilvl = num_pr.find("w:ilvl", NS).get(qn("val")) if num_pr is not None and num_pr.find("w:ilvl", NS) is not None else None
        styles[style_id] = {
            "name": name,
            "based_on": based_on.get(qn("val")) if based_on is not None else None,
            "num_id": num_id,
            "ilvl": ilvl,
        }
        normalized_name = compact_text(name).lower()
        if normalized_name in {"heading1", "\u6807\u98981"}:
            heading_by_level[1].add(style_id)
        if normalized_name in {"heading2", "\u6807\u98982"}:
            heading_by_level[2].add(style_id)
    return {"styles": styles, "heading_by_level": heading_by_level}


def paragraph_style_id(p: etree._Element) -> str | None:
    pstyle = p.find("w:pPr/w:pStyle", NS)
    return pstyle.get(qn("val")) if pstyle is not None else None


def heading_level_for_paragraph(p: etree._Element, catalog: dict) -> int | None:
    style_id = paragraph_style_id(p)
    if not style_id:
        return None
    for level, ids in catalog["heading_by_level"].items():
        if style_id in ids:
            return level
    return None


def style_num_pr(style_id: str | None, catalog: dict) -> tuple[str | None, str | None]:
    seen = set()
    while style_id and style_id not in seen:
        seen.add(style_id)
        info = catalog["styles"].get(style_id)
        if not info:
            break
        if info["num_id"] is not None or info["ilvl"] is not None:
            return info["num_id"], info["ilvl"]
        style_id = info["based_on"]
    return None, None


def paragraph_num_pr(p: etree._Element, catalog: dict) -> tuple[str | None, str | None, str]:
    num_pr = p.find("w:pPr/w:numPr", NS)
    if num_pr is not None:
        num_id_node = num_pr.find("w:numId", NS)
        ilvl_node = num_pr.find("w:ilvl", NS)
        num_id = num_id_node.get(qn("val")) if num_id_node is not None else None
        ilvl = ilvl_node.get(qn("val")) if ilvl_node is not None else None
        if num_id is not None or ilvl is not None:
            return num_id, ilvl, "direct"
    num_id, ilvl = style_num_pr(paragraph_style_id(p), catalog)
    return num_id, ilvl, "style" if (num_id is not None or ilvl is not None) else "none"


def numbering_catalog(numbering_root: etree._Element | None) -> dict:
    if numbering_root is None:
        return {"num_to_abstract": {}, "lvl_text": {}}
    num_to_abstract: dict[str, str] = {}
    lvl_text: dict[tuple[str, str], str] = {}
    for abstract in numbering_root.findall("w:abstractNum", NS):
        abstract_id = abstract.get(qn("abstractNumId"))
        if not abstract_id:
            continue
        for lvl in abstract.findall("w:lvl", NS):
            ilvl = lvl.get(qn("ilvl"))
            text_node = lvl.find("w:lvlText", NS)
            if ilvl is not None and text_node is not None:
                lvl_text[(abstract_id, ilvl)] = text_node.get(qn("val")) or ""
    for num in numbering_root.findall("w:num", NS):
        num_id = num.get(qn("numId"))
        abstract = num.find("w:abstractNumId", NS)
        if num_id and abstract is not None:
            num_to_abstract[num_id] = abstract.get(qn("val")) or ""
    return {"num_to_abstract": num_to_abstract, "lvl_text": lvl_text}


def lvl_text_for(num_id: str | None, ilvl: str | None, numbering: dict) -> str | None:
    if num_id is None:
        return None
    abstract_id = numbering["num_to_abstract"].get(num_id)
    if abstract_id is None:
        return None
    return numbering["lvl_text"].get((abstract_id, ilvl or "0"))


def iter_complex_fields(paras: list[etree._Element]) -> list[dict]:
    fields: list[dict] = []
    stack: list[dict] = []
    for idx, p in enumerate(paras, 1):
        for active in stack:
            active["paragraph_indexes"].add(idx)
        for run in p.findall("w:r", NS):
            fld = run.find("w:fldChar", NS)
            if fld is not None:
                fld_type = fld.get(qn("fldCharType"))
                if fld_type == "begin":
                    field = {
                        "instr": "",
                        "paragraph_indexes": {idx},
                        "has_separate": False,
                        "has_end": False,
                        "dirty": (fld.get(qn("dirty")) or "").lower() in {"1", "true", "on"},
                    }
                    stack.append(field)
                elif fld_type == "separate" and stack:
                    stack[-1]["has_separate"] = True
                elif fld_type == "end" and stack:
                    field = stack.pop()
                    field["has_end"] = True
                    field["paragraph_indexes"].add(idx)
                    fields.append(field)
            instr = "".join(t.text or "" for t in run.findall("w:instrText", NS))
            if instr and stack:
                stack[-1]["instr"] += instr
    fields.extend(stack)
    return fields


def field_instr_from_simple_fields(paras: list[etree._Element]) -> list[dict]:
    out = []
    for idx, p in enumerate(paras, 1):
        for fld in p.findall(".//w:fldSimple", NS):
            out.append(
                {
                    "instr": fld.get(qn("instr")) or "",
                    "paragraph_indexes": {idx},
                    "has_separate": False,
                    "has_end": True,
                    "dirty": (fld.get(qn("dirty")) or "").lower() in {"1", "true", "on"},
                }
            )
    return out


def is_caption_toc(instr: str) -> bool:
    return bool(re.search(r'\\c\s+"', instr)) or CHINESE_FIGURE in instr or CHINESE_TABLE in instr


def is_main_toc(instr: str) -> bool:
    return bool(re.search(r"\bTOC\b", instr)) and not is_caption_toc(instr)


def is_figure_list_toc(instr: str) -> bool:
    return bool(re.search(r"\bTOC\b", instr)) and (
        CHINESE_FIGURE in instr or re.search(r'\\c\s+"[^"]*(?:Figure|figure)[^"]*"', instr)
    )


def update_fields_on_open(settings_root: etree._Element | None) -> bool:
    if settings_root is None:
        return False
    node = settings_root.find("w:updateFields", NS)
    if node is None:
        return False
    val = (node.get(qn("val")) or "true").lower()
    return val not in {"0", "false", "off"}


def toc_report(paras: list[etree._Element], settings_root: etree._Element | None) -> dict:
    fields = iter_complex_fields(paras) + field_instr_from_simple_fields(paras)
    main_fields = [f for f in fields if is_main_toc(f["instr"])]
    main = main_fields[0] if main_fields else None
    toc_result_count = 0
    hyperlink_count = 0
    if main is not None:
        for idx in sorted(main["paragraph_indexes"]):
            p = paras[idx - 1]
            text = compact_text(para_text(p))
            if text and text != CHINESE_TOC and "TOC" not in "".join(p.xpath(".//w:instrText/text()", namespaces=NS)):
                toc_result_count += 1
            hyperlink_count += len(p.findall(".//w:hyperlink", NS))
    static_candidates = static_toc_candidate_count(paras)
    return {
        "main_toc_field_found": main is not None,
        "main_toc_instr": (main["instr"].strip() if main is not None else ""),
        "main_toc_result_paragraph_count": toc_result_count,
        "main_toc_hyperlink_count": hyperlink_count,
        "toc_is_static_only": bool(static_candidates and main is None),
        "toc_dirty_or_updateable": bool(
            main is not None
            and (main["dirty"] or (main["has_separate"] and main["has_end"]) or update_fields_on_open(settings_root))
        ),
    }


def static_toc_candidate_count(paras: list[etree._Element]) -> int:
    texts = [compact_text(para_text(p)) for p in paras]
    start = next((i for i, text in enumerate(texts) if text in {CHINESE_TOC, "TableofContents"}), None)
    if start is None:
        return 0
    end = len(paras)
    for i in range(start + 1, len(paras)):
        if texts[i] in {CHINESE_FIGURE_LIST, CHINESE_TABLE_LIST, CHINESE_REFERENCE}:
            end = i
            break
    count = 0
    for p in paras[start + 1 : end]:
        text = para_text(p)
        has_hyperlink = bool(p.findall(".//w:hyperlink", NS))
        has_leader = bool(re.search(r"\.{3,}|\t+\d+\s*$", text))
        if compact_text(text) and (has_hyperlink or has_leader):
            count += 1
    return count


def has_page_break_before(p: etree._Element) -> bool:
    node = p.find("w:pPr/w:pageBreakBefore", NS)
    if node is None:
        return False
    val = (node.get(qn("val")) or "true").lower()
    return val not in {"0", "false", "off"}


def figure_list_report(paras: list[etree._Element]) -> dict:
    fields = iter_complex_fields(paras) + field_instr_from_simple_fields(paras)
    field_found = any(is_figure_list_toc(f["instr"]) for f in fields)
    heading_index = next(
        (idx for idx, p in enumerate(paras, 1) if compact_text(para_text(p)) == CHINESE_FIGURE_LIST),
        None,
    )
    starts_new_page = bool(heading_index and has_page_break_before(paras[heading_index - 1]))
    return {
        "figure_list_field_found": field_found,
        "figure_list_heading_found": heading_index is not None,
        "figure_list_heading_index": heading_index,
        "figure_list_starts_new_page": starts_new_page,
    }


def heading_numbering_report(paras: list[etree._Element], catalog: dict) -> dict:
    heading_paras = {1: [], 2: []}
    for p in paras:
        level = heading_level_for_paragraph(p, catalog)
        if level in heading_paras:
            heading_paras[level].append(p)
    heading1_style_num = any(style_num_pr(style_id, catalog)[0] is not None for style_id in catalog["heading_by_level"][1])
    heading2_style_num = any(style_num_pr(style_id, catalog)[0] is not None for style_id in catalog["heading_by_level"][2])
    counts = {}
    missing = {}
    ilvls = {}
    num_ids = {}
    for level, items in heading_paras.items():
        resolved = [paragraph_num_pr(p, catalog) for p in items]
        counts[level] = sum(1 for num_id, _ilvl, _source in resolved if num_id is not None)
        missing[level] = sum(1 for num_id, _ilvl, _source in resolved if num_id is None)
        ilvls[level] = sorted({ilvl for _num_id, ilvl, _source in resolved if ilvl is not None})
        num_ids[level] = sorted({num_id for num_id, _ilvl, _source in resolved if num_id is not None})
    heading_num_id = (num_ids[1] or num_ids[2] or [None])[0]
    return {
        "heading1_style_numPr": heading1_style_num,
        "heading2_style_numPr": heading2_style_num,
        "heading1_paragraph_count": len(heading_paras[1]),
        "heading2_paragraph_count": len(heading_paras[2]),
        "heading1_direct_or_style_numPr_count": counts[1],
        "heading2_direct_or_style_numPr_count": counts[2],
        "heading1_missing_numPr_count": missing[1],
        "heading2_missing_numPr_count": missing[2],
        "heading1_resolved_ilvls": ilvls[1],
        "heading2_resolved_ilvls": ilvls[2],
        "heading2_expected_ilvl": "1",
        "heading_num_id": heading_num_id,
    }


def reference_report(paras: list[etree._Element], catalog: dict, numbering: dict, ref_heading: str) -> dict:
    ref_heading_compact = compact_text(ref_heading)
    texts = [compact_text(para_text(p)) for p in paras]
    start = next((i for i, text in enumerate(texts) if text in {ref_heading_compact, CHINESE_REFERENCE, "References"}), None)
    ref_paras = []
    if start is not None:
        for p in paras[start + 1 :]:
            text = compact_text(para_text(p))
            if not text:
                continue
            if heading_level_for_paragraph(p, catalog) is not None:
                break
            ref_paras.append(p)
    resolved = [paragraph_num_pr(p, catalog) for p in ref_paras]
    ref_num_ids = sorted({num_id for num_id, _ilvl, _source in resolved if num_id is not None})
    reference_num_id = ref_num_ids[0] if ref_num_ids else None
    bracketed_by_text = all(re.match(r"^\[\d+\]", compact_text(para_text(p))) for p in ref_paras) if ref_paras else False
    bracketed_by_numbering = False
    if reference_num_id is not None:
        texts_by_level = [lvl_text_for(reference_num_id, ilvl, numbering) for _num_id, ilvl, _source in resolved]
        bracketed_by_numbering = any(text and re.search(r"\[%\d+\]", text) for text in texts_by_level)
    heading_report = heading_numbering_report(paras, catalog)
    heading_num_id = heading_report["heading_num_id"]
    return {
        "reference_heading_found": start is not None,
        "reference_paragraph_count": len(ref_paras),
        "reference_num_id": reference_num_id,
        "heading_num_id": heading_num_id,
        "reference_independent_from_heading": bool(reference_num_id and heading_num_id and reference_num_id != heading_num_id),
        "reference_format_bracketed": bool(ref_paras) and (bracketed_by_text or bracketed_by_numbering),
    }


def audit(path: Path, template: Path | None = None, ref_heading: str = CHINESE_REFERENCE) -> dict:
    with zipfile.ZipFile(path) as zf:
        doc_root = read_xml(zf, "word/document.xml")
        if doc_root is None:
            raise ValueError("word/document.xml not found")
        styles_root = read_xml(zf, "word/styles.xml")
        numbering_root = read_xml(zf, "word/numbering.xml")
        settings_root = read_xml(zf, "word/settings.xml")

    paras = doc_root.xpath(".//w:body//w:p", namespaces=NS)
    catalog = style_catalog(styles_root)
    numbering = numbering_catalog(numbering_root)
    report = {
        "path": str(path),
        "heading_numbering": heading_numbering_report(paras, catalog),
        "toc": toc_report(paras, settings_root),
        "figure_list": figure_list_report(paras),
        "reference_numbering": reference_report(paras, catalog, numbering, ref_heading),
    }

    if template is not None:
        with zipfile.ZipFile(template) as zf:
            template_doc_root = read_xml(zf, "word/document.xml")
        template_paras = template_doc_root.xpath(".//w:body//w:p", namespaces=NS) if template_doc_root is not None else []
        report["template"] = {
            "path": str(template),
            "figure_list_starts_new_page": figure_list_report(template_paras)["figure_list_starts_new_page"],
        }
    return report


def strict_failures(report: dict) -> list[str]:
    failures = []
    heading = report["heading_numbering"]
    if heading["heading1_paragraph_count"] and heading["heading1_missing_numPr_count"]:
        failures.append("heading1_numPr_missing")
    if heading["heading2_paragraph_count"] and heading["heading2_missing_numPr_count"]:
        failures.append("heading2_numPr_missing")
    if heading["heading2_paragraph_count"] and heading["heading2_resolved_ilvls"] != ["1"]:
        failures.append("heading2_ilvl_not_1")

    toc = report["toc"]
    if not toc["main_toc_field_found"]:
        failures.append("main_toc_field_found")
    if toc["toc_is_static_only"]:
        failures.append("toc_is_static_only")
    if toc["main_toc_field_found"] and not re.search(r"\\h\b", toc["main_toc_instr"]):
        failures.append("main_toc_missing_hyperlinks")
    if toc["main_toc_field_found"] and not toc["toc_dirty_or_updateable"]:
        failures.append("toc_not_updateable")

    figure = report["figure_list"]
    template_requires_page = report.get("template", {}).get("figure_list_starts_new_page")
    if (figure["figure_list_heading_found"] or template_requires_page) and not figure["figure_list_starts_new_page"]:
        failures.append("figure_list_page_break_before")

    refs = report["reference_numbering"]
    if refs["reference_paragraph_count"]:
        if not refs["reference_independent_from_heading"]:
            failures.append("reference_numbering_not_independent")
        if not refs["reference_format_bracketed"]:
            failures.append("reference_numbering_not_bracketed")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit DOCX template fidelity structure.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--template", type=Path, help="Template DOCX used to create the output.")
    parser.add_argument("--ref-heading", default=CHINESE_REFERENCE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = audit(args.docx, args.template, args.ref_heading)
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
