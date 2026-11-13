# Scholar Trails｜学缘寻踪｜学术合作检索：查学者在哪些团队做过研究、常和谁合作，检索方向内代表学者

> 输入学者姓名，查他在哪些团队做过研究、常和谁合作；输入研究方向，找持续发表相关成果的代表学者。

<p align="left">
  <a href="https://github.com/peng-xiaobai/scholar-trails"><img alt="GitHub stars" src="https://img.shields.io/github/stars/peng-xiaobai/scholar-trails?style=flat&amp;label=stars"></a>
  <img alt="科研合作网络" src="https://img.shields.io/badge/Agent%20Skills-Research%20Networks-286453">
  <img alt="文档语言：中文" src="https://img.shields.io/badge/language-%E4%B8%AD%E6%96%87-brightgreen">
</p>

![定量遥感虚构数据的合作网络，展示署名单位和合著连线](assets/preview.png)

## 定位

学缘寻踪用公开研究成果梳理学术合作。查一个人，可以看到他的直接合著者、共同发表的篇数、论文署名单位和有出处的机构经历。查一个方向，可以看到哪些人持续发表相关论文、各自做过哪些代表性工作。也可以单独核对中英文署名，或查论文、专利和软件著作权。有公开资料时，结果附上 ORCID 或可核实的导师关系。

[发布到 GitHub](docs/publish.md) · [查看参数与输出说明](skills/academic-faction-finder/references/workflow.md)

## 使用方式

安装后可以直接用下面的提示词。把方括号换成实际的姓名、单位或方向。手头已有 DOI、论文题名或文献导出文件，也可以一起交给助手补查。

| 想做什么 | 专属 Skill | 直接这样说 |
| --- | --- | --- |
| 查合著者和合作团队 | [`academic-faction-finder`](skills/academic-faction-finder/SKILL.md) | `查 [单位] [姓名] 的合作团队，画出合著网络。` |
| 按方向找代表学者 | [`academic-topic-scholars`](skills/academic-topic-scholars/SKILL.md) | `找 [研究方向] 近五年的代表学者，列出已核实的方向论文数和代表作。` |
| 核对作者身份与机构 | [`academic-author-match`](skills/academic-author-match/SKILL.md) | `核对 [姓名] 的中英文署名，判断 [单位 A] 和 [单位 B] 的作者是不是同一人。` |
| 检索论文、专利和软著 | [`academic-output-search`](skills/academic-output-search/SKILL.md) | `查 [单位] [姓名] 的中英文论文、专利和软著，列出来源，并标出还有哪些来源没查全。` |
| 导出逐篇论文清单 | [`academic-paper-list`](skills/academic-paper-list/SKILL.md) | `导出 [单位] [姓名] 已核实的论文，含年份、作者、题名和 DOI，第一作者和通讯作者优先。` |

不确定用哪个 Skill 时，直接描述任务即可。想指定入口时，可以写 `使用 academic-author-match，核对 [姓名] 在 [单位 A] 和 [单位 B] 的署名。`

**查一个人时**，单位可以帮助区分同名作者。默认会追查换单位前后的成果，给出可交互的合作网络、主要合作者和覆盖缺口。需要逐篇书目时，再说「导出论文清单」。

**查一个方向时**，可以直接说 `检索定量遥感领域的代表学者，重点关注植被覆盖度反演。` 结果会列出中英文关键词、检索范围、代表学者及代表作。

