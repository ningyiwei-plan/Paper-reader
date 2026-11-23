# 批量翻译与抽查

## 处理范围

先用小段样本建立论文自己的术语表，如 `{"memory recall": "记忆回忆", "memory use": "记忆运用"}`。对专名、缩写和量纲采用全文一致写法。只为已选定的精读段落准备原文和译文。附录提要由模型阅读各节后直接生成。

正文默认使用本地机翻打底。已翻译段落会保留，重复内容可直接命中缓存。模型重点检查摘要、结论、主要方法或结果、对照组、方向、显著性、范围条件和人工指定的难段。其余段落按章节抽样。抽样中发现系统性错误时扩大到受影响的章节或同一术语。数值与术语检测是辅助规则。

## 生成初稿

在稿件中先填写 `original`，将待翻译段落的 `zh` 留空。标记关键段落可加 `"review": true`。图表标题、公式释义和附录提要可直接填写中文。

已在本机运行 LibreTranslate 时，用支持数组输入的本地接口。脚本只连接回环地址。也可使用已安装 Argos 源语言到中文模型的 Python 环境。

```text
python scripts/draft_translation.py manuscript.json draft.json --engine libre --report review.json --glossary glossary.json
python scripts/draft_translation.py manuscript.json draft.json --engine argos --report review.json
```

`--glossary` 可省略。LibreTranslate 的缺省地址是 `http://127.0.0.1:5000/translate`，可用 `--endpoint` 选本机端口。使用前核对部署实例的批量大小与语言代码，可调 `--batch-size`、`--batch-chars`、`--source` 和 `--target`。Argos 将同批段落交给同一个已加载的本地模型处理。

缓存默认保存在初稿旁的 `.translation-cache`。切换翻译模型时传新的 `--revision` 或指定 `--cache`。中断后重跑同一命令，可复用已完成结果。已有中文译文时保留，可对已有译文使用 `--engine review` 只生成检查报告。

脚本默认跳过附录的精读段落，使用 `--appendix full` 或 `--appendix-detail SECTION_ID` 限定时，渲染用相同选项。按 `review.json` 中的 ID 读取对应段落及邻文，再校对和补译。保持段落对齐，并保留数值、条件、否定、引用、术语和语气。

本地引擎不可用时，按小节将空译文交给当前模型或已经授权的模型一次性批量生成，按段落 ID 写回，复用同一术语表。保留初稿与校对结果，便于续跑。只有用户授权相应服务处理论文内容时，才使用外部翻译服务。
