from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "skills" / "thesis-literature-review-builder" / "scripts"
PROPOSAL = ROOT / "skills" / "thesis-proposal-report-builder" / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONVERT = load_module("convert_refs", REVIEW / "convert_refs_to_crossrefs.py")
SCRUB = load_module("privacy_scrub", REVIEW / "privacy_scrub_template.py")
AUDIT_DOCX = load_module("audit_docx", REVIEW / "audit_docx_report.py")
AUDIT_STRUCTURE = load_module("audit_docx_structure", REVIEW / "audit_docx_structure.py")
AUDIT_MD = load_module("audit_md", REVIEW / "audit_markdown_report.py")


class DocxScriptTests(unittest.TestCase):
    def test_duplicate_skill_scripts_stay_identical(self) -> None:
        for name in (
            "audit_docx_report.py",
            "audit_docx_structure.py",
            "audit_markdown_report.py",
            "convert_refs_to_crossrefs.py",
            "inspect_docx_template.py",
            "preserve_template_numbering.py",
            "privacy_scrub_template.py",
        ):
            self.assertEqual((REVIEW / name).read_bytes(), (PROPOSAL / name).read_bytes(), name)

    def test_single_citation_preserves_unrelated_run_formatting(self) -> None:
        p = etree.fromstring(
            b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:r><w:rPr><w:b/></w:rPr><w:t>Bold</w:t></w:r>'
            b'<w:r><w:t> plain [1]</w:t></w:r></w:p>'
        )
        pattern = re.compile(r"\[(?:\d+(?:\s*-\s*\d+)?)(?:\s*[,;]\s*\d+(?:\s*-\s*\d+)?)*\]")
        changed, unsupported = CONVERT.rebuild_paragraph_with_fields(p, pattern, {1: 1})
        self.assertTrue(changed)
        self.assertFalse(unsupported)
        self.assertEqual(len(p.xpath('.//w:r[w:rPr/w:b]', namespaces=CONVERT.NS)), 1)
        self.assertEqual(len(p.xpath('.//w:fldChar', namespaces=CONVERT.NS)), 3)

    def test_combined_citation_expands_to_adjacent_ref_fields(self) -> None:
        p = etree.fromstring(
            b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:r><w:t>Text [1,2]</w:t></w:r></w:p>'
        )
        pattern = re.compile(r"\[(?:\d+(?:\s*-\s*\d+)?)(?:\s*[,;]\s*\d+(?:\s*-\s*\d+)?)*\]")
        changed, unsupported = CONVERT.rebuild_paragraph_with_fields(p, pattern, {1: 1, 2: 2})
        refs = "".join(p.xpath(".//w:instrText/text()", namespaces=CONVERT.NS))
        self.assertTrue(changed)
        self.assertFalse(unsupported)
        self.assertIn("Text ", CONVERT.para_text(p))
        self.assertEqual(refs.count("REF Ref_001"), 1)
        self.assertEqual(refs.count("REF Ref_002"), 1)

    def test_removed_object_relationship_removes_word_object_markup(self) -> None:
        data = (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            b'xmlns:o="urn:schemas-microsoft-com:office:office"><w:body><w:p><w:object>'
            b'<o:OLEObject r:id="rId9"/></w:object></w:p></w:body></w:document>'
        )
        cleaned = SCRUB.scrub_word_xml(data, accept_revisions=True, remove_hidden_text=True, removed_ids={"rId9"})
        root = etree.fromstring(cleaned)
        self.assertEqual(len(root.xpath('.//w:object', namespaces={"w": SCRUB.W_NS})), 0)

    def test_reference_paragraph_indent_is_compact(self) -> None:
        ppr = etree.fromstring(
            b'<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:tabs><w:tab w:val="left" w:pos="1440"/></w:tabs>'
            b'<w:ind w:left="1440" w:hanging="1440"/>'
            b'</w:pPr>'
        )
        p = CONVERT.make_ref_para("Example reference", ppr, None)
        ind = p.find("w:pPr/w:ind", namespaces=CONVERT.NS)
        tab = p.find("w:pPr/w:tabs/w:tab", namespaces=CONVERT.NS)
        self.assertEqual(ind.get(CONVERT.qn("left")), "420")
        self.assertEqual(ind.get(CONVERT.qn("hanging")), "420")
        self.assertEqual(tab.get(CONVERT.qn("pos")), "420")

    def test_markdown_audit_flags_ai_style_and_uncited_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "draft.md"
            md.write_text(
                "# 题目\n\n"
                "这不是简单检测，而是系统分析——需要说明。博士研究生论文引用了研究[1]。\n\n"
                "## 参考文献\n\n"
                "[1] A. First paper.\n"
                "[2] B. Unused paper.\n",
                encoding="utf-8",
            )
            report = AUDIT_MD.audit(md, "博士", "参考文献")
        self.assertIn(2, report["uncited_reference_numbers"])
        self.assertTrue(report["ai_style_findings"]["not_x_but_y"])
        self.assertTrue(report["ai_style_findings"]["em_dash"])
        self.assertIn("uncited_reference_numbers", AUDIT_MD.strict_failures(report))

    def test_docx_audit_flags_plain_citation_and_unused_reference(self) -> None:
        document_xml = (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body>'
            b'<w:p><w:r><w:t>Body citation [1].</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Reference heading</w:t></w:r></w:p>'
            b'<w:p><w:pPr><w:ind w:left="1440" w:hanging="1440"/></w:pPr><w:r><w:t>[1] Used.</w:t></w:r></w:p>'
            b'<w:p><w:pPr><w:ind w:left="1440" w:hanging="1440"/></w:pPr><w:r><w:t>[2] Unused.</w:t></w:r></w:p>'
            b'</w:body></w:document>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "report.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("word/document.xml", document_xml)
            report = AUDIT_DOCX.audit(docx, "Reference heading")
        self.assertEqual(report["plain_citation_numbers"], [1])
        self.assertEqual(report["uncited_reference_numbers"], [2])
        self.assertEqual(report["reference_indent_issue_count"], 2)
        failures = AUDIT_DOCX.strict_failures(report)
        self.assertIn("plain_citation_count", failures)
        self.assertIn("uncited_reference_numbers", failures)

    def test_docx_audit_checks_cover_title_toc_and_sample_residue(self) -> None:
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>'
            '<w:p><w:r><w:rPr><w:sz w:val="44"/></w:rPr><w:t>基于超图的 DeFi 漏洞检测研究</w:t></w:r></w:p>'
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
            '<w:p><w:r><w:t>示例图片：请替换为自己的图片</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>参考文献</w:t></w:r></w:p>'
            '</w:body></w:document>'
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "report.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("word/document.xml", document_xml)
            report = AUDIT_DOCX.audit(docx, "参考文献", "基于超图的 DeFi 漏洞检测研究")
        self.assertTrue(report["title_on_cover"])
        self.assertTrue(report["title_large_enough"])
        self.assertEqual(report["toc_field_count"], 1)
        self.assertEqual(report["sample_content_hit_count"], 2)
        self.assertIn("sample_content_hit_count", AUDIT_DOCX.strict_failures(report))

    def test_structure_audit_accepts_numbered_headings_real_toc_and_independent_references(self) -> None:
        document_xml = (
            f'<w:document xmlns:w="{AUDIT_STRUCTURE.W}"><w:body>'
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>Chapter.....1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
            '<w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>Chapter</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:pStyle w:val="2"/></w:pPr><w:r><w:t>Section</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>&#22270;&#30446;</w:t></w:r></w:p>'
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText> TOC \\h \\z \\c "&#22270;" </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
            '<w:p><w:r><w:t>Reference heading</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            '<w:r><w:t>[1] Used.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        ).encode("utf-8")
        styles_xml = (
            f'<w:styles xmlns:w="{AUDIT_STRUCTURE.W}">'
            '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/>'
            '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/>'
            '<w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr></w:pPr></w:style>'
            '</w:styles>'
        ).encode("utf-8")
        numbering_xml = (
            f'<w:numbering xmlns:w="{AUDIT_STRUCTURE.W}">'
            '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:lvlText w:val="[%1]"/></w:lvl></w:abstractNum>'
            '<w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:lvlText w:val="%1."/></w:lvl>'
            '<w:lvl w:ilvl="1"><w:lvlText w:val="%1.%2"/></w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>'
            '</w:numbering>'
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "report.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("word/document.xml", document_xml)
                zf.writestr("word/styles.xml", styles_xml)
                zf.writestr("word/numbering.xml", numbering_xml)
            report = AUDIT_STRUCTURE.audit(docx, ref_heading="Reference heading")
        self.assertEqual(report["heading_numbering"]["heading2_resolved_ilvls"], ["1"])
        self.assertTrue(report["toc"]["main_toc_field_found"])
        self.assertFalse(report["toc"]["toc_is_static_only"])
        self.assertTrue(report["reference_numbering"]["reference_independent_from_heading"])
        self.assertEqual(AUDIT_STRUCTURE.strict_failures(report), [])

    def test_structure_audit_rejects_static_toc_without_word_field(self) -> None:
        document_xml = (
            f'<w:document xmlns:w="{AUDIT_STRUCTURE.W}"><w:body>'
            '<w:p><w:r><w:t>&#30446;&#24405;</w:t></w:r></w:p>'
            '<w:p><w:hyperlink><w:r><w:t>Chapter.....1</w:t></w:r></w:hyperlink></w:p>'
            '</w:body></w:document>'
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "report.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("word/document.xml", document_xml)
            report = AUDIT_STRUCTURE.audit(docx)
        failures = AUDIT_STRUCTURE.strict_failures(report)
        self.assertIn("main_toc_field_found", failures)
        self.assertIn("toc_is_static_only", failures)


if __name__ == "__main__":
    unittest.main()
