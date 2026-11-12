# 在 GitHub 发布 Scholar Trails

将 `README.md`、`LICENSE`、`assets/`、`docs/`、`skills/` 和 `.gitignore` 提交到仓库，访客就能在 GitHub 上阅读说明和浏览源码。将 `scholar-trails.zip` 上传到 **Releases** 作为安装包。

## 创建仓库

**Repository name** 填 `scholar-trails`。公开分享时选择 **Public**。**Description** 可以直接粘贴下面这句。

> Follow the bylines to see where researchers have worked, what they’ve published, and who they work with. Four Agent Skills for scholarly discovery.

## 方式一 · 网页上传

1. 解压发布包，进入新建仓库的首页。
2. 通过 **Add file → Upload files** 上传解压后的 `README.md`、`LICENSE`、`assets/`、`docs/`、`skills/` 和 `.gitignore`，保持目录层级。空仓库也可以通过 **uploading an existing file** 进入上传页面。
3. 检查上传清单后提交。仓库首页应显示 Scholar Trails｜学缘寻踪的 README，点开 `skills/` 能看到四个入口。[GitHub 网页上传说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

## 方式二 · Git 推送

在 GitHub 创建空仓库。在解压目录的根目录运行以下命令，把 `OWNER` 换成你的 GitHub 用户名或组织名。执行 `git diff --cached --name-only` 后，确认清单只有准备公开的文件，再提交并推送。[GitHub 命令行发布说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

```bash
git init -b main
git add -- README.md LICENSE assets docs skills .gitignore
git diff --cached --name-only
git commit -m "Publish Scholar Trails"
git remote add origin https://github.com/OWNER/scholar-trails.git
git push -u origin main
```

## 发布 ZIP

在仓库首页打开 **Releases → Draft a new release**，选择已提交的版本并创建标签（例如 `v0.1.0`）。将 `scholar-trails.zip` 添加到发布附件，再发布。用户可以在 **Assets** 下载它，按[安装指南](install.md)操作。[GitHub Releases 说明](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

发布包仅包含说明和 Skill 所需文件。本地检索结果、原始数据导出及运行日志应留在本地。
