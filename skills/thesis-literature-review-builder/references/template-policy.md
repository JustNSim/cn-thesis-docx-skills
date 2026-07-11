# Template Policy

## Template Modes

Use one of two modes:

1. **User template mode**
   - Treat the user's DOCX as authoritative for style, heading hierarchy, margins, cover pages, headers/footers, TOC, captions, and page numbering.
   - Work on a copy of the template.
   - Leave personal cover fields blank if requested.

2. **Base template mode**
   - Use `assets/base-templates/literature-review-template.docx`.
   - The bundled template must not contain real school, college, major, student, supervisor, project, or confidential information.
   - Identifying labels should use neutral placeholders such as `XX University`, `XX College`, `XX Major`, `Student Name`, and `Supervisor`.

Ask the user to choose between user template mode and base template mode before producing DOCX output.

## Public Release Requirements

Before publishing a bundled template:

- remove document properties that expose author, organization, path, revision history, comments, or hidden text;
- inspect headers, footers, watermarks, custom XML, embedded objects, and alt text;
- replace school/college/profession-specific labels with generic placeholders;
- run `scripts/privacy_scrub_template.py` and then `scripts/inspect_docx_template.py` before release;
- ensure the template can be used legally and ethically as a generic academic-document skeleton;
- keep templates editable rather than screenshot-based.

## Style Preservation Rules

When generating DOCX:

- use existing heading styles instead of manual font sizes where possible;
- preserve section breaks, page setup, headers/footers, and TOC fields;
- do not flatten the document into images;
- do not overwrite the user's original template;
- create a timestamped backup before risky structural rewrites.
