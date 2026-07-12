#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import re
import shutil
import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
W = NS["w"]
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
REFERENCE_INDENT_TWIPS = "420"


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS))


def first_rpr(p: etree._Element) -> etree._Element | None:
    r = p.find("w:r", namespaces=NS)
    if r is None:
        return None
    rpr = r.find("w:rPr", namespaces=NS)
    return copy.deepcopy(rpr) if rpr is not None else None


def superscript_rpr(rpr: etree._Element | None) -> etree._Element:
    out = copy.deepcopy(rpr) if rpr is not None else etree.Element(qn("rPr"))
    for old in out.findall("w:vertAlign", namespaces=NS):
        out.remove(old)
    va = etree.SubElement(out, qn("vertAlign"))
    va.set(qn("val"), "superscript")
    return out


def text_run(text: str, rpr: etree._Element | None = None) -> etree._Element:
    r = etree.Element(qn("r"))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = etree.SubElement(r, qn("t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text
    return r


def field_runs(bookmark: str, display: str, rpr: etree._Element | None) -> list[etree._Element]:
    rpr = superscript_rpr(rpr)
    runs = []
    for kind in ("begin",):
        r = etree.Element(qn("r"))
        r.append(copy.deepcopy(rpr))
        fld = etree.SubElement(r, qn("fldChar"))
        fld.set(qn("fldCharType"), kind)
        runs.append(r)

    r = etree.Element(qn("r"))
    r.append(copy.deepcopy(rpr))
    instr = etree.SubElement(r, qn("instrText"))
    instr.set(XML_SPACE, "preserve")
    instr.text = f" REF {bookmark} \\n \\h \\* MERGEFORMAT "
    runs.append(r)

    r = etree.Element(qn("r"))
    r.append(copy.deepcopy(rpr))
    sep = etree.SubElement(r, qn("fldChar"))
    sep.set(qn("fldCharType"), "separate")
    runs.append(r)

    runs.append(text_run(display, rpr))

    r = etree.Element(qn("r"))
    r.append(copy.deepcopy(rpr))
    end = etree.SubElement(r, qn("fldChar"))
    end.set(qn("fldCharType"), "end")
    runs.append(r)
    return runs


def citation_numbers(citation: str) -> list[int]:
    nums: list[int] = []
    for a, b in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", citation):
        start = int(a)
        end = int(b) if b else start
        if end >= start and end - start <= 50:
            nums.extend(range(start, end + 1))
        else:
            nums.append(start)
    return nums


def rebuild_paragraph_with_fields(
    p: etree._Element,
    citation_pat: re.Pattern,
    old_to_new: dict[int, int],
) -> tuple[bool, bool]:
    """Convert only simple, single-number citations without rebuilding the paragraph.

    Returns (changed, unsupported_citation_found). Multi-number/range citations and
    citations inside complex runs are rejected rather than silently losing formatting.
    """
    total_citations = len(citation_pat.findall(para_text(p)))
    handled_citations = 0
    changed = False
    for child in list(p):
        if child.tag != qn("r"):
            continue
        text_nodes = child.findall("w:t", namespaces=NS)
        content_nodes = [node for node in child if node.tag != qn("rPr")]
        if len(text_nodes) != 1 or content_nodes != text_nodes:
            continue
        text = text_nodes[0].text or ""
        matches = list(citation_pat.finditer(text))
        if not matches:
            continue
        rpr = child.find("w:rPr", namespaces=NS)
        replacement: list[etree._Element] = []
        position = 0
        for match in matches:
            numbers = citation_numbers(match.group(0))
            if len(numbers) != 1 or numbers[0] not in old_to_new:
                continue
            if match.start() > position:
                replacement.append(text_run(text[position : match.start()], rpr))
            new_no = old_to_new[numbers[0]]
            replacement.extend(field_runs(f"Ref_{new_no:03d}", f"[{new_no}]", rpr))
            position = match.end()
            handled_citations += 1
        if position == 0:
            continue
        if position < len(text):
            replacement.append(text_run(text[position:], rpr))
        index = list(p).index(child)
        p.remove(child)
        for node in replacement:
            p.insert(index, node)
            index += 1
        changed = True
    return changed, handled_citations != total_citations


def ensure_numbering(files: dict[str, bytes]) -> tuple[etree._Element, int]:
    numbering_xml = files.get("word/numbering.xml")
    if numbering_xml:
        root = etree.fromstring(numbering_xml)
    else:
        root = etree.Element(qn("numbering"), nsmap={"w": W})

    abstract_ids = [
        int(x.get(qn("abstractNumId")))
        for x in root.findall("w:abstractNum", namespaces=NS)
        if (x.get(qn("abstractNumId")) or "").isdigit()
    ]
    num_ids = [
        int(x.get(qn("numId")))
        for x in root.findall("w:num", namespaces=NS)
        if (x.get(qn("numId")) or "").isdigit()
    ]
    abstract_id = max(abstract_ids, default=0) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = etree.Element(qn("abstractNum"))
    abstract.set(qn("abstractNumId"), str(abstract_id))
    lvl = etree.SubElement(abstract, qn("lvl"))
    lvl.set(qn("ilvl"), "0")
    etree.SubElement(lvl, qn("start")).set(qn("val"), "1")
    etree.SubElement(lvl, qn("numFmt")).set(qn("val"), "decimal")
    etree.SubElement(lvl, qn("lvlText")).set(qn("val"), "[%1]")
    etree.SubElement(lvl, qn("lvlJc")).set(qn("val"), "left")
    ppr = etree.SubElement(lvl, qn("pPr"))
    tabs = etree.SubElement(ppr, qn("tabs"))
    tab = etree.SubElement(tabs, qn("tab"))
    tab.set(qn("val"), "num")
    tab.set(qn("pos"), REFERENCE_INDENT_TWIPS)
    ind = etree.SubElement(ppr, qn("ind"))
    ind.set(qn("left"), REFERENCE_INDENT_TWIPS)
    ind.set(qn("hanging"), REFERENCE_INDENT_TWIPS)
    root.append(abstract)

    num = etree.Element(qn("num"))
    num.set(qn("numId"), str(num_id))
    etree.SubElement(num, qn("abstractNumId")).set(qn("val"), str(abstract_id))
    root.append(num)
    return root, num_id


def add_numpr(p: etree._Element, num_id: int) -> None:
    ppr = p.find("w:pPr", namespaces=NS)
    if ppr is None:
        ppr = etree.Element(qn("pPr"))
        p.insert(0, ppr)
    for old in ppr.findall("w:numPr", namespaces=NS):
        ppr.remove(old)
    numpr = etree.Element(qn("numPr"))
    etree.SubElement(numpr, qn("ilvl")).set(qn("val"), "0")
    etree.SubElement(numpr, qn("numId")).set(qn("val"), str(num_id))
    ppr.append(numpr)


def apply_reference_indent(ppr: etree._Element) -> None:
    for old in ppr.findall("w:ind", namespaces=NS):
        ppr.remove(old)
    for old in ppr.findall("w:tabs", namespaces=NS):
        ppr.remove(old)
    tabs = etree.Element(qn("tabs"))
    tab = etree.SubElement(tabs, qn("tab"))
    tab.set(qn("val"), "num")
    tab.set(qn("pos"), REFERENCE_INDENT_TWIPS)
    ind = etree.Element(qn("ind"))
    ind.set(qn("left"), REFERENCE_INDENT_TWIPS)
    ind.set(qn("hanging"), REFERENCE_INDENT_TWIPS)
    ppr.append(tabs)
    ppr.append(ind)


def add_bookmark(p: etree._Element, name: str, bm_id: int) -> None:
    start = etree.Element(qn("bookmarkStart"))
    start.set(qn("id"), str(bm_id))
    start.set(qn("name"), name)
    end = etree.Element(qn("bookmarkEnd"))
    end.set(qn("id"), str(bm_id))
    insert_idx = 1 if len(p) and p[0].tag == qn("pPr") else 0
    p.insert(insert_idx, start)
    p.append(end)


def max_bookmark_id(root: etree._Element) -> int:
    ids = []
    for b in root.xpath(".//w:bookmarkStart|.//w:bookmarkEnd", namespaces=NS):
        val = b.get(qn("id"))
        if val and val.isdigit():
            ids.append(int(val))
    return max(ids, default=0)


def make_ref_para(text: str, ppr_template: etree._Element | None, rpr: etree._Element | None) -> etree._Element:
    p = etree.Element(qn("p"))
    if ppr_template is not None:
        ppr = copy.deepcopy(ppr_template)
        for old in ppr.findall("w:numPr", namespaces=NS):
            ppr.remove(old)
        apply_reference_indent(ppr)
        p.append(ppr)
    else:
        ppr = etree.Element(qn("pPr"))
        apply_reference_indent(ppr)
        p.append(ppr)
    p.append(text_run(text, rpr))
    return p


def ensure_numbering_relationship(files: dict[str, bytes]) -> None:
    rels_name = "word/_rels/document.xml.rels"
    if rels_name in files:
        rels = etree.fromstring(files[rels_name])
    else:
        rels = etree.Element(f"{{{NS['rel']}}}Relationships")
    if not any((r.get("Type") or "").endswith("/numbering") for r in rels):
        ids = [
            int((r.get("Id") or "rId0").replace("rId", ""))
            for r in rels
            if (r.get("Id") or "").startswith("rId") and (r.get("Id") or "")[3:].isdigit()
        ]
        rel = etree.SubElement(rels, f"{{{NS['rel']}}}Relationship")
        rel.set("Id", f"rId{max(ids, default=0) + 1}")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering")
        rel.set("Target", "numbering.xml")
    files[rels_name] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone="yes")

    ct_name = "[Content_Types].xml"
    if ct_name in files:
        ct = etree.fromstring(files[ct_name])
        if not any(x.get("PartName") == "/word/numbering.xml" for x in ct):
            override = etree.SubElement(ct, f"{{{NS['ct']}}}Override")
            override.set("PartName", "/word/numbering.xml")
            override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml")
        files[ct_name] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone="yes")


