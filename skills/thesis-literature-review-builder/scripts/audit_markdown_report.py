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


def audit(path: Path, degree: str | None, ref_heading: str) -> dict:
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
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = audit(args.markdown, args.degree, args.ref_heading)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    if args.strict and strict_failures(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
