from __future__ import annotations

import importlib.util
from pathlib import Path

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "skills" / "thesis-literature-review-builder" / "scripts" / "audit_docx_report.py"
CONVERTER_PATH = ROOT / "skills" / "thesis-literature-review-builder" / "scripts" / "convert_refs_to_crossrefs.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


audit = load_module("audit_docx_report", AUDIT_PATH)
converter = load_module("convert_refs_to_crossrefs", CONVERTER_PATH)
W = audit.W


def xml(fragment: str):
    return etree.fromstring(fragment.format(w=W).encode())


def test_cover_title_ignores_paragraph_mark_size():
    paragraph = xml(
        '<w:p xmlns:w="{w}"><w:pPr><w:rPr><w:sz w:val="64"/></w:rPr></w:pPr>'
        '<w:r><w:t>测试标题</w:t></w:r></w:p>'
    )
    styles_xml = (
        f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>'
    ).encode()
    report = audit.title_report([paragraph], "测试标题", audit.style_context(styles_xml))
    assert report["title_max_half_points"] == 22
    assert report["title_large_enough"] is False


def test_cover_title_accepts_explicit_large_run_size():
    paragraph = xml(
        '<w:p xmlns:w="{w}"><w:r><w:rPr><w:sz w:val="64"/></w:rPr>'
        '<w:t>测试标题</w:t></w:r></w:p>'
    )
    report = audit.title_report([paragraph], "测试标题", audit.style_context(None))
    assert report["title_min_half_points"] == 64
    assert report["title_unresolved_run_count"] == 0
    assert report["title_large_enough"] is True


def test_reference_indent_above_540_is_rejected():
    paragraph = xml(
        '<w:p xmlns:w="{w}"><w:pPr><w:ind w:left="600" w:hanging="600"/></w:pPr>'
        '<w:r><w:t>Reference</w:t></w:r></w:p>'
    )
    assert audit.reference_indent_issues([paragraph], {})


def test_embedded_single_citation_is_converted():
    paragraph = xml('<w:p xmlns:w="{w}"><w:r><w:t>GenProg[1]以来</w:t></w:r></w:p>')
    changed, unsupported = converter.rebuild_paragraph_with_fields(
        paragraph, converter.re.compile(r"\[(\d+)\]"), {1: 1}
    )
    assert changed is True
    assert unsupported is False
    assert "GenProg" in converter.para_text(paragraph)
    assert "以来" in converter.para_text(paragraph)
    assert "REF Ref_001" in "".join(paragraph.xpath(".//w:instrText/text()", namespaces=converter.NS))


def test_combined_citation_expands_to_adjacent_ref_fields():
    paragraph = xml('<w:p xmlns:w="{w}"><w:r><w:t>相关研究[1,2]表明</w:t></w:r></w:p>')
    changed, unsupported = converter.rebuild_paragraph_with_fields(
        paragraph,
        converter.re.compile(r"\[(?:\d+(?:\s*[-–—]\s*\d+)?)(?:\s*[,;，、]\s*\d+(?:\s*[-–—]\s*\d+)?)*\]"),
        {1: 1, 2: 2},
    )
    refs = "".join(paragraph.xpath(".//w:instrText/text()", namespaces=converter.NS))
    assert changed is True
    assert unsupported is False
    assert "相关研究" in converter.para_text(paragraph)
    assert "表明" in converter.para_text(paragraph)
    assert refs.count("REF Ref_001") == 1
    assert refs.count("REF Ref_002") == 1


def test_range_citation_expands_to_adjacent_ref_fields():
    paragraph = xml('<w:p xmlns:w="{w}"><w:r><w:t>已有方法[1-3]仍存在不足</w:t></w:r></w:p>')
    changed, unsupported = converter.rebuild_paragraph_with_fields(
        paragraph,
        converter.re.compile(r"\[(?:\d+(?:\s*[-–—]\s*\d+)?)(?:\s*[,;，、]\s*\d+(?:\s*[-–—]\s*\d+)?)*\]"),
        {1: 1, 2: 2, 3: 3},
    )
    refs = "".join(paragraph.xpath(".//w:instrText/text()", namespaces=converter.NS))
    assert changed is True
    assert unsupported is False
    assert refs.count("REF Ref_001") == 1
    assert refs.count("REF Ref_002") == 1
    assert refs.count("REF Ref_003") == 1


def test_adjacent_citations_are_all_converted():
    paragraph = xml('<w:p xmlns:w="{w}"><w:r><w:t>已有方法[1][2][3]仍存在不足</w:t></w:r></w:p>')
    changed, unsupported = converter.rebuild_paragraph_with_fields(
        paragraph,
        converter.re.compile(r"\[(?:\d+(?:\s*[-–—]\s*\d+)?)(?:\s*[,;，、]\s*\d+(?:\s*[-–—]\s*\d+)?)*\]"),
        {1: 1, 2: 2, 3: 3},
    )
    refs = "".join(paragraph.xpath(".//w:instrText/text()", namespaces=converter.NS))
    assert changed is True
    assert unsupported is False
    assert refs.count("REF Ref_001") == 1
    assert refs.count("REF Ref_002") == 1
    assert refs.count("REF Ref_003") == 1


def test_combined_citation_with_missing_reference_is_rejected():
    paragraph = xml('<w:p xmlns:w="{w}"><w:r><w:t>相关研究[1,4]表明</w:t></w:r></w:p>')
    changed, unsupported = converter.rebuild_paragraph_with_fields(
        paragraph,
        converter.re.compile(r"\[(?:\d+(?:\s*[-–—]\s*\d+)?)(?:\s*[,;，、]\s*\d+(?:\s*[-–—]\s*\d+)?)*\]"),
        {1: 1},
    )
    assert changed is False
    assert unsupported is True
    assert not paragraph.xpath(".//w:instrText/text()", namespaces=converter.NS)


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"{len(tests)} safety-gate tests passed")
