# 县城中国（复刻版）

《县城中国》章节 Markdown 转换成的静态阅读网站，采用掘金课程阅读页样式，通过 GitHub Pages 部署。

## 目录结构

```
content/      章节 Markdown 源文件（自序、前言、第一至第二十八章、余论、附录、后记）
web/          样式与脚本源文件（style.css、app.js）
build.py      静态站点生成脚本（含脚注、表格、ASCII 图渲染）
site/         构建产物（由 build.py 生成）
.github/workflows/deploy.yml   GitHub Pages 自动部署
```

## 本地构建

```bash
pip install markdown-it-py
python build.py
# 产物输出到 site/，用任意静态服务器预览：
python -m http.server -d site 8000
```

## 部署

推送到 `main` 分支后，GitHub Actions 会自动构建并发布到 GitHub Pages。
访问地址：`https://zhugewuwo.github.io/xianxiang-china/`
