---
name: academic-faction-finder
description: Profile a researcher and map their role-weighted co-authorship and overlapping collaboration communities across institutions. Use for 查某位学者、合著者检索、学术派系、合作团队、合作网络 or a combined researcher profile and output search.
---

# 学缘寻踪｜合作网络检索

输入学者姓名，查他在哪些团队做过研究、常和谁合作，以及这些人和团队之间有什么联系。

## 按任务调用

只查合著者、建合作网络或综合检索学者时，用 `academic-faction-finder`。整套安装后，单项任务可使用对应的 Skill。

| 任务 | Skill |
| --- | --- |
| 核对中英文署名、同名作者或跨机构身份 | [`academic-author-match`](../academic-author-match/SKILL.md) |
| 查论文、专利、软著或核对成果覆盖 | [`academic-output-search`](../academic-output-search/SKILL.md) |
| 列出或导出逐篇论文 | [`academic-paper-list`](../academic-paper-list/SKILL.md) |
| 核查某位作者的期刊任职或公开审稿记录 | [`academic-journal-role`](../academic-journal-role/SKILL.md) |

## 默认交付

收到“用这个 Skill 查某人”或“查某人的派系”后，直接核实身份、并行查成果、对账和建图。交付简短结论、可交互论文网络、合著者明细、分角色专利与软著关系及覆盖缺口。只有用户明确要求“列出论文”“导出论文清单”或同义请求时，才交付逐篇论文清单。用户指定某一成果类型、期刊、分区、年代或领域时，沿用其范围。分区使用用户提供或已核实的映射及版本。没有时间或期刊限制时，纳入实际核实的成果并报告覆盖区间。

- **定位作者。** 单位默认用于确认身份。只有用户明确限定单位范围时，才排除其他任职阶段的成果。用机构或本人公开履历、双语登记、ORCID 或可核实的成果署名定位作者。确认双语姓名后用两个名字并行检索。只给姓名时，在已知领域按已核实去重论文数选默认作者，超过 10 篇的同名者各自展示网络。身份仍有实质歧义时，列出候选及证据，等身份确认后再归属成果和建图。[身份核实](references/workflow.md#9-跨机构检索与归并) · [仅姓名检索](references/workflow.md#11-仅姓名检索)
- **反查作者的另一语种姓名。** 对论文中只有单语署名的目标与合作者，按署名机构逐人反查官网、团队新闻和公开公示。以具体成果或团队证据核实对应关系，结果优先显示已核实的中文名，保留原始署名与来源。[姓名反查](references/workflow.md#10-双语搜索与备用源)
- **对齐双语单位。** 把中文单位译成英文检索，比较论文署名中的专名、上级机构与地点。缩写、语序和轻微译法差异若仍能唯一对应，可记为同一机构别名，保存映射和依据并用于后续查询与建图。[机构对齐](references/workflow.md#10-双语搜索与备用源)
- **并行查四类成果。** 优先使用已有数据、学术搜索及专业索引的网页与批量导出。生物医学作者用 PubMed 网页批量查，再以出版社补漏。按双语署名、历史机构、旧合作者和时间段对账。专利和软著查各自的官方来源。默认流程不消耗学术数据库 API 额度。[网页与导出检索](references/workflow.md#8-多源检索与漏检排查) · [来源与对账](references/research_outputs.md)
- **沿履历和旧合作者回查。** 按就读和任职阶段，从已核实成果找旧合作者和公开资料中的导师，用双语姓名结合这些线索跨机构回查，覆盖只用现单位会漏掉的阶段。核对具体署名位置、旧合作者身份与履历后，将跨机构成果归入同一人。只列有公开证据的导师关系，和论文合作分开呈现。[跨机构检索](references/workflow.md#9-跨机构检索与归并)
- **逐单位记录署名。** 同一作者在同篇论文列出多个单位时，每个单位各记一行，共用该论文的署名位置和已核实的人员标识。为目标和合作者保留这些单位。后续查询遇到该人只列其中一个单位时，用已有机构记录定位候选，再核实具体署名。
- **整理机构时间线。** 从校方履历、任免公告、个人简历或 ORCID 公开任职栏目记录有来源的任职、就读和访学区间。日期缺证时按多年的原始署名推断约略范围并明确标记。后续连续使用其他单位是推断线索，缺失署名单位的论文不参与判断。[机构时间线](references/workflow.md#13-机构时间线)
- **核实论文版本与角色。** 正式版、勘误和预印本对齐后再计数。按作者位置核对第一、共同第一、通讯及共同通讯标记，以能定位到具体作者的出版方脚注为准。重点复核会改变合著权重的角色。[成果版本](references/research_outputs.md#成果版本与归属) · [角色与权重](references/workflow.md#12-署名角色与权重)
- **按需导出论文。** 用户明确要求时，核对范围内所有已确认归属的论文，运行 `research_outputs.py --paper-list` 生成 `paper_list.csv`。检索对象担任一作或通讯的论文优先，两组各按年份从新到旧。核实年份、完整作者顺序、标题和 DOI，缺失或冲突未解的字段留空。只要论文清单时直接走此入口。[论文清单](references/research_outputs.md#按需导出论文清单)
- **识别可重叠的合作社区。** 默认用合著者之间至少共同署名 2 篇的边识别社区，再按实际合著为目标和其他合作者补充社区归属。默认在某组与至少两位成员累计合著至少两篇即可加入，允许同一人在多个组。保留每组的合作篇数、年份、支撑论文和原始署名单位。与检索对象相连的边按双方角色计 3、2 或 1 分。专利共同发明、软著共同开发和自然人共同著作权分别统计。[社区与署名权重](references/workflow.md#4-解读注意)
- **按需核查期刊角色。** 用户询问某位合作者在目标期刊的身份时，优先复用已有合著证据，核实其公开的主编、编委、客座编辑或审稿记录，沿官方专刊和公开文章记录补查文献线索。[期刊角色核查](references/workflow.md#14-期刊编辑与审稿角色)

## 执行入口

仅查期刊角色时，直接按[期刊角色核查](references/workflow.md#14-期刊编辑与审稿角色)执行。

1. 用公开网页和已有证据发现论文。RIS 导出用 `scripts/collect_ris.py`，PubMed 导出用 `scripts/collect_pubmed.py` 离线整理候选。按来源、语言和职业阶段补缺，再核实逐条归属。[默认采集入口](references/workflow.md#8-多源检索与漏检排查)
2. 按 `assets/research_outputs_template.csv` 整理证据，使用 `scripts/research_outputs.py --input evidence.csv --target PERSON_ID --reference known_outputs.csv --network --out OUT`。该命令对账、导出分层关系、从已核实署名选种子并建图。传入 `--affiliation-history` 使用已核实的履历日期，传入 `--alias-map` 使用机构映射，已排除同名冲突的作者异写可传入 `--name-alias`。仅姓名模式附加 `--network-min-papers 11`。独立清单取不到时省略 `--reference` 并说明范围。指定年份、期刊或自定义图参数时，先生成 `paper_authorship.csv`，再用 `scripts/faction_query.py --source local` 应用对应筛选。[参数和本地流程](references/workflow.md) · [书目来源与字段](references/data_sources.md)
3. 从 `output_summary.json` 和论文图的 `summary.json` 读取统计。真实结果用原始署名对照重点合作者的篇数及角色。正文列主要社区、代表性合作者、实际篇数和加权分、主要机构时间线与导师关系、可核实范围与缺口，明细用文件交付。检索和计数用脚本处理，模型按需要读摘要、待核项和少量关键证据。
