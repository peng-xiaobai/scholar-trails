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
2. **核对同一记录上的同一角色。** 用 DOI 对齐双语作者表的同一署名位置，用申请号对齐专利发明人，用登记号对齐软著人员。无直接对应时，从同一批论文的共同作者、署名单位、时间与主题缩小范围，再核对能连到个人的公开来源。常见拼音、共享一组共同作者或任职单位相似时保留候选，直至排除其他可能身份。
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

## 署名单位补录

先打开 DOI 跳转后的原刊，展开 `Authors and affiliations` 或作者弹层。遇到 403、页面缺单位或没有 DOI，就用 Google 搜完整英文题名，打开同篇的免费网页或 PDF，例如机构仓储和公开作者稿。仍缺某位作者时，用完整题名加该作者的英文署名继续搜。核对题名或 DOI，再按作者顺序、上标和脚注逐一匹配英文单位。录入单位原文与能复核该对应关系的链接。个人主页和其他论文可用来找线索，只有同篇记录可用于补录单位。Crossref 可辅助核对作者名单及顺序。仍有缺口时记录具体作者和已查页面。

用 `affiliation_basis=paper` 标记正式版作者栏及 PDF 的署名，`source` 填来源。使用同篇索引的逐作者单位时，先交叉核对作者与单位的绑定，再填 `same_work`，并在 `affiliation_confirmation` 记录能支持该绑定的独立来源 URL。单一索引结果、仅核对 DOI 或作者顺序的记录填 `index`。其他论文与任职记录中的单位填 `other`。后两类只保留在证据表。旧表仍可用于成果对账，建图前须补录核验字段。保留所署院系层级，同一署名里的学校与下属院系作为一条记录。

对每位作者核实完整署名后，在对应证据行填 `affiliation_complete=yes` 和正式作者数 `author_count`。建图前先运行成果脚本生成 `affiliation_gaps.csv`，按论文和作者位置逐项回查、回填、重跑对账。缺口表清空才报告单位核验完成。作者必须在该篇有已核实的署名单位才进入该篇的网络；合著连线的两端都须通过这项核验。论文目录保留全部已确认归属的论文，成果统计另列。直接用生成的长表建图时保留 `source` 和上述核验字段，并传入 `--affiliation-gaps`。

出现署名缺口时，成果脚本生成 `paper_affiliation_lookups.csv`，每篇一行，列出缺失位置、出版社 DOI 入口、DOI 和题名的网页检索链接以及 Crossref 登记入口。查过原刊与题名搜索结果后仍缺单位，就进入逐篇补录。单位核验缺口可在 `affiliation_gaps.csv` 查看。

1. 一次发一篇的题名，将回查表的 `publisher_url` 用独立一行的 Markdown 链接发到聊天里。链接文字可用「打开论文原刊」，地址使用完整的 `https://doi.org/...` 网址。消息或提问卡片使用裸网址时，在网址后加一个半角空格，再接标点或说明，避免它们被识别成地址的一部分。卡片无法渲染链接时，在聊天中保留可点击链接，卡片用于粘贴回复或选择「跳过本篇」「跳过剩余论文」。请用户打开原刊后复制完整题名、作者顺序及上标、署名单位表。缺 DOI 时提供已找到的原刊网址。已有对应原刊材料可直接核对。
2. 能在当前轮次接收回复并等待时，发出当篇补录请求后立即用实际时钟确定截止时间（发送时间加 180 秒）。告知用户「本篇最多等 3 分钟，收到回复或选择跳过后立即继续」。整理已有结果的时间也计入这 180 秒。还有剩余时间时，用可被新消息打断的等待工具分段等待，并在每次恢复时检查回复和剩余时间。收到资料后按 DOI 或题名、作者顺序和上标核对，保存原刊出处并回填能确认的单位。格式不齐时可在当篇剩余时间内请用户补全。用户点「跳过本篇」后直接问下一篇，每篇重新计时。
3. 用户点「跳过剩余论文」或实际已满 180 秒仍未收到当篇回复时，结束本轮补录，用当前证据交付。已跳过和超时的缺口保留在核验表。建图只使用同篇已核实的作者单位，论文清单另从成果表导出。若客户端只支持下一轮回复，或当前环境无法实际等待，就发出当篇问题并交付当前结果，说明可在下一条消息补录。这种情况不承诺三分钟，也不标记为超时。

需要已存证据辅助定位时，可运行 [署名重检脚本](../scripts/recheck_affiliations.py)。

~~~bash
python scripts/recheck_affiliations.py --gaps out/affiliation_gaps.csv \
  --evidence evidence.csv --out out/affiliation_recheck.csv
~~~

先用 `original_lookup` 的原刊入口、题名、原始姓名和作者位置查正文及 PDF。可加 `--online` 检查 Crossref 书目，或加 `--openalex-byline` 查同 DOI 的逐作者单位候选。回填前应独立核对姓名、顺序、总人数和该作者对应的单位。按 `author_lookup` 找到的其他论文记录附自身 DOI 和年份，用于定位同一作者在目标论文上的单位。

作者身份确认后，将核实的公开 ORCID 写入目标的证据行。`output_summary.json` 的 `orcid_status` 记录是否找到，`orcid_url` 给出个人页面链接或空值。合作图和检索正文都显示个人页面链接，找不到已核实的记录时显示“ORCID 未找到”。

## 论文候选对账

发现论文时登记到 `paper_candidates.csv`，列为 `result_id,source,title,exclusion_reason`。前两列必填，已知 DOI 用 DOI，只有题名时先用稳定的候选键和来源，核定 DOI 或正式记录键后同步更新。只对有证据证明同名误命中、重复版本或超出范围的条目填写 `exclusion_reason`。来源暂不可访问、署名未核实等情况保留候选，并在覆盖记录中写明原因。独立目录照常使用 `--reference`。

执行统计或建图时加 `--paper-candidates paper_candidates.csv`。按 `paper_candidate_coverage.csv` 检查 `missing_from_input`、`attribution_pending` 和 `decision_conflict`。已核实成果进入 `evidence.csv`，有依据的排除写回候选表，剩余缺口随结果交付。候选计数按去重后的论文编号汇总。

## 按需导出论文清单

用户明确要求逐篇列出或导出论文时，核对范围内所有已确认归属的论文，再加 `--paper-list`。仅要清单时可省略 `--network`。默认交付合作分析时，署名证据表用于对账与建图，用户侧报告只给论文统计。

- 以出版方最终版本、DOI 注册元数据或期刊原始记录核对年份、标题、DOI 和署名顺序。优先使用正式卷期年份，只有在线发表时采用已核实的在线年份。双语题名采用同一版本的原始题名。DOI 与题名及署名对应后，才用 `doi:<值>` 作为 `result_id`。
- 核实完整作者表后，在该来源记录的署名行中填写 `author_count`。按同一 `source`、`source_record_id` 和连续署名位置核对作者数，保留原始排序。不同来源的部分名单不拼接。年份、标题或作者表的差异仍无法核实时，对应列留空。DOI 无法确认时留空，并用其他已核实记录键保留该篇论文。
- `paper_list.csv` 每篇一行，包含年份、作者、标题、DOI、目标的一作与通讯标记及来源。目标担任一作或通讯的论文列在前面，含共同一作、共同通讯。两组分别按年份降序，缺年份的论文排在本组最后。角色待核的论文放在后组，角色字段留空。
