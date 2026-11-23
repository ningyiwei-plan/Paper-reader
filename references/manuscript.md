# 稿件格式

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

顶层的 `authors`、`citation`、`scope` 及每章的 `subtitle`、每块的 `label` 均可省略。每块提供原文或图片。若图片已完整包含图注，可省略该块的 `original`。图片路径从稿件位置解析，只支持其目录内的 PNG、JPEG 或 WebP。对图表内的大量数据可保留原图并翻译标题、图注和理解所需的标签。正文中的公式可使用 Unicode 或原版裁图，译文保持原符号定义。

附录章节使用 `"appendix": true` 并提供 `"summary": {"id": "app-a-summary", "pages": "pp. 12–15", "zh": "本节中文提要", "explain": "何时值得回查此附录"}`。若用户只要求提要，`blocks` 可留空。若已有逐段译文，放在 `blocks` 供 `--appendix full` 或 `--appendix-detail` 选用。提要中也要显示的图表在对应块设置 `"show_in_summary": true`，可选 `"summary_zh"` 提供简版图表说明。

译文打底阶段可以把待翻译块的 `zh` 留空，渲染前补齐所有将显示的块。可加 `"review": true` 将一个有原文字段的块加入重点校对。

裁图清单示例。坐标以 PDF 点为单位，从页面左上角起算，页码从 1 开始。输出支持 `.png` 或无损 `.webp`。

```json
[
  {"page": 2, "box": [72, 101, 524, 329], "file": "fig-1.webp"}
]
```
