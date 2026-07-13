# Proposal Report Workflow

## Main Purpose

Produce a Chinese undergraduate or graduate thesis/design proposal or opening report from a research introduction document and optional DOCX template.

## Suggested Structure

1. Research background and significance
2. Domestic and international research status
3. Research objectives and contents
4. Technical route and methods
5. Feasibility analysis
6. Schedule
7. Expected outcomes
8. References

Adjust the structure to the user's institutional template when one is supplied.

## Writing Focus

- Make the problem definition explicit.
- Keep research contents parallel and non-overlapping.
- Keep research objectives, research contents, and research schemes/methods aligned one-to-one. If there are three research contents, normally write three corresponding objectives and three corresponding scheme/method subsections in the same order.
- Connect each research content to a method, validation plan, and expected outcome.
- Use related work to justify the research gap rather than writing a full literature review.
- Ask for real schedule dates when the user has not provided them.
- Follow `numbering-style.md` for non-heading numbered points: `（一）` for standalone lead points, `（1）` for lower-level body items, and `a.` for short third-level details.

## DOCX Focus

- Preserve the user's template hierarchy and heading styles.
- After DOCX conversion, compare heading names and levels against the Markdown source with `compare_md_docx_headings.py`.
- Keep Chinese academic style formal and concise.
- Use technical route figures and schedule tables only when they improve readability.
- Use Word cross-references for citations when the bibliography may be updated later.
