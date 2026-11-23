# 迁移到其他 Agent

保留完整的 `paper-reading-html/` 目录及其中的 `SKILL.md`、`scripts/`、`references/` 和 `assets/`。Agent 需要能读取 PDF 和 Skill、运行 Python 3.10+ 并写入工作区。提取使用 `pdfplumber` 0.11.9 或更新版本，其依赖 `pypdfium2` 和 Pillow 用于裁图与图册。HTML 构建使用 Python 标准库。离线机翻是可选依赖，见[批量翻译与抽查](translation.md)。

```text
python -m pip install "pdfplumber>=0.11.9"
```

DeepSeek Harness 可将整个目录放到项目的 `.dsh/skills/paper-reading-html/`。也可用项目的 `.agents/skills/paper-reading-html/`，或用户目录 `~/.dsh/skills/paper-reading-html/`（设置了 `DSH_HOME` 时使用该目录）。在项目会话中明确指定 `paper-reading-html`，让 Agent 加载技能后使用提供的 PDF。自定义 Agent 预设需启用文件系统技能提供器及相应加载工具。

前置检查可运行 `python -c "import pdfplumber"` 和 `python scripts/prepare_reader.py --help`。Windows 上优先使用 DSH 工作区依赖提供的 Python，尤其是系统 Python 导入不了 `pdfplumber` 时。其他 Agent 可读取 `SKILL.md` 的完整路径后执行。HTML 在本地浏览器完成搜索与筛选。

[DeepSeek Harness 文件系统 Skill 官方文档](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)
