#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a static reading website for 《县城中国》(復刻版) from markdown chapters."""
import os
import re
import html
import shutil
import unicodedata
from markdown_it import MarkdownIt

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "content")
OUT = os.path.join(ROOT, "site")
BOOK_TITLE = "县城中国"
BOOK_SUBTITLE = "半城半乡：从人物、关系到产业与生计"
REPO = "https://github.com/zhugewuwo/xianxiang-china"

BOX_CHARS = set("─│┌┐└┘├┤┬┴┼▶◀▼▲╭╮╯╰═║╔╗╚╝━┃┏┓┗┛┣┫┳┻╋")
DIAGRAM_INNER = 736
DIAGRAM_MIN_FONT = 9.0
DIAGRAM_MAX_FONT = 13.5

CH_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
    "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
    "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
}


def cell_width(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def diagram_font_size(content):
    cells = max((cell_width(line) for line in content.splitlines()), default=0)
    if cells == 0:
        return None
    size = DIAGRAM_INNER / (cells * 0.6)
    return round(max(DIAGRAM_MIN_FONT, min(DIAGRAM_MAX_FONT, size)), 1)


def is_diagram(content):
    if not any(c in BOX_CHARS for c in content):
        return False
    cells = max((cell_width(line) for line in content.splitlines()), default=0)
    return cells <= 170


def split_h1(text):
    """Split a markdown file into sections, each starting at an H1 heading."""
    lines = text.split("\n")
    sections = []
    cur_title = None
    cur = []
    for line in lines:
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            if cur_title is not None:
                sections.append((cur_title, "\n".join(cur).strip()))
            cur_title = m.group(1).strip()
            cur = [line]
        else:
            cur.append(line)
    if cur_title is not None:
        sections.append((cur_title, "\n".join(cur).strip()))
    return sections


def reading_time(text):
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    minutes = cjk / 500.0
    total = max(30, int(round(minutes * 60)))
    mm, ss = divmod(total, 60)
    return f"{mm}分{ss}秒" if mm else f"{ss}秒"


def collect_parts():
    """Return the ordered list of reading units (parts) for the book."""
    parts = []

    def title_from_h1(h1):
        return h1

    def chapter_num(h1):
        m = re.match(r"^第([一二三四五六七八九十]+)章", h1)
        if m:
            return CH_NUM.get(m.group(1))
        return None

    def sidebar_title(h1, num):
        if num is not None:
            t = re.sub(r"^第[一二三四五六七八九十]+章[\s　]*", "", h1).strip()
            return t or h1
        return h1

    # front matter (自序 / 前言)
    fm = os.path.join(SRC, "frontmatter.md")
    if os.path.exists(fm):
        for title, body in split_h1(open(fm, encoding="utf-8").read()):
            parts.append({"h1": title, "text": body, "num": None, "kind": "front"})

    # chapters
    for name in sorted(os.listdir(SRC)):
        m = re.match(r"^ch(\d+)\.md$", name)
        if not m:
            continue
        text = open(os.path.join(SRC, name), encoding="utf-8").read()
        h1 = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), name)
        parts.append({"h1": h1, "text": text, "num": chapter_num(h1) or int(m.group(1)), "kind": "chapter"})

    # back matter (余论 / 附录 / 后记)
    bm = os.path.join(SRC, "backmatter.md")
    if os.path.exists(bm):
        for title, body in split_h1(open(bm, encoding="utf-8").read()):
            parts.append({"h1": title, "text": body, "num": None, "kind": "back"})

    for i, p in enumerate(parts, 1):
        p["id"] = f"part-{i:02d}"
        p["sidebar_title"] = sidebar_title(p["h1"], p["num"])
        p["time"] = reading_time(p["text"])
    return parts


def build_renderer():
    md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    return md


def extract_footnotes(text):
    """Pull footnote definitions out of the text; return (text_without_defs, defs_in_order)."""
    defs = {}
    order = []
    kept = []
    for line in text.split("\n"):
        m = re.match(r"^\[\^([^\]]+)\]:\s?(.*)$", line)
        if m:
            key = m.group(1)
            if key not in defs:
                order.append(key)
            defs[key] = m.group(2).strip()
        else:
            kept.append(line)
    return "\n".join(kept), [(k, defs[k]) for k in order]


def process_tokens(tokens):
    """Add heading ids, collect toc, mark ascii diagrams."""
    toc = []
    used = {}
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag in ("h2", "h3"):
            inline = tokens[i + 1]
            title = inline.content
            base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-").lower() or "sec"
            idx = used.get(base, 0)
            used[base] = idx + 1
            hid = base if idx == 0 else f"{base}-{idx}"
            tok.attrSet("id", hid)
            toc.append({"id": hid, "text": title, "level": int(tok.tag[1])})
        elif tok.type == "fence" and is_diagram(tok.content):
            size = diagram_font_size(tok.content)
            tok.attrSet("class", "diagram")
            if size is not None:
                tok.attrSet("style", f"font-size:{size}px")
    return toc


