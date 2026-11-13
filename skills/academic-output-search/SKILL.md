---
name: academic-output-search
description: Search and reconcile a researcher's scholarly output across sources and affiliations. Use for 查学者的中英文论文、SCIE 收录、专利、软著、成果归属或检索覆盖缺口。
---

# 学缘寻踪｜科研成果检索

复用已核实的身份和已有导出。需要确认身份时，按[作者身份核对](../academic-author-match/SKILL.md)定位目标。按用户指定的成果类型、时间和范围检索，未限定类型时查国际与中文论文、专利及软著。沿双语署名、历史机构、旧合作者和任职阶段扩展。优先使用公开网页、专业索引及批量导出。[多源检索](../academic-faction-finder/references/workflow.md#8-多源检索与漏检排查) · [各类成果的核验规则](../academic-faction-finder/references/research_outputs.md#并行检索)

回到原始署名或登记记录逐条核实角色，合并重复版本，并与独立清单对账。先打开 DOI 跳转后的出版社页面核对作者单位。遇到 403 或来源缺单位，直接用 Google 搜完整英文题名，在同篇免费网页或 PDF 上核对每位作者的英文单位并记录链接。Crossref 和专业索引可辅助核对作者顺序。仍有署名缺口时，按[逐篇补录流程](../academic-faction-finder/references/research_outputs.md#署名单位补录)发送可点击的原刊链接，请用户打开后粘贴署名。该流程规定网址格式和实际等待时间。

用[成果证据表模板](../academic-faction-finder/assets/research_outputs_template.csv)记录来源。运行 [`research_outputs.py`](../academic-faction-finder/scripts/research_outputs.py) 时传入 `--input`、`--target` 和 `--out`，有独立清单时加 `--reference`。[证据表和输出](../academic-faction-finder/references/research_outputs.md#证据表和输出)

查论文时登记检索发现的候选，交付前用 `--paper-candidates` 对账并处理缺失项。[论文候选对账](../academic-faction-finder/references/research_outputs.md#论文候选对账)

交付各类已核实成果统计、专利和软著明细（如在范围内）、来源覆盖和待核项。有已核实的 ORCID 时附公开页面链接。明确要求逐篇列论文时，使用[论文清单](../academic-paper-list/SKILL.md)导出。
