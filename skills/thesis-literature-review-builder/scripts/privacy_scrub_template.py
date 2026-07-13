#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from lxml import etree as LET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
DCTYPE_NS = "http://purl.org/dc/dcmitype/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

ET.register_namespace("cp", CP_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("dcterms", DCTERMS_NS)
ET.register_namespace("dcmitype", DCTYPE_NS)
ET.register_namespace("xsi", XSI_NS)
ET.register_namespace("ep", EP_NS)
ET.register_namespace("vt", VT_NS)
ET.register_namespace("w", W_NS)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def rels_source_part(name: str) -> str | None:
    if not name.startswith("word/_rels/") or not name.endswith(".rels"):
        return None
    return f"word/{name[len('word/_rels/'):-len('.rels')]}"


def qn(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def core_properties() -> bytes:
    root = ET.Element(qn(CP_NS, "coreProperties"))
    ET.SubElement(root, qn(DC_NS, "title")).text = ""
    ET.SubElement(root, qn(DC_NS, "subject")).text = ""
    ET.SubElement(root, qn(DC_NS, "creator")).text = ""
    ET.SubElement(root, qn(CP_NS, "keywords")).text = ""
    ET.SubElement(root, qn(DC_NS, "description")).text = ""
    ET.SubElement(root, qn(CP_NS, "lastModifiedBy")).text = ""
    ET.SubElement(root, qn(CP_NS, "revision")).text = "1"
    created = ET.SubElement(root, qn(DCTERMS_NS, "created"))
    created.set(qn(XSI_NS, "type"), "dcterms:W3CDTF")
    created.text = utc_now()
    modified = ET.SubElement(root, qn(DCTERMS_NS, "modified"))
    modified.set(qn(XSI_NS, "type"), "dcterms:W3CDTF")
    modified.text = utc_now()
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def app_properties() -> bytes:
    root = ET.Element(qn(EP_NS, "Properties"))
    ET.SubElement(root, qn(EP_NS, "Template")).text = "Normal.dotm"
    ET.SubElement(root, qn(EP_NS, "Application")).text = "Microsoft Office Word"
    ET.SubElement(root, qn(EP_NS, "DocSecurity")).text = "0"
    ET.SubElement(root, qn(EP_NS, "ScaleCrop")).text = "false"
    ET.SubElement(root, qn(EP_NS, "Company")).text = ""
    ET.SubElement(root, qn(EP_NS, "LinksUpToDate")).text = "false"
    ET.SubElement(root, qn(EP_NS, "SharedDoc")).text = "false"
    ET.SubElement(root, qn(EP_NS, "HyperlinksChanged")).text = "false"
    ET.SubElement(root, qn(EP_NS, "AppVersion")).text = "16.0000"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def should_drop_part(name: str, remove_embedded: bool) -> bool:
    low = name.lower()
    if low == "docprops/custom.xml":
        return True
    if low.startswith("customxml/"):
        return True
    if low.startswith("word/comments") or low.startswith("word/people"):
        return True
    if low.startswith("word/_rels/comments") or "comments" in low and low.endswith(".rels"):
        return True
    if remove_embedded and (low.startswith("word/embeddings/") or low.startswith("word/activeX/".lower())):
        return True
    return False


def strip_content_types(data: bytes, remove_embedded: bool) -> bytes:
    root = ET.fromstring(data)
    for child in list(root):
        part = (child.get("PartName") or "").lower()
        ctype = (child.get("ContentType") or "").lower()
        drop = (
            part == "/docprops/custom.xml"
            or part.startswith("/customxml/")
            or "/comments" in part
            or "/people" in part
            or "comments" in ctype
            or "custom-properties" in ctype
        )
        if remove_embedded and (part.startswith("/word/embeddings/") or part.startswith("/word/activex/")):
            drop = True
        if drop:
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def relationship_ids_to_remove(files: dict[str, bytes], remove_external: bool, remove_embedded: bool) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for name, data in files.items():
        source = rels_source_part(name)
        if source is None:
            continue
        root = ET.fromstring(data)
        for child in root:
            target = (child.get("Target") or "").lower()
            mode = (child.get("TargetMode") or "").lower()
            should_remove = (remove_external and mode == "external") or (
                remove_embedded and ("embeddings/" in target or "activex/" in target)
            )
            if should_remove and child.get("Id"):
                result.setdefault(source, set()).add(child.get("Id"))
    return result


def strip_relationships(data: bytes, remove_external: bool, remove_embedded: bool) -> bytes:
    root = ET.fromstring(data)
    for child in list(root):
        target = (child.get("Target") or "").lower()
        rtype = (child.get("Type") or "").lower()
        mode = (child.get("TargetMode") or "").lower()
        drop = (
            "comments" in target
            or "people" in target
            or "customxml" in target
            or "custom-properties" in rtype
        )
        if remove_external and mode == "external":
            drop = True
        if remove_embedded and ("embeddings/" in target or "activex/" in target):
            drop = True
        if drop:
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def unwrap(parent: ET.Element, child: ET.Element) -> None:
    index = list(parent).index(child)
    parent.remove(child)
    for grandchild in list(child):
        parent.insert(index, grandchild)
        index += 1


def local_name_lxml(element: LET._Element) -> str:
    return LET.QName(element).localname


def unwrap_lxml(child: LET._Element) -> None:
    parent = child.getparent()
    if parent is None:
        return
    index = parent.index(child)
    parent.remove(child)
    for grandchild in list(child):
        parent.insert(index, grandchild)
        index += 1


def accept_revision_elements_lxml(root: LET._Element) -> None:
    for child in list(root.xpath(".//*[local-name()='del' or local-name()='moveFrom']")):
        parent = child.getparent()
        if parent is not None:
            parent.remove(child)
    for child in list(root.xpath(".//*[local-name()='ins' or local-name()='moveTo']")):
        unwrap_lxml(child)


def remove_hidden_runs_lxml(root: LET._Element) -> None:
    for run in list(root.xpath(".//*[local-name()='r'][.//*[local-name()='vanish']]")):
        parent = run.getparent()
        if parent is not None:
            parent.remove(run)


def remove_removed_relationship_markup_lxml(root: LET._Element, removed_ids: set[str]) -> None:
    if not removed_ids:
        return
    rid = qn(R_NS, "id")
    for child in list(root.xpath(".//*[@r:id]", namespaces={"r": R_NS})):
        if child.get(rid) not in removed_ids:
            continue
        parent = child.getparent()
        if parent is None:
            continue
        local = local_name_lxml(child)
        if local == "hyperlink":
            unwrap_lxml(child)
        else:
            parent.remove(child)


def remove_removed_relationship_markup(root: ET.Element, removed_ids: set[str]) -> None:
    if not removed_ids:
        return
    rid = qn(R_NS, "id")
    for parent in list(root.iter()):
        for child in list(parent):
            child_local = local_name(child.tag)
            descendant_ids = {element.get(rid) for element in child.iter() if element.get(rid)}
            if not descendant_ids.intersection(removed_ids):
                continue
            if child_local == "hyperlink" and child.get(rid) in removed_ids:
                unwrap(parent, child)
            elif child_local == "object" or child.get(rid) in removed_ids:
                parent.remove(child)


def scrub_word_xml(data: bytes, accept_revisions: bool, remove_hidden_text: bool, removed_ids: set[str]) -> bytes:
    try:
        root = LET.fromstring(data)
    except LET.XMLSyntaxError:
        return data

    for el in root.iter():
        for attr in list(el.attrib):
            local = attr.rsplit("}", 1)[-1]
            if local.startswith("rsid") or local in {"author", "date", "initials", "userId"}:
                del el.attrib[attr]

    for child in list(
        root.xpath(
            ".//*[local-name()='commentRangeStart' or local-name()='commentRangeEnd' "
            "or local-name()='commentReference' or local-name()='proofErr' "
            "or local-name()='permStart' or local-name()='permEnd']"
        )
    ):
        parent = child.getparent()
        if parent is not None:
            parent.remove(child)

    if accept_revisions:
        accept_revision_elements_lxml(root)
    if remove_hidden_text:
        remove_hidden_runs_lxml(root)
    remove_removed_relationship_markup_lxml(root, removed_ids)

    return LET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def accept_revision_elements(root: ET.Element) -> None:
    for parent in list(root.iter()):
        children = list(parent)
        for child in children:
            local = child.tag.rsplit("}", 1)[-1]
            if local in {"del", "moveFrom"}:
                parent.remove(child)
            elif local in {"ins", "moveTo"}:
                idx = list(parent).index(child)
                parent.remove(child)
                for grandchild in list(child):
                    parent.insert(idx, copy.deepcopy(grandchild))
                    idx += 1


def remove_hidden_runs(root: ET.Element) -> None:
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] != "r":
                continue
            has_vanish = child.find(f".//{{{W_NS}}}vanish") is not None
            if has_vanish:
                parent.remove(child)


def replace_sensitive_text(data: bytes, patterns: list[str], replacement: str) -> bytes:
    if not patterns:
        return data
    text = data.decode("utf-8", errors="ignore")
    for pat in patterns:
        if pat:
            text = text.replace(pat, replacement)
    return text.encode("utf-8")


def scrub_docx(
    input_path: Path,
    output_path: Path,
    patterns: list[str],
    replacement: str,
    accept_revisions: bool,
    remove_hidden_text: bool,
    remove_external_relationships: bool,
    remove_embedded_objects: bool,
) -> dict:
    if input_path.resolve() == output_path.resolve():
        backup = input_path.with_suffix(".privacy-backup.docx")
        shutil.copy2(input_path, backup)
    with zipfile.ZipFile(input_path, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    removed_relationship_ids = relationship_ids_to_remove(
        files, remove_external_relationships, remove_embedded_objects
    )

    out: dict[str, bytes] = {}
    removed: list[str] = []
    changed: list[str] = []
    for name, data in files.items():
        if should_drop_part(name, remove_embedded_objects):
            removed.append(name)
            continue
        new_data = data
        low = name.lower()
        if low == "docprops/core.xml":
            new_data = core_properties()
        elif low == "docprops/app.xml":
            new_data = app_properties()
        elif low == "[content_types].xml":
            new_data = strip_content_types(data, remove_embedded_objects)
        elif low.endswith(".rels"):
            new_data = strip_relationships(data, remove_external_relationships, remove_embedded_objects)
        elif low.startswith("word/") and low.endswith(".xml"):
            new_data = scrub_word_xml(
                data,
                accept_revisions,
                remove_hidden_text,
                removed_relationship_ids.get(name, set()),
            )

        if patterns and low.endswith((".xml", ".rels")):
            new_data = replace_sensitive_text(new_data, patterns, replacement)
        if new_data != data:
            changed.append(name)
        out[name] = new_data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in out.items():
            zout.writestr(name, data)
    return {"output": str(output_path), "removed_parts": removed, "changed_parts": changed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrub DOCX templates before public release.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pattern", action="append", default=[], help="Sensitive literal text to replace in XML parts.")
    parser.add_argument("--replacement", default="XX", help="Replacement text for --pattern.")
    parser.add_argument("--keep-revisions", action="store_true", help="Keep tracked-change markup instead of accepting insertions/deletions.")
    parser.add_argument("--keep-hidden-text", action="store_true", help="Keep runs marked with w:vanish.")
    parser.add_argument("--keep-external-relationships", action="store_true", help="Keep external hyperlinks/relationships.")
    parser.add_argument("--keep-embedded-objects", action="store_true", help="Keep embedded OLE/ActiveX objects.")
    args = parser.parse_args()

    result = scrub_docx(
        args.input,
        args.output,
        patterns=args.pattern,
        replacement=args.replacement,
        accept_revisions=not args.keep_revisions,
        remove_hidden_text=not args.keep_hidden_text,
        remove_external_relationships=not args.keep_external_relationships,
        remove_embedded_objects=not args.keep_embedded_objects,
    )
    print(f"output: {result['output']}")
    print(f"removed_parts: {len(result['removed_parts'])}")
    for item in result["removed_parts"]:
        print(f"  - {item}")
    print(f"changed_parts: {len(result['changed_parts'])}")


if __name__ == "__main__":
    main()
