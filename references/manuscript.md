# 稿件格式

## 提取与补丁

- `prepare_reader.py scan PAPER.pdf WORK` 将文字和坐标写入 `layout.json`，将图注、表格横线、光栅图像坐标及可能的矢量图页写入 `figure-plan.json`。后者提供候选，有时会遗漏嵌入图内的标签或把文本装饰识别成图表。只读取有疑问的页记录，必要时用 `pdf_layout.py contact PAPER.pdf WORK/previews --pages 2,5,8` 每六页拼一张。已核对的 `CROPS.json` 可直接复用。`--columns one` 或 `--columns two` 可手动覆盖早期版式判断。
- `prepare_reader.py draft PAPER.pdf WORK --crops CROPS.json` 读取布局、批量裁图并生成 `manuscript.json`。`--crops` 适用于有选定图表的文档。查看它打印的章节、页段和块数，聚焦核对漏掉的章名、栏序、图表或 OCR 页。
- `reader_jobs.py queue BASE.json WORK/batches` 输出本次要处理的批次文件路径。每条记录包含稳定的 ID 和 `task`。每批保存一个 `WORK/patches/patch-001.json` 之类的文件。普通段落填 `zh`，选定的重点段落加 `explain`。图表有 `label` 但缺图注时，基于原图或可定位证据写中文说明。附录 `sampled: true` 时只概括摘录支持的内容，可在 `scope` 注明摘录范围。
- `reader_jobs.py merge BASE.json WORK/final.json WORK/patches` 一次合并，可传多个独立补丁路径。补丁只含可编辑的中文字段，原文、源页和锚点来自稿件。已完成批次可复用。

补丁示例

```json
{
  "paper": {"title": "中文论文标题"},
  "abstract-001": {"zh": "对应的摘要译文。", "explain": "说明作者所检验的核心问题。"},
  "s-09-summary": {"zh": "本节附录的简短提要。"}
}
```

排批、机翻和构建都接受 `--appendix summary|full|omit` 与可重复的 `--appendix-detail SECTION_ID`。精读范围变更时用同一组参数。

## 稿件字段

中间稿件是 UTF-8 JSON。章节与块的数组顺序即阅读顺序。每个 ID 在整份文档中唯一，使用小写字母开头，只含小写字母、ASCII 数字与连字符。同一文档的段落锚点和笔记均使用这些 ID。

```json
{
  "title": "中文论文标题",
  "original_title": "The title printed on the PDF",
  "authors": "作者",
  "citation": "版本、年份或页数",
  "scope": "必要时说明覆盖范围",
  "sections": [
    {
      "id": "intro",
      "title": "1 引言",
      "subtitle": "Introduction",
      "blocks": [
        {
          "id": "intro-1",
          "pages": "p. 1",
          "original": "The extracted paragraph with its original citations.",
          "zh": "对应段落的中文翻译。",
          "explain": "说明段落如何支持作者的问题设定。"
        },
        {
          "id": "fig-1",
          "label": "图 1 · 实验设置",
          "pages": "pp. 2–3",
          "image": "media/fig-1.png",
          "alt": "原论文的实验设置流程图",
          "original": "The original caption, if it is not part of the crop.",
          "zh": "图注的中文翻译。",
          "explain": "说明如何阅读图中的箭头和分组。"
        }
      ]
    }
  ]
}
```

顶层的 `authors`、`citation`、`scope` 及每章的 `subtitle`、每块的 `label`、`explain` 均可省略。每块提供原文或图片。若图片已完整包含图注，可省略该块的 `original`。图片路径从稿件位置解析，只支持其目录内的 PNG、JPEG 或 WebP。对图表内的大量数据可保留原图并翻译标题、图注和理解所需的标签。正文中的公式可使用 Unicode 或原版裁图，译文保持原符号定义。参考文献章节可设 `"bibliography": true`，仅呈现书目信息。

附录章节使用 `"appendix": true` 并提供 `"summary": {"id": "app-a-summary", "pages": "pp. 12–15", "zh": "本节中文提要", "explain": "何时值得回查此附录"}`。若用户只要求提要，`blocks` 可留空。若已有逐段译文，放在 `blocks` 供 `--appendix full` 或 `--appendix-detail` 选用。提要中也要显示的图表在对应块设置 `"show_in_summary": true`，可选 `"summary_zh"` 提供简版图表说明。

译文打底阶段可以把待翻译块的 `zh` 留空，渲染前补齐所有将显示的块。可加 `"review": true` 将一个有原文字段的块加入重点校对。

裁图清单示例。坐标以 PDF 点为单位，从页面左上角起算，页码从 1 开始。输出支持 `.png` 或无损 `.webp`。

```json
[
  {"page": 2, "box": [72, 101, 524, 329], "file": "fig-1.webp"}
]
```

文件名用 `fig-1.webp` 或 `table-1.webp` 等形式，便于按编号附上识别到的原版图注。图注未被识别时可在清单中提供 `caption`；自定义图表名用 `label`。附录提要中保留指定图表时可加 `"show_in_summary": true`。
