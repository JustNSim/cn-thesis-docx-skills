from __future__ import annotations

import importlib.util
import re
import unittest
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


class DocxScriptTests(unittest.TestCase):
    def test_duplicate_skill_scripts_stay_identical(self) -> None:
        for name in ("audit_docx_report.py", "convert_refs_to_crossrefs.py", "inspect_docx_template.py", "privacy_scrub_template.py"):
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

    def test_combined_citation_is_rejected_without_rewriting(self) -> None:
        p = etree.fromstring(
            b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:r><w:t>Text [1,2]</w:t></w:r></w:p>'
        )
        pattern = re.compile(r"\[(?:\d+(?:\s*-\s*\d+)?)(?:\s*[,;]\s*\d+(?:\s*-\s*\d+)?)*\]")
        changed, unsupported = CONVERT.rebuild_paragraph_with_fields(p, pattern, {1: 1, 2: 2})
        self.assertFalse(changed)
        self.assertTrue(unsupported)
        self.assertEqual(CONVERT.para_text(p), "Text [1,2]")

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


if __name__ == "__main__":
    unittest.main()
