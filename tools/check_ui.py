# -*- coding: utf-8 -*-
"""界面静态自检：DOM id 引用、CSS 括号平衡、JS 语法（调用 node --check）。"""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.void_tags = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id" and value:
                if value in self.ids:
                    self.errors.append(f"重复 id: {value}")
                self.ids.add(value)
        if tag not in self.void_tags:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.void_tags:
            return
        if not self.stack:
            self.errors.append(f"多余的结束标签 </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(f"标签未正确闭合: <{self.stack[-1]}> 遇到 </{tag}>")
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack:
                self.stack.pop()
        else:
            self.stack.pop()


def check_html() -> tuple[set[str], list[str]]:
    parser = IdCollector()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    parser.close()
    errors = list(parser.errors)
    if parser.stack:
        errors.append(f"未闭合标签: {parser.stack}")
    return parser.ids, errors


def check_css() -> list[str]:
    css = (WEB / "css" / "style.css").read_text(encoding="utf-8")
    errors = []
    if css.count("{") != css.count("}"):
        errors.append(f"CSS 大括号不匹配: {{={css.count('{')} }}={css.count('}')}")
    for line_no, line in enumerate(css.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("/*", "*", "//")) or not stripped:
            continue
        if re.search(r":\s*#(?![0-9a-fA-F]{3,8}\b)[a-zA-Z]", line):
            errors.append(f"第 {line_no} 行疑似非法颜色值: {stripped[:60]}")
    return errors


def check_js_ids(ids: set[str]) -> list[str]:
    app_js = (WEB / "js" / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\('#([\w-]+)'\)", app_js))
    return [f"JS 引用了不存在的 id: #{item}" for item in sorted(used) if item not in ids]


def check_js_syntax() -> list[str]:
    errors = []
    for path in [WEB / "js" / "app.js", WEB / "js" / "charts.js"]:
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            errors.append(f"{path.name} 语法错误: {result.stderr.strip()[:300]}")
    return errors


def main() -> int:
    ids, html_errors = check_html()
    problems = []
    problems += html_errors
    problems += check_css()
    problems += check_js_ids(ids)
    problems += check_js_syntax()

    app_js = (WEB / "js" / "app.js").read_text(encoding="utf-8")
    endpoints = sorted(set(re.findall(r"['\"`](/api/[\w/\-]+)", app_js)))
    print(f"HTML id 共 {len(ids)} 个")
    print(f"前端调用接口: {', '.join(endpoints) if endpoints else '无'}")

    if problems:
        print("\n发现问题:")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("\n静态检查通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
