# Paper Reader

把论文 PDF 做成一个可离线打开的中文精读页面。左侧展示原文与译文，右侧提供释义和笔记。

## 功能

- 从目录跳转到章节，放大原版图表，按页码回查 PDF。
- 离线搜索原文、译文、释义和笔记。可组合章节与内容类型，快速定位图表、附录或做过笔记的段落。
- 选中文字即可高亮、加粗或「记下判断」。判断笔记自动带入引文、章节、页码和段落链接，可补充其他解释及需要核实的证据。
- 切换纸本、清透和夜读三种外观。笔记、判断、标记和外观可以一起导出到单个 HTML。
- 正文默认逐段对照，附录默认提供提要。可针对指定附录做完整翻译。

## 在 Agent 中使用

克隆或下载此仓库，把完整目录作为 Skill 使用。GitHub 仓库名为 `paper-reader`，Skill 名为 `paper-reading-html`。

- **Codex**。让 Codex 读取仓库中的 [SKILL.md](SKILL.md)，并提供论文 PDF。
- **DeepSeek Harness**。将完整目录放在项目的 `.dsh/skills/paper-reading-html/`，再在会话中指定该 Skill。参见[迁移说明](references/portability.md)。

> 使用 paper-reading-html 处理这篇 PDF。正文逐段翻译，附录给提要，附录 F 逐段精读。

## 从命令行生成

需要 Python 3.10 或更新版本。PDF 提取与裁图使用 `pdfplumber`。HTML 渲染只使用 Python 标准库。可选用本地 LibreTranslate 或 Argos 生成初稿，详见[批量翻译与抽查](references/translation.md)。

```sh
python -m pip install "pdfplumber>=0.11.9"
python scripts/prepare_reader.py scan paper.pdf work
python scripts/prepare_reader.py draft paper.pdf work --crops crops.json
python scripts/reader_jobs.py queue work/manuscript.json work/batches
python scripts/reader_jobs.py merge work/manuscript.json work/final.json work/patches
python scripts/build_reader.py work/final.json paper-reader.html --source-pdf paper.pdf
```

从坐标和选页缩略图核对裁图框。翻译时按批次生成只含中文字段的补丁，保留脚本从 PDF 提取的原文与页码。命令细节见[稿件格式](references/manuscript.md)。已有完整稿件可直接构建。双击生成的 HTML 即可打开。使用「导出笔记与标记」生成带笔记的副本。
