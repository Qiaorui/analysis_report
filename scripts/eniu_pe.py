#!/usr/bin/env python3
"""亿牛网 PE/PB 历史百分位提取工具。

数据源: eniu.com (亿牛网) — 提供 PE/PB 3年/5年/10年/全时间百分位 + 历史统计。
优势: 比 baidu PE分位窗口更长(10年)、更直观，且同时提供PB分位作交叉验证。

用法:
    uv run python3 scripts/eniu_pe.py 600519              # 单只
    uv run python3 scripts/eniu_pe.py 600519 600150 300750 # 多只
    uv run python3 scripts/eniu_pe.py 600519 --json        # JSON输出

零外部依赖(仅 stdlib)。用 curl --noproxy 直连绕过系统代理。
"""

import json
import re
import subprocess
import sys

_TIMEOUT = 20


def _fetch(url: str) -> str:
    result = subprocess.run(
        ["/usr/bin/curl", "-s", "--noproxy", "*", "--connect-timeout", "10",
         "--max-time", str(_TIMEOUT),
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT + 5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"请求失败: {url}")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return result.stdout.decode("gbk")


def _code_prefix(code: str) -> str:
    code = code.strip()
    if code.startswith(("6", "9", "5")):
        return "sh"
    elif code.startswith(("0", "3", "2", "1")):
        return "sz"
    elif code.startswith(("4", "8")):
        return "bj"
    return "sh"


def get_eniu_data(code: str) -> dict:
    """从亿牛网提取 PE/PB 百分位及关键指标。"""
    code = code.strip()
    prefix = _code_prefix(code)
    url = f"https://eniu.com/gu/{prefix}{code}"

    text = _fetch(url)

    data = {"代码": code, "URL": url}

    # PE 百分位
    for window in ["近3年", "近5年", "近10年", "所有时间"]:
        m = re.search(rf"{window}：([\d.]+)%", text)
        if m:
            data[f"PE百分位_{window}"] = float(m.group(1))

    # PB 百分位 (如果页面有)
    pb_section = re.search(r'当前市净率百分位.*?所有时间：([\d.]+)%', text, re.DOTALL)
    if pb_section:
        data["PB百分位_所有时间"] = float(pb_section.group(1))

    # PE 统计 (HTML结构: <span>历史平均</span> ... <h3>30.83</h3>)
    for key, label in [
        ("当前PE", "当前市盈率"),
        ("历史平均PE", "历史平均"),
        ("历史最高PE", "历史最高"),
        ("历史最低PE", "历史最低"),
    ]:
        m = re.search(rf'{label}.*?<h3>([\d.]+)</h3>', text, re.DOTALL)
        if m:
            data[key] = float(m.group(1))

    # 关键指标 (HTML结构: 标签：<a ...>值 元/亿/%</a>)
    for key, pattern in [
        ("价格", r"价\s*格：.*?>([\d.]+)\s*元"),
        ("市值_亿", r"市\s*值：.*?>([\d.]+)\s*亿"),
        ("ROE", r"ROE：.*?>([\d.]+)"),
        ("毛利率", r"毛利率：.*?>([\d.]+)"),
        ("负债率", r"负债率：.*?>([\d.]+)"),
        ("股息率", r"股息率：.*?>([\d.]+)"),
        ("市净率", r"市净率：.*?>([\d.]+)"),
        ("市销率", r"市销率：.*?>([\d.]+)"),
    ]:
        m = re.search(pattern, text)
        if m:
            val = m.group(1)
            data[key] = float(val) if "." in val else int(val)

    # 公司名
    m = re.search(r"<title>([^（]+)\(", text)
    if m:
        data["名称"] = m.group(1)

    return data


def _fmt_val(key: str, val) -> str:
    if val is None or val == "":
        return "-"
    if isinstance(val, float):
        if "百分位" in key or "ROE" in key or "毛利率" in key or "负债率" in key or "股息率" in key:
            return f"{val:.1f}%"
        if "亿" in key:
            return f"{val:.0f}亿"
        return f"{val:.2f}"
    return str(val)


def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    codes = [a for a in args if a != "--json"]

    if not codes:
        print(__doc__)
        sys.exit(1)

    results = []
    for code in codes:
        try:
            data = get_eniu_data(code)
            results.append(data)
        except Exception as e:
            results.append({"代码": code, "错误": str(e)})

    if json_mode:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # 表格输出
    for d in results:
        if "错误" in d:
            print(f"❌ {d['代码']}: {d['错误']}")
            continue

        name = d.get("名称", d["代码"])
        print(f"{'='*60}")
        print(f"{name} ({d['代码']})")
        print(f"{'='*60}")
        print(f"  价格: {d.get('价格', '-')}  市值: {d.get('市值_亿', '-')}亿")
        print()
        print(f"  PE百分位:")
        for w in ["近3年", "近5年", "近10年", "所有时间"]:
            k = f"PE百分位_{w}"
            v = d.get(k, "-")
            bar = "█" * int(float(v) / 5) if isinstance(v, (int, float)) else ""
            print(f"    {w:6s}: {v:>6}%  {bar}")
        print()
        pe_str = f"当前PE={d.get('当前PE', '-')}  历史平均={d.get('历史平均PE', '-')}  最高={d.get('历史最高PE', '-')}  最低={d.get('历史最低PE', '-')}"
        print(f"  {pe_str}")
        print()
        extras = []
        for k in ["ROE", "毛利率", "负债率", "股息率", "市净率", "市销率"]:
            if k in d:
                extras.append(f"{k}={d[k]}{'%' if '率' in k else ''}")
        if extras:
            print(f"  {'  '.join(extras)}")
        print()


if __name__ == "__main__":
    main()