**需要补录署名时**，助手会一次发一篇，把可点击的 DOI 原刊链接单独放一行。打开原刊后，复制完整题名、带上标的作者名单和署名单位表即可。支持在本轮接收回复的客户端，从发出请求起按实际时间每篇最多等 180 秒。可以跳过本篇或结束补录。满 180 秒仍无回复，就用已核实的资料交付。只能在下一轮回复时，可以在下一条消息补录。[署名补录说明](skills/academic-faction-finder/references/research_outputs.md#署名单位补录)

## 目录结构

```text
.gitignore
LICENSE
README.md
assets/
  preview.png
docs/
  install.md
  publish.md
skills/
  academic-faction-finder/
  academic-author-match/
  academic-output-search/
  academic-paper-list/
  academic-topic-scholars/
```

每个入口都有自己的 `SKILL.md`。配套脚本、参考说明和数据模板位于 `skills/academic-faction-finder/`。

## 适用 Agent 与安装方式

Scholar Trails 可在 **Codex** 和 **Claude Code** 中作为 Agent Skills 使用。

| Agent | 仅当前项目 | 当前用户的所有项目 | 调用示例 |
| --- | --- | --- | --- |
| Codex | `.agents/skills/` | `~/.agents/skills/` | `$academic-faction-finder` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | `/academic-faction-finder` |

- **下载后手动安装。** 在 GitHub 的 **Code → Download ZIP** 下载源码，也可以在 [Releases](https://github.com/peng-xiaobai/scholar-trails/releases) 选择所需版本。解压后，把 `skills/` 下的目录一起复制到上表对应位置，保持同级。
- **从 Git 克隆后安装。** 运行 `git clone https://github.com/peng-xiaobai/scholar-trails.git`，再复制 `skills/` 下的目录。
- **用 GitHub CLI 批量安装。** 在目标 Git 项目目录运行下面的命令。使用 Claude Code 时将 `codex` 改为 `claude-code`。安装到个人目录时将 `project` 改为 `user`。[GitHub CLI 命令说明](https://cli.github.com/manual/gh_skill_install)

```bash
gh skill install peng-xiaobai/scholar-trails --all --agent codex --scope project
```

临时试用时，也可以让能读取本地文件的 Agent 直接读取解压目录里的 `skills/academic-faction-finder/SKILL.md`。[完整安装指南](docs/install.md)

## 运行离线演示

准备 Python 3.11 或更新版本，在仓库根目录运行。演示使用内置虚构数据，仅需 Python 标准库。

```bash
python skills/academic-faction-finder/scripts/faction_query.py --source demo --author "示例作者 A" --mode seed --min-collab 2 --out ./output/demo
```

用浏览器打开 `output/demo/network.html`。离线演示使用定量遥感虚构数据，包含 **12 篇论文、10 位作者和 5 个合作社区**，每篇论文都有同一位「示例作者 A」。滚轮可以缩放，拖动画布空白处可以平移。悬停在作者节点上可以查看署名记录。

## 使用自己的数据

1. 将 PubMed 的 `.nbib` 或标记文本交给 `collect_pubmed.py`，或将 RIS 导出交给 `collect_ris.py`。
2. 对照原始署名核实身份和角色，按[成果证据表模板](skills/academic-faction-finder/assets/research_outputs_template.csv)整理成 `evidence.csv`。每条已核实署名使用对应的 `person_id`。
3. 运行以下命令，将 `researcher-01` 换成目标作者在证据表中的 `person_id`。

```bash
python skills/academic-faction-finder/scripts/research_outputs.py --input evidence.csv --target researcher-01 --network --out ./output/researcher
```

有独立成果清单时，可加 `--reference known_outputs.csv` 对账。有按 DOI 或题名收集的候选论文时，可用 `--paper-candidates paper_candidates.csv` 查漏。需要单独输出逐篇书目时，加 `--paper-list`。[证据字段和导出说明](skills/academic-faction-finder/references/research_outputs.md)

| 主要输出 | 内容 |
| --- | --- |
| `paper_network/network.html` | 可离线打开的交互式论文合作网络，显示作者、社区、合作连线和篇数 |
| `paper_network/seed_coauthors.csv` | 目标作者的直接合著者、共同论文篇数和加权分 |
| `paper_network/faction_memberships.csv` | 每位作者所属的社区及各社区的支撑文献 |
| `paper_network/affiliation_timeline.csv` | 有来源的机构经历和论文署名观察区间 |
| `paper_affiliation_lookups.csv` | 按篇汇总署名缺口，提供 DOI 原刊入口和题名检索链接 |
| `affiliation_recheck.csv` | 署名缺口重检时生成，列出原论文回查线索和其他论文的单位证据 |
| `typed_collaborations.csv` | 按共同作者、共同发明人、共同开发者等具名角色统计的合作记录 |
| `paper_list.csv` | 按需导出，包含年份、完整作者顺序、题名和 DOI。一作与通讯作者论文优先，两组各按年份从新到旧排列 |

## 原理

- **成果怎么找。** 用中英文姓名、历史单位和常见合作者交叉检索，再对照期刊官网、出版社、机构成果页或学科数据库补缺。OpenAlex 可用于补充。正式论文按 DOI 去重，缺 DOI 时核对题名、年份和署名。专利和软著分别核对公开登记记录。[多来源检索](skills/academic-faction-finder/references/workflow.md#8-多源检索与漏检排查)
- **谁算合作者。** 两人署名在同一篇论文上，就记一篇合著。遇到同名作者、姓名异写或机构变更时，结合双语署名、持续合著、研究方向和公开履历核对身份。结果附已核实的 ORCID 页面链接，未查到时明确注明。[作者身份核对规则](skills/academic-faction-finder/references/workflow.md#9-跨机构检索与归并)
- **单位怎么记录。** 优先在 DOI 原刊核对每位作者的上标与单位表。原刊打不开或署名不全时，用完整题名找同篇公开版本。一个人可以在不同年份或同一篇论文署名多个单位，逐条保留。公开履历中的任职时间和论文署名出现的年份分开记录。[单位与时间线规则](skills/academic-faction-finder/references/workflow.md#13-机构时间线)
- **合作分怎么算。** 对被查学者和每位合作者，先看两人在同一篇论文上的角色。独立第一作者或独立通讯作者是 3 分档，共同第一作者或共同通讯作者是 2 分档，其他署名或角色待核是 1 分档。每人取自己最高的一档，两人取较低的一档作为该篇的合作分，再把各篇加起来。例如，一人是独立第一作者，另一人是共同通讯作者，这篇合著记 2 分。其他作者彼此合作时，每篇共同论文计 1 分。[计分规则](skills/academic-faction-finder/references/workflow.md#12-署名角色与权重)
- **合作组怎么划分。** 按论文实际署名的学校、院系或实验室命名。一个单位至少要有两位作者在同一篇论文署名，且在本次范围内至少有一条只署该单位的记录，才单列社区。合作一次的作者也能按本人署名入组，同一作者可以属于多个社区。始终作为联合署名出现的单位仍显示在作者节点上。图上的作者和连线依据对应论文中已核实的单位。经校方确认的院系更名可归到同一社区，原署名逐篇保留。[分组规则](skills/academic-faction-finder/references/workflow.md#4-解读注意)
- **按方向怎么找学者。** 先理解方向，再用论文里常见的中英文术语检索，逐篇核对研究内容和作者。默认统计近五个自然年（含当年）的期刊和正式会议论文，按已核实的方向成果数排序，每位学者附代表作。只有对账过同期同类成果总量，才计算方向成果占比。篇数反映本轮核实到的产出，代表性还可以结合代表作和公开项目来判断。[方向检索规则](skills/academic-faction-finder/references/topic_scholars.md)

## 风险提醒

本仓库检索的是公开可查的论文、专利和软件著作权等成果。能查到的记录受数据来源和检索范围影响，同名作者或不完整的署名也可能影响判断。合著关系、合作分和分组结果仅供参考。引用结果或判断具体关系前，请自行检索相关成果，核对原文的作者、署名单位和发表时间。涉及师门或任职时，请再查相关公开资料。

## 数据与隐私

分发包提供通用工作流、脚本、数据模板和虚构演示。检索产生的原始导出、日志和个人资料在本地保存。对外分享检索结果前，先删除与结论无关的联系方式、个人识别号码和本机路径，只保留核验结论需要的公开出处。

## 许可证

本项目采用 MIT 许可证，允许免费使用、修改、再分发和商用。软件副本或实质部分须附带版权声明和许可文本。[MIT 许可证全文](LICENSE)
