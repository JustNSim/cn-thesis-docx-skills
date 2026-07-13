# Template Policy

## Template Modes

Use one of two modes:

1. **User template mode**
   - Treat the user's DOCX as authoritative for style, heading hierarchy, margins, cover pages, headers/footers, TOC, captions, and page numbering.
   - Work on a copy of the template.
   - Leave personal cover fields blank if requested.

2. **Base template mode**
   - Use `assets/base-templates/proposal-template.docx`.
   - The bundled template must not contain real school, college, major, student, supervisor, project, or confidential information.
   - Identifying labels should use neutral placeholders such as `XX University`, `XX College`, `XX Major`, `Student Name`, and `Supervisor`.

Ask the user to choose between user template mode and base template mode before producing DOCX output.

## Public Release Requirements

Before publishing a bundled template:

- remove document properties that expose author, organization, path, revision history, comments, or hidden text;
- inspect headers, footers, watermarks, custom XML, embedded objects, and alt text;
- replace school/college/profession-specific labels with generic placeholders;
- run `scripts/privacy_scrub_template.py input.docx output.docx` and then `scripts/inspect_docx_template.py output.docx --strict` before release;
- ensure the template can be used legally and ethically as a generic academic-document skeleton;
- keep templates editable rather than screenshot-based.

## Style Preservation Rules

When generating DOCX:

- use existing heading styles instead of manual font sizes where possible;
- write the thesis title into the template's cover title position. Preserve the large cover-title paragraph or content-control style; do not create a normal body heading as the title substitute;
- when replacing cover-title runs, clone the original non-empty title run's `w:rPr`, including `w:sz`/`w:szCs`, onto the new run. Do not assume `w:pPr/w:rPr` cascades to text runs; it formats the paragraph mark and can make an XML-only size check look correct while the visible title falls back to the Normal style;
- replace mapped content slots in place. Remove body sample content, sample pictures, sample captions, and example tables when they do not match the user's topic;
- before updating TOC/table-of-figures/table-of-tables fields, remove stale static list entries and old field results from template placeholders. A generated list line must contain one entry only, not an updated blue field result followed by the old black `图 1 ...` or `表 1 ...` text in the same paragraph;
- preserve section breaks, page setup, headers/footers, and TOC fields;
- update the table of contents after headings and page breaks change. If Word or LibreOffice is unavailable, set fields to update on open and report that the TOC was not visually verified;
- do not flatten the document into images;
- do not overwrite the user's original template;
- create a timestamped backup before risky structural rewrites.
