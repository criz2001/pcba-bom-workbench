"""从设计稿中抽取 CSS 与共享外壳样式，生成前端静态资源。

一次性工具：设计稿（pcba-bom-workbench/）是视觉基准，本脚本把它里面的
<style> 块按用途拆分，避免在可运行项目里重复抄写样式。

    python tools/extract_css.py
"""

from __future__ import annotations

import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGN = os.path.join(os.path.dirname(ROOT), "pcba-bom-workbench")
OUT_ASSETS = os.path.join(ROOT, "app", "static", "assets")

SKIP_IDS = {"theme-vars", "semantic-token-fallback"}
SHELL_IDS = {"shell-critical-layout", "icon-discipline", "theme-toggle"}

STYLE_RE = re.compile(r"<style([^>]*)>(.*?)</style>", re.S | re.I)
ID_RE = re.compile(r'id="([^"]+)"')

PAGES = [
    "workbench", "check-setup", "check-running", "check-result",
    "check-detail", "gen-setup", "gen-result", "library",
]


def blocks(html: str):
    for attrs, body in STYLE_RE.findall(html):
        if "tailwindcss" in attrs:
            continue  # Tailwind 运行时专用，本地软件不依赖 CDN
        m = ID_RE.search(attrs)
        yield (m.group(1) if m else ""), body


def main() -> None:
    os.makedirs(os.path.join(OUT_ASSETS, "pages"), exist_ok=True)

    shutil.copyfile(
        os.path.join(DESIGN, "colors_and_type.css"),
        os.path.join(OUT_ASSETS, "colors_and_type.css"),
    )

    shell_parts: dict[str, str] = {}

    for page in PAGES:
        path = os.path.join(DESIGN, "pages", f"{page}.html")
        html = open(path, encoding="utf-8").read()
        page_parts: list[str] = []
        for style_id, body in blocks(html):
            if style_id in SKIP_IDS:
                continue
            if style_id in SHELL_IDS:
                shell_parts.setdefault(style_id, body)
                continue
            page_parts.append(f"/* ---- {style_id or 'inline'} ---- */{body}")

        out = os.path.join(OUT_ASSETS, "pages", f"{page}.css")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(
                f"/* 由设计稿 {page}.html 抽取，请勿手工微调；改设计请改设计稿后重新运行 "
                f"tools/extract_css.py */\n"
            )
            fh.write("\n".join(page_parts))
        print(f"pages/{page}.css  <- {len(page_parts)} block(s)")

    order = ["shell-critical-layout", "icon-discipline", "theme-toggle"]
    with open(os.path.join(OUT_ASSETS, "shell.css"), "w", encoding="utf-8") as fh:
        fh.write("/* 由设计稿 partials/project-shell.html 抽取 —— 共享应用外壳样式 */\n")
        for key in order:
            if key in shell_parts:
                fh.write(f"\n/* ---- {key} ---- */{shell_parts[key]}\n")
    print("shell.css <-", ", ".join(k for k in order if k in shell_parts))


if __name__ == "__main__":
    main()
