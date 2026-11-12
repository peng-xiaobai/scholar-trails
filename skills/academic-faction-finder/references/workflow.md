# 参数速查、输出字段与故障排查

## 1. 完整参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--source` | `demo` | `demo` 合成数据 / `local` 本地长表 CSV / `openalex` 公开 API |
| `--input` | — | `local` 模式的输入 CSV 路径 |
| `--author` | — | 种子作者姓名，可重复；OpenAlex 模式下还会解析成作者 ID 过滤 |
| `--seed-name` | — | 仅作种子名、不添加作者 ID 过滤，可重复；目标作者被 OpenAlex 拆成多个 ID 时用它 |
| `--author-id` | — | OpenAlex 作者 ID（`A...`），可重复，OR 关系 |
| `--org` | — | 单位名称，可重复；论文级过滤，会尝试解析为机构 ID |
| `--org-id` | — | OpenAlex / ROR 机构 ID（`I...`），可重复 |
| `--affil-search` | — | 原始署名机构字符串检索，可重复、OR；用于学院 / 系 / 实验室等无机构 ID 的二级单位 |
| `--journal` | — | 期刊名子串或 ISSN（`1234-5678`），可重复 |
| `--source-id` | — | OpenAlex source ID（`S...`），可重复 |
| `--zone` | — | 分区值，如 `Q1`、`Q2`、`一区`，可重复（OR 关系） |
| `--zone-map` | — | 分区映射 CSV；真实数据指定 `--zone` 时必须提供 |
| `--topic` | — | OpenAlex 全文检索词，可重复 |
| `--from-year` / `--to-year` | — | 发表年下限 / 上限 |
| `--mode` | `all` | `scope` 全范围 / `seed` 种子邻域 / `all` 两者 |
| `--hop` | `1` | `seed` 模式的邻域跳数 |
| `--min-collab` | `2` | 参与派系构图的最小共同署名论文数 |
| `--edge-weight` | `role` | 默认按检索对象与合作者双方的署名角色计 3、2 或 1 分，`papers` 按实际共同署名篇数计权 |
| `--community` | `labelprop` | `labelprop` 加权标签传播（零依赖）/ `louvain`（需 networkx） |
| `--resolution` | `1.0` | Louvain 分辨率 |
| `--max-works` | `500` | OpenAlex 单次运行最多拉取论文数，控制用量；达到上限会告警并标记 `truncated_by_max_works`，结果不是全量 |
| `--max-orgs` | `8` | 某人机构数超过该值即 `review_flag=1` |
| `--orcid-policy` | `warn` | `warn` = ORCID 冲突不否决机构匹配（合并+复核）；`strict` = 冲突即拆人 |
| `--name-alias` | — | `"规范名=写法1\|写法2\|..."`（可重复），消歧前把多种姓名写法折成同一人 |
| `--max-nodes` | `600` | HTML 最多节点数，超出按合作强度截断 |
| `--max-edges` | `4000` | HTML 最多连线数，超出保留当前边权最高的连线 |
| `--no-html` | 关闭 | 跳过交互图生成，适合只取 CSV / SQLite 的大批量运行 |
| `--api-key` | `OPENALEX_API_KEY` | OpenAlex API key |
| `--with-titles` | 关闭 | 额外取回 DOI 与题名；默认关闭，只拉作者相关字段 |
| `--alias-map` | 内置模板 | 用 `from_key,to_key` CSV 补充机构别名，可加 `source` 记录依据 |
| `--affiliation-history` | — | 已核实的任职、就读或访学履历 CSV，见[机构时间线](#13-机构时间线) |
| `--ignore-orgs` | 内置模板 | 泛化机构 CSV：`value,note` |
| `--out` | `./faction_output` | 输出目录 |
| `--demo-out` | — | 打印快速上手命令后退出 |

## 2. 典型命令

离线查看单一作者的合作网络。内置的 12 篇虚构论文均包含同一位作者 W. Zhang。

```bash
python scripts/faction_query.py --source demo --author "W. Zhang" \
  --mode seed --min-collab 2 --out ./faction_output
```

按分区 + 年份限定范围：

```bash
python scripts/faction_query.py --source demo --author "W. Zhang" \
  --mode seed --zone Q1 --zone-map assets/zone_map_template.csv --from-year 2019 \
  --out ./faction_output_q1
```

只用单位圈定集合，输出集合内全部派系（不指定作者）：

```bash
python scripts/faction_query.py --source local --input my_papers.csv \
  --org "某大学" --journal "1234-5678" --min-collab 2 --out ./out
```

可选 OpenAlex 补充检索（作者 + 单位 + 期刊 + 分区）：

```bash
python scripts/faction_query.py --source openalex --author "Author Name" \
  --org "University Name" --journal "1234-5678" \
  --zone Q1 --zone-map zones.csv --from-year 2018 \
  --api-key "$OPENALEX_API_KEY" --max-works 800 --out ./out
```

只看某位作者的直接合著者圈：

```bash
python scripts/faction_query.py --source demo --author "W. Zhang" \
  --mode seed --hop 1 --min-collab 1 --out ./out_seed
```

学院级单位可用 `--affil-search` 查原始署名机构。需要限定上级机构时，再加已核实的 `--org-id`。以 `--seed-name` 传入已确认的署名写法。

单次运行即按 6 个阶段顺序执行，全过程写入 `out/run.log`，统计写入 `out/summary.json`。

## 3. 输出字段字典

| 文件 | 关键字段 | 含义 |
|---|---|---|
| `factions.csv` | `faction_id`, `size`, `members`, `core_members` | 派系编号、人数、成员、按加权度排序的核心成员 |
| | `internal_pairs`, `internal_collab_times`, `mean_collab_per_pair` | 派系内合作对数、合著次数总和（含阈值以下边）、平均每对次数 |
| | `top_pairs` | 派系内合著次数最高的 3 对作者 |
| | `cross_faction_collab_times` | 该派系成员与其他派系/未归类作者之间的合著次数 |
| | `edges_kept_by_threshold` | 实际参与构图的边数 |
| `faction_memberships.csv` | `person_id`, `faction_id`, `is_primary`, `is_base`, `supporting_papers`, `community_partners`, `first_year`, `last_year`, `year_counts`, `affiliations`, `work_ids` | 每人每组一行，标明主组和基础成员身份，记录支撑论文、涉及的基础成员数、发表年份和这些论文的署名单位 |
| `faction_cross.csv` | `faction_a`, `faction_b`, `collab_times` | 两端没有共同社区的边，按两端所属社区组合汇总 |
| `coauthors.csv` | `person_id`, `name`, `affiliations`, `n_affiliations` | 消歧后的作者与其全部历史机构 |
| | `papers_in_scope`, `n_coauthors`, `total_collab_times` | 范围内论文数、合著者数、合著次数总和 |
| | `faction_id`, `faction_ids`, `role`, `is_seed`, `review_flag` | 主社区（-1 表示未归类）、全部社区、主社区内的角色、是否种子、是否需复核 |
| `person_affiliations.csv` | `person_id`, `name`, `orcid`, `org_key`, `org_name`, `first_year`, `last_year`, `review_flag` | 每位作者与每个机构一行。年份是观察到该机构署名的首末发表年份 |
| `affiliation_timeline.csv` | `basis`, `relationship`, `start_date`, `end_date`, `ongoing`, `source`, `observed_first_year`, `observed_last_year`, `later_org` | 每人每个机构阶段的有来源日期或估计范围，含原始署名年份和支撑论文 |
| `edges.csv` | `src_name`, `dst_name`, `coauthored_papers`, `role_weight`, `year_counts` | 每一对作者的共同署名论文数、角色加权分与逐年分布 |
| | `kept_by_threshold`, `same_faction` | 是否参与构图、是否属于同一派系 |
| `seed_coauthors.csv` | `seed`, `coauthor`, `coauthored_papers`, `coauthor_faction_ids`, `kept_by_threshold` | 种子作者的全部合著者及其全部社区，含只合作一次者 |
| `merge_log.csv` | `decision`, `evidence`, `detail` | 每次身份判定的依据，用于审计与回滚 |
| `network.html` | — | 自包含离线交互图，节点底色为主社区，彩色外圈与悬停提示显示多重归属 |
| `factions.db` | — | SQLite 库，`faction` 为主社区，`faction_membership` 记录每人每组及证据 |

`merge_log.decision` 取值：`orcid_match`（ORCID 命中）、`org_match`（机构交集命中，主规则）、`orcid_conflict_merged`（ORCID 冲突但机构命中，仍合并并标记复核）、`ambiguous`（多个同名候选，取交集最大者并标记复核）、`orcid_conflict`（无机构命中且 ORCID 冲突，新建）、`new_person`（新建）、`unresolved`（无可用机构证据，新建）、`no_org_unique`（双方均无机构且同名候选唯一，合并）。

## 4. 解读注意

- **先找合作组。** 默认作者分析使用 `seed` 模式，按合著者之间达到阈值的边识别基础社区，避免检索对象把各组连成一个团。用 Louvain，缺依赖时用加权标签传播。相同单位可以有多个组，一个组也可跨单位。编号按基础组规模排序，仅在本次运行内有效。
- **再判断重叠成员。** 对目标和邻域中的每位作者，逐组检查其与基础成员共同署名的不同论文。至少 `max(2, --min-collab)` 篇且覆盖至少两位基础成员，可加入该组。一次大型合著或单一联系人只能提供候选线索。各组同时基于基础成员判定，避免重叠逐轮扩散。主社区供旧表及图布局使用，基础成员保留原组，其他人按支撑论文数、合作者数取主组。
- **解释跨机构经历。** 若转单位前后分别与两组有足够合著，就保留两组归属。每组报告支撑论文年份、署名机构和篇数。任职、署名及估计时间按[机构时间线](#13-机构时间线)解读。有明确来源的导师关系另行呈现。
- **读统计。** 组内合作对至少有一端是本组基础成员，包含低于构图阈值的边。同一合著可支持多个社区的归属，全网作者和论文总数按去重结果读。未归组包括合著证据不足或邻域之外的作者。
- **署名计权。** 检索对象与合作者双方均为独立一作或独立通讯时计 3 分，双方均有一作或通讯角色且至少一方仅为共同角色时计 2 分，其余计 1 分。每对每篇只计一次。[署名细则](#12-署名角色与权重)

## 5. 故障排查

| 现象 | 原因与处理 |
|---|---|
| `No works matched the scope` | 范围过窄；逐个去掉 `--zone` / `--org` / `--journal` / 年份定位；检查 `run.log` 中 `Scope filtering excluded` 计数 |
| 指定 `--zone` 后论文大量消失 | 真实数据缺少分区信息；提供 `--zone-map` 或在输入 CSV 中补 `zone` 列 |
| `--zone` 看似无效 | 分区值大小写与空格被归一化，但必须与映射表 `zone` / `quartile` 列的字面值一致（如 `Q1` 与 `1区` 不同） |
| OpenAlex HTTP 402 / 429 | 记录该路受限，继续作者档案、Crossref 和对应语种索引；已有已授权 key 时可用于补充 |
| 作者被拆成两个人 | 主规则要求至少有一个历史机构重合；补 `--alias-map` 映射机构异名，或在 `org_ignored_template.csv` 中移除被排除的机构，必要时用 `--author-id` 指定 |
| 同名不同人被误并 | 把造成误并的大伞机构加入 `--ignore-orgs`；检查 `merge_log.csv` 的 `evidence` 列 |
| `--community louvain` 回退 | 未安装 networkx；`pip install networkx>=3.0`，或改用默认 `labelprop` |
| HTML 图节点过多 | 用 `--max-nodes` 截断，或提高 `--min-collab` 减少弱边 |
| 结果明显少于期刊全部文章 | 多半命中默认 `--max-works 500` 被截断；查 `run.log` 的 `TRUNCATED` 告警与 `summary.json` 的 `truncated_by_max_works`，调高上限或按年份分批 |
| 浏览器打开网络图很卡 | 边数过多；提高 `--min-collab`、降低 `--max-nodes` / `--max-edges`，或直接用 `--no-html` 只看 CSV |
| 中文姓名被拆开 | 同名不同写法（如拼音/中文）视为不同 `name_key`；在输入前统一写法，或用 `--author-id` / ORCID 锚定 |
| 只能拿到 100 篇 / HTTP 401 | OpenAlex 的 `cursor` 分页从第二页起要求免费 API key；脚本无 key 时自动改用 `page` 分页（日志显示 `paging=page`）。若仍只有 100 篇，检查 `--max-works` 与当日额度；超过 1 万条必须设 key 或分批 |
| 学院 / 系 / 实验室查不到机构 | 二级单位通常没有 OpenAlex 机构 ID；改用 `--affil-search "College of ..."`，并配合 `--org-id <大学ID>` 收紧 |
| 中文姓名锚定到完全不相关的人 | `/authors` 模糊检索会返回 `Wei-Guo Zhu` 之类结果；脚本已用机构 ID 限定候选并只取精确同名。更稳妥的做法是改用 `--seed-name`，完全不绑作者 ID |
| 目标作者被拆成多个人 | 多为 ORCID 冲突或机构证据不重合；默认 `warn` 策略已缓解，仍出现时查 `merge_log.csv` 的 `new_person` / `orcid_conflict`，补 `--alias-map` 或用 `--seed-name` 重新跑 |
| 派系只有一个超大社区 | `labelprop` 在密集合作网络上容易过度合并；改用 `--community louvain`（需 networkx）、提高 `--min-collab` 或缩小检索范围，并对比 `run_id` |
| 结果里出现同名重复行（如两个 `Hui Zhang`） | 消歧拆成了两个候选但仍各自与种子合著；合计次数通常正确，需按 `merge_log` 判断是否同一人 |

## 6. 规模与耗时实测

本地计算（合成数据，12 个合作团体、600 位作者、每篇 4–6 位作者）：

| 论文数 | 长表行数 | 合作对数 | 派系数 | 本地耗时 |
|---|---|---|---|---|
| 1,000 | 5,994 | 7,518 | 14 | 0.12 s |
| 5,000 | 30,040 | 14,265 | 12 | 0.56 s |
| 20,000 | 119,915 | 14,700 | 12 | 2.39 s |

数据量 ×20、耗时 ×20，为近线性扩展。带不带 HTML 的命令行耗时几乎相同（HTML 只是字符串生成），渲染成本发生在浏览器端：力导向布局步数已按节点数自适应（60–320 步），并受 `--max-nodes` / `--max-edges` 限制。

OpenAlex 实时检索的耗时估算（每页 100 篇、页间 0.15 s、单请求约 0.5–2 s，含 `authorships` 大字段）：

| 论文数 | 请求数 | 估算耗时 |
|---|---|---|
| 500（默认上限） | 5 | 约 3–10 秒 |
| 5,000 | 50 | 约 0.5–2 分钟 |
| 20,000 | 200 | 约 2–7 分钟 |

该估算不含网络抖动与 429/402 重试退避。计费额度见 `references/data_sources.md`。

**token 开销**：脚本在本地执行，元数据不进入模型上下文；模型只看到命令、十几行摘要日志和附件路径。文章数量不显著影响 token。唯一会随规模线性增长的情形是要求把完整名单或论文全文贴进对话——应改为汇报摘要 + 附 CSV。

**只取作者信息**：默认 `select` 为 `id,publication_year,authorships`，不取摘要、全文、题名、DOI；仅在指定期刊/分区过滤时追加 `primary_location`，仅在 `--with-titles` 时追加 `doi,title`。本地 CSV 的 `title` / `doi` 列可整列留空。这既减小响应体积、降低 API 用量，也保证不会把论文内容带进上下文。

## 7. 核对真实结果

核对原始署名、作者位置、机构和合著次数。检查重点作者是否因中英文异写被拆开，以及同名者是否被误并。报告社区时记录 `run_id`、算法与参数。

## 8. 多源检索与漏检排查

1. **先读取已有记录。** 复用证据表、参考文献管理器、作者或机构成果导出。把公开简历、历任机构成果目录及本人档案作为独立对账基准。通过已核实论文定位 ORCID、Google Scholar、WoS 或 Scopus 作者档案；同一人有多个档案时逐个核实后合并候选。
2. **并行检索网页和数据库界面。** 英文查 Google Scholar 公开档案及 `author:"姓名"`、ORCID Works、机构库、出版社和学科索引。有授权时用 WoS 和 Scopus 界面检索并分批导出。中文查知网、万方、维普、国家科技期刊平台、期刊目录和机构库。用中文名、原始英文署名、姓名异写、历任单位和旧合作者分别组合，并查无单位过滤的已核实作者档案。网页分页用来源提供的界面。
3. **分段处理过宽或截断的结果。** 按职业阶段和年份分段，遇结果上限时缩短时间段或按刊物、会议、合作者分批；交界年份允许重叠，合并后去重。记录每批显示总量、实取量、可访问范围及缺页。早期或无 DOI 的论文可从卷期目录、会议论文集、机构库，以及已核实论文或公开简历的参考文献回查。无单位或无年份的候选走档案或题名路线。
4. **核验并对账。** 先按 DOI、数据库入藏号或稳定来源记录编号去重。缺编号时用原文题名、年份、卷期页和署名核对，把同一研究的预印本及正式版对应后按既定范围计数。对各来源独有项和独立清单的缺失项逐条核查，对缺口用另一来源补查。只有明确核实的署名归入作者。报告已确认篇数、可核对清单的命中数量及未覆盖来源、时间段或文献类型。

```bash
python scripts/collect_ris.py --source "Web of Science" --input batch_1.ris --input batch_2.ris --out wos_candidates.csv
```

RIS 导入在本地运行，保留逐批原始候选及 DOI、来源编号、作者顺序、卷期页。`complete_record=0` 标记缺少结束标签的记录，核对原导出后再纳入。CSV 等已有导出可直接按证据表字段整理。以出版方原始署名核对作者和单位，RIS 的作者列只作候选证据。[Google Scholar 搜索帮助](https://scholar.google.com/intl/en/scholar/help.html) · [WoS 导出说明](https://webofscience.help.clarivate.com/en-us/Content/export-records.htm) · [Scopus 检索结果](https://service.elsevier.com/app/answers/detail/a_id/11423/)

### PubMed 网页与批量导出

生物医学领域先用作者全名 `[fau]` 及连字符等已知异写检索。将现校、历任学校、附属医院和历史院名用 `OR` 组合。再做一轮放开单位、用旧合作者或疾病与研究方向限缩的检索。缩写 `[au]` 作为补查；题录同时命中姓名和 `[ad]` 时，仍需逐条核对该作者本人对应的机构。将来源独有项按 DOI 或 PMID 补查，特别是索引未收录的文章、期刊来信和在线先发。

在结果页选用 **Save → PubMed** 或 **Send to → Citation Manager** 批量保存。单篇页面访问失败时，直接从可访问的结果页下载标记文本或保存 PubMed 格式页面，保留查询显示总数与各批条数。导入文件可以是 `.nbib`、标记文本或带标记正文的已保存 HTML。收录来源及缺页按查询登记。[PubMed 搜索与导出帮助](https://pubmed.ncbi.nlm.nih.gov/help/)

```bash
python scripts/collect_pubmed.py --input batch_1.nbib --input batch_2.txt --out pubmed_candidates.csv
```

导出与证据表同列，保留原署名顺序、逐作者机构、PMID、可核实的 DOI、文献类型及勘误和撤稿的关联题录。不同批次的重复记录保留供对账。历史题录可能只有第一作者的单位，缺项用原刊核对。候选表的人员归属与角色待核，按[成果版本与归属](research_outputs.md#成果版本与归属)筛查后再建图。

`collect_profiles.py`、`collect_crossref.py` 和 `collect_wide.py` 留作可选 API 入口。普通检索跳过这些入口。确需补查时先复用已有采集结果，再按已核实标识定点查询。

## 9. 跨机构检索与归并

每位研究者单独执行以下步骤。已有结果时，从 `person_affiliations.csv` 查找每个单位，沿“姓名或已核实异写 + 单位”分别回查目标及相关合作者。没有建图时使用 `paper_authorship.csv` 或 `output_evidence.csv`。图内人员编号仅用于本次结果关联，跨次归并回到原论文署名、ORCID 或履历证据核实。

1. **核实身份。** 从机构主页、个人简历、双语登记或 ORCID 核对全名、曾任机构和至少一篇论文的作者位置。区分实际作者单位、刊物主办方、其他作者单位和招生阶段。报名或初审记录仅作为候选线索。身份尚有歧义时，列出候选及各自的署名证据，缺少能定位到同一人的证据时，只问一项最能区分的线索，如二级单位、方向、导师或已知成果。
2. **并行收集。** 按上节用核实的 ORCID 和作者档案枚举候选，以每种原始署名和历史机构独立查询。作者 ID 和 ORCID 命中保留为候选，即使论文中没有熟悉的姓名写法。原始署名路线须在同一条署名上匹配完整姓名写法。
3. **沿旧合作者追查。** 从公开简历、学位论文导师栏、机构主页和已核实成果梳理就读与任职阶段、导师和常见合作者。每个阶段用目标的中英文姓名配合已核实的导师或合作者、历史机构或阶段年份回查，放开当前单位过滤。用双人姓名查学术搜索、中文库、机构成果页和出版社。新确认的署名写法、作者 ID 或遗漏阶段可以启动下一轮，已做过的组合跳过。没有新增可核实的署名锚点或未覆盖的阶段线索时结束追查。
4. **核实跨机构连续性。** 核对新旧成果的原始署名与位置。目标姓名或已确认异写一致，旧合作者也核实为同一人，并且署名时间和学业或任职轨迹吻合时，可用这组证据归并不同机构的署名。必要时对照论文、机构页和注册记录中的同一公开学术联系方式，只在结果中记录证据来源和匹配理由。若旧合作者仅同名、目标同名者也与其合作、出现 ORCID 冲突或同一论文有两个独立署名，保留待核并查独立来源。在 `identity_source` 保留新旧成果编号、共同作者及履历证据，同一人的已核实署名用同一 `person_id`。师生或指导关系单独列双方、单位、阶段和明确记载该关系的公开来源。共同署名仅作为合作证据，导师关系本身不计论文边权。
5. **补齐独立来源并对账。** 结合机构成果清单、出版社、专业索引和中文数据库补项。按 DOI、PMID 等标识去重，缺标识时核对题名、年份和署名，再统一 `work_id`。每位作者的多条机构行使用同一个 `author_order`。直接运行本地长表流程时，给各阶段核实的署名分别传入 `--seed-work WORK_ID@POSITION`，用 `--reference-works` 与独立的 `work_id,source` 成果清单逐篇对账。已证实但未采集到的成果从独立来源补入。

```bash
python scripts/faction_query.py --source local --input combined.csv \
  --seed-name "Demo Author" --name-alias "Demo Author=Author Demo" \
  --seed-work LOCAL_WORK_ID@2 --reference-works known.csv \
  --mode seed --community louvain --out ./out
```

- `--seed-work` 使用长表实际输出的 `work_id` 加上 `@位置`，位置从 1 开始。核实不同任职阶段的署名后可重复指定。统计范围外的已知署名可参与本地归并，合著次数按最终期刊和年份范围统计。
- `reference_coverage.csv` 区分已纳入（`counted`）、范围外（`outside_scope`）、输入缺失（`missing_from_input`）和归属待核（`unresolved_attribution`）。`summary.json` 的 `reference_coverage` 汇总独立清单的核对状态。逐条处理已知缺失、复核 ORCID 冲突，并记录仍无法查证的年份、文献类型或受限来源。只有查询状态、署名核验和独立清单对账均满足时，才报告已核对来源和范围内的覆盖情况。

使用可选的 `collect_wide.py` 时，以 `--known-work` 提供 `DOI@位置` 或 `OpenAlex论文ID@位置`，用 `--across-affiliations` 放开现单位限制。检查 `*_coverage.json` 的各路线分页状态及 `incomplete_bylines`。姓名过滤可能跨多个署名命中词组，采集器回查完整姓名并补取超过列表接口长度的署名。作者 ID 仍需逐条核验。[署名搜索](https://help.openalex.org/api/searching/) · [OpenAlex 署名字段](https://help.openalex.org/data/authorships/)

## 10. 双语搜索与备用源

收到单语姓名时，先用输入姓名配合已知机构、研究方向、ORCID 或成果编号查公开网页。高校或研究机构的个人主页、实验室介绍、作者公开简历或出版方页面若明确把中英文姓名指向同一位作者，直接采纳页面拼写，记录来源 URL，并立即用两个名字并行检索。两个语种的个人页面也可通过相互链接、同一 ORCID 或同一篇成果的署名位置对齐。核实的是姓名对应关系，成果归属仍逐条核对。

公开资料未能确认另一语种时，用拼音和常见异写扩展候选，按证据继续回查。已确认且在当前数据范围内排除了同名冲突的写法可传入 `--name-alias`。遇到同名冲突时，用具体署名的 `person_id` 和 `identity_source` 记录对应关系。

- **中文输入。** 保留汉字，生成无声调拼音、姓在前和姓在后两种顺序。有多个给名音节时，再试连写、分写或连字符。以姓名加单位查询作者主页、出版社署名和 ORCID，补入来源实际使用的英文拼写。多音字或地区拼写先作为检索候选。
- **拉丁字母输入。** 保留原写法，结合单位全称、已知 DOI 或共同作者定位身份。从同一机构的中英文主页、ORCID 或同篇论文的双语署名反查汉字。用同一 ORCID 或同一篇论文的同一署名位置核对。若仍找不到汉字，继续用已核实的拉丁字母拼写。机构也优先采用官方中英文名和历史名称。
- **按机构逐人反查。** 论文未列另一语种姓名时，对检索对象和纳入结果的合作者分别用原始署名或候选姓名加机构的中文全称、学院或实验室、研究主题、已核实合作者检索。优先查看机构官网、团队成果新闻、会议议程和项目或获奖公示，再查相关中文期刊、专利及公开履历。有多段署名机构时分别查。双语同页、同一 DOI 的相同署名位置、同一 ORCID 可直接对齐。跨页时，用具体成果、项目或多位已核实合作者与机构、时间及方向交叉核对。同一单位和相同拼音仅用于发现候选。将核实的中文名写入 `canonical_name`，原始署名保留在 `raw_name`，来源和对应依据写入 `identity_source`。证据不足时以原署名显示，有实际歧义的候选留待核。
- **区分原始署名与档案。** OpenAlex 采集优先保留论文原始姓名，宽口径表另存档案名和档案 ORCID。当原始姓名与档案名不一致且没有原始 ORCID 时，档案 ORCID 用于回查。同一成果的双语署名用相同成果编号与同一位置对齐，再以已核实的人物编号、ORCID 或已确认且在该数据范围无同名冲突的别名保留两种来源中的机构和角色。姓名拼音、缩写和顺序变体用于召回候选。
- **归并机构译名。** 先用中文、官方译名和论文常见译法分别检索。若完整专名和地点、上级单位或地址能唯一对应，允许缩写、语序和轻微翻译差异，未查到机构编号时也可登记别名。共享简称、同名分校、附属医院与上级院校有多个可能时，按各自单位保留并核对机构证据。把每个确认写法写入 `from_key,to_key,source` CSV，目标用同一个 `name:<规范名称>` 或已核实的 `id:<机构编号>`。机构映射同时用于本地筛选与归并。某个规范名称只对应一个已观察到的机构编号时，纯名称记录可沿该编号归并。若同一规范名称对应多个编号，保留各编号分别处理。
- **网页发现。** 分别用中文和英文检索“姓名 + 单位”“姓名 + 论文题名或 DOI”，定位机构主页、出版社、会议和成果清单。Google Scholar 可用 `author:"姓名"` 或完整题名查找，结果回到来源逐篇确认。批量候选优先用来源提供的导出。[Google Scholar 搜索帮助](https://scholar.google.com/intl/en/scholar/help.html)
- **独立采集。** 用[默认多源流程](#8-多源检索与漏检排查)分语种扩展，按档案编号、DOI 和原始署名核对各源命中。

## 11. 仅姓名检索

适用于只有姓名、缺少单位或可唯一定位作者的证据的查询。

1. **发现并区分同名者。** 按第 10 节生成双语查询，查找各候选的研究方向、单位履历和 ORCID 或可核实的论文署名。若用户或当前任务给出了目标领域，优先在该领域比较。若领域未定，保留能核实的不同领域候选，并在结果中标出领域。姓名相同的候选各自按第 9 节核对，分别维护来源和署名锚点。
2. **以成果数排序。** 按同一年份、文献类型和用户指定范围，统计各人经消歧后确认归属的去重论文。仅有姓名命中或归属待核的论文不参与计数。成果数唯一最高者列为默认对象。来源覆盖不全时标注「已核实至少 N 篇」。若并列或缺口足以改变首位，列出候选和已核实数量，保留首位待定。
3. **分人展示。** 已核实成果大于 10 篇的每位候选都可单独展示网络。若有多人达标，按已核实成果数降序分别列出，使用各自的 `--seed-work`、`--mode seed` 和独立 `--out` 目录。没有人达标时，给出默认对象或并列候选的成果与合著者清单，用 `--no-html` 跳过独立网络。候选摘要注明研究方向、单位、已核实成果数和覆盖缺口。

例如，同名候选分别有 24、12、10 篇已核实论文时，24 篇者为默认对象，前两人各有一张网络，10 篇者只在候选摘要中列出。

## 12. 署名角色与权重

按论文和具体署名记录 `author_order`、`is_first`、`is_corresponding` 与 `role_source`。角色字段可填 `sole`（明确独立）、`shared`（明确共同）、`yes`（已确认角色）、`no`、`conflict` 或留空。先核对出版社 HTML 或正式版 PDF 中作者旁的符号及其对应脚注。贡献声明中的相同分工、未指向具体作者的同等贡献脚注或末位署名，均只作线索。存在可能改变首位作者档位的脚注、却无法绑定具体作者，或来源冲突时，标为 `conflict`，保留实际署名位置，待核角色按普通署名计分。单个 `yes` 且无共同标记时按已记录的单人角色计分。

OpenAlex 的通讯作者正向标记会随采集结果保存。Crossref 采集器保留首位线索。PubMed 与出版社的角色标记粒度可能不同。出版社的明确署名和勘误优先，其次用能指到同篇文献和作者的机构成果页或数据库记录。通讯缺字段或只有数据库默认否值时，保留未知。优先补查目标本人及会改变主要合作边权的角色。[OpenAlex 署名字段](https://help.openalex.org/data/authorships/) · [Crossref 作者顺序与角色](https://www.crossref.org/documentation/schema-library/markup-guide-metadata-segments/contributors)

每篇论文先按每个人的最高已确认角色定档。独立第一或独立通讯为 3，只有共同第一或共同通讯为 2，普通署名或角色待核为 1。至少一端是检索对象时，这对作者取两端较低的一档，每篇只计一次。比如检索对象是独立一作，其与独立通讯作者的边计 3，与仅共同通讯的作者计 2，与普通合著者计 1。检索对象只是普通合著者时，其各条边都计 1。两端都不是检索对象的边每篇计 1。未指定检索对象时，每条边按实际合著篇数计权。

边权跨论文累加，用于分组、连线排序与绘制。最低合著阈值仍按实际篇数，默认 2 篇。`--edge-weight papers` 可切回按篇计权。

- `authorship_roles.csv` 逐条列出角色、来源及各人的署名档位 `role_score`。两人的实际合作边权见 `edges.csv`。
- `edges.csv`、`seed_coauthors.csv` 同时给出 `coauthored_papers` 和 `role_weight`。`coauthors.csv` 汇总每位作者的第一、通讯、兼任和普通署名篇数。兼任同时计入第一与通讯两列，另有兼任列可核对重叠。
- `summary.json` 的 `role_coverage` 按角色报告确认、未知和冲突的署名数，`edge_weight` 记录构图口径。

## 13. 机构时间线

- **有明确履历时记录实际日期。** 查官方履历、任免公告、机构或本人公开简历，以及 ORCID 的任职、教育和其他活动页面。任职、就读、访学和兼职分别记录。同一人可以在同一时期和多个机构有关系。保留来源精度，只有年份就填 `YYYY`，明确到月份或日期时填 `YYYY-MM` 或 `YYYY-MM-DD`。明确仍在任才填 `ongoing=yes`，结束日不详则留空。相互矛盾的履历先回查来源，保留无法核实的日期缺口。[ORCID 任职日期字段](https://support.orcid.org/hc/en-us/articles/360006894694-Metadata-in-the-Employment-section)
- **只有署名时估计历史机构范围。** 默认对身份已锚定且未按期刊、机构、年代等缩小范围的本地目标论文估计。旧单位至少在两个不同发表年出现。其末次署名之后，同一后续机构至少出现在三个不同发表年的论文中，且最晚证据与旧单位末次署名至少相隔三年。达到条件时，以旧单位首末署名年份填写约略范围，同时保存后续机构和支撑论文。双重署名仍计为旧单位的出现，空单位或未知年份无从支持转换。推断反映论文中可见的历史关联，兼职、滞后发表等情况通过履历核对。用于沿历史机构补查时同时查看相邻年份和无单位过滤的作者档案。
- **交付字段。** 以 [`assets/affiliation_history_template.csv`](../assets/affiliation_history_template.csv) 录入有来源的履历，用 `--affiliation-history` 传给 `research_outputs.py --network` 或 `faction_query.py --source local`。使用证据表的 `person_id` 作为 `verified_person_id`，或使用已核实的 ORCID。机构填写名称或标识，采用与论文相同的机构别名映射。每个机构阶段一行，并为 `relationship` 填写 `employment`、`education`、`visiting`、`appointment` 等明确关系。没有论文署名的已核实机构阶段也可入表。
- **解读输出。** `affiliation_timeline.csv` 的 `documented` 表示来自履历，`estimated` 表示署名推断，`observed` 仅填已观察到的年份。有明确履历的机构优先显示履历，同时保留论文署名起止年。合作者的任职时间可以用独立履历补全。若希望推断某位合作者的机构历史，按该作者完整可查的论文范围单独检索。各组合作期仍按实际合著年份统计。
