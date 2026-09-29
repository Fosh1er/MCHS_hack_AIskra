"""Руководства пользователя в PDF: docs/manuals/{teacher,student}.md → корень репозитория.

Markdown → HTML (нумерация разделов и рисунков, титульный лист, содержание) → PDF печатью Chrome (Playwright).
Скриншоты — docs/manuals/img, снимает `shoot.py`. Запуск из backend:

    uv run --with markdown --with playwright python ../docs/manuals/build.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
VERSION, DATE = "1.0", "29.09.2026"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 18mm; }
* { box-sizing: border-box; }
body { font-family: "Roboto", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1f1f1f; margin: 0; }
h1, h2, h3 { color: #1f1f1f; line-height: 1.25; break-after: avoid; }
h1 { font-size: 18pt; margin: 22pt 0 10pt; padding-bottom: 6pt; border-bottom: 2.5pt solid #157dbd; }
h2 { font-size: 13pt; margin: 16pt 0 6pt; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; }
h1 .num, h2 .num { color: #157dbd; margin-right: 6pt; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin: 2pt 0; }
strong { font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 9.5pt; break-inside: auto; }
th { background: #2f353a; color: #fff; text-align: left; font-weight: 500; padding: 5pt 7pt; }
td { padding: 4pt 7pt; border-bottom: 0.6pt solid #cacdce; vertical-align: top; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: #f4f6f7; }
blockquote { margin: 8pt 0; padding: 6pt 10pt; background: #dcecf7; border-left: 3pt solid #157dbd; }
blockquote p { margin: 0; }
figure { margin: 8pt 0 12pt; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; max-height: 100mm; border: 0.6pt solid #cacdce; box-shadow: 0 1pt 3pt rgba(0,0,0,.12); }
figcaption { margin-top: 4pt; font-size: 9pt; color: #555; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; }

.cover { height: 257mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover__top { display: flex; align-items: center; gap: 14pt; }
.cover__logo { font-size: 44pt; font-weight: 200; color: #157dbd; letter-spacing: -1pt; }
.cover__brand { font-size: 11pt; color: #2f353a; text-transform: uppercase; letter-spacing: 1.5pt; }
.cover__mid { border-left: 5pt solid #157dbd; padding-left: 16pt; }
.cover__product { font-size: 30pt; font-weight: 500; margin: 0; }
.cover__sub { font-size: 13pt; color: #444; margin: 6pt 0 26pt; }
.cover__title { font-size: 22pt; font-weight: 400; margin: 0; }
.cover__role { font-size: 16pt; margin: 6pt 0 0; color: #157dbd; }
.cover__img img { width: 100%; border: 0.6pt solid #cacdce; }
.cover__bottom { font-size: 9.5pt; color: #555; display: flex; justify-content: space-between; border-top: 0.6pt solid #cacdce; padding-top: 6pt; }

.toc { break-after: page; }
.toc h1 { margin-top: 0; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li { display: flex; gap: 6pt; margin: 3pt 0; }
.toc li.l2 { padding-left: 18pt; font-size: 9.5pt; color: #333; }
.toc .n { color: #157dbd; min-width: 26pt; }
.toc a { color: inherit; text-decoration: none; }
.toc li.l1 { font-weight: 500; margin-top: 7pt; }
"""


def front_matter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
    return meta, text[m.end() :]


def number(body: str) -> tuple[str, list[tuple[int, str, str, str]]]:
    """Нумерует h1/h2 («2», «2.1»), подписывает рисунки «Рисунок N — …», собирает содержание."""
    toc: list[tuple[int, str, str, str]] = []
    h1 = h2 = 0

    def head(m: re.Match[str]) -> str:
        nonlocal h1, h2
        level, text = int(m.group(1)), m.group(2)
        if level == 1:
            h1, h2 = h1 + 1, 0
            num = f"{h1}"
        else:
            h2 += 1
            num = f"{h1}.{h2}"
        anchor = f"s{num.replace('.', '-')}"
        toc.append((level, num, text, anchor))
        return f'<h{level} id="{anchor}"><span class="num">{num}</span>{text}</h{level}>'

    body = re.sub(r"<h([12])>(.*?)</h\1>", head, body)
    fig = 0

    def figure(m: re.Match[str]) -> str:
        nonlocal fig
        fig += 1
        alt, src = html.unescape(m.group(1)), m.group(2)
        return f'<figure><img src="{src}" alt="{html.escape(alt)}"><figcaption>Рисунок {fig} — {html.escape(alt)}</figcaption></figure>'

    body = re.sub(r'<p><img alt="([^"]*)" src="([^"]*)" ?/?></p>', figure, body)
    return body, toc


def page(meta: dict[str, str], body: str, toc: list[tuple[int, str, str, str]], cover_img: str) -> str:
    items = "".join(
        f'<li class="l{lv}"><span class="n">{num}</span><a href="#{a}">{t}</a></li>' for lv, num, t, a in toc
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{meta["title"]} — {meta["role"]}</title>
<style>{CSS}</style></head><body>
<section class="cover">
  <div class="cover__top"><span class="cover__logo">112</span><span class="cover__brand">Смена · учебный тренажёр</span></div>
  <div class="cover__mid">
    <p class="cover__product">АИскра</p>
    <p class="cover__sub">ИИ-тренажёр оператора системы-112 и диспетчера ДДС</p>
    <p class="cover__title">{meta["title"]}</p>
    <p class="cover__role">Роль «{meta["role"]}»</p>
  </div>
  <div class="cover__img"><img src="{cover_img}" alt=""></div>
  <div class="cover__bottom"><span>Версия {VERSION} · {DATE}</span><span>ЛЦТ-2026, задача № 9</span></div>
</section>
<section class="toc"><h1>Содержание</h1><ol>{items}</ol></section>
{body}
</body></html>"""


def build(name: str, cover: str) -> Path:
    meta, text = front_matter((HERE / f"{name}.md").read_text(encoding="utf-8"))
    body = markdown.markdown(text, extensions=["tables", "sane_lists"])
    body, toc = number(body)
    out_html = HERE / f"{name}.html"
    out_html.write_text(page(meta, body, toc, cover), encoding="utf-8")
    return out_html


def main() -> None:
    jobs = [("teacher", "img/t03_home.jpg"), ("student", "img/s03_home.jpg")]
    footer = (
        '<div style="width:100%;font-size:8px;color:#777;padding:0 16mm 0 18mm;display:flex;justify-content:space-between;'
        'font-family:Helvetica Neue,Arial,sans-serif"><span>АИскра · {label}</span>'
        '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page_ = browser.new_page()
        for name, cover in jobs:
            src = build(name, cover)
            meta, _ = front_matter((HERE / f"{name}.md").read_text(encoding="utf-8"))
            page_.goto(src.as_uri())
            page_.wait_for_load_state("load")
            out = ROOT / meta["out"]
            page_.pdf(
                path=str(out),
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer.format(label=f"{meta['title']} · {meta['role']}"),
                margin={"top": "16mm", "bottom": "18mm", "left": "18mm", "right": "16mm"},
                prefer_css_page_size=False,
            )
            src.unlink()
            print("PDF:", out.relative_to(ROOT), f"{out.stat().st_size // 1024} КБ")
        browser.close()


if __name__ == "__main__":
    main()
