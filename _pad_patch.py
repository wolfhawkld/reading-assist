# -*- coding: utf-8 -*-
"""pad 阅读增强补丁（2026-10-04）：深色主题 + 窄屏目录抽屉 + 缺样式补齐。

对 <BOOKS>/index.html 与 <BOOKS>/<书名>/<书名>.html **就地**打补丁：
  ① 把 CSS 里残留的硬编码浅色改成变量（浅色下取值不变，只为深色可覆盖）
  ② 注入深色主题块 `:root[data-theme="dark"]{…}`
  ③ 窄屏（≤900px）：`aside{display:none}` → 改为可滑出的抽屉 + 浮动「目录」按钮 + 遮罩
  ④ 浮动「主题」按钮（所有页都有）
  ⑤ **缺样式补齐**：某档标签被使用却在 CSS 里找不到 `.<类名>{` 规则时补上
     （实例：《我看见的世界》11 处 `tag t-talk` 无任何样式 —— 渲染成无色，且自检抓不到）
  ⑥ `<head>` 里加一段同步脚本设置 `data-theme`，避免深色下加载瞬间白闪

用法（**放一份到书目根目录，一行跑完**）：
    cd ~/.openclaw/workspace/reading-assist && python3 _pad_patch.py --check   # 预演
    cd ~/.openclaw/workspace/reading-assist && python3 _pad_patch.py          # 落盘

根目录解析顺序：`RA_ROOT` 环境变量 → **脚本自己所在目录（含 `index.html` 时）** → 默认 UNC 路径。
中间那条是给「脚本被放进 <BOOKS>/ 里、在 WSL 内跑」用的——不用带任何环境变量；
从别处（如 tools/）跑则落到 UNC。★ 先在本地副本上跑通再指向 WSL —— 这是既定三段式。

★ 规范副本在技能里：`~/.workbuddy/skills/book-digest/assets/_pad_patch.py`；
  书目根目录里的那份是**部署副本**，两份必须逐字节相同（改一处就同步另一处）。
"""
import os, re, sys, shutil

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
MARK = 'pad-2026-10-04'
UNC = r'\\wsl.localhost\Ubuntu-24.04\home\damon\.openclaw\workspace\reading-assist'
R = os.environ.get('RA_ROOT')
if not R:
    _here = os.path.dirname(os.path.abspath(__file__))
    R = _here if os.path.exists(os.path.join(_here, 'index.html')) else UNC
BACKUP = os.environ.get('PAD_BACKUP') or os.path.join(R, '_backup_pad')
CHECK = '--check' in sys.argv

# ---- 硬编码浅色 → 变量 ------------------------------------------------------
VAR_MAP = [
    (r'background:#fff(?![0-9a-fA-F])', 'background:var(--chipbg)'),
    (r'color:#fff(?![0-9a-fA-F])',      'color:var(--onaccent)'),
    (r'#f4f2ec', 'var(--hover)'),
    (r'#f6f4ee', 'var(--thbg)'),
    (r'#1a3a5c', 'var(--keyink)'),
    (r'#234a6e', 'var(--boxink)'),
    (r'#cfe0f0', 'var(--linkline)'),
    (r'#dbe8f4', 'var(--linkhover)'),
    (r'#fdf4f4', 'var(--warnbg)'),
    (r'#f0dcdc', 'var(--warnline)'),
    (r'#6b3232', 'var(--warnink)'),
    (r'#fcfbf9', 'var(--cardread)'),
    (r'#254c73', 'var(--btnhover)'),
]

LIGHT_ADD = (
    '  /* %s · 原硬编码浅色提为变量，供深色覆盖 */\n'
    '  --chipbg:#fff; --onaccent:#fff; --btnhover:#254c73;\n'
    '  --hover:#f4f2ec; --thbg:#f6f4ee; --keyink:#1a3a5c; --boxink:#234a6e;\n'
    '  --linkline:#cfe0f0; --linkhover:#dbe8f4;\n'
    '  --warnbg:#fdf4f4; --warnline:#f0dcdc; --warnink:#6b3232; --cardread:#fcfbf9;\n'
) % MARK

