#!/usr/bin/env python3
"""
Lấy dữ liệu giao dịch từ Google Sheet -> lưu vào data/ -> sinh báo cáo docs/index.html
Chỉ dùng thư viện chuẩn của Python (không cần pip install).

Sheet cần được chia sẻ: "Bất kỳ ai có đường liên kết" -> Người xem.
"""
import csv
import io
import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

SHEET_ID = os.getenv("SHEET_ID", "1aHx9w5q-gVp6E4Xq71-FgyUuY7MKNG3K9gA4MEFHMx8")
GID = os.getenv("SHEET_GID", "1273594710")
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

# (nhãn, cận dưới, cận trên) theo số ngày nắm giữ
BUCKETS = [("1–2 ngày", 0, 2), ("3–7 ngày", 3, 7), ("8–14 ngày", 8, 14),
           ("15–21 ngày", 15, 21), ("22+ ngày", 22, 10**6)]


# ----------------------------------------------------------------- helpers
def norm(s):
    return " ".join(str(s).replace("\u200b", "").split()).lower()


def num(s):
    s = str(s).replace(",", "").replace("%", "").replace("\u200b", "").strip()
    if s in ("", "-", "#DIV/0!", "#N/A", "#REF!", "#VALUE!"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(s):
    """Hỗ trợ '8/Sep/26', '08/09/2026', '2026-09-08'."""
    s = str(s).strip()
    if not s:
        return None
    try:
        if "-" in s and s[:4].isdigit():
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        p = s.split("/")
        if len(p) != 3:
            return None
        d, m, y = p
        m = MONTHS[m[:3].lower()] if m.isalpha() else int(m)
        y = int(y)
        y += 2000 if y < 100 else 0
        return date(y, m, int(d))
    except (ValueError, KeyError):
        return None


def fetch_csv():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig")


# ----------------------------------------------------------------- parse
def parse_trades(raw_csv, today):
    rows = list(csv.reader(io.StringIO(raw_csv)))
    hi = next((i for i, r in enumerate(rows)
               if "cổ phiếu" in map(norm, r) and "ngày mua" in map(norm, r)), None)
    if hi is None:
        raise RuntimeError("Không tìm thấy dòng tiêu đề (Cổ phiếu / Ngày mua). "
                           "Sheet có bị đổi cấu trúc hoặc chưa chia sẻ công khai?")
    col = {}
    for i, h in enumerate(rows[hi]):
        col.setdefault(norm(h), i)

    def find(*names, prefix=False):
        for n in names:
            n = norm(n)
            if prefix:
                for k, v in col.items():
                    if k.startswith(n):
                        return v
            elif n in col:
                return col[n]
        return None

    C = {
        "ticker": find("Cổ phiếu"), "buy_date": find("Ngày mua"),
        "hold_qty": find("SL CP nắm giữ"), "buy_qty": find("KL mua"),
        "buy_price": find("Giá mua"), "cur_price": find("Giá hiện tại"),
        "exp_pct": find("% Lãi lỗ dự kiến"), "account": find("Vị thế mua"),
        "buy_value": find("Giá trị lệnh mua (trừ phí)", "Giá trị lệnh mua", prefix=True),
        "sell_date": find("Ngày bán / ngày hiện tại", "Ngày bán", prefix=True),
        "sell_qty": find("KL bán"), "sell_price": find("Giá bán"),
        "reason": find("Vị thế bán"),
        "sell_value": find("Giá trị lệnh bán (trừ thuế phí)", "Giá trị lệnh bán", prefix=True),
        "pnl": find("Lãi lỗ"), "pnl_pct": find("% lãi lỗ"),
    }

    def g(r, k):
        i = C[k]
        return r[i] if i is not None and i < len(r) else ""

    trades = []
    for r in rows[hi + 1:]:
        ticker = g(r, "ticker").strip().upper()
        buy_date = parse_date(g(r, "buy_date"))
        if not ticker or ticker == "0" or buy_date is None:
            continue
        sell_date = parse_date(g(r, "sell_date"))
        buy_price = num(g(r, "buy_price")) or 0
        cur_price = num(g(r, "cur_price")) or 0
        buy_qty = num(g(r, "buy_qty")) or 0
        hold_qty = num(g(r, "hold_qty")) or 0
        closed = sell_date is not None and (num(g(r, "sell_qty")) or 0) > 0

        t = {
            "ticker": ticker,
            "buy_date": buy_date.isoformat(),
            "buy_price": buy_price,
            "account": g(r, "account").strip() or "N/A",
            "status": "closed" if closed else "open",
        }
        if closed:
            qty = num(g(r, "sell_qty")) or buy_qty
            buy_value = num(g(r, "buy_value")) or buy_price * qty
            sell_value = num(g(r, "sell_value")) or 0
            pnl = num(g(r, "pnl"))
            if pnl is None:
                pnl = sell_value - buy_value
            pct = num(g(r, "pnl_pct"))
            if pct is None:
                pct = pnl / buy_value * 100 if buy_value else 0
            t.update(qty=qty, sell_date=sell_date.isoformat(),
                     sell_price=num(g(r, "sell_price")) or 0,
                     reason=g(r, "reason").strip().replace("\u200b", "") or "Không ghi",
                     pnl=pnl, pnl_pct=pct,
                     hold_days=max((sell_date - buy_date).days, 0))
        else:
            qty = hold_qty or buy_qty
            value = qty * cur_price
            unreal = (cur_price - buy_price) * qty
            t.update(qty=qty, cur_price=cur_price, market_value=value,
                     pnl=unreal,
                     pnl_pct=(cur_price / buy_price - 1) * 100 if buy_price else 0,
                     hold_days=max((today - buy_date).days, 0))
        trades.append(t)
    return trades


# ----------------------------------------------------------------- analytics
def agg(items):
    n = len(items)
    wins = sum(1 for x in items if x["pnl"] > 0)
    pnl = sum(x["pnl"] for x in items)
    return {
        "trades": n, "wins": wins, "pnl": round(pnl),
        "win_rate": round(wins / n * 100, 1) if n else 0,
        "avg_pct": round(sum(x["pnl_pct"] for x in items) / n, 2) if n else 0,
        "avg_hold": round(sum(x["hold_days"] for x in items) / n, 1) if n else 0,
    }


def group(items, keyfn):
    d = defaultdict(list)
    for x in items:
        d[keyfn(x)].append(x)
    return d


def analyse(trades, today):
    closed = [t for t in trades if t["status"] == "closed"]
    opened = [t for t in trades if t["status"] == "open"]
    closed.sort(key=lambda t: t["sell_date"])

    gp = sum(t["pnl"] for t in closed if t["pnl"] > 0)
    gl = -sum(t["pnl"] for t in closed if t["pnl"] < 0)
    summary = agg(closed)
    summary.update(
        profit_factor=round(gp / gl, 2) if gl else None,
        best=max((t["pnl"] for t in closed), default=0),
        worst=min((t["pnl"] for t in closed), default=0),
        open_count=len(opened),
        open_value=round(sum(t["market_value"] for t in opened)),
        open_unrealized=round(sum(t["pnl"] for t in opened)),
    )

    # ---- góc nhìn THỜI GIAN (theo ngày bán / ngày chốt lãi lỗ)
    def tagg(items, key):
        return [{"k": k, **agg(v)} for k, v in sorted(group(items, key).items())]

    monthly = tagg(closed, lambda t: t["sell_date"][:7])

    def wk(t):
        y, w, _ = date.fromisoformat(t["sell_date"]).isocalendar()
        return f"{y}-W{w:02d}"
    weekly = tagg(closed, wk)

    cum, daily = 0, []
    for k, v in sorted(group(closed, lambda t: t["sell_date"]).items()):
        s = sum(x["pnl"] for x in v)
        cum += s
        daily.append({"date": k, "pnl": round(s), "cum": round(cum), "trades": len(v)})

    # ---- góc nhìn CỔ PHIẾU
    by_c = group(closed, lambda t: t["ticker"])
    by_o = group(opened, lambda t: t["ticker"])
    stocks = []
    for tk in sorted(set(by_c) | set(by_o)):
        a = agg(by_c.get(tk, []))
        o = by_o.get(tk, [])
        a.update(ticker=tk,
                 open_qty=round(sum(x["qty"] for x in o)),
                 open_value=round(sum(x["market_value"] for x in o)),
                 unrealized=round(sum(x["pnl"] for x in o)))
        stocks.append(a)
    stocks.sort(key=lambda s: s["pnl"], reverse=True)

    # ---- góc nhìn THỜI GIAN NẮM GIỮ
    buckets = []
    for label, lo, hi in BUCKETS:
        items = [t for t in closed if lo <= t["hold_days"] <= hi]
        buckets.append({"label": label, **agg(items)})

    reasons = [{"k": k, **agg(v)} for k, v in group(closed, lambda t: t["reason"]).items()]
    accounts = [{"k": k, **agg(v)} for k, v in group(closed, lambda t: t["account"].split()[0]).items()]
    scatter = [{"x": t["hold_days"], "y": round(t["pnl_pct"], 2), "t": t["ticker"]} for t in closed]

    return {
        "updated": today.strftime("%d/%m/%Y"),
        "summary": summary, "monthly": monthly, "weekly": weekly, "daily": daily,
        "stocks": stocks, "buckets": buckets, "reasons": reasons, "accounts": accounts,
        "scatter": scatter, "open": opened, "trades": closed,
    }


# ----------------------------------------------------------------- output
def main():
    today = date.today()
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)

    raw = fetch_csv()
    (DATA_DIR / "raw_sheet.csv").write_text(raw, encoding="utf-8")

    trades = parse_trades(raw, today)
    if not trades:
        raise RuntimeError("Không đọc được giao dịch nào.")
    result = analyse(trades, today)

    with open(DATA_DIR / "trades.csv", "w", newline="", encoding="utf-8-sig") as f:
        keys = sorted({k for t in trades for k in t})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(trades)
    (DATA_DIR / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    (DOCS_DIR / "index.html").write_text(tpl.replace("__DATA__", payload), encoding="utf-8")

    s = result["summary"]
    print(f"OK: {s['trades']} lệnh đã đóng, {s['open_count']} lệnh đang mở, "
          f"lãi lỗ thực hiện {s['pnl']:,} đ, tỷ lệ thắng {s['win_rate']}%")


if __name__ == "__main__":
    main()
