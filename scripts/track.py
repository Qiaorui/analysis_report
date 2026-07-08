#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
季度跟踪模板 — 投资组合监控
用法: python3 track.py [--md]
功能: 拉取稳健主仓20+小市值20的实时行情/财务/PB分位,对比建仓价/止损/目标价,输出状态表+告警
数据源: 腾讯qt.gtimg.cn + 东方财富datacenter + baidu估值 (eastmoney push2被屏蔽,已绕过)
"""
import akshare as ak
import requests, warnings, re, time, sys, datetime
warnings.filterwarnings("ignore")

# ============ 稳健主仓20 (建仓/止损/目标, 来自深度报告) ============
MAIN = [
    # code, name, 建仓low, 建仓high, 止损, 目标low, 目标high
    ("600519","贵州茅台",1100,1200,1050,1450,1550),
    ("000858","五粮液",65,72,62,88,95),
    ("600887","伊利股份",23,25,22,29,31),
    ("603288","海天味业",31,34,30,40,43),
    ("000333","美的集团",72,79,70,90,95),
    ("600036","招商银行",35.5,37.5,34.5,45,48),
    ("601398","工商银行",7.0,7.3,6.8,8.0,8.5),
    ("600900","长江电力",26.0,27.2,25.3,30,31),
    ("601728","中国电信",5.0,5.6,4.8,6.5,7.0),
    ("600938","中国海油",25.5,27,24.8,32,34),
    ("300750","宁德时代",340,361,330,430,450),
    ("002594","比亚迪",80,88,75,110,120),
    ("300274","阳光电源",110,125,105,160,180),
    ("600276","恒瑞医药",48,54,46,65,70),
    ("603259","药明康德",105,115,100,130,140),
    ("601899","紫金矿业",24,27,22,31,35),
    ("600547","山东黄金",23,25,22,30,31),
    ("600988","赤峰黄金",28,31,26,35,38),
    ("300124","汇川技术",56,63,53,78,88),
    ("300759","三花智控",27,30,26,36,40),
]
# ============ 小市值20 (彩票仓, 无精确目标, 仅跟踪现价/PB分位) ============
SMALL = [
    ("002896","中大力德"),("300580","贝斯特"),("688160","步科股份"),("300969","恒帅股份"),
    ("301160","翔楼新材"),("300718","长盛轴承"),("300100","双林股份"),("000099","中信海直"),
    ("688631","莱斯信息"),("300681","英搏尔"),("300410","金盾股份"),("688070","纵横股份"),
    ("300768","迪普科技"),("000555","神州信息"),("300777","中简科技"),("688591","泰凌微"),
    ("300576","容大感光"),("300827","上能电气"),("603612","索通发展"),("002664","信质集团"),
]

def fv(v,dec=1,yi=False):
    try:
        if v is None: return None
        vv=float(v)
        if yi and abs(vv)>10000: return vv/1e8
        return vv
    except: return None

def fetch_qt(codes):
    """腾讯批量行情"""
    qt={}
    for i in range(0,len(codes),40):
        batch=codes[i:i+40]
        qcodes=",".join([("sh" if c.startswith("6") else "sz")+c for c in batch])
        try:
            r=requests.get(f"https://qt.gtimg.cn/q={qcodes}",headers={"Referer":"https://gu.qq.com/"},timeout=20)
            r.encoding='gbk'
            for line in r.text.strip().split(';'):
                if '"' in line:
                    p=line.split('"')[1].split('~')
                    if len(p)>48:
                        qt[p[2]]={'price':float(p[3]),'pe':float(p[39]) if p[39] else 0,'mktcap':float(p[44]),
                                  'hi52':float(p[47]) if p[47] else 0,'lo52':float(p[48]) if p[48] else 0}
        except: pass
    return qt

def fetch_fin(code):
    """datacenter 2025年报+Q1"""
    try:
        url=f"https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=REPORTDATE&sortTypes=-1&pageSize=8&pageNumber=1&reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECURITY_CODE=%22{code}%22)"
        rows=requests.get(url,timeout=15).json().get('result',{}).get('data',[]) or []
        q1=[x for x in rows if x.get('REPORTDATE','').startswith('2026-03-31')]; q1r=q1[0] if q1 else {}
        an=[x for x in rows if x.get('REPORTDATE','').startswith('2025-12-31')]; anr=an[0] if an else (rows[0] if rows else {})
        return q1r, anr
    except: return {},{}

def fetch_pb(code):
    """baidu PB分位"""
    try:
        bv=ak.stock_zh_valuation_baidu(symbol=code,indicator="市净率",period="近十年")
        s=bv['value'].astype(float).dropna()
        cur=float(s.iloc[-1]); pct=float((s<cur).sum())/len(s)*100
        return cur, pct
    except: return None,None

def status_label(price, bl, bh, sl, tl, th):
    """建仓/止损/目标状态"""
    if price <= sl: return "🔴破止损"
    if bl <= price <= bh: return "🟢建仓区"
    if price < bl: return "🟡低于建仓(更便宜)"
    if price >= th: return "🟣超目标(止盈)"
    if price >= tl: return "🟠接近目标"
    return "⚪在建仓上方"

def main():
    md = "--md" in sys.argv
    today = datetime.date.today().isoformat()
    all_codes = [c for c,*_ in MAIN] + [c for c,_ in SMALL]
    qt = fetch_qt(all_codes)

    out = []
    out.append(f"# 投资组合跟踪 ({today})\n")
    alerts = []

    # === 稳健主仓 ===
    out.append("## 一、稳健主仓20（建仓/止损/目标监控）\n")
    out.append("| 代码 | 名称 | 现价 | PE | 市值亿 | 52周位置 | 建仓区 | 现状 | 距目标% | 2025净利亿 | PB分位 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for code,name,bl,bh,sl,tl,th in MAIN:
        q=qt.get(code,{})
        if not q: continue
        price=q['price']
        pos52 = f"{(price-q['lo52'])/(q['hi52']-q['lo52'])*100:.0f}%" if q['hi52']>q['lo52'] else "-"
        st = status_label(price, bl, bh, sl, tl, th)
        tgt_pct = f"{(th/price-1)*100:+.0f}%"
        # 财务
        time.sleep(0.3)
        q1r,anr = fetch_fin(code)
        np = fv(anr.get('PARENT_NETPROFIT'), yi=True)
        npstr = f"{np:.0f}" if np else "-"
        pb,pbp = fetch_pb(code); time.sleep(0.2)
        pbstr = f"{pbp:.0f}%" if pbp is not None else "-"
        out.append(f"| {code} | {name} | {price:.1f} | {q['pe']:.0f} | {q['mktcap']:.0f} | {pos52} | {bl}-{bh} | {st} | {tgt_pct} | {npstr} | {pbstr} |")
        if "破止损" in st: alerts.append(f"🔴 {name}{code} 现价{price:.1f} 破止损{sl}")
        elif "超目标" in st: alerts.append(f"🟣 {name}{code} 现价{price:.1f} 超目标{th}，止盈")
        elif "建仓区" in st: alerts.append(f"🟢 {name}{code} 现价{price:.1f} 在建仓区{bl}-{bh}")

    # === 小市值 ===
    out.append("\n## 二、小市值20（彩票仓，跟踪现价/PB分位）\n")
    out.append("| 代码 | 名称 | 现价 | PE | 市值亿 | 52周位置 | PB分位 |")
    out.append("|---|---|---|---|---|---|---|")
    for code,name in SMALL:
        q=qt.get(code,{})
        if not q: continue
        price=q['price']
        pos52 = f"{(price-q['lo52'])/(q['hi52']-q['lo52'])*100:.0f}%" if q['hi52']>q['lo52'] else "-"
        pb,pbp = fetch_pb(code); time.sleep(0.2)
        pbstr = f"{pbp:.0f}%" if pbp is not None else "-"
        out.append(f"| {code} | {name} | {price:.1f} | {q['pe']:.0f} | {q['mktcap']:.0f} | {pos52} | {pbstr} |")

    # === 告警 ===
    out.append("\n## 三、告警\n")
    if alerts:
        for a in alerts: out.append(f"- {a}")
    else:
        out.append("- 无告警")

    out.append(f"\n> 数据源:腾讯行情+东方财富datacenter+baidu估值 | 财务2025年报 | 生成{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    result = "\n".join(out)
    if md:
        with open("tracking_report.md","w",encoding="utf-8") as f: f.write(result)
        print("已生成 tracking_report.md")
    else:
        print(result)

if __name__ == "__main__":
    main()
