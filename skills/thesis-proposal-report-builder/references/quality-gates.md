# Quality Gates

Run these gates before delivery. Fix findings before moving to the next artifact.

## Markdown Gate

After drafting Markdown:

1. Check degree alignment against the preflight choice: `本科`, `硕士`, `博士`, or `其他`.
2. Check references and citations. Every numbered reference should be cited in the body, and every body citation should have a matching reference.
3. Reduce formulaic wording. Avoid the pattern `不是...而是...`; replace long dashes with commas, semicolons, or separate sentences; explain terms in normal sentences instead of short parenthetical notes when possible.
4. Run:

```bash
python scripts/audit_markdown_report.py <draft.md> --degree <本科|硕士|博士|其他> --strict
```

Use the JSON output when debugging:

```bash
python scripts/audit_markdown_report.py <draft.md> --degree <本科|硕士|博士|其他> --json
```

## DOCX Gate

After creating DOCX:

1. Ensure the thesis title is written into the cover title position and keeps the template's large title style.
2. Remove unrelated sample body content from the template, including sample images, figure captions, tables, and placeholder paragraphs.
3. Convert plain numeric citations to Word `REF` fields when citations need stable numbering.
4. Ensure in-text citations display as superscript.
5. Ensure reference paragraphs use a compact hanging indent. The second and later lines should align near the reference text start after `[n]`, not far to the right.
6. Update all fields and the table of contents in Word or LibreOffice after headings and page breaks change.
7. Run:

```bash
python scripts/audit_docx_report.py <report.docx> --title "<论文题目>" --strict
```

If the audit reports title, TOC, field error, sample-content, plain citation, uncited reference, non-superscript field, or reference-indent issues, revise the DOCX and rerun the audit.

Do not treat exit code alone as sufficient. Before delivery, confirm all applicable metrics:

- `title_on_cover=True`, `title_large_enough=True`, and `title_unresolved_run_count=0` when `--title` is supplied;
- `ref_field_count > 0` when references exist, `plain_citation_count=0`, and `superscript_ref_fields == ref_field_count`;
- `missing_reference_bookmarks=[]` and `missing_field_bookmarks=[]`;
- `uncited_reference_numbers=[]` and `missing_reference_numbers=[]`;
- `reference_indent_issue_count=0`, `duplicate_reference_count=0`, and `field_error_count=0`.
