"""Run the pinned daily scanner on live data, rejecting stale completed sessions."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from cloud_guard import completed_bars


def run(root, manifest, symbols):
    for item in manifest["source_files"]:
        if hashlib.sha256((root / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("pinned source hash mismatch: " + item["path"])
    spec = importlib.util.spec_from_file_location("pinned_scanner", root / "trader-scanner/scan.py")
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    now = dt.datetime.now(dt.timezone.utc)
    now_plain = now.replace(tzinfo=None)
    local = now.astimezone(ZoneInfo("America/New_York"))
    if local.year not in scanner.CALENDAR_YEARS:
        raise ValueError("unknown exchange calendar year")
    day = local.date()
    session = scanner.session(day)
    if not session or local.time().replace(tzinfo=None) < session[1]:
        day -= dt.timedelta(days=1)
    while not scanner.trading_day(day)[0]:
        day -= dt.timedelta(days=1)
    data, errors = scanner.fetch_spark(symbols, "3mo", "1d", scanner.PAUSE)
    recovered, closing_observations, latest_dates = [], [], {}
    for symbol in symbols:
        bars = scanner.daily_closes(data[symbol], now_plain) if symbol in data else []
        if not bars or bars[-1][0] != day:
            try:
                fresh = scanner.parse_chart(scanner.yahoo_get(scanner.chart_path(symbol, "3mo", "1d")), symbol)
                bars = scanner.daily_closes(fresh, now_plain)
                if not bars or bars[-1][0] != day:
                    # Yahoo can leave the completed daily candle null after the close.
                    # A complete live intraday session plus its actual closing print is
                    # separate evidence of the close; never forward-fill an old quote.
                    previous = day - dt.timedelta(days=1)
                    while not scanner.trading_day(previous)[0]:
                        previous -= dt.timedelta(days=1)
                    if not bars or bars[-1][0] != previous:
                        raise ValueError("daily history has a gap larger than the latest session")
                    text = scanner.yahoo_get(scanner.chart_path(symbol, "5d", "5m"))
                    intraday = json.loads(text)
                    result = intraday["chart"]["result"][0]
                    session_times = scanner.session(day)
                    opens = dt.datetime.combine(day, session_times[0], ZoneInfo("America/New_York"))
                    closes = dt.datetime.combine(day, session_times[1], ZoneInfo("America/New_York"))
                    full_session = completed_bars(intraday, now, opens, closes)
                    prices = result["indicators"]["quote"][0]["close"]
                    printed = [float(p) for t, p in zip(result["timestamp"], prices)
                               if t == int(closes.timestamp()) and p is not None]
                    meta = result["meta"]
                    event = dt.datetime.fromtimestamp(meta["regularMarketTime"], dt.timezone.utc)
                    price = float(meta["regularMarketPrice"])
                    if not printed or abs(printed[-1] - price) > 0.011 or not closes <= event <= now:
                        raise ValueError("actual closing print and timestamped regular quote do not reconcile")
                    if event.astimezone(ZoneInfo("America/New_York")).date() != day:
                        raise ValueError("closing observation belongs to another session")
                    # Keep the real closing print timestamp, not a fabricated daily start.
                    fresh["t"].append(int(closes.timestamp()))
                    fresh["c"].append(printed[-1])
                    fresh["meta"] = meta
                    closing_volume = sum((v or 0) for t, v in zip(result["timestamp"], result["indicators"]["quote"][0]["volume"])
                                         if t == int(closes.timestamp()))
                    observed_volume = sum(b["volume"] for b in full_session) + closing_volume
                    fresh["meta"]["regularMarketVolume"] = observed_volume
                    closing_observations.append({"symbol": symbol, "session_id": day.isoformat(),
                                                 "source_event_epoch": int(closes.timestamp()),
                                                 "close": printed[-1], "observed_five_minute_volume": observed_volume,
                                                 "method": "observed live closing print after full OHLCV session; volume is bar sum, not official consolidated volume"})
                    bars = scanner.daily_closes(fresh, now_plain)
                data[symbol] = fresh
                errors.pop(symbol, None)
                recovered.append(symbol)
            except Exception as exc:
                data.pop(symbol, None)
                errors[symbol] = str(exc)
                continue
        latest_dates[symbol] = bars[-1][0].isoformat()
    hits, counts, last = scanner.scan_daily(data, symbols, now_plain, 5, 1000000)
    return {"status": "BLOCK" if errors else "WAITING", "checked_ist": now.astimezone(ZoneInfo("Asia/Kolkata")).isoformat(),
            "latest_completed_session_id": day.isoformat(), "daily_bar_session_ids": latest_dates,
            "universe": symbols, "counts": counts, "hits": hits, "recovered_with_live_chart": recovered,
            "closing_observations": closing_observations,
            "errors": errors, "qualification": "Daily context only. Entry requires an actual fresh completed five-minute trigger."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--symbols", default="SNDK,MSFT,AAPL,NVDA,AMD")
    args = parser.parse_args()
    try:
        result = run(Path(args.source), json.loads(Path(args.manifest).read_text()), args.symbols.split(","))
        print(json.dumps(result, indent=2))
        raise SystemExit(1 if result["errors"] else 0)
    except Exception as exc:
        print(json.dumps({"status": "BLOCK", "error": str(exc)}))
        raise SystemExit(1)