def render_part(md, text):
    body_text, defs_list = extract_footnotes(text)
    defs = {k: v for k, v in defs_list}
    number = {}

    def repl(m):
        key = m.group(1)
        if key not in defs:
            return m.group(0)
        if key not in number:
            number[key] = len(number) + 1
        return f'<sup class="fn-ref"><a href="#fn-{key}" id="fnref-{key}">[{number[key]}]</a></sup>'

    body_text = re.sub(r"\[\^([^\]]+)\]", repl, body_text)
    tokens = md.parse(body_text)
    toc = process_tokens(tokens)
    body_html = md.renderer.render(tokens, md.options, {})

    notes = []
    for key, txt in defs_list:
        if key in number:
            notes.append({"id": f"fn-{key}", "num": number[key], "text": txt})
    notes.sort(key=lambda x: x["num"])
    if notes:
        items = "\n".join(
            f'<li id="{nt["id"]}" class="footnote-item">'
            f'<span class="fn-num">[{nt["num"]}]</span> '
            f'<span class="fn-text">{html.escape(nt["text"])}</span> '
            f'<a class="footnote-backref" href="#fnref-{nt["id"][3:]}" title="返回正文">↩</a></li>'
            for nt in notes
        )
        body_html += (
            '\n<section class="footnotes">\n<hr class="footnotes-sep">\n'
            f'<ol class="footnotes-list">\n{items}\n</ol>\n</section>\n'
        )
    return body_html, toc, notes


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} - {book_title}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="topbar-title" href="index.html">{book_title}</a>
    <div class="topbar-right">
      <a class="login-btn" href="{repo}" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</header>

<div class="layout{layout_cls}">
  <aside class="sidebar">
    <nav class="chapter-list">
      <ol>
        {chapter_items}
      </ol>
    </nav>
  </aside>

  <main class="content">
    <article class="markdown-body">
      {body}
    </article>
    <div class="pager">
      {prev_link}
      {next_link}
    </div>
  </main>
{toc_aside}
</div>

<script src="assets/app.js"></script>
</body>
</html>
"""

TOC_ASIDE = """
  <aside class="toc">
    <div class="toc-head"><span>本章注释</span><span class="toc-toggle">≫</span></div>
    <ul>{items}</ul>
  </aside>"""


def make_chapter_items(parts, active_id):
    items = []
    for p in parts:
        cls = ' class="active"' if p["id"] == active_id else ""
        num = p["num"] if p["num"] is not None else "·"
        items.append(
            f'<li{cls}><a href="{p["id"]}.html">'
            f'<span class="num">{num}</span>'
            f'<span class="info"><span class="t">{html.escape(p["sidebar_title"])}</span>'
            f'<span class="d">阅读时长: {p["time"]}</span></span>'
            f'</a></li>'
        )
    return "\n        ".join(items)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    for asset in ("style.css", "app.js"):
        shutil.copy(os.path.join(ROOT, "web", asset), os.path.join(OUT, "assets", asset))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    md = build_renderer()
    parts = collect_parts()
    for p in parts:
        p["html"], p["toc"], p["notes"] = render_part(md, p["text"])

    for i, p in enumerate(parts):
        if p["notes"]:
            items = "\n      ".join(
                f'<li><a href="#{nt["id"]}">{nt["num"]}. {html.escape(nt["text"][:22])}'
                f'{"…" if len(nt["text"]) > 22 else ""}</a></li>'
                for nt in p["notes"]
            )
            toc_aside = TOC_ASIDE.format(items=items)
            layout_cls = ""
        else:
            toc_aside = ""
            layout_cls = " no-toc"

        prev_link = next_link = ""
        if i > 0:
            q = parts[i - 1]
            prev_link = f'<a class="prev" href="{q["id"]}.html">← {html.escape(q["sidebar_title"])}</a>'
        if i < len(parts) - 1:
            q = parts[i + 1]
            next_link = f'<a class="next" href="{q["id"]}.html">{html.escape(q["sidebar_title"])} →</a>'

        page = PAGE.format(
            page_title=html.escape(p["h1"]),
            book_title=html.escape(BOOK_TITLE),
            repo=REPO,
            layout_cls=layout_cls,
            chapter_items=make_chapter_items(parts, p["id"]),
            body=p["html"],
            toc_aside=toc_aside,
            prev_link=prev_link,
            next_link=next_link,
        )
        with open(os.path.join(OUT, f'{p["id"]}.html'), "w", encoding="utf-8") as f:
            f.write(page)

    first = parts[0]
    cards = "\n      ".join(
        f'<a class="card" href="{p["id"]}.html"><span class="card-num">{i:02d}</span>'
        f'<span class="card-t">{html.escape(p["sidebar_title"])}</span>'
        f'<span class="card-d">{p["time"]}</span></a>'
        for i, p in enumerate(parts, 1)
    )
    index = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(BOOK_TITLE)}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body class="landing-body">
<header class="topbar">
  <div class="topbar-inner">
    <a class="topbar-title" href="index.html">{html.escape(BOOK_TITLE)}</a>
    <div class="topbar-right">
      <a class="login-btn" href="{REPO}" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</header>
<div class="landing">
  <h1>{html.escape(BOOK_TITLE)}</h1>
  <p class="sub">{html.escape(BOOK_SUBTITLE)}</p>
  <p class="desc">自序、前言、二十八章正文，以及余论与附录，共 {len(parts)} 篇 · 一个关于县城的社会结构观察。</p>
  <a class="start-btn" href="{first['id']}.html">开始阅读</a>
  <div class="cards">
      {cards}
  </div>
</div>
</body>
</html>
"""
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"Generated {len(parts)} parts into {OUT}")


if __name__ == "__main__":
    main()
