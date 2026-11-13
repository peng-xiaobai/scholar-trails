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
| 按研究方向找代表学者 | [`academic-topic-scholars`](../academic-topic-scholars/SKILL.md) |
| 核对中英文署名、同名作者或跨机构身份 | [`academic-author-match`](../academic-author-match/SKILL.md) |
| 查论文、专利、软著或核对成果覆盖 | [`academic-output-search`](../academic-output-search/SKILL.md) |
| 列出或导出逐篇论文 | [`academic-paper-list`](../academic-paper-list/SKILL.md) |

## 默认交付

收到“用这个 Skill 查某人”或“查某人的派系”后，直接核实身份、并行查成果、对账和建图。交付简短结论、可交互论文网络、合著者明细、分角色专利与软著关系及覆盖缺口。只有用户明确要求“列出论文”“导出论文清单”或同义请求时，才交付逐篇论文清单。用户指定某一成果类型、期刊、分区、年代或领域时，沿用其范围。分区使用用户提供或已核实的映射及版本。没有时间或期刊限制时，纳入实际核实的成果并报告覆盖区间。

- **定位作者。** 单位默认用于确认身份。只有用户明确限定单位范围时，才排除其他任职阶段的成果。用机构或本人公开履历、双语登记、ORCID 或可核实的成果署名定位作者。确认双语姓名后用两个名字并行检索。只给姓名时，在已知领域按已核实去重论文数选默认作者，超过 10 篇的同名者各自展示网络。身份仍有实质歧义时，列出候选及证据，等身份确认后再归属成果和建图。[身份核实](references/workflow.md#9-跨机构检索与归并) · [仅姓名检索](references/workflow.md#11-仅姓名检索)
- **在同一合作范围内核对中英文姓名。** 优先用同篇论文的双语作者位置或已核实 ORCID。只有单语署名时，先从本批论文中反查反复出现的已核实合作者，再核对论文单位、时间和主题，定向找双语署名或校方资料。共用一个合作者群是线索，遇到同名候选或跨单位证据不足时保留原始署名。逐篇显示已核实的中文名和论文署名。[姓名反查](references/workflow.md#10-双语搜索与备用源)
- **对齐双语单位。** 把中文单位译成英文检索，比较论文署名中的专名、上级机构与地点。缩写、语序和轻微译法差异若仍能唯一对应，可记为同一机构别名，保存映射和依据并用于后续查询与建图。[机构对齐](references/workflow.md#10-双语搜索与备用源)
- **并行查四类成果。** 论文至少走两条独立检索路径。用学术搜索或网页搜索查双语署名、历史单位及旧合作者，再用校方成果页、机构仓储、出版社或对应学科和语种的索引对账。OpenAlex 仅作可选补充，限流、无结果或字段不全时继续其他路径。生物医学优先用 PubMed 网页和导出，中文期刊用期刊官网及知网、万方或维普的可用记录。专利和软著查各自的官方来源。默认使用网页和已有导出，无需数据库密钥。[网页与导出检索](references/workflow.md#8-多源检索与漏检排查) · [来源与对账](references/research_outputs.md)
- **追查换单位后的论文。** 用目标的中英文姓名搭配已核实身份的旧合作者，放开旧单位限制，反查新单位论文。同一作者换到新单位后，即使完全停止署名旧单位，也可依据持续合著、研究方向和时间线核实连续性。对通过核验的署名沿用同一个 `person_id`，并继续从新阶段的合作者补查成果。[跨机构检索](references/workflow.md#9-跨机构检索与归并)
- **核对作者署名单位。** 先展开 DOI 原刊的作者和单位栏。原刊或已有来源缺单位时，用 Google 搜完整英文题名，查同篇免费网页或 PDF。仍有缺口时，按[署名补录流程](references/research_outputs.md#署名单位补录)一次发一篇的原刊链接，裸网址后加半角空格。能在本轮接收回复时，从发出补录请求起按实际时钟最多等 180 秒。核对题名和署名后回填，用已核实的作者位置和署名单位建图。
- **整理机构时间线。** 从校方履历、任免公告、个人简历或 ORCID 公开任职栏目记录有来源的任职、就读和访学区间。日期缺证时按多年的原始署名推断约略范围并明确标记。后续连续使用其他单位是推断线索，缺失署名单位的论文不参与判断。[机构时间线](references/workflow.md#13-机构时间线)
- **核实论文版本与角色。** 正式版、勘误和预印本对齐后再计数。按作者位置核对第一、共同第一、通讯及共同通讯标记，以能定位到具体作者的出版方脚注为准。重点复核会改变合著权重的角色。[成果版本](references/research_outputs.md#成果版本与归属) · [角色与权重](references/workflow.md#12-署名角色与权重)
- **按需导出论文。** 用户明确要求时，核对范围内所有已确认归属的论文，运行 `research_outputs.py --paper-list` 生成 `paper_list.csv`。检索对象担任一作或通讯的论文优先，两组各按年份从新到旧。核实年份、完整作者顺序、标题和 DOI，缺失或冲突未解的字段留空。只要论文清单时直接走此入口。[论文清单](references/research_outputs.md#按需导出论文清单)
- **按合著关系和署名单位划分社区。** 保留院系、实验室层级。两位作者在同一篇论文上都署名某单位，且该单位有至少一份核实的独立署名记录，就可建立一个社区。在检索范围内有该单位本人署名的合作者均可加入，合作一次或权重为 1 也可入组。始终与其他单位一起署名的单位显示在作者节点姓名下方。正式任职按履历核实。[社区与署名权重](references/workflow.md#4-解读注意)
- **核对同校院系更名。** 多位已核实为同一人的作者先后从同校一个院系署名换到另一个院系时，联网查校方更名或组织调整公告、学院沿革及前后单位代码。确认同一建制延续后，将旧名和新名写入 `--alias-map`，社区统一显示现名，逐篇保留论文所载名称。[院系更名核对](references/workflow.md#4-解读注意)

## 执行入口

1. 用公开网页和已有证据发现论文。RIS 与 PubMed 导出可离线整理。将已发现的 DOI 或题名和来源登记到候选表，再按独立清单、近期出版社记录和合作者反查补缺。[默认采集入口](references/workflow.md#8-多源检索与漏检排查)
2. 按 `assets/research_outputs_template.csv` 整理证据，先运行 `scripts/research_outputs.py --input evidence.csv --target PERSON_ID --reference known_outputs.csv --out OUT`。处理回查表中的署名缺口，补录完成、跳过或超时后加 `--network` 重跑。图页展示作者、社区、合作连线与篇数统计，逐篇书目留在成果表。传入 `--affiliation-history` 使用已核实的履历日期，传入 `--alias-map` 使用机构映射，已排除同名冲突的作者异写可传入 `--name-alias`。仅姓名模式附加 `--network-min-papers 11`。独立清单取不到时省略 `--reference` 并说明范围。指定年份、期刊或自定义图参数时，先生成 `paper_authorship.csv`，再用 `scripts/faction_query.py --source local` 应用对应筛选。[参数和本地流程](references/workflow.md) · [书目来源与字段](references/data_sources.md)
3. 用 `--paper-candidates` 对账，按候选表和独立清单的输出补查缺失项。正文列主要社区、代表性合作者、篇数与加权分、机构时间线、导师关系和覆盖缺口。每次用目标的已核实姓名、单位和代表作查找公开 ORCID。正文有可核实结果时给出个人页面链接，否则写“ORCID 未找到”。[候选对账](references/research_outputs.md#论文候选对账)
