#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给每本书页加「返回书目总览」按钮。

用法
----
    cd ~/.openclaw/workspace/reading-assist && python3 _add_back.py
    python3 _add_back.py --check     # 只看现状，不改任何文件
    python3 _add_back.py --revert    # 从备份还原

为什么需要你手工跑一次
----------------------
各书页是独立打开的（`<书名>/<书名>.html`），没有回到根目录 `index.html` 的入口。
从 Windows 侧经 `\\\\wsl.localhost\\...` 改**既存文件**会 `PermissionError errno=13`
（2026-09-27 实测：6 本书页 ＋ index.html ＋ README.md ＋ _serve.py **全部被拒**），
只有「新建文件」可写。**在 WSL 内部执行本脚本不受此限。**

本脚本做的事
------------
1. 备份原文件到 `_backup_backlink/`（首次跑时，不覆盖已有备份）
2. 在 `</style>` 前注入 `.backlink` 样式（两行 CSS）
3. 在 `<main>` 之后插入一个 `<a class="backlink" href="../index.html">`
4. 自检：锚点唯一、结构未变、字节数增量符合预期、无 CRLF

★ 幂等：已注入过的文件直接跳过，可以反复跑。
★ 全程按**字节**读写，不会碰换行符（LF 保持 LF）。
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / "_backup_backlink"

LINK_TEXT = "← 返回书目总览"
LINK_HREF = "../index.html"

CSS_BLOCK = (
    "\n"
    "/* 返回书目总览 */\n"
    ".backlink{display:inline-flex;align-items:center;gap:6px;margin:18px 0 0;\n"
    "  font-size:12.5px;font-weight:600;padding:6px 13px;border-radius:8px;\n"
    "  background:var(--accent-bg);color:var(--accent);text-decoration:none;\n"
    "  border:1px solid #cfe0f0;line-height:1.5}\n"
    ".backlink:hover{background:#dbe8f4;border-color:var(--accent)}\n"
)

LINK_BLOCK = '<a class="backlink" href="%s">%s</a>\n' % (LINK_HREF, LINK_TEXT)

CSS_ANCHOR = b"</style>"
MAIN_ANCHOR = b"<main>"
MARK = b'<a class="backlink"'

# 注入会新增的换行数：从常量推导，别写死魔数（写死过一次，CSS 块一改就假失败）
EXTRA_LINES = CSS_BLOCK.count("\n") + LINK_BLOCK.count("\n") + 1


def books():
    """根目录下每个非下划线目录里的 `<目录名>.html`。"""
    out = []
    for d in sorted(ROOT.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            p = d / (d.name + ".html")
            if p.is_file():
                out.append(p)
    return out


def analyse(raw):
    """返回 (能否注入, 原因) —— 只读检查，不做修改。"""
    if MARK in raw:
        return False, "已注入（跳过）"
    if raw.count(CSS_ANCHOR) != 1:
        return False, "`</style>` 出现 %d 次（应为 1）" % raw.count(CSS_ANCHOR)
    if raw.count(MAIN_ANCHOR) != 1:
        return False, "`<main>` 出现 %d 次（应为 1）" % raw.count(MAIN_ANCHOR)
    if b"--accent-bg" not in raw:
        return False, "缺少 CSS 变量 --accent-bg"
    if b"\r\n" in raw:
        return False, "文件含 CRLF（先修换行再加）"
    return True, "可注入"


def build(raw):
    """返回注入后的 bytes。"""
    new = raw.replace(CSS_ANCHOR, CSS_BLOCK.encode("utf-8") + CSS_ANCHOR, 1)
    new = new.replace(MAIN_ANCHOR, MAIN_ANCHOR + b"\n" + LINK_BLOCK.encode("utf-8"), 1)
    return new


def verify(raw, new):
    """注入后自检 —— 返回错误列表（空表示通过）。"""
    errs = []
    if new.count(MARK) != 1:
        errs.append("backlink 出现 %d 次（应为 1）" % new.count(MARK))
    if new.count(b".backlink{") != 1:
        errs.append(".backlink{ 出现 %d 次（应为 1）" % new.count(b".backlink{"))
    if new.count(CSS_ANCHOR) != 1:
        errs.append("</style> 数量变了")
    if new.count(MAIN_ANCHOR) != 1:
        errs.append("<main> 数量变了")
    for key in (b"<section id=", b'href="#', b"<table>", b"<h2>", b"<h3>"):
        if new.count(key) != raw.count(key):
            errs.append("%r 数量变了：%d → %d" % (key, raw.count(key), new.count(key)))
    if b"\r\n" in new:
        errs.append("引入了 CRLF")
    if new.count(b"\n") != raw.count(b"\n") + EXTRA_LINES:
        errs.append("换行数增量应为 %d，实际 %d"
                    % (EXTRA_LINES, new.count(b"\n") - raw.count(b"\n")))
    return errs


def main():
    ap = argparse.ArgumentParser(description="给书页注入「返回书目总览」链接")
    ap.add_argument("--check", action="store_true", help="只检查，不修改")
    ap.add_argument("--revert", action="store_true", help="从备份还原")
    args = ap.parse_args()

    if args.revert:
        if not BACKUP.is_dir():
            sys.exit("没有备份目录：%s" % BACKUP)
        n = 0
        for d in sorted(ROOT.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            p = d / (d.name + ".html")
            b = BACKUP / (d.name + ".html")
            if p.is_file() and b.is_file():
                shutil.copyfile(b, p)
                print("  还原 %s" % p.relative_to(ROOT))
                n += 1
        print("\n已还原 %d 个文件。" % n)
        return

    targets = books()
    if not targets:
        sys.exit("没找到任何书页（%s/*/<书名>.html）" % ROOT)
    print("根目录：%s" % ROOT)
    print("待处理书页：%d 个\n" % len(targets))

    deltas = []
    for p in targets:
        rel = p.relative_to(ROOT)
        raw = p.read_bytes()
        ok, why = analyse(raw)
        if not ok:
            print("  [跳过] %-42s %s" % (rel, why))
            continue
        new = build(raw)
        errs = verify(raw, new)
        if errs:
            print("  [失败] %-42s %s" % (rel, " / ".join(errs)))
            continue
        delta = len(new) - len(raw)
        deltas.append(delta)
        if args.check:
            print("  [可注入] %-40s +%d B" % (rel, delta))
            continue
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / p.name
        if not bak.exists():
            bak.write_bytes(raw)
        p.write_bytes(new)
        back = p.read_bytes()
        assert back == new, "回读不一致：%s" % rel
        print("  [已注入] %-40s +%d B  sha=%s" % (rel, delta, hashlib.sha256(new).hexdigest()[:12]))

    if deltas:
        print("\n增量：min=%d max=%d  %s"
              % (min(deltas), max(deltas), "（全部相同 ✓）" if len(set(deltas)) == 1 else "⚠ 不一致"))
    print("\n完成。%s" % ("未做任何修改。" if args.check else "备份在 %s" % BACKUP.name))


if __name__ == "__main__":
    main()
