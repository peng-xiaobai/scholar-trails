---
name: academic-output-search
description: Search and reconcile a researcher's scholarly output across sources and affiliations. Use for 查学者的中英文论文、SCIE 收录、专利、软著、成果归属或检索覆盖缺口。
---

# 学缘寻踪｜科研成果检索

复用已核实的身份和已有导出。需要确认身份时，按[作者身份核对](../academic-author-match/SKILL.md)定位目标。按用户指定的成果类型、时间和范围检索，未限定类型时查国际与中文论文、专利及软著。沿双语署名、历史机构、旧合作者和任职阶段扩展。优先使用公开网页、专业索引及批量导出。[多源检索](../academic-faction-finder/references/workflow.md#8-多源检索与漏检排查) · [各类成果的核验规则](../academic-faction-finder/references/research_outputs.md#并行检索)

回到原始署名或登记记录逐条核实角色，合并重复版本，并与可取得的独立清单对账。用[成果证据表模板](../academic-faction-finder/assets/research_outputs_template.csv)记录来源。运行 [`research_outputs.py`](../academic-faction-finder/scripts/research_outputs.py) 时传入 `--input`、`--target` 和 `--out`，有独立清单时加 `--reference`。[证据表和输出](../academic-faction-finder/references/research_outputs.md#证据表和输出)

交付各类已核实成果统计、专利和软著明细（如在范围内）、来源覆盖和待核项。明确要求逐篇列论文时，使用[论文清单](../academic-paper-list/SKILL.md)导出。
