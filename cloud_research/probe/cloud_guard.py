"""Cloud research gates; no network, file writes, broker calls, or fill recording.

The durable journal is supplied by the cloud agent from its authoritative
Library identity on every run. This module never treats a scratch file as state.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math

NY = ZoneInfo("America/New_York")
IST = ZoneInfo("Asia/Kolkata")


def ist_text(value):
    if value.tzinfo is None:
        raise ValueError("timestamp requires a time zone")
    return value.astimezone(IST).strftime("%d %B %Y %H:%M:%S IST")


def week_key(value):
    local = value.astimezone(NY)
    return (local.date() - timedelta(days=local.weekday())).isoformat()


def setup_key(ticker, setup, session, trigger_epoch):
    value = [ticker.upper(), setup, session, int(trigger_epoch)]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def completed_bars(raw_chart, now, session_open, session_close):
    """Reject missing raw OHLC instead of the upstream close-value substitution."""
    if any(t.tzinfo is None for t in (now, session_open, session_close)):
        raise ValueError("aware clocks required")
    result = raw_chart["chart"]["result"][0]
    if result["meta"].get("dataGranularity") != "5m":
        raise ValueError("five-minute data required")
    columns = result["indicators"]["quote"][0]
    output = []
    seen = set()
    for i, epoch in enumerate(result.get("timestamp") or []):
        start = datetime.fromtimestamp(epoch, timezone.utc)
        end = start + timedelta(minutes=5)
        if not session_open <= start < session_close or end > now:
            continue
        if epoch % 300:
            continue  # A live off-grid print is not a completed candle.
        if epoch in seen:
            raise ValueError("duplicate candle timestamp")
        seen.add(epoch)
        row = {key: columns[key][i] for key in ("open", "high", "low", "close", "volume")}
        if any(v is None or not math.isfinite(float(v)) for v in row.values()):
            raise ValueError("missing or invalid OHLCV")
        if min(row[k] for k in ("open", "high", "low", "close")) <= 0 or row["volume"] <= 0:
            raise ValueError("nonpositive price or volume")
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError("inconsistent OHLC")
        output.append(dict(row, epoch=epoch, end=end))
    output.sort(key=lambda b: b["epoch"])
    expected = int((min(now, session_close) - session_open).total_seconds() // 300)
    if expected < 0 or len(output) != expected:
        raise ValueError("incomplete session candle coverage")
    if any(b["epoch"] != int(session_open.timestamp()) + i * 300 for i, b in enumerate(output)):
        raise ValueError("missing session candle")
    return output


def entry_gate(entry_result, quote_time, trigger_end, now, open_time, entry_cutoff):
    """A historical first trigger never becomes a new current entry."""
    if any(t.tzinfo is None for t in (quote_time, now, open_time, entry_cutoff)):
        return "BLOCK", "timezone information missing"
    if not open_time + timedelta(minutes=15) <= now <= entry_cutoff:
        return "WAITING", "outside the current-session entry window"
    if entry_result.get("date") != now.astimezone(NY).date().isoformat():
        return "BLOCK", "entry evidence belongs to another session"
    quote_age = (now - quote_time).total_seconds()
    if not 0 <= quote_age <= 120:
        return "BLOCK", "quote is stale or in the future"
    if entry_result.get("status") != "triggered" or not entry_result.get("trigger"):
        return "WAITING", "no actual completed-bar trigger"
    if trigger_end is None or trigger_end.tzinfo is None:
        return "BLOCK", "trigger timestamp missing"
    age = (now - trigger_end).total_seconds()
    if not 0 <= age < 300 or not open_time + timedelta(minutes=15) <= trigger_end <= entry_cutoff:
        return "WAITING", "trigger has expired or is outside the entry window"
    return "RESEARCH_ONLY", "entry evidence is eligible for downstream draft analysis"


def alert_gate(journal, ticker, setup, session, trigger_epoch, now):
    """Read-only check. Sending and durable recording must be serialized by the agent."""
    key = setup_key(ticker, setup, session, trigger_epoch)
    records = journal.get("alerted_setups", [])
    if any(r.get("setup_key") == key for r in records):
        return "UPDATE_OR_QUIET", key
    count = sum(r.get("kind") == "NEW" and r.get("week_key") == week_key(now) for r in records)
    return ("ALLOW_NEW" if count < 2 else "WEEKLY_LIMIT"), key


def broker_command_allowed(command):
    return command == "show"


if __name__ == "__main__":
    raise SystemExit("Library-backed cloud agent orchestration is required; no standalone or local scheduled runner.")
