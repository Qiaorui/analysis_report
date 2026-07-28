#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用行情工具 v2 — 传入任意 A股/港股/北交所 代码, 输出行情/PE/PB/PE分位/PB分位/52周/Q1同比/财务
v2 修复(v1的4个缺口):
  - PE分位: baidu indicator "市盈率"坏→改"市盈率(TTM)"(实测6票全通)
  - Q1同比: eastmoney PARENT_NETPROFIT_YOY常返回0→手算(2026Q1/2025Q1-1, 拉多季度财报)
  - 港股: 腾讯qt加hk前缀(price=p3/PE=p40/市值=p45/52周=p49-50); PB/PE分位baidu港股接口失败→标注
  - 北交所: 腾讯qt加bj前缀(price=p3/PE=p40/PB=p44/市值=p45); 52周/PB分位不可靠→标注
用法:
  python3 scripts/quote.py 600519 000858 --pb --fin        # A股
  python3 scripts/quote.py 00700 02313 --pb                 # 港股(5位)
  python3 scripts/quote.py 920982 --pb                       # 北交所
数据源: 腾讯qt.gtimg.cn(行情) + baidu估值/akshare(A股PE/PB分位) + 东方财富datacenter(财务)
设计: 不预设股票池, 由调用方决定拉哪些票 → 配合开放调研原则
"""
import requests, warnings, re, sys, json
warnings.filterwarnings("ignore")
try:
    import akshare as ak
    HAS_AK = True
except ImportError:
    HAS_AK = False

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
import time

def parse_codes(argv):
    """解析代码, 自动识别 A股/港股/北交所"""
    codes = []
    for a in argv:
        if a.startswith("--"): continue
        for c in re.split(r"[,\s]+", a):
            c = c.strip()
            if re.match(r"^\d{5,6}$", c):
                codes.append(c)
    return codes

def code_type(c):
    """识别代码类型与腾讯前缀"""
    if len(c) == 5:
        return "hk", "hk" + c           # 港股 5位
    if c[0] == "6":
        return "sh", "sh" + c           # 沪市
    if c[0] in "03":
        return "sz", "sz" + c           # 深市
    if c[0] in "489":                    # 北交所/新三板 8/4/9开头6位
        return "bj", "bj" + c
    return "sh", "sh" + c               # 默认沪

def fetch_qt(codes):
    """腾讯批量行情, 按类型解析字段"""
    qt = {}
    for i in range(0, len(codes), 40):
        batch = codes[i:i+40]
        qcodes = ",".join([code_type(c)[1] for c in batch])
        try:
            r = requests.get(f"https://qt.gtimg.cn/q={qcodes}",
                             headers={"Referer":"https://gu.qq.com/"}, timeout=20)
            r.encoding = 'gbk'
            for line in r.text.strip().split(';'):
                if '"' not in line: continue
                p = line.split('"')[1].split('~')
                if len(p) < 5: continue
                code = p[2] if len(p) > 2 else ""
                # 原始代码(去前导0对齐5位港股/6位A股) - 用p[2]即代码本身
                try:
                    f = lambda idx: float(p[idx]) if len(p) > idx and p[idx] else 0
                    price = f(3)
                    if price == 0: continue
                    ctype, _ = code_type(code) if code else ("sh","")
                    # 不同类型字段位置不同(腾讯qt格式: A股/HK/BJ字段不同)
                    if ctype == "hk":
                        rec = {'name': p[1], 'price': price, 'pct': f(32),
                               'pe': f(39), 'pb': 0, 'mktcap': f(44),
                               'hi52': f(48), 'lo52': f(49), 'turnover': 0,
                               'type': 'hk'}
                    elif ctype == "bj":
                        # 北交所: 52周字段qt不可靠(返回当日高低), 置0不报
                        rec = {'name': p[1], 'price': price, 'pct': f(32),
                               'pe': f(39), 'pb': f(43), 'mktcap': f(44),
                               'hi52': 0, 'lo52': 0, 'turnover': f(38),
                               'type': 'bj'}
                    else:  # sh/sz A股
                        rec = {'name': p[1], 'price': price, 'pct': f(32),
                               'pe': f(39), 'pb': f(46) if len(p) > 46 else 0,
                               'mktcap': f(44), 'hi52': f(67) if len(p) > 67 else 0,
                               'lo52': f(68) if len(p) > 68 else 0,
                               'turnover': f(38), 'vol': f(36), 'type': ctype}
                    rec['pos52'] = ((price-rec['lo52'])/(rec['hi52']-rec['lo52'])*100) if rec['hi52']>rec['lo52'] else 0
                    qt[code] = rec
                except Exception:
                    continue
        except Exception as e:
            print(f"  批次失败: {e}", file=sys.stderr)
    return qt

def fetch_pb_percentile(code, ctype):
    """PB分位(近十年). A股用baidu市净率; 港股stock_hk_valuation_baidu(可能失败); 北交所不支持"""
    if not HAS_AK: return None, None
    try:
        if ctype == "hk":
            bv = ak.stock_hk_valuation_baidu(symbol=code, indicator="市净率", period="近十年")
        elif ctype == "bj":
            return None, None  # baidu估值不支持北交所
        else:
            bv = ak.stock_zh_valuation_baidu(symbol=code, indicator="市净率", period="近十年")
        s = bv['value'].astype(float).dropna()
        cur = float(s.iloc[-1]); pct = float((s < cur).sum()) / len(s) * 100
        return cur, pct
    except Exception:
        return None, None

def fetch_pe_percentile(code, ctype):
    """PE分位(近十年). A股用baidu"市盈率(TTM)"(关键: 不是"市盈率"!); 港股/北交所不支持"""
    if not HAS_AK: return None, None
    if ctype in ("hk", "bj"): return None, None  # 港股baidu估值接口失败/北交所不支持
    try:
        bv = ak.stock_zh_valuation_baidu(symbol=code, indicator="市盈率(TTM)", period="近十年")
        s = bv['value'].astype(float).dropna()
        cur = float(s.iloc[-1]); pct = float((s < cur).sum()) / len(s) * 100
        return cur, pct
    except Exception:
        return None, None

def fetch_fin(code, ctype):
    """东方财富 datacenter: 拉多季度财报, 返回 2025年报+2026Q1+2025Q1(算Q1同比用)
    注: 港股/北交所财务用不同接口, 此处仅A沪深; 港股用stock_financial_hk, 北交所datacenter支持"""
    try:
        if ctype in ("hk", "bj"):
            # 港股财务走akshare stock_financial_hk_analysis_indicator_em; 北交所走datacenter(代码同6位)
            if ctype == "hk":
                return {}, {}, None
            # bj 走datacenter同A股
        url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=REPORTDATE"
               f"&sortTypes=-1&pageSize=12&pageNumber=1&reportName=RPT_LICO_FN_CPD"
               f"&columns=ALL&filter=(SECURITY_CODE=%22{code}%22)")
        rows = requests.get(url, timeout=15).json().get('result', {}).get('data', []) or []
        q1_2026 = [x for x in rows if x.get('REPORTDATE', '').startswith('2026-03-31')]
        q1_2025 = [x for x in rows if x.get('REPORTDATE', '').startswith('2025-03-31')]
        an2025 = [x for x in rows if x.get('REPORTDATE', '').startswith('2025-12-31')]
        q1r = q1_2026[0] if q1_2026 else {}
        anr = an2025[0] if an2025 else (rows[0] if rows else {})
        # Q1同比手算
        q1_yoy = None
        if q1_2026 and q1_2025:
            np_now = q1_2026[0].get('PARENT_NETPROFIT')
            np_prev = q1_2025[0].get('PARENT_NETPROFIT')
            if np_now and np_prev and float(np_prev) != 0:
                q1_yoy = (float(np_now) / float(np_prev) - 1) * 100
        return q1r, anr, q1_yoy
    except Exception:
        return {}, {}, None

def yi(v):
    try:
        f = float(v)
        return f / 1e8 if abs(f) > 1e6 else f  # 元→亿
    except Exception:
        return None

def main():
    args = sys.argv[1:]
    do_pb = "--pb" in args
    do_fin = "--fin" in args
    do_json = "--json" in args
    codes = parse_codes(args)
    if not codes:
        print("用法: python3 scripts/quote.py 600519 000858 00700 920982 [--pb] [--fin] [--json]")
        print("  支持 A股(6/0/3开头6位) / 港股(5位) / 北交所(8/4/9开头6位)")
        print("  --pb 额外拉 PE分位+PB分位(A股可靠; 港股PE分位不可用; 北交所PB分位不可用)")
        print("  --fin 额外拉 2025年报+2026Q1财务+Q1同比(手算, 修复akshare返回0)")
        return
    qt = fetch_qt(codes)
    results = []
    for code in codes:
        q = qt.get(code)
        if not q:
            results.append({"code": code, "err": "无行情(检查代码或交易时间)"})
            continue
        ctype = q.get('type', 'sh')
        rec = {
            "code": code, "type": ctype, "name": q['name'], "price": q['price'],
            "pct": q['pct'], "pe": q['pe'], "pb": q['pb'],
            "mktcap": q['mktcap'], "hi52": q['hi52'], "lo52": q['lo52'],
            "pos52": q['pos52'], "turnover": q['turnover'],
        }
        if do_pb:
            pb, pbp = fetch_pb_percentile(code, ctype); time.sleep(0.2)
            pe, pep = fetch_pe_percentile(code, ctype); time.sleep(0.2)
            rec.update({"pb_pct": pbp, "pe_pct": pep, "pb_now": pb, "pe_now": pe})
        if do_fin:
            q1r, anr, q1_yoy = fetch_fin(code, ctype); time.sleep(0.2)
            rec.update({
                "net_2025": yi(anr.get('PARENT_NETPROFIT')) if anr else None,
                "rev_2025": yi(anr.get('TOTAL_OPERATE_INCOME')) if anr else None,
                "net_q1": yi(q1r.get('PARENT_NETPROFIT')) if q1r else None,
                "rev_q1": yi(q1r.get('TOTAL_OPERATE_INCOME')) if q1r else None,
                "q1_yoy": q1_yoy,  # 手算Q1同比, 修复akshare返回0的问题
            })
        results.append(rec)

    if do_json:
        print(json.dumps(results, ensure_ascii=False, indent=2)); return

    # markdown 表
    print("| 代码 | 类型 | 名称 | 现价 | 涨跌% | PE | PB | 市值亿 | 52周位 |", end="")
    if do_pb: print(" PE分位 | PB分位 |", end="")
    if do_fin: print(" 2025净利亿 | Q1净利亿 | Q1同比 |", end="")
    print()
    print("|---|---|---|---|---|---|---|---|---|", end="")
    if do_pb: print("---|---|", end="")
    if do_fin: print("---|---|---|", end="")
    print()
    for r in results:
        if "err" in r:
            print(f"| {r['code']} | - | - | - | - | - | - | - | - |", end="")
            if do_pb: print(" - | - |", end="")
            if do_fin: print(" - | - | - |", end="")
            print(); continue
        print(f"| {r['code']} | {r['type']} | {r['name']} | {r['price']:.2f} | {r['pct']:+.2f} | "
              f"{r['pe']:.1f} | {r['pb']:.2f} | {r['mktcap']:.0f} | {r['pos52']:.0f}% |", end="")
        if do_pb:
            pep = f"{r.get('pe_pct'):.0f}%" if r.get('pe_pct') is not None else "N/A"
            pbp = f"{r.get('pb_pct'):.0f}%" if r.get('pb_pct') is not None else "N/A"
            print(f" {pep} | {pbp} |", end="")
        if do_fin:
            n25 = f"{r.get('net_2025'):.1f}" if r.get('net_2025') is not None else "-"
            nq1 = f"{r.get('net_q1'):.1f}" if r.get('net_q1') is not None else "-"
            yoy = f"{r.get('q1_yoy'):+.1f}%" if r.get('q1_yoy') is not None else "N/A"
            print(f" {n25} | {nq1} | {yoy} |", end="")
        print()

if __name__ == "__main__":
    main()
