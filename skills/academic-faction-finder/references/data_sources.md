# 数据源、分区表与消歧风险

默认检索入口见[多源检索与漏检排查](workflow.md#8-多源检索与漏检排查)。优先用已有导出、公开作者页、出版社和各语种数据库界面。

## 1. OpenAlex（可选补充通道）

基础地址 `https://api.openalex.org`。脚本只用到三个端点：`/authors`（姓名→作者 ID）、`/institutions`（单位名→机构 ID）、`/works`（拉论文）。

### 计费现状（2026）

- 数据本体为 CC0，全量快照可免费下载；托管 API 自 2026 年 2 月起改为按用量计费。
- 免费账号的 API key 每天约 $1 用量额度；无 key 约 $0.10/天；按 ID / DOI 的单条查询免费。
- 额度按 UTC 每日重置，响应头可查剩余用量。HTTP 402 / 429 表示额度耗尽。
- 因此脚本默认 `--max-works 500`，并在分页间加 0.15s 间隔；大范围检索应分批多日运行，或改用全量快照本地查询。
- **实测（2026-11）**：匿名调用（无 key）时，`/works` 的 `cursor` 分页第一页正常，第二页起返回 HTTP 401 `API key required for cursor paging`；但 `page=N` 普通分页可用，上限约 1 万条。脚本检测无 key 自动回退 `page` 分页并在日志写明 `paging=page`。需要超过 1 万条或更稳的深分页时，去 `https://openalex.org/settings/api` 领免费 key。

### 使用的字段

| 用途 | OpenAlex 字段 |
|---|---|
| 论文 ID | `id`（取最后一段，如 `W123456`） |
| 题名 / 年份 / DOI | `title`, `publication_year`, `doi` |
| 期刊 | `primary_location.source.display_name` |
| ISSN | `primary_location.source.issn_l`, `issns`（兼容 `issn`） |
| 作者 | `authorships[].author.display_name`, `authorships[].author.orcid` |
| 机构 | `authorships[].institutions[].id` / `ror` / `display_name`；缺失时回退 `raw_affiliation_strings` |

**默认只取作者相关的最小字段集**，不读取摘要、全文、参考文献或题名/DOI，因此响应体积与用量都明显更小：

| 条件 | `select` 字段 |
|---|---|
| 默认 | `id,publication_year,authorships` |
| 指定 `--journal` / `--zone` / `--source-id` | 追加 `primary_location`（期刊名与 ISSN 只用于范围过滤） |
| 指定 `--with-titles` | 追加 `doi,title`（仅用于溯源，不参与任何计算） |

`authorships` 是唯一必需的大字段，无法在 API 层再裁剪子字段（OpenAlex 不支持嵌套 select）；其中的 `raw_affiliation_strings` 只在 `institutions` 缺失时作为机构名称回退。分页 `per-page=100`：有 key 用 `cursor`，无 key 回退 `page=N`。过滤用 `authorships.author.id`、`authorships.institutions.id`、`raw_affiliation_strings.search`（学院/系级单位，对应 `--affil-search`）、`primary_location.source.id`、`from_publication_date`、`to_publication_date`，多值 OR 用 `|`。

注意 `authorships.raw_affiliation_strings.search` 不是合法过滤键（返回 400），必须写成 `raw_affiliation_strings.search:...`。`/authors` 支持 `last_known_institutions.id` 过滤但不支持 `affiliations.institution_id`（返回 400）。

本地长表通道同理：`title`、`doi` 列可以整列留空，只要 `work_id`、`year`、`author_name`、`org_name` 齐全即可完成全部分析；`issn` / `zone` 仅在需要分区过滤时填写。

注意：OpenAlex 的作者消歧由自动算法完成，同名可能拆分或合并；公开命名前必须核验。期刊覆盖以英文与 DOI 文献为主，中文期刊覆盖有限。

## 2. 期刊分区范围

**OpenAlex 不提供中科院分区或 JCR 分区字段。** 分区必须由用户提供，两种形式任选：

1. `--zone-map` CSV，列：`issn,venue,zone,quartile`。脚本按 ISSN 与期刊名归一化后建索引，`--zone` 与 `zone` 或 `quartile` 列的值比较。
2. 输入长表 CSV 自带 `zone` 列（一行一篇论文，值重复填写），此时可不传 `--zone-map`。

示例模板 `assets/zone_map_template.csv` 中的行仅演示格式，均为虚构期刊，必须替换为权威分区表。分区表有版本与年份差异（中科院升级版/基础版、JCR 年份），汇报时需注明所依据的表与年份。

若某篇论文既不在映射表、又没有 inline `zone`，指定 `--zone` 时会被剔除，`run.log` 记录 `zone_unknown` 数量并告警。

## 3. 本地长表格式

`assets/authorship_template.csv` 的列：

```
work_id,doi,title,year,venue,issn,zone,author_name,orcid,org_name,org_id,author_order
```

一行 = 一篇论文 × 一位作者 × 一个机构。同一作者多个机构就写多行（这是「一人多单位」规则的输入前提）。`work_id` 必填且唯一标识论文；`org_name` / `org_id` 可空；`org_id` 优先填 ROR 或 OpenAlex 机构 ID。

适用场景：从 CNKI / 万方 / Web of Science 导出、本地 PDF 解析结果、机构内部论文清单。中文期刊、学位论文、无 DOI 文献通过这条通道接入更可靠。

## 4. 中文与补充数据源建议

- **中文姓名消歧**：中文名与拼音写法会被视为不同 `name_key`，导入前统一写法；优先补 ORCID 或机构 ID。AMiner 开放平台提供中文学者消歧能力与开放 API / 数据集，可作为合并参考。
- **ORCID 冲突是常态**：数据库档案可能关联到同名作者的 ORCID。默认 `warn` 策略保留机构主规则、只做复核标记；若需要「冲突即拆人」，用 `--orcid-policy strict`。
- **机构异名**：`org_alias_template.csv` 的 `from_key` 是规范化后的名称（小写、去标点），`to_key` 可写 `name:标准名` 或 `id:ROR...`。例如 `northlake univ` → `name:northlake university`。
- **大伞机构**：`org_ignored_template.csv` 中列出的机构不参与身份判定。建议把「中国科学院」「××大学」这类覆盖过广的名称替换成二级单位（研究所、学院、实验室），否则大量同名者会被串成一人。
- 书目库通常不编码导师关系。只从校方履历、学位论文导师栏或明确写出指导关系的公开记录确认，作为独立证据呈现。[跨机构检索](workflow.md#9-跨机构检索与归并)

## 5. 消歧规则的固有风险

主规则（机构集合有交集即同一人）简单、可解释，但存在三类已知偏差：

1. **换单位断裂**：完全更换单位时，先查共同 ORCID 或双署名记录。履历可核实但数据中缺少连接记录时，传入各阶段经核实的 `--seed-work`。参见 [跨机构检索](workflow.md#9-跨机构检索与归并)。
2. **大伞机构误并**：同名的两位作者都挂在同一个宽泛机构时会被误并。用 `--ignore-orgs` 排除，并降低 `--max-orgs` 以便尽早触发 `review_flag`。
3. **链式合并**：A–B 共享机构 X、B–C 共享机构 Y 时，C 可能被并入 A 所在的簇。脚本按年份升序处理，保留每次判定的 `evidence`，并对机构数异常、多候选命中的人打复核标记；`--mode seed` 可先在小邻域内人工核验再扩到全范围。
4. **ORCID 冲突下的误并**：默认 `warn` 策略允许「机构命中 + ORCID 不同」时合并，这能把被 OpenAlex 拆分/重复注册的同一个人合回来，但也可能把确有不同 ORCID 的两位同名者并成一人。所有这类判定都记为 `orcid_conflict_merged` 且 `review_flag=1`，`detail` 里写出两个 ORCID，不能跳过复核；高风险场景用 `--orcid-policy strict`。

`merge_log.csv` 与 `factions.db` 的 `merge_log` 表用于本地回滚和人工核验。对外报告附上核验结论所需的公开出处。

## 6. 合规与使用边界

- 输出只描述基于公开文献的合作结构（谁与谁共同署名、多少次），不对个人做能力、立场、利益关系评价。
- 派系是算法社区划分，受 `--min-collab`、范围、算法参数影响；改变参数需重新运行并标明 `run_id`、算法与参数。
- 涉及真实人物姓名的数据集对外发布前，核验数据来源许可与机构内部规定；OpenAlex 元数据为 CC0，但第三方分区表、CNKI 导出数据通常有使用限制。
- 分发 Skill 时只纳入通用规则、脚本、模板和虚构数据。分享检索结果时删除与结论无关的联系方式、个人识别号码、本机路径和原始日志，保留必要的公开证据。
- 合成演示数据 `assets/demo_authorship.csv` 中所有人名、机构、期刊均为虚构，不指向真实学者，仅用于验证链路。

## 7. 检索期刊全量文章时的成本控制

- 脚本用 `per-page=100` 分页，N 篇论文约需 `N/100` 次请求，页间固定 0.15 s；有 API key 用 `cursor`，无 key 自动回退 `page=N`（上限约 1 万条，见第 1 节）。单本期刊近十年全量通常在几百到几千篇，落在免费额度内；几十种期刊、上十万篇时，请求数上千，时间以分钟到十几分钟计，且会更快耗尽当日额度。
- `--max-works` 默认 500 是防误跑的保护值，**不是全量**。达到上限会打印 `TRUNCATED` 告警、在 `summary.json` 写 `truncated_by_max_works=true`。做「期刊全部文章」时必须调高该值或按年份/期刊分批，并核对 `works_in_scope` 是否等于预期总数。
- 推荐分批方式：`--from-year 2020 --to-year 2021` 逐年跑，或 `--journal` 逐刊跑，最后把各批长表 CSV 合并成一份再用 `--source local` 统一建图。这样既绕开额度限制，也便于断点续跑。
- 十万篇以上建议直接下载 OpenAlex 全量快照（CC0，季度更新）在本地筛选，或用带 daily sync 的付费方案；此时完全不再消耗 API 额度，脚本的 `--source local` 通道可直接对接。
- 与 token 无关：OpenAlex 的 JSON 元数据在本地进程内被消费，不进入模型上下文。真正需要控制的是请求次数、当日额度与浏览器渲染规模（见 `references/workflow.md` 第 6 节）。

## 8. 覆盖边界：为什么必须多源

将 OpenAlex 的候选记录与作者或机构的已知成果、出版社元数据和中文库对账。中文期刊、学位论文及无 DOI 文献可通过本地长表接入。核对缺失项时，依次检查姓名异写、历史机构、作者 ID 混并、ORCID 归属和分页状态。参见 [多源检索与漏检排查](workflow.md#8-多源检索与漏检排查)。
