#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自建 Web 检索工具 — 绕过被拦的 WebSearch/WebFetch 工具
用法:
  python3 scripts/websearch.py "查询词"                    # Bing 网页搜索, 默认 top10 (标题/URL/摘要)
  python3 scripts/websearch.py "查询词" --top 5             # 限制条数
  python3 scripts/websearch.py "查询词" --json              # JSON 输出(便于管道处理)
  python3 scripts/websearch.py --arxiv "DeepSeek-V4"        # arXiv API 检索(all字段, 最新优先)
  python3 scripts/websearch.py --arxiv "query" --field ti   # 按 title 字段检索
  python3 scripts/websearch.py --arxiv-id 2606.19348        # 按 ID 取论文(标题+摘要+日期)
  python3 scripts/websearch.py --arxiv-id "2606.19348,2412.19437"  # 批量验证多个 ID
  python3 scripts/websearch.py --fetch URL                  # 抓取 URL 正文(去 HTML 标签)
  python3 scripts/websearch.py --fetch URL --max 5000       # 限制字符数

后端:
  - Bing HTML (www.bing.com)         — 兼容旧 LibreSSL, 通用网页搜索
  - arXiv API (export.arxiv.org)     — 论文检索 / ID 真伪验证
  - 通用抓取 (requests + 去标签)
注: DuckDuckGo / Wikipedia / Google 因系统 LibreSSL 2.8.3 太旧, TLS 握手失败, 不可用。
    实测 2026-07-09: Bing + arXiv 可达, 覆盖论文核实 + 通用新闻检索两大需求。
"""
import sys, re, json, argparse, html, warnings
warnings.filterwarnings("ignore")
try:
    import requests
except ImportError:
    print("需安装 requests: pip3 install requests", file=sys.stderr); sys.exit(1)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def _clean(s):
    """去标签 + 反转义实体 + 压缩空白"""
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


# ---------- Bing 网页搜索 ----------
def bing_search(query, top=10):
    url = "https://www.bing.com/search"
    r = requests.get(url, headers=HEADERS, params={"q": query, "count": str(max(top, 10))}, timeout=25)
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', r.text, re.S)
    out = []
    for b in blocks[:top]:
        href = re.search(r'<a[^>]+href="([^"]+)"', b)
        title = re.search(r'<h2[^>]*>(.*?)</h2>', b, re.S)
        snip = re.search(r'<p[^>]*>(.*?)</p>', b, re.S)
        u = href.group(1) if href else ""
        # Bing 偶尔用 ck/a 跳转, 尝试解出真实 URL
        if "bing.com/ck/a" in u:
            m = re.search(r'[?&]u=([^&]+)', u)
            if m:
                try:
                    from urllib.parse import unquote
                    dec = unquote(m.group(1))
                    if dec.startswith("a1"):  # a1 前缀 + base64, 取后续 http
                        mm = re.search(r'(https?://[^ ]+)', dec[2:])
                        if mm: u = mm.group(1)
                    else:
                        u = dec
                except Exception:
                    pass
        out.append({
            "title": _clean(title.group(1)) if title else "",
            "url": u,
            "snippet": _clean(snip.group(1)) if snip else "",
        })
    return out


# ---------- arXiv ----------
ARXIV = "https://export.arxiv.org/api/query"


def _parse_arxiv(xml):
    out = []
    for m in re.finditer(r'<entry>(.*?)</entry>', xml, re.S):
        e = m.group(1)
        idm = re.search(r'<id>http://arxiv\.org/abs/([^<]+?)</id>', e)
        tm = re.search(r'<title>(.*?)</title>', e, re.S)
        pm = re.search(r'<published>([^<]+)</published>', e)
        sm = re.search(r'<summary>(.*?)</summary>', e, re.S)
        if idm:
            out.append({
                "id": idm.group(1),
                "title": _clean(tm.group(1)) if tm else "",
                "published": (pm.group(1)[:10] if pm else ""),
                "summary": _clean(sm.group(1)) if sm else "",
            })
    return out


def arxiv_search(query, field="all", max_results=5):
    sq = f"{field}:{query}" if field and field != "all" else query
    r = requests.get(ARXIV, headers=HEADERS, params={
        "search_query": sq, "max_results": str(max_results),
        "sortBy": "submittedDate", "sortOrder": "descending",
    }, timeout=30)
    return _parse_arxiv(r.text)


def arxiv_by_id(ids):
    r = requests.get(ARXIV, headers=HEADERS, params={"id_list": ids, "max_results": "30"}, timeout=30)
    return _parse_arxiv(r.text)


# ---------- 通用抓取 ----------
def fetch_text(url, max_chars=4000):
    r = requests.get(url, headers=HEADERS, timeout=25)
    txt = _clean(r.text)
    txt = re.sub(r'\{[^}]*\}', '', txt)  # 残留 JS 对象
    return txt[:max_chars]


def _emit(res, a):
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2)); return
    if not res:
        print("(无结果)"); return
    for i, r in enumerate(res, 1):
        print(f"[{i}] {r.get('title','')}")
        if r.get('url'):        print(f"    URL: {r['url']}")
        if r.get('published'):  print(f"    日期: {r['published']}")
        if r.get('id'):         print(f"    arXiv: {r['id']}")
        if r.get('snippet'):    print(f"    {r['snippet'][:220]}")
        if r.get('summary'):    print(f"    摘要: {r['summary'][:400]}")
        print()


def main():
    ap = argparse.ArgumentParser(description="自建 Web 检索 (Bing + arXiv), 绕过被拦工具")
    ap.add_argument("query", nargs="?", help="搜索词")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--arxiv", action="store_true", help="arXiv 检索")
    ap.add_argument("--arxiv-id", dest="arxiv_id", help="按 arXiv ID 取论文 (逗号分隔多个)")
    ap.add_argument("--field", default="all", help="arXiv 检索字段 (ti/au/all/abs)")
    ap.add_argument("--fetch", help="抓取 URL 正文")
    ap.add_argument("--max", type=int, default=4000, help="fetch 最大字符数")
    a = ap.parse_args()

    try:
        if a.fetch:
            print(fetch_text(a.fetch, a.max)); return
        if a.arxiv_id:
            _emit(arxiv_by_id(a.arxiv_id), a); return
        if a.arxiv:
            if not a.query: ap.error("arxiv 检索需要 query")
            _emit(arxiv_search(a.query, a.field, a.top), a); return
        if a.query:
            _emit(bing_search(a.query, a.top), a); return
        ap.print_help()
    except Exception as e:
        print(f"ERR {type(e).__name__}: {str(e)[:160]}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
