#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path

from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = NS["w"]
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
HEADING_STYLE_IDS = {"1": "0", "Heading1": "0", "2": "1", "Heading2": "1"}
CHINESE_REFERENCE = "\u53c2\u8003\u6587\u732e"


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def read_xml(zf: zipfile.ZipFile, name: str) -> etree._Element | None:
    if name not in zf.namelist():
        return None
    return etree.fromstring(zf.read(name))


def xml_bytes(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def find_style(root: etree._Element | None, style_id: str) -> etree._Element | None:
    if root is None:
        return None
    return root.find(f"w:style[@w:styleId='{style_id}']", NS)


def copy_heading_style_numbering(template_styles: etree._Element, output_styles: etree._Element) -> dict[str, tuple[str, str]]:
    copied: dict[str, tuple[str, str]] = {}
    for style_id, ilvl in HEADING_STYLE_IDS.items():
        src = find_style(template_styles, style_id)
        dst = find_style(output_styles, style_id)
        if src is None or dst is None:
            continue
        src_num_pr = src.find("w:pPr/w:numPr", NS)
        if src_num_pr is None:
            continue
        dst_ppr = dst.find("w:pPr", NS)
        if dst_ppr is None:
            dst_ppr = etree.Element(qn("pPr"))
            dst.insert(0, dst_ppr)
        old = dst_ppr.find("w:numPr", NS)
        if old is not None:
            dst_ppr.remove(old)
        dst_ppr.insert(0, deepcopy(src_num_pr))
        num_id = src_num_pr.find("w:numId", NS)
        ilvl_node = src_num_pr.find("w:ilvl", NS)
        copied[style_id] = (
            num_id.get(qn("val")) if num_id is not None else "",
            ilvl_node.get(qn("val")) if ilvl_node is not None else ilvl,
        )
    return copied


def abstract_id_for_num(numbering: etree._Element, num_id: str) -> str | None:
    num = numbering.find(f"w:num[@w:numId='{num_id}']", NS)
    abstract = num.find("w:abstractNumId", NS) if num is not None else None
    return abstract.get(qn("val")) if abstract is not None else None


def replace_child_by_attr(parent: etree._Element, child: etree._Element, attr_name: str, attr_value: str) -> None:
    old = parent.find(f"w:{etree.QName(child).localname}[@w:{attr_name}='{attr_value}']", NS)
    if old is not None:
        parent.remove(old)
    parent.append(deepcopy(child))


def copy_heading_numbering(template_numbering: etree._Element | None, output_numbering: etree._Element | None, heading_num_ids: set[str]) -> etree._Element | None:
    if template_numbering is None or not heading_num_ids:
        return output_numbering
    if output_numbering is None:
        output_numbering = etree.Element(qn("numbering"), nsmap=template_numbering.nsmap)
    for num_id in heading_num_ids:
        template_num = template_numbering.find(f"w:num[@w:numId='{num_id}']", NS)
        abstract_id = abstract_id_for_num(template_numbering, num_id)
        template_abstract = (
            template_numbering.find(f"w:abstractNum[@w:abstractNumId='{abstract_id}']", NS)
            if abstract_id is not None
            else None
        )
        if template_abstract is not None:
            replace_child_by_attr(output_numbering, template_abstract, "abstractNumId", abstract_id)
        if template_num is not None:
            replace_child_by_attr(output_numbering, template_num, "numId", num_id)
    return output_numbering


def para_text(p: etree._Element) -> str:
    return "".join(t.text or "" for t in p.xpath(".//w:t", namespaces=NS))


def compact_text(text: str) -> str:
    return "".join(text.split())


def paragraph_style_id(p: etree._Element) -> str | None:
    pstyle = p.find("w:pPr/w:pStyle", NS)
    return pstyle.get(qn("val")) if pstyle is not None else None


def ensure_direct_num_pr(p: etree._Element, num_id: str, ilvl: str) -> None:
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        ppr = etree.Element(qn("pPr"))
        p.insert(0, ppr)
    old = ppr.find("w:numPr", NS)
    if old is not None:
        ppr.remove(old)
    num_pr = etree.Element(qn("numPr"))
    ilvl_node = etree.SubElement(num_pr, qn("ilvl"))
    ilvl_node.set(qn("val"), ilvl)
    num_id_node = etree.SubElement(num_pr, qn("numId"))
    num_id_node.set(qn("val"), num_id)
    ppr.insert(0, num_pr)


def assign_heading_paragraph_numbering(document_root: etree._Element, copied_styles: dict[str, tuple[str, str]]) -> int:
    changed = 0
    for p in document_root.xpath(".//w:body//w:p", namespaces=NS):
        style_id = paragraph_style_id(p)
        if style_id not in copied_styles:
            continue
        num_id, ilvl = copied_styles[style_id]
        if not num_id:
            continue
        ensure_direct_num_pr(p, num_id, ilvl)
        changed += 1
    return changed


def first_reference_num_id(document_root: etree._Element, ref_heading: str) -> str | None:
    paras = document_root.xpath(".//w:body//w:p", namespaces=NS)
    start = next((i for i, p in enumerate(paras) if compact_text(para_text(p)) in {compact_text(ref_heading), CHINESE_REFERENCE}), None)
    if start is None:
        return None
    for p in paras[start + 1 :]:
        if not compact_text(para_text(p)):
            continue
        num_id_node = p.find("w:pPr/w:numPr/w:numId", NS)
        return num_id_node.get(qn("val")) if num_id_node is not None else None
    return None


def write_docx(src: Path, dst: Path, replacements: dict[str, bytes]) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = replacements.get(item.filename)
            zout.writestr(item, data if data is not None else zin.read(item.filename))
        existing = set(zin.namelist())
        for name, data in replacements.items():
            if name not in existing:
                zout.writestr(name, data)


def ensure_numbering_links(replacements: dict[str, bytes], rels_xml: bytes | None, content_types_xml: bytes | None) -> None:
    rels_name = "word/_rels/document.xml.rels"
    if rels_xml:
        rels = etree.fromstring(rels_xml)
    else:
        rels = etree.Element(f"{{{REL_NS}}}Relationships")
    if not any((rel.get("Type") or "").endswith("/numbering") for rel in rels):
        ids = [
            int((rel.get("Id") or "rId0").replace("rId", ""))
            for rel in rels
            if (rel.get("Id") or "").startswith("rId") and (rel.get("Id") or "")[3:].isdigit()
        ]
        rel = etree.SubElement(rels, f"{{{REL_NS}}}Relationship")
        rel.set("Id", f"rId{max(ids, default=0) + 1}")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering")
        rel.set("Target", "numbering.xml")
    replacements[rels_name] = xml_bytes(rels)

    if content_types_xml:
        content_types = etree.fromstring(content_types_xml)
    else:
        content_types = etree.Element(f"{{{CT_NS}}}Types")
    if not any(node.get("PartName") == "/word/numbering.xml" for node in content_types):
        override = etree.SubElement(content_types, f"{{{CT_NS}}}Override")
        override.set("PartName", "/word/numbering.xml")
        override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml")
    replacements["[Content_Types].xml"] = xml_bytes(content_types)


def preserve_numbering(report: Path, template: Path, out: Path | None, ref_heading: str) -> dict:
    with zipfile.ZipFile(template) as zf:
        template_styles = read_xml(zf, "word/styles.xml")
        template_numbering = read_xml(zf, "word/numbering.xml")
    with zipfile.ZipFile(report) as zf:
        output_styles = read_xml(zf, "word/styles.xml")
        output_numbering = read_xml(zf, "word/numbering.xml")
        document = read_xml(zf, "word/document.xml")
        rels_xml = zf.read("word/_rels/document.xml.rels") if "word/_rels/document.xml.rels" in zf.namelist() else None
        content_types_xml = zf.read("[Content_Types].xml") if "[Content_Types].xml" in zf.namelist() else None
    if template_styles is None or output_styles is None or document is None:
        raise ValueError("report and template must contain word/document.xml and word/styles.xml")

    copied_styles = copy_heading_style_numbering(template_styles, output_styles)
    heading_num_ids = {num_id for num_id, _ilvl in copied_styles.values() if num_id}
    output_numbering = copy_heading_numbering(template_numbering, output_numbering, heading_num_ids)
    heading_paragraphs_updated = assign_heading_paragraph_numbering(document, copied_styles)
    reference_num_id = first_reference_num_id(document, ref_heading)
    shared_reference_numbering = bool(reference_num_id and reference_num_id in heading_num_ids)

    replacements = {
        "word/styles.xml": xml_bytes(output_styles),
        "word/document.xml": xml_bytes(document),
    }
    if output_numbering is not None:
        replacements["word/numbering.xml"] = xml_bytes(output_numbering)
        ensure_numbering_links(replacements, rels_xml, content_types_xml)

    target = out or report
    if target == report:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp_path = Path(tmp.name)
        write_docx(report, tmp_path, replacements)
        shutil.move(str(tmp_path), report)
    else:
        write_docx(report, target, replacements)
    return {
        "output": str(target),
        "copied_heading_styles": sorted(copied_styles),
        "heading_num_ids": sorted(heading_num_ids),
        "heading_paragraphs_updated": heading_paragraphs_updated,
        "reference_num_id": reference_num_id,
        "reference_shares_heading_num_id": shared_reference_numbering,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore heading numbering from a DOCX template.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ref-heading", default=CHINESE_REFERENCE)
    parser.add_argument("--strict", action="store_true", help="Fail if references share the restored heading numId.")
    args = parser.parse_args()

    report = preserve_numbering(args.docx, args.template, args.out, args.ref_heading)
    for key, value in report.items():
        print(f"{key}: {value}")
    if args.strict and report["reference_shares_heading_num_id"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
