"""Pure notification eligibility checks. No network, orders or account mutations.

This is a component, not an executable unattended research runner. Call only
with evidence produced by the trusted research engine, never a public request.
The durable store must reserve and reconcile delivery under one transaction.
"""
import datetime as dt
import hashlib
import json
import math
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')

def aware(value):
    return isinstance(value, dt.datetime) and value.utcoffset() is not None

def week(now):
    d = now.astimezone(NY).date()
    return (d - dt.timedelta(days=d.weekday())).isoformat()

def alert_key(candidate):
    # Preserve the existing cloud_guard key for BUY; otherwise a previously
    # alerted setup could look new after migration.
    setup = candidate['setup'] if candidate['action'] == 'BUY' else 'sell:' + candidate['setup']
    values = [candidate['ticker'].upper(), setup, candidate['session'], int(candidate['trigger_epoch'])]
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()

def eligible(candidate, journal, now):
    """Return eligibility only; never reserve, send or mark an alert delivered."""
    if not aware(now):
        return False, 'BLOCK: aware clock required'
    required = ['action','ticker','setup','session','trigger_epoch','quote_time',
                'valid_until','entry_open','entry_cutoff','calendar_verified',
                'material_news_verified','data_verified','plan_fingerprint',
                'risk_checked_fingerprint','risk_passed','shares','session_open','session_close']
    if any(k not in candidate for k in required):
        return False, 'BLOCK: missing decision evidence'
    c = candidate
    clocks = [c[k] for k in ['quote_time','valid_until','entry_open','entry_cutoff','session_open','session_close']]
    if not all(aware(x) for x in clocks):
        return False, 'BLOCK: timestamp qualification missing'
    if any(c[k] is not True for k in ['calendar_verified','material_news_verified','data_verified','risk_passed']):
        return False, 'BLOCK: required gate failed'
    if not c['plan_fingerprint'] or c['plan_fingerprint'] != c['risk_checked_fingerprint']:
        return False, 'BLOCK: exact plan changed or unchecked'
    if c['session'] != now.astimezone(NY).date().isoformat():
        return False, 'WAIT: different session'
    if not c['session_open'] <= now < c['session_close']:
        return False, 'WAIT: outside actual regular session'
    if not 0 <= (now - c['quote_time']).total_seconds() <= 120:
        return False, 'BLOCK: stale or future quote'
    if now >= c['valid_until']:
        return False, 'WAIT: decision expired'
    if type(c['shares']) is not int or c['shares'] <= 0:
        return False, 'BLOCK: positive whole shares required'
    try:
        trigger = float(c['trigger_epoch'])
        if not math.isfinite(trigger):
            raise ValueError()
        age = now.timestamp() - trigger
    except (TypeError, ValueError, OverflowError):
        return False, 'BLOCK: invalid trigger time'
    if not 0 <= age < 300:
        return False, 'WAIT: trigger expired or in future'
    key = alert_key(c)
    records = journal.get('decision_alerts', []) + journal.get('alerted_setups', [])
    if any(r.get('setup_key', r.get('alert_key')) == key for r in records):
        return False, 'QUIET: already recorded; reconcile updates or delivery'
    if c['action'] == 'BUY':
        if not c['entry_open'] <= now <= c['entry_cutoff']:
            return False, 'WAIT: outside entry window'
        if journal.get('new_setup_alerts_enabled') is not True:
            return False, 'QUIET: replacement hold'
        if journal.get('replacement_status') != 'local_fallback_paused_confirmed':
            return False, 'QUIET: local fallback unresolved'
        # Count actual NEW alerts plus unresolved delivery reservations. A failed
        # transport is not permission to blindly resend or consume a new key.
        count = sum(r.get('kind') == 'NEW' and r.get('week_key') == week(now)
                    and r.get('delivery_status') != 'confirmed_not_sent'
                    for r in records)
        if count >= 2:
            return False, 'QUIET: weekly allowance exhausted'
    elif c['action'] == 'SELL':
        # An alert, target touch or simulated fill must never create a holding.
        positions = journal.get('account', {}).get('positions', [])
        confirmed = sum(p.get('shares', 0) for p in positions
                        if p.get('ticker') == c['ticker'] and p.get('user_confirmed') is True
                        and p.get('source_execution_id') in {
                            x.get('execution_id') for x in journal.get('account', {}).get('user_confirmed_executions', [])
                            if x.get('execution_id')})
        if confirmed < c['shares']:
            return False, 'BLOCK: no sufficient user-confirmed holding'
    else:
        return False, 'BLOCK: unsupported action'
    return True, key