DARK = (
    '/* ===== %s · 深色主题；data-theme 由 <head> 同步脚本设置，避免白闪 ===== */\n'
    ':root[data-theme="dark"]{\n'
    '  --bg:#15161a; --panel:#1c1e23; --ink:#e7e6e2; --ink2:#b7b5ae; --ink3:#8d8b84;\n'
    '  --line:#2c2f35; --line2:#3b3f46; --accent:#8fbde8; --accent-bg:#22303e;\n'
    '  --src:#5fd3ac; --src-bg:#16302a;\n'
    '  --talk:#e3a7d1; --talk-bg:#332230;\n'
    '  --rep:#e3b569; --rep-bg:#33280f;\n'
    '  --inf:#b6acf7; --inf-bg:#252344;\n'
    '  --warn:#ee8a8a;\n'
    '  --chipbg:#24272e; --onaccent:#15161a; --btnhover:#a8caea;\n'
    '  --hover:#24272e; --thbg:#212429; --keyink:#bcd7f0; --boxink:#cfe0f2;\n'
    '  --linkline:#33465a; --linkhover:#26313d;\n'
    '  --warnbg:#2b1f1f; --warnline:#5a3030; --warnink:#f0b4b4; --cardread:#1a1c20;\n'
    '}\n'
    ':root[data-theme="dark"] .backlink{box-shadow:none}\n'
    ':root[data-theme="dark"] aside{box-shadow:0 0 40px rgba(0,0,0,.5)}\n'
) % MARK

CTL_CSS = (
    '/* ===== %s · 浮动控件（目录 / 主题）===== */\n'
    '#ctl{position:fixed;top:calc(12px + env(safe-area-inset-top,0px));right:12px;z-index:130;display:flex;gap:8px}\n'
    '#ctl button{-webkit-appearance:none;appearance:none;font-family:inherit;cursor:pointer;\n'
    '  display:flex;align-items:center;gap:6px;height:34px;padding:0 12px;border-radius:9px;\n'
    '  border:1px solid var(--line2);background:var(--panel);color:var(--ink2);\n'
    '  font-size:12.5px;font-weight:600;box-shadow:0 1px 4px rgba(0,0,0,.07)}\n'
    '#ctl button:hover{color:var(--ink);border-color:var(--accent)}\n'
    '#ctl #navbtn{display:none}\n'
    '/* ★ 必须带 #ctl 前缀：`#ctl button{display:flex}` 是 (1,0,1)，裸 `#navbtn` 只有 (1,0,0) 压不过它 */\n'
    '@media(max-width:900px){#ctl #navbtn{display:flex}}\n'
    '#navscrim{position:fixed;inset:0;background:rgba(0,0,0,.42);z-index:110;opacity:0;\n'
    '  pointer-events:none;transition:opacity .2s}\n'
    'body.nav-open #navscrim{opacity:1;pointer-events:auto}\n'
) % MARK

NARROW_OLD = ('@media(max-width:900px){\n'
              '  aside{display:none}\n'
              '  main{margin-left:0;padding:0 20px 80px}\n'
              '  .hero{padding-top:34px}\n'
              '}')
NARROW_NEW = ('@media(max-width:900px){\n'
              '  /* %s · 目录不再整体消失，改为可滑出的抽屉 */\n'
              '  aside{\n'
              '    display:block;width:min(86vw,320px);z-index:120;\n'
              '    transform:translateX(-102%%);transition:transform .22s ease;\n'
              '  }\n'
              '  body.nav-open aside{transform:none}\n'
              '  main{margin-left:0;padding:0 20px 80px}\n'
              '  .hero{padding-top:58px}\n'
              '}') % MARK

