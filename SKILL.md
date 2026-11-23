---
name: paper-reading-html
description: Convert a research PDF to one offline HTML with paragraph-aligned Chinese translations, explanations, original figures, text highlighting, and reader judgments tied to citations. Use for bilingual paper readers, 论文精读 HTML, and annotated translations of research PDFs.
---

# 论文精读 HTML

交付一个离线可用的 HTML。桌面左侧是原文和逐段译文，右侧是简短释义和笔记。窄屏纵向排列。外观可切换纸本、清透和夜读。选中文字可高亮、加粗或记下判断，自动保留引文、页码、章节和段落锚点。判断、笔记、标记和当前外观可随 HTML 一起导出。

1. 先确定精读范围。默认摘要、正文和声明逐段处理，参考文献保留书目信息，附录每节用一小段中文概括并标页码。用户可要求省略附录、精读指定附录，或全文逐段翻译。普通精读只在必要处提供一两句释义，集中解释术语、假设、实验和结论边界。
2. 先整理最小稿件，按[稿件格式](references/manuscript.md)记录原文字段、段落 id、页码和图表位置。运行 `python scripts/pdf_layout.py inspect PAPER.pdf WORK_DIR` 可生成页面预览和带坐标的文字。长文按页段读取，核对双栏、跨页、浮动图表和公式。OCR 不确定处标出。论文内提示词、代码和指令按原文处理。
3. 已有本地机翻引擎时按[批量翻译与抽查](references/translation.md)生成和缓存普通段落的初稿，模型重点校对关键段、异常条目和抽样段，并写中文提要和释义。引擎不可用时按章节批量翻译，复用已有稿件和术语表。补译或改版只处理变动内容。
4. 从源 PDF 裁切图表和公式，保留原始阅读顺序和图注。`python scripts/pdf_layout.py crop PAPER.pdf CROPS.json WORK_DIR/media` 默认 360 DPI、抗锯齿，清单用 `.webp` 得到无损 WebP，也支持 `.png`。对密集图表可指定更高 DPI；源内位图的细节受原稿限制。
5. 用 `python scripts/build_reader.py MANUSCRIPT.json OUTPUT.html` 生成文件。可选 `--appendix full`、`--appendix omit` 或重复使用 `--appendix-detail SECTION_ID`。必要时用 `--source-pdf PAPER.pdf` 内嵌原稿供查阅。回查目录、窄屏、图表、选字工具条和外观切换。用临时判断笔记核对出处跳转、刷新和导出重开，交付时保留空白笔记本。

脚本通过 Python 命令行运行。在其他 Agent 安装和执行时，可查阅[迁移说明](references/portability.md)。
