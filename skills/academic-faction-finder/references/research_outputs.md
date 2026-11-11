# 全面成果检索

## 并行检索

先为每位研究者建立身份档案，包含已确认的中英文姓名、ORCID、已核实署名位置、历任机构及其时间。按 [双语搜索与备用源](workflow.md#10-双语搜索与备用源) 优先从公开网页确认中英文姓名并记录来源，再补充候选写法，并以姓名、ORCID、历任机构、共同署名者和已知成果编号扩展。当前单位用于定位作者。若用户限定单位、领域、年份或文献类型，再应用对应的统计条件。

| 路线 | 操作与核验 |
|---|---|
| 英文及国际论文 / SCIE | 用已有导出、Google Scholar 与 ORCID 公开档案、机构和出版方目录及适用的专业索引查论文。获授权时同步查 WoS、Scopus 界面和历任机构。保留 DOI、数据库编号、年份、文献类型和完整署名。SCIE 逐篇用 WoS 记录或明确覆盖该论文发表年卷期的证据核验，缺证时标记待核。期刊当期收录状态只作线索。 |
| 中文期刊 | 分别查知网、万方、维普，结合期刊官网、CSCD 和机构成果库补项。先用作者中文全名、繁简字和历史单位查，再按共同作者、题名或 DOI 回查。取论文的实际刊载语言。中文 SCIE 论文同时加两个标记，论文总数按一篇计。 |
| 专利 | 从国家知识产权局按发明人、申请人、历史机构和申请号检索。跨境成果用 WIPO PATENTSCOPE 和其他相应专利局核验。保留申请号、公开号、授权号、同族号、类型及有证据的公开或授权状态。按同一司法辖区的申请号合并该申请的公开与授权版本，同族号单列。分开发明人、申请人与专利权人。 |
| 软件著作权 | 用中国版权保护中心登记公告、登记证书或经授权的档案查询，按软件全称、登记号、单位及历史名称找记录。用机构成果库和项目公示补查单位登记的软件及可证实的个人开发角色。按登记号去重，保留软件版本和自然人或机构权利人。个人归属及合作边须有对应的具名角色依据。 |

[Web of Science 核心合集](https://webofscience.help.clarivate.com/Content/wos-core-collection/wos-core-collection.htm) · [维普作者检索](https://www.cqvip.com/) · [CNIPA 专利检索](https://www.cnipa.gov.cn/art/2023/2/13/art_3166_182074.html) · [WIPO PATENTSCOPE](https://www.wipo.int/documents/d/patentscope/docs-en-patentscope_user_guide.pdf) · [国家版权局软件登记说明](https://www.ncac.gov.cn/xxfb/flfg/bmgz/202410/t20241015_869486.html)

先逐个消化机构简历、成果目录、已知 DOI、专利号和软著登记号。对这些独立已知成果另建对账表。再按成果类型、年代和曾任机构补查薄弱段，核对结果分页、署名和归属。受订阅、登录或导出权限限制时，使用用户已授权的访问或用户提供的导出，并从可访问的机构和出版社来源继续查。

每轮生成 `source_coverage.csv`，按来源记录 `route,source,query,years,status,reported_total,retrieved,attributed,gap`。`reported_total` 记录查询显示或导出注明的总数，无法获取时留空；`retrieved` 记录实际取得的来源条目，`attributed` 记录该路线确认归属的独立成果。不同路线会重复命中，成果总数按全局去重计算。状态用 `exhausted_for_query`、`partial`、`inaccessible` 或 `not_checked`。独立对账使用另有出处的书目或成果目录；同一导出整理出的候选用于记录导入量。覆盖结论对应已核对的来源、条件和时段。

## 成果版本与归属

- **论文。** 先核对文献类型与 DOI 或 PMID。勘误按关联记录修正原作的作者、单位或角色，证据保留原文与勘误链接，按一项成果计。已证实同一工作的预印本与正式版合并，单独预印本、撤稿记录或待核版本在覆盖报告中列出。病例报告、综述和期刊来信按实际类型记录，独立发表且归属已确认的条目可纳入，报告可核实的类型。在线先发用公开上线日期判断是否纳入，正式卷期已确定时保留正式卷期年份。
- **收录。** 区分 Web of Science 的单篇入藏记录、覆盖该发表年卷期的期刊证据及仅能查到的当前期刊状态。前两项注明依据和层级；只有当前状态时，历史收录待核。PubMed 命中仅说明该条书目可检索。
- **补充线索。** 临床研究注册、项目公示、录取和答辩安排可支持双语身份、关系或时间线，按来源所载角色记录。单独的注册或答辩记录留在报告或覆盖表。媒体提及的专利、软著及缺少编号或具名角色的记录留作待核线索，取得可核对的书目或登记及署名后再计数和建边。各类成果均保留来源链接。

## 中英文姓名和署名对齐

1. **扩展检索写法。** 中文保留原字形并查繁简形式、拼音顺序、连写、连字符、分写和缩写。英文保留来源原写，从机构双语主页、同一论文或专利记录反查中文姓名。把高频重名写法和每个候选人的身份分开记录。
2. **核对同一记录上的同一角色。** 用 DOI 或等效论文编号对齐出版社的双语作者表，用申请号对齐同一专利的中英文发明人表，用登记号对齐软著资料。确认作者表顺序和具体署名位置后再确认配对。对跨机构或更名情况，查署名 ORCID、个人简历或明确列有该成果的机构页面。以姓名、单位任职时段及共同署名者定位候选，最后记录能把该署名连到个人的来源。
3. **逐条写入确认结果。** 每条原始署名保留 `raw_name`、角色、位置和 `source`，已核实的署名再填稳定的 `person_id`、`canonical_name`、`identity_source`。同一拼音可以对应多个 `person_id`。在证据无法区分时保留未归属记录。整批 `--name-alias` 只用于在当前数据范围内确认无同名冲突的异写。

## 证据表和输出

以 `assets/research_outputs_template.csv` 为长表。每行是一条来源中的一项成果署名或角色。仅知登记号或机构成果时也可登记，将未知个人留空。

- `result_type` 取 `paper`、`patent` 或 `software`。`result_id` 采用去重后的 DOI、期刊记录键、带辖区的专利申请号或软著登记号。缺 DOI 时先用题名、年份、卷期和署名核对，再给同一成果统一记录键。保留 `source_record_id` 原始编号或版本；存在多种权利人名单时按名单版本分别记录。
- 论文角色为 `author`，`position` 从 1 开始。同一署名列多个单位时，按 `org_name`、`org_id` 分行，保持 `result_id`、`position` 和已核实的 `person_id` 一致。成果和合著按论文去重。另用 `is_first`、`is_corresponding` 和 `role_source` 记录同一署名的第一或通讯身份，共同第一和共同通讯分别给各位作者标记。[署名角色规则](workflow.md#12-署名角色与权重)
- 专利角色为 `inventor`、`applicant`、`patent_holder`。软著角色为 `developer`、`copyright_holder`。`entity_type` 取 `person`、`organization` 或 `unknown`。只知道有该成果时，角色和署名留空，实体类型填 `unknown`。
- `language=zh` 表示中文全文。`chinese_journal` 取 `yes`、`no` 或 `unverified`，确认后填 `chinese_journal_source`。论文的 `index_status` 取 `scie`、`not_scie` 或 `unverified`，前两项均填写 `index_source`。刊物类别、正文语种和 SCIE 收录分别记录。
- 专利类别及来源所示状态填 `result_subtype`、`status_as_recorded`，软著版本填 `software_version`。
- 用单独的 `result_type,result_id,source` CSV 记录经独立来源核实的已知成果。对账时保留尚未采到的编号。软著有机构权利人但缺少个人证据时，归属仍为待核。

```bash
python scripts/research_outputs.py --input evidence.csv --target researcher-01 \
  --reference known_outputs.csv --network --out ./outputs
```

已核实的机构译名可通过 `--alias-map org_aliases.csv` 传给建图流程。数据范围内已排除同名冲突的作者异写可通过 `--name-alias "规范名=写法1|写法2"` 同时用于对齐同一论文的署名证据和建图。逐条核实的 `person_id` 用于区分共享同一拼音的不同作者。

`research_outputs.csv` 列出专利和软著的来源及归属状态。原始署名与论文收录证据保存在工作文件 `output_evidence.csv`。待核与缺失项见 `output_reference_coverage.csv` 和 `output_summary.json`。`typed_collaborations.csv` 逐角色列出同一来源记录上已确认的共同作者、共同发明人、共同开发者和自然人共同著作权人及对应成果编号。跨来源共用角色表时，先把证据对齐到同一份署名或登记版本。

`--network` 从已核实署名自动选种子，写入 `paper_network/`。仅姓名检索时附加 `--network-min-papers 11`，成果不足时照常导出成果与合著明细。以当前 `output_summary.json` 中的建图状态为准。若用户限定期刊、年份或图参数，省略 `--network`，使用 `paper_authorship.csv` 和已核实的署名位置运行 `faction_query.py`。从 `faction_memberships.csv` 核对每位作者的全部社区、合作年份和支撑论文。`--affiliation-history` 接收有来源的实际机构阶段，结果见 `affiliation_timeline.csv`。[机构时间线](workflow.md#13-机构时间线) 发明和软著关联在结果中分层呈现。

`paper_authorship.csv` 只含已经归属目标的论文。它携带 `verified_person_id`、`verified_name` 和 `identity_source`，供图脚本按已核实身份跨语种和跨机构归并。原始署名仍可按论文流程核对。

## 按需导出论文清单

用户明确要求逐篇列出或导出论文时，核对范围内所有已确认归属的论文，再加 `--paper-list`。仅要清单时可省略 `--network`。默认交付合作分析时，署名证据表用于对账与建图，用户侧报告只给论文统计。

- 以出版方最终版本、DOI 注册元数据或期刊原始记录核对年份、标题、DOI 和署名顺序。优先使用正式卷期年份，只有在线发表时采用已核实的在线年份。双语题名采用同一版本的原始题名。DOI 与题名及署名对应后，才用 `doi:<值>` 作为 `result_id`。
- 核实完整作者表后，在该来源记录的署名行中填写 `author_count`。按同一 `source`、`source_record_id` 和连续署名位置核对作者数，保留原始排序。不同来源的部分名单不拼接。年份、标题或作者表的差异仍无法核实时，对应列留空。DOI 无法确认时留空，并用其他已核实记录键保留该篇论文。
- `paper_list.csv` 每篇一行，包含年份、作者、标题、DOI、目标的一作与通讯标记及来源。目标担任一作或通讯的论文列在前面，含共同一作、共同通讯。两组分别按年份降序，缺年份的论文排在本组最后。角色待核的论文放在后组，角色字段留空。
