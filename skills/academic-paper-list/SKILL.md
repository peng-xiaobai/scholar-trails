---
name: academic-paper-list
description: Export a verified researcher bibliography with author order, year, title and DOI, prioritizing first and corresponding authorship. Use for 列出某学者的论文、导出论文清单、输出全部论文或按一作通讯优先排序。
---

# 学缘寻踪｜论文清单导出

先复用已有身份档案和论文证据表。需要补查时，按[多源检索流程](../academic-faction-finder/references/workflow.md#8-多源检索与漏检排查)补齐论文范围内的年份、双语署名和历史机构。核实每篇论文归属，核对正式题名、年份、完整署名顺序、DOI 及目标作者的角色。字段仍有冲突或缺失时留空，附可核验来源。[论文核验与导出规则](../academic-faction-finder/references/research_outputs.md#按需导出论文清单)

运行 [`research_outputs.py`](../academic-faction-finder/scripts/research_outputs.py)，传入 `--input`、`--target`、`--out` 和 `--paper-list`。仅请求清单时，交付 `paper_list.csv` 与覆盖说明。目标担任一作或通讯的论文优先，含共同角色，其余论文放在后组，两组各按年份从新到旧排列。
