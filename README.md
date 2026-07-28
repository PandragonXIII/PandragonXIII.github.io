# Utopia

基于 [Hexo](https://hexo.io/zh-cn/docs/) 和
[Fluid](https://github.com/fluid-dev/hexo-theme-fluid) 的个人博客，发布地址：
<https://pandragonxiii.github.io/>。

仓库使用两个分支：

- `source`：Hexo 源码、文章和配置
- `main`：Hexo 生成的静态站点，由部署命令自动维护

不要手动修改或提交 `main` 中的文件。

## 环境要求

- Node.js 18 或更高版本
- npm
- Git
- `uv`，用于 Obsidian 导出器及其测试环境

Hexo 和 Fluid 由 npm 管理；Obsidian 导出器由 uv 管理。初始化环境：

```bash
uv sync
```

## 初始化

切换到源码分支并按锁文件安装依赖：

```bash
git switch source
npm ci
uv sync
```

默认 Vault 是 `~/Knowledge`。临时使用其他位置时设置
`OBSIDIAN_VAULT=/path/to/vault`，或在 npm 命令末尾传入
`-- --vault /path/to/vault`。

## Obsidian 发布约定

Vault 是笔记内容的唯一来源，不要把整个博客仓库、`.git` 或
`node_modules` 放入 Syncthing。需要公开的笔记可位于 Vault 任意目录，但必须包含：

```yaml
---
publish: true
slug: stable-post-name
tags:
  - note
categories:
  - Knowledge
---
```

- `publish` 必须是 YAML 布尔值 `true`。
- `slug` 必填且在忽略大小写后唯一，只能包含小写 ASCII 字母、数字和连字符。
- `title` 可选，默认使用文件名。
- `date` 可选；第一次正式部署时会自动写回 Vault，并通过 Syncthing 同步。
- `tags` 和 `categories` 可选；多级 `categories` 会形成分类路径。

公开笔记可以使用 `[[笔记]]`、`[[笔记|显示文字]]`、标题链接、
`![[图片.png]]` 和本地 Markdown 图片。图片会被复制到对应的 Hexo 文章资源目录。
暂不支持笔记嵌入、block 引用和非图片附件嵌入。

为了防止泄露，公开笔记只要链接到未设置 `publish: true` 的笔记，检查和部署就会失败。
代码围栏和行内代码中的 `[[...]]` 不会被转换。

## 本地预览

```bash
npm run server
```

访问 <http://localhost:4000/>。服务器启动前会合并现有 Hexo 内容和公开 Obsidian
笔记。修改 Vault 后需要重启预览服务器，才能重新导出笔记。

## 写作

创建文章：

```bash
npm run new -- post "文章标题"
```

常用目录：

- 文章：`source/_posts/`
- 关于页：`source/about/index.md`
- 图片、音频和自定义页面：`source/img/`、`source/audio/`、`source/gallery/`
- Hexo 配置：`_config.yml`
- Fluid 配置：`_config.fluid.yml`

## 构建检查

只验证公开边界、链接和附件，不生成站点：

```bash
npm run notes:check
```

验证并生成完整站点：

```bash
npm run clean
npm run build
```

导出的文章只存在于 `.cache/obsidian-publish/`，命令结束后自动删除；最终输出位于
`public/`。这些目录都是生成内容，已被 Git 忽略，不会进入 `source` 分支。

## 部署

先在 `source` 分支保存并推送源码：

```bash
git add -A
git commit -m "Update site"
git push origin source
```

然后生成站点并部署到 `main`：

```bash
npm run deploy
```

部署器会显示本次公开的 Obsidian 笔记及目标 URL，并要求确认。确认后才会回写缺失的
首次发布日期、构建站点，并通过 `hexo-deployer-git` 更新远端 `main`。自动化环境必须
显式运行 `npm run deploy -- --yes`。

部署器会把 Pages workflow 一起复制到 `main`；GitHub Actions 随后上传静态文件并
发布站点。通常等待几十秒后即可在 <https://pandragonxiii.github.io/> 查看新版本。

不要手动提交 `.deploy_git/` 或 `public/`。如果要查看发布进度，请打开仓库的
**Actions** 页面并选择 **Publish static site to Pages**。

如部署时 GitHub 要求认证，请使用 Git Credential Manager、SSH，或具有仓库写权限的
令牌；不要把令牌写进 `_config.yml`。

本站目前不使用自定义域名，因此 `source/CNAME` 不应存在。

## Syncthing 注意事项

- 发布前等待 Syncthing 完成同步并停止编辑；导出期间检测到输入变化会中止。
- Windows 与 Linux 共用 Vault 时，文件名和 slug 必须在忽略大小写后仍唯一，并避免
  Windows 非法文件名字符。
- 建议在 `.stignore` 中排除 `.obsidian/workspace*.json`、缓存等设备状态文件，减少
  两台设备频繁产生无意义冲突。
- 如果没有购买和使用 Obsidian Sync，应在 Obsidian 中关闭其 Sync 核心插件，避免与
  Syncthing 同时管理同一 Vault。
- 当前 Syncthing Staggered Versioning 可用于恢复误删或首次日期回写前的版本。

旧 Hexo 文章暂时继续存放在 `source/_posts/`。后续应逐篇迁入 Vault，保留原 slug、
日期和分类，比较生成 URL 后再删除旧副本，避免一次迁移造成断链。
