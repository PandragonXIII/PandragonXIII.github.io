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
- `uv`，用于仓库内的 Python 虚拟环境

Hexo 和 Fluid 是 Node.js 包，由 npm 管理。当前没有 Python 工具依赖，
`.venv` 暂时为空；需要重建时运行：

```bash
uv venv .venv
```

## 初始化

切换到源码分支并按锁文件安装依赖：

```bash
git switch source
npm ci
```

## 本地预览

```bash
npm run server
```

访问 <http://localhost:4000/>。开发服务器会监听源码变化并自动重新生成页面。

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

```bash
npm run clean
npm run build
```

输出位于 `public/`。该目录是生成内容，已被 Git 忽略。

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

`npm run deploy` 会依次清理缓存、生成静态文件，并通过
`hexo-deployer-git` 更新远端 `main`。部署器还会把 Pages workflow 一起复制到
`main`；GitHub Actions 随后上传这些静态文件并发布站点。通常等待几十秒后即可在
<https://pandragonxiii.github.io/> 查看新版本。

不要手动提交 `.deploy_git/` 或 `public/`。如果要查看发布进度，请打开仓库的
**Actions** 页面并选择 **Publish static site to Pages**。

如部署时 GitHub 要求认证，请使用 Git Credential Manager、SSH，或具有仓库写权限的
令牌；不要把令牌写进 `_config.yml`。

本站目前不使用自定义域名，因此 `source/CNAME` 不应存在。