CTL_HTML_TOC = ('<div id="ctl">\n'
            '  <button id="navbtn" type="button" aria-controls="toc" aria-expanded="false">☰ 目录</button>\n'
            '  <button id="themebtn" type="button" aria-label="切换深色／浅色">◐ 深色</button>\n'
            '</div>\n'
            '<div id="navscrim"></div>\n')
# 总入口页没有目录栏，只放主题按钮
CTL_HTML_NOTOC = ('<div id="ctl">\n'
                  '  <button id="themebtn" type="button" aria-label="切换深色／浅色">◐ 深色</button>\n'
                  '</div>\n')

HEAD_JS = ('<script>/* %s 深色：尽早设置，避免白闪 */'
           'try{var _t=localStorage.getItem("ra-theme")||((window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light");'
           'document.documentElement.setAttribute("data-theme",_t);}catch(e){}</script>\n') % MARK

TAIL_JS = '''
;/* ===== %s · 目录抽屉 + 主题切换 ===== */
(function(){
  var root = document.documentElement, KEY = 'ra-theme';
  function sys(){ return (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light'; }
  function saved(){ try{ return localStorage.getItem(KEY); }catch(e){ return null; } }
  function paint(t){
    root.setAttribute('data-theme', t);
    var b = document.getElementById('themebtn');
    if (b) b.textContent = (t === 'dark') ? '☀ 浅色' : '◐ 深色';
  }
  paint(saved() || sys());
  var tb = document.getElementById('themebtn');
  if (tb) tb.addEventListener('click', function(){
    var n = (root.getAttribute('data-theme') === 'dark') ? 'light' : 'dark';
    try { localStorage.setItem(KEY, n); } catch(e) {}
    paint(n);
  });
  try {
    if (window.matchMedia && !saved()) {
      var mq = matchMedia('(prefers-color-scheme: dark)');
      var on = function(){ if (!saved()) paint(sys()); };
      if (mq.addEventListener) mq.addEventListener('change', on); else if (mq.addListener) mq.addListener(on);
    }
  } catch(e) {}
  var bd = document.body, nb = document.getElementById('navbtn'), sc = document.getElementById('navscrim');
  function set(on){
    bd.classList.toggle('nav-open', on);
    if (nb) nb.setAttribute('aria-expanded', on ? 'true' : 'false');
  }
  if (nb) nb.addEventListener('click', function(){ set(!bd.classList.contains('nav-open')); });
  if (sc) sc.addEventListener('click', function(){ set(false); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') set(false); });
  Array.prototype.forEach.call(document.querySelectorAll('#toc a'), function(a){
    a.addEventListener('click', function(){ if (window.innerWidth <= 900) set(false); });
  });
})();
''' % MARK


def sub_once(text, old, new, what, book):
    n = text.count(old)
    if n != 1:
        raise SystemExit('[%s] %s 锚点命中 %d 次（应为 1）：%r' % (book, what, n, old[:60]))
    return text.replace(old, new, 1)