def convert(input_path: Path, output_path: Path, ref_heading: str, preserve_order: bool) -> dict:
    with zipfile.ZipFile(input_path, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}
    root = etree.fromstring(files["word/document.xml"])
    body = root.find("w:body", namespaces=NS)
    paras = body.findall("w:p", namespaces=NS)
    texts = [para_text(p).strip() for p in paras]
    heading_idx = next((i for i, text in enumerate(texts) if text == ref_heading), None)
    if heading_idx is None:
        raise RuntimeError(f"Reference heading not found: {ref_heading}")

    ref_items: list[tuple[int, str, etree._Element]] = []
    for p in paras[heading_idx + 1 :]:
        text = para_text(p).strip()
        if not text:
            continue
        m = re.match(r"^\[(\d+)\]\s*(.+)$", text)
        if m:
            ref_items.append((int(m.group(1)), m.group(2).strip(), p))
        elif ref_items:
            break
    if not ref_items:
        raise RuntimeError("No bibliography entries like [1] ... were found after the reference heading.")

    old_ref_text = {old: text for old, text, _ in ref_items}
    old_numbers = [old for old, _, _ in ref_items]
    citation_pat = re.compile(r"\[(?:\d+(?:\s*-\s*\d+)?)(?:\s*[,;，、]\s*\d+(?:\s*-\s*\d+)?)*\]")
    first_order: list[int] = []
    seen: set[int] = set()
    for p in paras[:heading_idx]:
        text = para_text(p)
        for cit in citation_pat.findall(text):
            for old_no in citation_numbers(cit):
                if old_no in old_ref_text and old_no not in seen:
                    seen.add(old_no)
                    first_order.append(old_no)
    final_old_order = old_numbers if preserve_order else first_order + [n for n in old_numbers if n not in seen]
    old_to_new = {old: i + 1 for i, old in enumerate(final_old_order)}

    converted = 0
    unsupported = []
    for p in paras[:heading_idx]:
        changed, has_unsupported = rebuild_paragraph_with_fields(p, citation_pat, old_to_new)
        if has_unsupported:
            unsupported.append(para_text(p)[:160])
        if changed:
            converted += 1
    if unsupported:
        examples = "; ".join(repr(text) for text in unsupported[:3])
        raise RuntimeError(
            "Only standalone [n] citations in simple text runs can be converted safely. "
            f"Found unsupported combined, range, or rich-text citations: {examples}"
        )

    first_ref_ppr = copy.deepcopy(ref_items[0][2].find("w:pPr", namespaces=NS)) if ref_items[0][2].find("w:pPr", namespaces=NS) is not None else None
    first_ref_rpr = first_rpr(ref_items[0][2])
    ref_para_set = {id(p) for _, _, p in ref_items}
    for p in list(body):
        if id(p) in ref_para_set:
            body.remove(p)

    numbering_root, num_id = ensure_numbering(files)
    bm_id = max_bookmark_id(root) + 1
    insert_pos = list(body).index(paras[heading_idx]) + 1
    for new_no, old_no in enumerate(final_old_order, 1):
        p = make_ref_para(old_ref_text[old_no], first_ref_ppr, first_ref_rpr)
        add_numpr(p, num_id)
        add_bookmark(p, f"Ref_{new_no:03d}", bm_id)
        bm_id += 1
        body.insert(insert_pos, p)
        insert_pos += 1

    files["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    files["word/numbering.xml"] = etree.tostring(numbering_root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    ensure_numbering_relationship(files)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() == output_path.resolve():
        backup = input_path.with_suffix(".crossref-backup.docx")
        shutil.copy2(input_path, backup)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "references": len(ref_items),
        "converted_paragraphs": converted,
        "renumbered_by_first_appearance": not preserve_order,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert plain numeric DOCX citations to Word REF cross-references.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ref-heading", default="参考文献")
    parser.add_argument("--preserve-reference-order", action="store_true")
    args = parser.parse_args()

    result = convert(args.input, args.output, args.ref_heading, args.preserve_reference_order)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
