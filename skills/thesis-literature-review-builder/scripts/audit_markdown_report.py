#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEGREE_TERMS = {
    "本科": ["本科", "学士", "毕业设计"],
    "硕士": ["硕士", "硕士研究生"],
    "博士": ["博士", "博士研究生"],
}

PLACEHOLDER_PATTERNS = {
    "template_research_prompt": re.compile(r"\*{0,2}研究目标与研究内容、关键科学问题\*{0,2}"),
    "template_content_note": re.compile(r"\*{0,2}（下面分别介绍每个研究内容）\*{0,2}"),
    "please_fill_here": re.compile(r"请在此处|请在此|此处插入"),
    "sample_or_template_text": re.compile(r"模板示例|样例内容|示例图片|示例图"),
    "todo_unverified": re.compile(r"TODO:|待核验"),
}

RESEARCH_ITEM_PATTERNS = {
    "objective": re.compile(r"(?:^|\n)\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\s*)?(?:研究)?目标[一二三四五六七八九十0-9]+"),
    "content": re.compile(r"(?:^|\n)\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\s*)?研究内容[一二三四五六七八九十0-9]+"),
    "scheme": re.compile(r"(?:^|\n)\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\s*)?(?:研究)?(?:方案|方法)[一二三四五六七八九十0-9]+"),
}


def split_body_and_refs(text: str, ref_heading: str) -> tuple[str, str]:
    pattern = re.compile(rf"^\s*#+\s*{re.escape(ref_heading)}\s*$|^\s*{re.escape(ref_heading)}\s*$", re.M)
    match = pattern.search(text)
    if not match:
        return text, ""
    return text[: match.start()], text[match.end() :]


def line_col(text: str, pos: int) -> str:
    line = text.count("\n", 0, pos) + 1
    col = pos - text.rfind("\n", 0, pos)
    return f"{line}:{col}"


def examples(pattern: re.Pattern, text: str, limit: int = 8) -> list[dict[str, str]]:
    out = []
    for match in pattern.finditer(text):
        snippet = re.sub(r"\s+", " ", match.group(0)).strip()
        out.append({"at": line_col(text, match.start()), "text": snippet[:120]})
        if len(out) >= limit:
            break
    return out


def citation_numbers(text: str) -> set[int]:
    nums: set[int] = set()
    for match in re.finditer(r"\[(\d+(?:\s*[-,;，、]\s*\d+)*)\]", text):
        for raw in re.findall(r"\d+", match.group(1)):
            nums.add(int(raw))
    return nums


def reference_numbers(refs: str) -> set[int]:
    nums: set[int] = set()
    for match in re.finditer(r"(?m)^\s*\[(\d+)\]\s+\S+", refs):
        nums.add(int(match.group(1)))
    return nums


def research_item_alignment(body: str, expected: int | None) -> dict:
    counts = {name: len(pattern.findall(body)) for name, pattern in RESEARCH_ITEM_PATTERNS.items()}
    mismatches = {}
    if expected is not None:
        mismatches = {name: count for name, count in counts.items() if count != expected}
    return {"expected": expected, "counts": counts, "mismatches": mismatches}


def audit(path: Path, degree: str | None, ref_heading: str, expected_research_items: int | None = None) -> dict:
    text = path.read_text(encoding="utf-8")
    body, refs = split_body_and_refs(text, ref_heading)

    ai_patterns = {
        "not_x_but_y": re.compile(r"不是[^。\n]{0,40}而是"),
        "em_dash": re.compile(r"——"),
        "short_parenthetical_explanations": re.compile(r"[\(（][^()\n（）]{1,18}[\)）]"),
    }
    body_citations = citation_numbers(body)
    ref_nums = reference_numbers(refs)

    degree_conflicts: list[str] = []
    degree_missing = False
    if degree and degree != "其他":
        expected_terms = DEGREE_TERMS[degree]
        if not any(term in text for term in expected_terms):
            degree_missing = True
        for other_degree, terms in DEGREE_TERMS.items():
            if other_degree == degree:
                continue
            for term in terms:
                if term in text:
                    degree_conflicts.append(term)

    return {
        "path": str(path),
        "degree": degree,
        "degree_missing": degree_missing,
        "degree_conflicts": sorted(set(degree_conflicts)),
        "citation_count": len(body_citations),
        "reference_count": len(ref_nums),
        "uncited_reference_numbers": sorted(ref_nums - body_citations),
        "missing_reference_numbers": sorted(body_citations - ref_nums),
        "placeholder_findings": {
            name: examples(pattern, body)
            for name, pattern in PLACEHOLDER_PATTERNS.items()
        },
        "research_item_alignment": research_item_alignment(body, expected_research_items),
        "ai_style_findings": {
            name: examples(pattern, body)
            for name, pattern in ai_patterns.items()
        },
    }


def strict_failures(report: dict) -> list[str]:
    failures = []
    if report["degree_conflicts"]:
        failures.append("degree_conflicts")
    if report["missing_reference_numbers"]:
        failures.append("missing_reference_numbers")
    if report["uncited_reference_numbers"]:
        failures.append("uncited_reference_numbers")
    if any(report["placeholder_findings"].values()):
        failures.append("placeholder_findings")
    if report["research_item_alignment"]["mismatches"]:
        failures.append("research_item_alignment")
    ai = report["ai_style_findings"]
    if ai["not_x_but_y"]:
        failures.append("not_x_but_y")
    if ai["em_dash"]:
        failures.append("em_dash")
    if len(ai["short_parenthetical_explanations"]) > 8:
        failures.append("too_many_parenthetical_explanations")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a thesis Markdown draft before DOCX conversion.")
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--degree", choices=["本科", "硕士", "博士", "其他"])
    parser.add_argument("--ref-heading", default="参考文献")
    parser.add_argument("--expect-research-items", type=int, help="Expected one-to-one count for proposal objectives, contents, and schemes/methods.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = audit(args.markdown, args.degree, args.ref_heading, args.expect_research_items)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    if args.strict and strict_failures(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
