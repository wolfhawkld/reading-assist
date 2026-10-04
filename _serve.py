#!/usr/bin/env python3
"""阅读库本地服务 —— `python3 _serve.py [端口]`（默认 18860）。

为什么需要它（★ 别删）
----------------------
交付的各页用的是**相对链接**（如 `哲学研究/哲学研究.html`）。本库放在 WSL 里，
Windows 侧只能通过 `\\\\wsl.localhost\\...` 访问；而**客户端预览面板会把相对链接解析成本地文件**，
它读不了那条 UNC 路径 ⇒ 点「打开阅读页」会报 **「暂无数据」**。

本服务在输出 HTML 时把相对 `href` **改写成绝对 HTTP 地址（并做百分号编码）**，
于是不论浏览器还是预览面板，都只能走 HTTP，从而正常工作。
⇒ 好处：**磁盘上的交付文件一字不改**，直接双击 `index.html` 也照旧可用。

用法
----
    cd ~/.openclaw/workspace/reading-assist && python3 _serve.py
    # 然后浏览器打开 http://127.0.0.1:18860/

端口默认 18860（18770 被 sensory_evolution 占用）。
只绑 127.0.0.1，不对外网开放。

改写规则（v2）
--------------
相对 `href` 按「**当前页面的 URL**」解析，而不是简单拼在站点根后面：
  - `index.html`（位于 `/`）里的 `哲学研究/哲学研究.html`
      ⇒ http://127.0.0.1:18860/%E5%93%B2%E5%AD%A6.../%E5%93%B2%E5%AD%A6....html
  - 书页（位于 `/瓦尔登湖/`）里的 `../index.html`
      ⇒ http://127.0.0.1:18860/index.html      ← `..` 已就地归一化
v1 是把相对链接一律拼到站点根，于是书页里的 `../index.html` 会输出成
`http://127.0.0.1:18860/../index.html`——浏览器自己会归一化所以**能用**，
但链接脏（复制出来带 `..`），且书页里若将来出现 `图片/x.jpg` 这类
**相对于书目录**的资源就会被静默指向错误的根路径。
"""

import http.server
import os
import re
import socketserver
import sys
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

# 默认服务「本脚本所在目录」，所以在哪执行都行；RA_ROOT 可覆盖（便于本地预演）
ROOT = os.environ.get("RA_ROOT") or os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18860

# 只改「相对」href：排除 `#frag`、`/abs`、`//host`、`scheme:` 四种
REL_HREF = re.compile(r'(href=")(?![a-zA-Z][a-zA-Z0-9+.\-]*:|/|#)([^"]*)(")')


def encode_rel(rel):
    """把相对地址编码成纯 ASCII，但**保留 `?` `#` 的结构**。

    ★ 不能对整串直接 quote：那会把 `?` `#` 也编码成 %3F / %23，
      跨页锚点（如 `瓦尔登湖.html#s1`）会失效。
    """
    sp = urlsplit(rel)
    return urlunsplit(
        (
            "",
            "",
            quote(sp.path, safe="/"),
            quote(sp.query, safe="=&"),
            quote(sp.fragment, safe=""),
        )
    )


def rewrite_html(text, page_url):
    """把相对 href 改成绝对 HTTP 地址（以当前页 URL 为基准）。

    ★ 必须编码：改成绝对地址后 URL 里会带中文路径，
      浏览器会自动编码、能正常跳，但**严格的 HTTP 客户端（如 Python urllib）
      会直接报 `UnicodeEncodeError: 'ascii' codec can't encode` 而拒收整个请求**。
      编码成纯 ASCII 后，两边都认。
    ★ 用 urljoin 而不是字符串拼接：它会顺带把 `.` / `..` 归一化，
      否则书页里的 `../index.html` 会输出成 `http://host/../index.html`。
    """

    def sub(m):
        return m.group(1) + urljoin(page_url, encode_rel(m.group(2))) + m.group(3)

    return REL_HREF.sub(sub, text)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))
        sys.stderr.flush()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _html_path(self):
        """本次请求真正对应的 .html 文件；目录则取其 index.html。"""
        local = self.translate_path(self.path)
        if os.path.isdir(local):
            idx = os.path.join(local, "index.html")
            return idx if os.path.isfile(idx) else None
        return local if local.lower().endswith((".html", ".htm")) else None

    def do_GET(self):
        target = self._html_path()
        if target:
            try:
                with open(target, "rb") as f:
                    raw = f.read()
            except OSError:
                self.send_error(404, "File not found")
                return
            host = self.headers.get("Host") or ("127.0.0.1:%d" % PORT)
            # 当前页的绝对 URL（自身编码成 ASCII；`%` 列入 safe 以免二次编码）
            path = self.path if self.path.startswith("/") else "/"
            page_url = "http://%s%s" % (host, quote(path, safe="/%"))
            text = raw.decode("utf-8", "replace")
            body = rewrite_html(text, page_url).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def main():
    if not os.path.isdir(ROOT):
        sys.exit("找不到根目录：%s" % ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print("阅读库已启动：http://127.0.0.1:%d/" % PORT)
        print("根目录：%s" % ROOT)
        print("按 Ctrl-C 停止。")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
