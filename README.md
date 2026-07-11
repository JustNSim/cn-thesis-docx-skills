# cn-thesis-docx-skills

用于中文高校本科/研究生毕业论文、毕业设计材料写作的 Agent Skills，重点支持**文献综述**和**开题报告**的草稿生成、DOCX 模板排版、参考文献编号与正文引用处理。

## 适合做什么

- 根据研究介绍生成中文文献综述
- 根据研究介绍生成中文开题报告
- 按用户提供或内置 DOCX 模板排版
- 整理参考文献编号、正文上标引用和 Word 交叉引用
- 检查 DOCX 中的参考文献、引用编号和格式问题

## 包含哪些 Skills

| Skill | 用途 |
| --- | --- |
| `thesis-literature-review-builder` | 文献综述写作与 DOCX 生成 |
| `thesis-proposal-report-builder` | 开题报告写作与 DOCX 生成 |

## 安装

交互式安装：

```bash
npx cn-thesis-docx-skills install
```

也可以指定安装内容、工具和范围：

```bash
npx cn-thesis-docx-skills install --skill review --tool codex --scope global
npx cn-thesis-docx-skills install --skill proposal --tool claude --scope project
npx cn-thesis-docx-skills install --skill all --tool opencode --scope global
```

参数说明：

- `--skill review|proposal|all`：安装文献综述、开题报告或全部
- `--tool codex|claude|opencode|agents|all`：选择目标工具
- `--scope global|project`：安装到全局或当前项目

## 更新

更新已经安装的 Skills：

```bash
npx cn-thesis-docx-skills@latest update
```

该命令会拉取 npm 上的最新版本，并自动查找当前项目与全局目录中已经安装的 Skills，只更新已存在的项目。安装器会记录受管文件；检测到本地修改或旧版手工安装时会停止，避免静默覆盖。确认需要替换时使用 `--force`，原目录会保留同级备份。也可以限定更新范围：

```bash
npx cn-thesis-docx-skills@latest update --skill review --tool codex --scope global
npx cn-thesis-docx-skills@latest update --skill proposal --scope project
```

更新前查看将被覆盖的目录：

```bash
npx cn-thesis-docx-skills@latest update --dry-run
```

如果 Skills 安装在其他项目目录，可增加 `--project-dir <path>`。更新后如未立即生效，请重启或重新加载对应的 Agent。

## DOCX 工具与发布前检查

进入对应 skill 的目录后执行。所有清理操作都应写到新文件，确认通过后再替换源文件。

```bash
# 公开模板：清除元数据、修订、隐藏文字、外部关系和 OLE/ActiveX，再作严格审计
python scripts/privacy_scrub_template.py input.docx output.docx
python scripts/inspect_docx_template.py output.docx --strict

# 最终报告：检查 TODO、重复参考文献、双括号和参考文献段落完整性
python scripts/audit_docx_report.py report.docx --strict

# 仅转换“纯文本 run 内的独立 [n]”引文；组合/范围/富文本引文会明确失败，避免损坏格式
python scripts/convert_refs_to_crossrefs.py input.docx output.docx
```

脚本只负责 OOXML 结构和引文检查。最终交付前仍须在 Word 或 LibreOffice 更新字段和目录，并渲染/逐页检查页码、表格、图片、字体及文字溢出；若环境无法完成该步骤，应明确标记为“未完成视觉验收”。

## 怎么使用

在支持 skills 的 Agent 中，可以这样说：

```text
使用 $thesis-literature-review-builder，根据我的研究介绍和模板生成文献综述。
```

```text
使用 $thesis-proposal-report-builder，根据我的研究介绍和模板生成开题报告。
```

建议先提供：

- 研究主题或研究介绍文档
- 学校/学院要求文件
- DOCX 模板（可选）
- 已有论文、参考文献或相关资料（可选；也可以由 Agent 协助检索）

首次生成 DOCX 前，skill 会确认模板模式与正文目标字数/区间（并确认封面、目录、参考文献等是否计入）。已明确指定用户模板或内置 base template 时不会重复询问，但仍必须补齐缺失的字数要求。DOCX 必须在模板副本中原位编辑；不得删除模板正文后用通用 Word 标题样式重建，也不得在模板自动编号的标题前手工添加中文或阿拉伯编号。

## 模板与引用处理

- 可以使用用户自己的 DOCX 模板
- 也可以使用内置通用模板
- 支持将普通 `[1]` 引用转换为 Word 交叉引用
- 正文引用默认使用上标形式
- 避免 Word 更新域后出现 `[[1]]`
- 支持参考文献去重、重排编号和基础审计
- 更新不会静默覆盖本地修改，并会为替换操作保留备份

## 暂不支持

- **自动生成图片**：目前不直接生成图片。可以在文档草稿中给出图示建议，包括图题、主要内容、建议放置位置；用户也可以继续要求生成绘图 Prompt。
- **正式毕业论文全文**：目前聚焦文献综述和开题报告。正式毕业论文通常需要完整实验结果、学校最终格式审查和导师多轮修改，后续可在此基础上扩展。

## 依赖

安装器需要 Node.js 18+。

DOCX 辅助脚本需要 Python 3.10+。如需使用引用转换、引用审计等脚本，请在对应 skill 目录下安装依赖：

```bash
python -m pip install -r scripts/requirements.txt
```

发布前可运行：

```bash
npm run check
npm test
python tests/test_docx_scripts.py
npm pack --dry-run
```

## 注意事项

- 使用前建议准备研究介绍、学校要求文件和 DOCX 模板，材料越完整，结果越接近实际要求。
- 参考文献可以由 Agent 协助检索；如果你已有 DOI、论文链接或 PDF，也可以一并提供，便于核验和格式整理。
- 生成 DOCX 后，建议人工检查封面、目录、页码、图表和参考文献格式。