def patch(book, path):
    raw = open(path, 'rb').read()
    h = raw.decode('utf-8').replace('\r\n', '\n')
    if MARK in h:
        return None, '已打过补丁，跳过'
    if '<style>' not in h or ':root{' not in h:
        return None, '!! 找不到 <style> / :root，跳过'
    s0 = h.index('<style>')
    e0 = h.index('</style>', s0)
    css = h[s0:e0]
    r0 = css.index(':root{') + len(':root{')
    r1 = css.index('}', r0)                      # :root 块结束
    root_block = css[r0:r1]
    body_css = css[r1:]                          # 只在这段里做颜色替换
    notes = []

    # ① 硬编码色 → 变量
    hits = {}
    for pat, rep in VAR_MAP:
        body_css, n = re.subn(pat, rep, body_css)
        if n:
            hits[pat] = n
        elif re.fullmatch(r'#[0-9a-fA-F]{6}', pat):
            notes.append('本文件无 %s' % pat)
    # ② :root 补声明（浅色）
    if '--chipbg' in body_css:
        add = LIGHT_ADD
        # 只在「这页真的用到作者谈话档」时才补变量，别给无关页面塞声明
        if (('class="tag t-talk"' in h) or ('.t-talk{' in h)) and ('--talk:' not in root_block):
            add += '  --talk:#8a4b7a; --talk-bg:#f8e9f4;\n'
            notes.append('补 --talk 变量')
        root_block = root_block.rstrip('\n') + '\n' + add
    css = css[:r0] + root_block + body_css
    # ③ 深色块 + 浮控件 CSS
    css = css.rstrip('\n') + '\n\n' + DARK + '\n' + CTL_CSS
    # ⑤ 缺样式补齐：用到 .t-xxx 但 CSS 里没有规则
    for cls, nm in (('t-src', '原书'), ('t-talk', '作者谈话'), ('t-rep', '转述'), ('t-inf', '推断')):
        if ('class="tag %s"' % cls) in h and ('.%s{' % cls) not in css:
            css = css.rstrip('\n') + '\n.%s{background:var(--%s-bg);color:var(--%s)}\n' % (
                cls, cls.split('-')[1], cls.split('-')[1])
            notes.append('补 .%s 规则（%s）' % (cls, nm))
    h = h[:s0] + css + h[e0:]

    # ④ 窄屏目录抽屉（只有带 aside 的书页有这一段）
    if NARROW_OLD in h:
        h = sub_once(h, NARROW_OLD, NARROW_NEW, '窄屏块', book)

    # ⑥ 控件 HTML（无目录栏的页只放主题按钮）
    has_toc = 'id="toc"' in h
    ctl_html = CTL_HTML_TOC if has_toc else CTL_HTML_NOTOC
    if '<div id="progress"></div>' in h:
        h = sub_once(h, '<div id="progress"></div>', '<div id="progress"></div>\n' + ctl_html, 'progress 锚点', book)
    else:
        h = sub_once(h, '<body>\n', '<body>\n' + ctl_html, 'body 锚点', book)

    # ⑦ head 同步脚本（防白闪）
    vp = '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    h = sub_once(h, vp, vp + HEAD_JS, 'viewport 锚点', book)

    # ⑧ 尾部 JS
    j = h.rfind('</script>')
    h = h[:j] + TAIL_JS + h[j:]

    return h, '改写 %d 处颜色；%s' % (sum(hits.values()), '，'.join(notes) if notes else '无需补齐')


def main():
    books = []
    if os.path.exists(os.path.join(R, 'index.html')):
        books.append(('index.html', os.path.join(R, 'index.html')))
    for d in sorted(os.listdir(R)):
        p = os.path.join(R, d)
        if os.path.isdir(p) and not d.startswith('_'):
            for f in sorted(os.listdir(p)):
                if f.endswith('.html') and not f.startswith('_'):
                    books.append(('%s/%s' % (d, f), os.path.join(p, f)))
    print('根目录 =', R)
    print('待处理 =', len(books), '个 html\n')
    done = 0
    for name, path in books:
        try:
            out, note = patch(name, path)
        except SystemExit as e:
            print('  %-34s %s' % (name, e)); continue
        if out is None:
            print('  %-34s %s' % (name, note)); continue
        print('  %-34s %s' % (name, note))
        if not CHECK:
            os.makedirs(BACKUP, exist_ok=True)
            flat = name.replace('/', '__')
            shutil.copyfile(path, os.path.join(BACKUP, flat))
            open(path, 'wb').write(out.encode('utf-8'))
            # 读回校验
            back = open(path, 'rb').read().decode('utf-8')
            assert back == out, '读回不一致：%s' % path
            assert '\r\n' not in back, '写回后含 CRLF：%s' % path
        done += 1
    print('\n%s = %d 个文件' % ('将改写' if CHECK else '已改写', done))
    if not CHECK and done:
        print('备份 →', BACKUP)


if __name__ == '__main__':
    main()
