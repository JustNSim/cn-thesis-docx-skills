---
name: thesis-proposal-report-builder
description: Build Chinese undergraduate or graduate thesis/design proposal or opening reports from a user's research introduction, requirements, references, and optional DOCX template. Use when creating or revising 中文开题报告, 毕业论文开题报告, 毕业设计开题报告, research proposal report, opening report, technical route, feasibility analysis, schedule plan, expected contributions, template-faithful Word/DOCX proposal documents, numbered citations, reference lists, Word cross-references, superscript citations, or DOCX layout validation for a proposal.
---

# Thesis Proposal Report Builder

## Core Use

Use this skill to turn a user's research introduction document into a Chinese university thesis/design proposal or opening report, with Markdown drafting and template-faithful DOCX output.

The proposal should emphasize:

- research background and significance;
- domestic and international research status;
- research objectives and contents;
- technical route and methods;
- feasibility analysis;
- schedule, expected outcomes, and references.

## Required Decisions

Ask only when the user has not already specified a high-impact choice:

- whether to use the user's DOCX template or the bundled base template;
- whether the user needs only Markdown, only DOCX, or both;
- research title, research object, research-content boundaries, and contribution ownership;
- timeline assumptions and real milestone dates;
- citation style and whether numbering must follow first appearance.

Proceed with reasonable defaults for minor typography and file naming.

## Workflow

1. **Read inputs**
   - Research introduction, requirements, previous drafts, personal papers, references, figures, and optional template.
   - If using the bundled template, prefer `assets/base-templates/proposal-template.docx`.

2. **Confirm proposal frame**
   - Resolve the title, research object, problem definition, research contents, and expected contribution boundaries.
   - Keep the proposal distinct from the literature review: summarize related work only as needed to support problem definition and feasibility.

3. **Plan the outline**
   - Use the user's template if supplied.
   - Otherwise use a structure like: background/significance; domestic/foreign status; objectives and contents; technical route; feasibility; schedule; expected outcomes; references.
   - Use clear subsection titles for each research content and method.

4. **Draft Markdown first**
   - Produce `outputs/proposal.md` unless the user requests another path.
   - Add figure placeholders for research framework, technical route, data/evaluation scheme, and schedule if useful.
   - Mark unverified claims as `TODO: 待核验`.

5. **Finalize references**
   - Verify references when external lookup is available or when the user requests it.
   - Do not fabricate authors, years, venues, page numbers, DOI, URLs, or experimental claims.
   - Deduplicate by normalized title, DOI, arXiv ID, or URL.
   - Number by first appearance unless the required style says otherwise.

6. **Build and validate DOCX**
   - Work on a copy of the template.
   - Preserve template styles, section settings, headers/footers, TOC fields, and heading levels.
   - Convert citations to Word REF fields when renumbering may be needed.
   - Run `inspect_docx_template.py <output> --strict` and `audit_docx_report.py <output> --strict` before delivery.
   - Update fields and TOC in Word or LibreOffice, then render and inspect pages. If field update or visual inspection is unavailable, report that limitation instead of claiming layout validation.

## Figure And Table Guidance

- When the user asks for figure support, provide the figure title, recommended placement, key elements, and an optional drawing prompt. Do not generate images unless the current agent environment explicitly supports image generation and the user requests it.
- Use concise, formal noun-phrase captions for tables and figures. Avoid sentence-style captions such as "介绍了...", "展示了...", "说明了...", or "分析了...".
- Prefer captions like "研究内容与技术路线", "研究计划安排", or "实验数据与评价指标".

## References To Load

- Read `references/docx-crossrefs.md` before modifying numbered references, Word fields, superscript citations, or bibliography order.
- Read `references/template-policy.md` before using, anonymizing, or publishing bundled templates.

## Bundled Scripts

- `scripts/inspect_docx_template.py`: audit template metadata, comments, tracked changes, hidden text, sensitive text hits, and external relationships.
- `scripts/privacy_scrub_template.py`: scrub DOCX templates before public release.
- `scripts/audit_docx_report.py`: inspect bibliography paragraphs, citation fields, superscript state, duplicate brackets, and bookmarks.
- `scripts/convert_refs_to_crossrefs.py`: convert plain numeric citations and bibliography entries into Word REF fields and automatic `[n]` reference numbering.

The converter only accepts standalone `[n]` citations contained in a simple text run. It intentionally rejects combined/range citations and citations in rich-text structures so that it never silently loses formatting.

Install Python script dependencies when needed:

```bash
python -m pip install -r scripts/requirements.txt
```

## Output Defaults

- `outputs/proposal.md`
- `outputs/proposal.docx`

Chinese-only projects may use `outputs/开题报告.md` and `outputs/开题报告.docx` when that better matches the user's existing files.
