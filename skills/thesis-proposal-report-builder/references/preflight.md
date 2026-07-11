# Proposal DOCX Preflight

Resolve and record these fields before drafting or creating DOCX.

1. **Template mode**: user template with path; bundled base template; or Markdown only. If the user already chose one, acknowledge it rather than asking again.
2. **Word-count target**: minimum/maximum or target count, and whether cover, TOC, references, captions, and tables are excluded. Do not invent a target.
3. **Numbering owner**: use template numbering by default. Manual Chinese/Arabic prefixes are forbidden when a template heading style already renders numbering.
4. **Output scope**: Markdown, DOCX, or both; and the requested filenames.

When fields 1 or 2 are absent, ask one short question, for example: “请确认使用哪种模板（你的 DOCX / 内置 base template / 仅 Markdown），并给出正文目标字数或区间；参考文献、目录和封面是否计入？”

For DOCX, copy the selected template, map content to existing slots, and preserve all non-slot package content. A template choice does not authorize reconstructing the document from a blank body.
