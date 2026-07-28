#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
20260728 Step2-2a 市场阶段判断数据底座 v2
数据源: 腾讯指数现价(s_前缀) + 新浪K线(均线/52周/近30日) + akshare北向
输出: reports_20260728/_market_stage_data.md
"""
import requests, warnings, re, sys, datetime, json
warnings.filterwarnings("ignore")
try:
    import akshare as ak
    HAS_AK = True
except ImportError:
    HAS_AK = False

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
HDR = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"}

INDICES = [
    ("sh000001", "上证综指"), ("sz399001", "深成指"), ("sz399006", "创业板指"),
    ("sh000688", "科创50"), ("sh000016", "上证50"), ("sh000300", "沪深300"),
]
ATTACK = [("300308", "中际旭创", "AI光模块"), ("601138", "工业富联", "AI服务器"),
          ("688256", "寒武纪", "AI芯片"), ("300750", "宁德时代", "新能源"),
          ("600030", "中信证券", "券商")]
DEFEND = [("600036", "招商银行", "银行"), ("600900", "长江电力", "电力"),
          ("600519", "贵州茅台", "白酒"), ("601225", "陕西煤业", "煤炭")]

def sina_prefix(code):
    return ("sh" if code.startswith("6") or code.startswith("5") else "sz") + code if len(code) == 6 else code

def fetch_index_qt():
    """腾讯指数现价(s_前缀短格式): p[1]=名称 p[3]=现价 p[5]=涨跌幅"""
    codes = ",".join(["s_" + c for c, _ in INDICES])
    r = requests.get(f"https://qt.gtimg.cn/q={codes}",
                     headers={"Referer": "https://gu.qq.com/"}, timeout=20)
    r.encoding = 'gbk'
    out = {}
    for line in r.text.strip().split(';'):
        if '=' in line and '"' in line:
            key = line.split('=')[0].strip().lower()  # v_s_sh000001
            key = re.sub(r'^v_s_', '', key)  # -> sh000001
            val = line.split('"')[1]
            p = val.split('~')
            if len(p) > 5:
                out[key] = {'name': p[1], 'price': p[3], 'pct': p[5]}
    return out

def fetch_sina_kline(symbol, datalen=250):
    """新浪K线API: symbol如sh000001/sz000001, 返回closes列表"""
    try:
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={datalen}"
        r = requests.get(url, headers=HDR, timeout=20)
        data = json.loads(r.text)
        closes = [float(d['close']) for d in data]
        return closes
    except Exception as e:
        return None

def analyze_closes(closes):
    """从closes算 MA/52周位/近5/30日涨跌"""
    if not closes or len(closes) < 5: return None
    cur = closes[-1]
    ma = lambda n: round(sum(closes[-n:]) / n, 2) if len(closes) >= n else None
    win = closes[-250:] if len(closes) >= 250 else closes
    hi52, lo52 = max(win), min(win)
    pos52 = round((cur - lo52) / (hi52 - lo52) * 100, 1) if hi52 > lo52 else 0
    chg5 = round((cur / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else None
    chg30 = round((cur / closes[-31] - 1) * 100, 2) if len(closes) >= 31 else None
    return {'cur': cur, 'ma20': ma(20), 'ma60': ma(60), 'ma250': ma(250),
            'hi52': round(hi52, 2), 'lo52': round(lo52, 2), 'pos52': pos52,
            'chg5': chg5, 'chg30': chg30}

def fetch_north():
    """北向资金(akshare, 可能失败)"""
    if not HAS_AK: return None
    for fn in ['stock_hsgt_hist_em']:
        for sym in ['北向资金', '沪深股通']:
            try:
                df = getattr(ak, fn)(symbol=sym)
                df = df.tail(20)
                vcol = [c for c in df.columns if '净流' in str(c) or '金额' in str(c)]
                if vcol:
                    vals = df[vcol[0]].astype(float).tolist()
                    return {'sum20': round(sum(vals), 0), 'avg': round(sum(vals)/len(vals), 0),
                            'last': round(vals[-1], 0)}
            except Exception:
                continue
    return None

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# 20260728 市场阶段判断数据底座 ({now})\n",
           "> Step2-2a 数据支撑 | 腾讯指数现价 + 新浪K线(均线/52周/近30日) + akshare北向\n"]

    # 1. 指数现价(腾讯)
    out.append("## 一、主要指数现价与当日涨跌(腾讯)\n")
    qt = fetch_index_qt()
    out.append("| 指数 | 名称 | 现价 | 当日涨跌% |")
    out.append("|---|---|---|---|")
    for code, name in INDICES:
        q = qt.get(code)
        if q:
            out.append(f"| {code} | {q['name']} | {q['price']} | {q['pct']}% |")
    out.append("")

    # 2. 指数均线/52周/近期涨跌(新浪K线)
    out.append("## 二、指数均线/52周位/近期涨跌(新浪K线, 阶段判断核心)\n")
    out.append("| 指数 | 现价 | MA20 | MA60 | MA250 | 52周位 | 近5日 | 近30日 | 价vs MA60 | 价vs MA250 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for code, name in INDICES:
        cs = fetch_sina_kline(code, 260)
        a = analyze_closes(cs) if cs else None
        if not a:
            out.append(f"| {name} | ERR | | | | | | | | |"); continue
        vs60 = "多头" if (a['ma60'] and a['cur'] > a['ma60']) else ("空头" if a['ma60'] else "-")
        vs250 = "多头" if (a['ma250'] and a['cur'] > a['ma250']) else ("空头" if a['ma250'] else "-")
        ma20s = f"{a['ma20']}" if a['ma20'] else "-"
        ma60s = f"{a['ma60']}" if a['ma60'] else "-"
        ma250s = f"{a['ma250']}" if a['ma250'] else "-"
        chg5s = f"{a['chg5']:+.2f}%" if a['chg5'] is not None else "-"
        chg30s = f"{a['chg30']:+.2f}%" if a['chg30'] is not None else "-"
        out.append(f"| {name} | {a['cur']} | {ma20s} | {ma60s} | {ma250s} | {a['pos52']:.0f}% | {chg5s} | {chg30s} | {vs60} | {vs250} |")
    out.append("")

    # 3. 攻防板块近5/30日
    out.append("## 三、攻防结构: 进攻 vs 防御 近5/30日涨跌\n")
    out.append("**进攻板块(科技/AI/新能源/券商)**\n")
    out.append("| 代码 | 名称 | 板块 | 近5日 | 近30日 |")
    out.append("|---|---|---|---|---|")
    atk5, atk30 = [], []
    for code, name, sec in ATTACK:
        cs = fetch_sina_kline(sina_prefix(code), 35)
        a = analyze_closes(cs) if cs else None
        if a:
            out.append(f"| {code} | {name} | {sec} | {a['chg5']:+.2f}% | {a['chg30']:+.2f}% |")
            if a['chg5'] is not None: atk5.append(a['chg5'])
            if a['chg30'] is not None: atk30.append(a['chg30'])
    out.append(f"\n**进攻板块均值**: 近5日 {sum(atk5)/len(atk5):+.2f}% | 近30日 {sum(atk30)/len(atk30):+.2f}%\n")

    out.append("**防御板块(银行/公用/食饮/煤炭)**\n")
    out.append("| 代码 | 名称 | 板块 | 近5日 | 近30日 |")
    out.append("|---|---|---|---|---|")
    def5, def30 = [], []
    for code, name, sec in DEFEND:
        cs = fetch_sina_kline(sina_prefix(code), 35)
        a = analyze_closes(cs) if cs else None
        if a:
            out.append(f"| {code} | {name} | {sec} | {a['chg5']:+.2f}% | {a['chg30']:+.2f}% |")
            if a['chg5'] is not None: def5.append(a['chg5'])
            if a['chg30'] is not None: def30.append(a['chg30'])
    out.append(f"\n**防御板块均值**: 近5日 {sum(def5)/len(def5):+.2f}% | 近30日 {sum(def30)/len(def30):+.2f}%\n")

    # 4. 北向
    out.append("## 四、北向资金(近20日)\n")
    nf = fetch_north()
    out.append(f"- {nf}" if nf else "- 北向资金接口不可用")
    out.append("")

    out.append(f"> 生成 {now} | 阶段判断核心看: §二指数多空+52周位, §三攻防相对强弱(防御>进攻=避险/熊市特征)")
    result = "\n".join(out)
    with open("reports_20260728/_market_stage_data.md", "w", encoding="utf-8") as f:
        f.write(result)
    print(result)

if __name__ == "__main__":
    main()
