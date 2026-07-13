---
name: thesis-literature-review-builder
description: Build Chinese undergraduate or graduate thesis/design literature review reports from a user's research introduction, requirements, references, and optional DOCX template. Use when creating or revising 中文文献综述, 毕业论文文献综述, 毕业设计文献综述, 研究现状综述, related work review, template-faithful Word/DOCX literature review documents, numbered citations, reference lists, Word cross-references, superscript citations, or DOCX layout validation for a literature review.
---

# Thesis Literature Review Builder

## Core Use

Use this skill to turn a user's research introduction document into a Chinese university thesis/design literature review, with Markdown drafting and template-faithful DOCX output.

The literature review should emphasize:

- research direction overview;
- domestic and international research status;
- method categories and technical lineage;
- limitations, trends, and summary analysis;
- verified references and correctly numbered citations.

## Required Decisions

Ask only when the user has not already specified a high-impact choice:

- whether to use the user's DOCX template or the bundled base template;
- whether the user needs only Markdown, only DOCX, or both;
- degree level: `本科`, `硕士`, `博士`, or `其他`;
- research title, research object, and review scope;
- citation style and whether numbering must follow first appearance;
- whether references should be retrieved, verified, or only formatted from a provided list.

Proceed with reasonable defaults for minor typography and file naming.

## DOCX Preflight Gate

Before drafting Markdown or creating DOCX, read `references/preflight.md` and resolve its required fields. Do not draft Markdown until degree level is recorded. Do not create a DOCX until template mode, word-count target, and degree level are recorded.

If the user explicitly requests the bundled base template or supplies a template path, acknowledge that choice and do not ask it again. If template mode, word-count target, or degree level is missing, ask one concise preflight question before continuing.

## Workflow

1. **Read inputs**
   - Research introduction, topic description, requirements, previous drafts, references, and optional template.
   - If using the bundled template, prefer `assets/base-templates/literature-review-template.docx`.

2. **Confirm review frame**
   - Identify the research object, review boundary, subfields, and key problem chain.
   - Keep the literature review distinct from the proposal: write research status and gaps, not a full implementation plan.

3. **Plan the outline**
   - Use the user's template if supplied.
   - Otherwise use a structure like: research direction overview; domestic/foreign research status; research status summary and analysis; references.
   - Use third-level headings when method categories need internal comparison.
   - When the template provides heading numbering, write semantic heading text only. Do not prepend manual Chinese or Arabic numbers such as `一、`, `1.`, or `2.1`; let the template's numbering definitions render them.

4. **Draft Markdown first**
   - Produce `outputs/literature-review.md` unless the user requests another path.
   - Add figure placeholders with suggested source, content, and placement.
   - Mark unverified claims as `TODO: 待核验`.
   - Avoid formulaic AI-sounding patterns such as `不是...而是...`, long dashes, and short parenthetical explanations when a normal sentence can explain the term.
   - Run `audit_markdown_report.py <draft.md> --degree <本科|硕士|博士|其他> --strict`; revise until degree alignment, citations, references, and style findings pass.

5. **Finalize references**
   - Verify references when external lookup is available or when the user requests it.
   - Do not fabricate authors, years, venues, page numbers, DOI, URLs, or experimental claims.
   - Deduplicate by normalized title, DOI, arXiv ID, or URL.
   - Number by first appearance unless the required style says otherwise.
   - Every numbered reference must be cited in the body. Add a semantically relevant citation or remove the unused reference.

6. **Build and validate DOCX**
   - Work on a copy of the template.
   - Edit mapped template slots in place. Never delete the template body and rebuild it with generic `Heading 1`, `Heading 2`, `Title`, `Normal`, or list styles.
   - Put the thesis title into the cover's existing large title position. Preserve that paragraph, table-cell, or content-control style; do not place the title only as a normal body heading.
   - Remove unrelated sample body content from the template, including sample images, captions, example tables, and placeholder paragraphs. Keep only fixed template chrome such as cover labels, TOC, headers, footers, and required structural pages.
   - Preserve the cover, TOC, section breaks, headers, footers, page-number fields, and template styles unless the user explicitly requests their removal.
   - Do not apply blanket run-level font or size overrides. Use the template's existing paragraph and character styles.
   - Preserve template styles, section settings, headers/footers, TOC fields, and heading levels.
   - Convert citations to Word REF fields when renumbering may be needed.
   - Keep in-text citations as superscript Word `REF` fields, not plain baseline text.
   - Keep reference-list hanging indent compact so continuation lines align near the text after `[n]`.
   - Update all fields and the TOC in Word or LibreOffice after headings and page breaks change.
   - Run `inspect_docx_template.py <output> --strict` and `audit_docx_report.py <output> --title "<论文题目>" --strict` before delivery.
   - Read the audit metrics, not only its exit code. Require a valid large cover title, at least one superscript `REF` field when references exist, no plain citations, complete bibliography/bookmark and field/bookmark mappings, no uncited or missing references, no duplicated figure/table-list entries, and zero indent, duplicate-reference, or field-error findings. See `references/quality-gates.md` for the exact checklist.
   - Render and inspect pages. If field update or visual inspection is unavailable, report that limitation instead of claiming layout validation.

## Figure And Table Guidance

- When the user asks for figure support, provide the figure title, recommended placement, key elements, and an optional drawing prompt. Do not generate images unless the current agent environment explicitly supports image generation and the user requests it.
- Use concise, formal noun-phrase captions for tables and figures. Avoid sentence-style captions such as "介绍了...", "展示了...", "说明了...", or "分析了...".
- Prefer captions like "智能合约漏洞检测方法分类", "代表性研究工作对比", or "DeFi 漏洞检测技术谱系".

## References To Load

- Read `references/preflight.md` before drafting or creating DOCX.
- Read `references/quality-gates.md` before delivering Markdown or DOCX.
- Read `references/docx-crossrefs.md` before modifying numbered references, Word fields, superscript citations, or bibliography order.
- Read `references/template-policy.md` before using, anonymizing, or publishing bundled templates.

## Bundled Scripts

- `scripts/inspect_docx_template.py`: audit template metadata, comments, tracked changes, hidden text, sensitive text hits, and external relationships.
- `scripts/privacy_scrub_template.py`: scrub DOCX templates before public release.
- `scripts/audit_markdown_report.py`: inspect Markdown drafts for degree alignment, citation/reference coverage, and common AI-sounding wording patterns.
- `scripts/audit_docx_report.py`: inspect bibliography paragraphs, citation fields, superscript state, duplicate brackets, and bookmarks.
- `scripts/convert_refs_to_crossrefs.py`: convert plain numeric citations and bibliography entries into Word REF fields and automatic `[n]` reference numbering.

The converter accepts numeric citations anywhere inside a simple text run, including forms such as `GenProg[1]以来`, `[1,2]`, `[1-3]`, and `[1][2][3]`. Combined and range citations are expanded into adjacent superscript `REF` fields, e.g. `[1][2][3]`. It intentionally rejects citations in complex rich-text structures, missing-reference citations, and oversized ranges so that it never silently loses formatting.

Install Python script dependencies when needed:

```bash
python -m pip install -r scripts/requirements.txt
```

## Output Defaults

- `outputs/literature-review.md`
- `outputs/literature-review.docx`

Chinese-only projects may use `outputs/文献综述.md` and `outputs/文献综述.docx` when that better matches the user's existing files.
