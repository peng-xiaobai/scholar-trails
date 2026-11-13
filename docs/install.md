# 安装 Scholar Trails｜学缘寻踪

各 Skill 共用主 Skill 中的工作流、脚本和数据模板。安装整套时，让 `academic-*` 目录保持同级。

## 下载后手动安装

1. 在仓库的 **Releases** 下载 `scholar-trails.zip` 并解压。也可以从 **Code → Download ZIP** 下载仓库源码。
2. 把解压后 `skills/` 中的目录复制到下表对应位置。项目路径从目标项目根目录算起，`~` 代表用户主目录。
3. 打开目标项目并开启新会话。Codex 可用 `$academic-faction-finder`，Claude Code 可用 `/academic-faction-finder`。也可以直接说「查 [单位] [姓名] 的合作团队」。[Codex Skill 文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) · [Claude Code Skill 文档](https://code.claude.com/docs/en/skills#choose-where-skills-load)

| 客户端 | 仅当前项目 | 当前用户的所有项目 |
| --- | --- | --- |
| Codex | `.agents/skills/` | `~/.agents/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |

例如，Codex 的项目安装完成后，主入口应位于 `.agents/skills/academic-faction-finder/SKILL.md`。团队可以把项目级目录提交到自己的仓库。

## 从 Git 克隆后安装

把 `OWNER` 换成发布者的 GitHub 用户名或组织名，克隆后按上表复制 `skills/` 里的目录。

```bash
git clone https://github.com/OWNER/scholar-trails.git
```

以后在克隆目录中运行 `git pull`，再用更新后的目录替换已安装的副本。

## 用 GitHub CLI 批量安装

使用支持 `gh skill install` 的 GitHub CLI。在目标 Git 项目目录执行以下命令，并替换 `OWNER`。用 Claude Code 时把 `codex` 改为 `claude-code`。想装到个人目录时把 `project` 改为 `user`。[GitHub CLI 安装命令说明](https://cli.github.com/manual/gh_skill_install)

```bash
gh skill install OWNER/scholar-trails --all --agent codex --scope project
```

## 临时试用

在能够读取本地文件的助手中打开解压目录，发送「读取 `skills/academic-faction-finder/SKILL.md`，查 [单位] [姓名] 的合作团队」。安装后可从[使用方式](../README.md#使用方式)选择其他入口。

离线建图和批量导入需要 Python 3.11 或更新版本。查询真实成果需要助手能够访问相应公开网页或读取用户提供的导出文件。
