# DOCX Citations, References, And Cross-References

## Goal

Keep in-text citations automatically updateable while preserving the expected display form, usually superscript numeric citations such as `[1]`.

## Recommended Representation

Use this model for Word-native citation numbering:

1. Reference list paragraphs use an automatic numbered list whose number format is `[%1]`.
2. Each reference paragraph has a stable bookmark, such as `Ref_001`, `Ref_002`, etc.
3. In-text citations are Word `REF` fields pointing to the bookmark.
4. The displayed field result is superscript.
5. Field codes include `\* MERGEFORMAT` when direct superscript formatting is used.

## Critical Bracket Rule

Do not wrap a `REF` field in literal square brackets if the referenced bibliography list number already includes brackets.

Bad pattern:

- reference list number format: `[%1]`
- in-text text: literal `[` + `REF Ref_001` + literal `]`
- after field update: `[[1]]`

Good pattern:

- reference list number format: `[%1]`
- in-text text: `REF Ref_001`
- after field update: `[1]`

## Superscript Rule

Apply superscript to every run that belongs to the citation field result and, when practical, to the field-code run with `w:vertAlign w:val="superscript"`.

Audit for:

- `REF` fields that are not superscript;
- citation fields that display normal baseline text;
- field updates that strip superscript because `MERGEFORMAT` was omitted.

## Inserting New References

When adding references to an existing DOCX:

1. Extract all in-text citations and current bibliography entries.
2. Insert new citation markers at semantically appropriate locations.
3. Build an ordered first-appearance list.
4. Deduplicate references before assigning final numbers.
5. Rewrite the reference list in that order.
6. Recreate or update bookmarks.
7. Update fields and TOC.
8. Audit for duplicate brackets, missing bookmarks, stale numbers, and bibliography entries with no line break.

## Bibliography Formatting Pitfalls

Check these issues explicitly:

- all references collapsed into one paragraph;
- missing paragraph break between entries;
- copied references with inconsistent punctuation or full-width/half-width symbols;
- duplicate references differing only by spaces, punctuation, DOI case, or URL suffix;
- references cited in text but absent from bibliography;
- bibliography entries present but never cited, if the style requires cited-only references.

## Field Update Notes

Prefer a Word automation update when available:

- update all fields in the main story, headers, footers, footnotes, textboxes, and TOC;
- save after field update;
- reopen or audit the DOCX to ensure fields persisted.

If Word automation is unavailable, update fields using the best available DOCX tooling and tell the user what could not be verified.
