# Scholar Trails｜学缘寻踪｜学术派系检索：查学者在哪些团队做过研究、常和谁合作

输入学者姓名，可以查有公开资料可核实的师门关系、曾参与的研究团队和常合作的同行。也可以核对中英文署名，整理公开可检索的论文、专利和软件著作权，并把合著关系画成可交互的网络。

[发布到 GitHub](docs/publish.md) · [查看参数与输出说明](skills/academic-faction-finder/references/workflow.md)

## 快速开始

把方括号里的内容换成查询对象。手头有 DOI、RIS 或 PubMed 导出时，可以随提示词一起交给助手。

| 想做什么 | 专属 Skill | 直接这样说 |
| --- | --- | --- |
| 查合著者和合作团队 | [`academic-faction-finder`](skills/academic-faction-finder/SKILL.md) | `查 [单位] [姓名] 的合作团队，画出合著网络。` |
| 核对作者身份与机构 | [`academic-author-match`](skills/academic-author-match/SKILL.md) | `核对 [姓名] 的中英文署名，判断 [单位 A] 和 [单位 B] 的作者是不是同一人。` |
| 检索论文、专利和软著 | [`academic-output-search`](skills/academic-output-search/SKILL.md) | `查 [单位] [姓名] 的中英文论文、专利和软著，列出来源和覆盖缺口。` |
| 导出逐篇论文清单 | [`academic-paper-list`](skills/academic-paper-list/SKILL.md) | `导出 [单位] [姓名] 已核实的论文，含年份、作者、题名和 DOI，一作和通讯优先。` |
| 核查期刊任职和审稿记录 | [`academic-journal-role`](skills/academic-journal-role/SKILL.md) | `查 [合著者] 在 [期刊] 的公开编辑和审稿记录，并沿相关特刊补查论文。` |

不确定用哪个 Skill 时，直接描述任务即可。想指定入口时，可以写 `使用 academic-author-match，核对 [姓名] 在 [单位 A] 和 [单位 B] 的署名。`

默认检索使用公开网页与已有导出，RIS 和 PubMed 批量导入可离线完成。公开书目、专利和软著的覆盖情况以实际取得的来源为准。

## 目录结构

```text
README.md
docs/
  install.md
  publish.md
skills/
  academic-faction-finder/
  academic-author-match/
  academic-output-search/
  academic-paper-list/
  academic-journal-role/
```

每个入口都有自己的 `SKILL.md`。配套脚本、参考说明和数据模板位于 `skills/academic-faction-finder/`。

## 适用 Agent 与安装方式

Scholar Trails 可在 **Codex** 和 **Claude Code** 中作为 Agent Skills 使用。

| Agent | 仅当前项目 | 当前用户的所有项目 | 调用示例 |
| --- | --- | --- | --- |
| Codex | `.agents/skills/` | `~/.agents/skills/` | `$academic-faction-finder` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | `/academic-faction-finder` |

- **下载后手动安装。** 在 GitHub 的 **Releases** 下载 `scholar-trails.zip`，或通过 **Code → Download ZIP** 下载源码。解压后，把 `skills/` 下的五个目录一起复制到上表对应位置，保持同级。
- **从 Git 克隆后安装。** 运行 `git clone https://github.com/peng-xiaobai/scholar-trails.git`，再复制 `skills/` 下的五个目录。
- **用 GitHub CLI 批量安装。** 在目标 Git 项目目录运行下面的命令。使用 Claude Code 时将 `codex` 改为 `claude-code`。安装到个人目录时将 `project` 改为 `user`。

```bash
gh skill install peng-xiaobai/scholar-trails --all --agent codex --scope project
```

临时试用时，也可以让能读取本地文件的 Agent 直接读取解压目录里的 `skills/academic-faction-finder/SKILL.md`。[完整安装指南](docs/install.md)

## 运行离线演示

准备 Python 3.11 或更新版本，在仓库根目录运行。演示使用内置虚构数据，仅需 Python 标准库。

```bash
python skills/academic-faction-finder/scripts/faction_query.py --source demo --author "K. Alden" --min-collab 2 --out ./output/demo
```

用浏览器打开 `output/demo/network.html`。示例包含 **12 篇论文、10 位作者和 3 个合作社区**。

## 使用自己的数据

1. 将 PubMed 的 `.nbib` 或标记文本交给 `collect_pubmed.py`，或将 RIS 导出交给 `collect_ris.py`。
2. 对照原始署名核实身份和角色，按[成果证据表模板](skills/academic-faction-finder/assets/research_outputs_template.csv)整理成 `evidence.csv`。每条已核实署名使用对应的 `person_id`。
3. 运行以下命令，将 `researcher-01` 换成目标作者在证据表中的 `person_id`。

```bash
python skills/academic-faction-finder/scripts/research_outputs.py --input evidence.csv --target researcher-01 --network --out ./output/researcher
```

有独立成果清单时，可加 `--reference known_outputs.csv` 对账。加 `--paper-list` 可输出论文清单。[证据字段和导出说明](skills/academic-faction-finder/references/research_outputs.md)

| 主要输出 | 内容 |
| --- | --- |
| `paper_network/network.html` | 可离线打开的交互式论文合作网络 |
| `paper_network/seed_coauthors.csv` | 目标作者的直接合著者、共同论文篇数和加权分 |
| `paper_network/faction_memberships.csv` | 每位作者所属的社区及各组的支撑文献 |
| `paper_network/affiliation_timeline.csv` | 有来源的机构经历和论文署名观察区间 |
| `typed_collaborations.csv` | 按共同作者、共同发明人、共同开发者等具名角色统计的合作记录 |

## 如何解读合作网络

默认用至少两次共同署名的关系识别合作社区。同一人可以在多个社区拥有足够的合著证据。对目标作者与合作者的每篇论文，按双方已核实角色中的较低档计分。独立一作或独立通讯为 3 分，共同一作或共同通讯为 2 分，普通署名或待核角色为 1 分，每对作者在一篇论文上计一次。

这里的「学术派系」指给定文献范围内的合著社区。社区结果随检索范围、数据覆盖和算法参数而变化。使用报告时，可对照署名证据和来源覆盖记录复核结论。[社区与权重说明](skills/academic-faction-finder/references/workflow.md#4-解读注意)

## 数据与隐私

分发包提供通用工作流、脚本、数据模板和虚构演示。检索产生的原始导出、日志和个人资料在本地保存。对外分享检索结果前，先删除与结论无关的联系方式、个人识别号码和本机路径，只保留核验结论需要的公开出处。

## 许可证

本项目采用 MIT 许可证，允许免费使用、修改、再分发和商用。软件副本或实质部分须附带版权声明和许可文本。[MIT 许可证全文](LICENSE)
