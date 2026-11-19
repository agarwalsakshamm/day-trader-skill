"""One-off public-data capability test, never an account or trading assessment.

No credentials, SEC identity, journal, holdings, orders, caches or artifacts.
The GitHub workflow has no scheduled trigger. Do not infer deployment readiness
or unattended recurrence from a successful push-triggered capability test.
"""
import ast
import concurrent.futures as cf
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
NY, IST = ZoneInfo('America/New_York'), ZoneInfo('Asia/Kolkata')
SYMBOLS = ['SNDK','MSFT','AAPL','NVDA','AMD']
COMMIT = '3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd'
STAGE = 'source_bootstrap'
REPORT = {}

def utcnow(): return dt.datetime.now(dt.timezone.utc)
def stamp(value): return value.astimezone(IST).strftime('%d %B %Y %H:%M:%S IST')
def get(url):
    request = urllib.request.Request(url, headers={'User-Agent':'Cloud public-data capability validation/1.0'})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded
def command(args):
    result = subprocess.run([sys.executable, *map(str,args)], capture_output=True, text=True, timeout=130)
    if result.returncode:
        raise RuntimeError('imported_tool_failed_exit_' + str(result.returncode))
    return json.loads(result.stdout)

def probe():
    global STAGE
    manifest = json.loads((HERE/'public_source_manifest.json').read_text())
    if manifest['commit'] != COMMIT: raise ValueError('unexpected source commit')
    report = {'kind':'public_data_capability_probe', 'checked_ist':stamp(utcnow()),
       'python':platform.python_version(), 'platform':platform.system(),
       'github_actions':os.getenv('GITHUB_ACTIONS') == 'true',
       'run_id':os.getenv('GITHUB_RUN_ID'), 'source_commit':COMMIT,
       'scheduled_monitoring_enabled':False, 'orders':False,
       'private_journal_access':'NOT_TESTED', 'immediate_alert_delivery':'NOT_TESTED',
       'scope':'Public data only. Not a paper-account assessment or recurring-run proof.'}
    REPORT.update(report)
    report = REPORT
    with tempfile.TemporaryDirectory(prefix='pinned-public-tools-') as tmp:
        source = Path(tmp)
        def fetch_one(item):
            raw = get('https://raw.githubusercontent.com/Jakeschincariol/day-trader-skill/'+COMMIT+'/'+item['path'])
            if hashlib.sha256(raw).hexdigest() != item['sha256']: raise ValueError('source_hash_mismatch')
            path = source/item['path']; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
            if path.suffix == '.py': ast.parse(raw)
            return path.suffix == '.py'
        with cf.ThreadPoolExecutor(max_workers=5) as pool:
            scripts = sum(pool.map(fetch_one, manifest['source_files']))
        if scripts != 11: raise ValueError('all_eleven_scripts_required')
        report['hash_verified_files'] = len(manifest['source_files'])
        report['hash_verified_scripts'] = scripts
        STAGE = 'official_calendar'
        # This artifact authorizes only a single date reviewed from the NYSE
        # primary calendar before the probe was prepared, not future sessions.
        now = utcnow(); day = now.astimezone(NY).date()
        scope = json.loads((HERE/'calendar_probe_scope.json').read_text())
        if day.isoformat() != scope['session']: raise ValueError('single_session_calendar_review_expired')
        calendar = get(scope['source_url'])
        if b'2026' not in calendar: raise ValueError('calendar_reference_not_recognized')
        report['calendar'] = {'source':scope['source_url'],'retrieved_ist':stamp(utcnow()),
            'sha256':hashlib.sha256(calendar).hexdigest(),'single_reviewed_session':scope['session'],
            'future_calendar_adapter':'NOT_VALIDATED'}
        now = utcnow(); opening = dt.datetime.combine(day,dt.time(9,30),NY)
        closing = dt.datetime.combine(day,dt.time(16,0),NY)
        if not opening + dt.timedelta(minutes=15) <= now <= closing-dt.timedelta(minutes=30):
            raise ValueError('outside_actual_entry_window_no_retroactive_probe')
        # Listings are verified without storing any user-specific information.
        STAGE = 'listing_directories'
        listings = get('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt').decode()
        found = {line.split('|')[0] for line in listings.splitlines()}
        if not all(s in found for s in SYMBOLS): raise ValueError('listing_coverage_incomplete')
        report['listings'] = {'requested':len(SYMBOLS),'verified':len(SYMBOLS),'retrieved_ist':stamp(utcnow())}
        STAGE = 'imported_daily_scanner'
        daily = command([HERE/'cloud_scan.py','--source',source,'--manifest',HERE/'public_source_manifest.json','--symbols',','.join(SYMBOLS)])
        report['daily_scan'] = {'status':daily.get('status'),'counts':daily.get('counts'),'errors':daily.get('errors'),
            'latest_completed_session_id':daily.get('latest_completed_session_id')}
        if daily.get('status') == 'BLOCK' or daily.get('errors'): raise ValueError('daily_source_validation_failed')
        STAGE = 'imported_two_stage_orb_scanner'
        orb = command([source/'trader-scanner/scan.py','orb','--symbols',','.join(SYMBOLS),
            '--until','15:30','--no-write','--quiet','--json'])
        report['orb_scan'] = {'counts':orb.get('counts'),'failed':orb.get('failed'),'source':orb.get('source')}
        entry = module('pinned_entry',source/'trader-entry/entry.py')
        guard = module('raw_guard',HERE/'cloud_guard.py')
        STAGE = 'raw_completed_bars_and_imported_entry'
        def check(sym):
            url='https://query2.finance.yahoo.com/v8/finance/chart/'+sym+'?range=1d&interval=5m'
            raw=get(url); chart=json.loads(raw); observed=utcnow()
            result=chart['chart']['result'][0]; meta=result['meta']
            if meta.get('symbol') != sym or meta.get('currency') != 'USD': raise ValueError('symbol_or_currency_mismatch')
            bars=guard.completed_bars(chart,observed,opening,closing)
            if len(bars)<3: raise ValueError('opening_range_incomplete')
            quote=dt.datetime.fromtimestamp(meta['regularMarketTime'],dt.timezone.utc)
            age=(observed-quote).total_seconds()
            if not 0 <= age <=120: raise ValueError('stale_or_future_quote')
            if quote < bars[-1]['end']: raise ValueError('source_not_caught_up_to_completed_bar')
            parsed=entry.parse_chart(raw.decode(),sym)
            evaluated=entry.evaluate(parsed,observed.replace(tzinfo=None),setup='orb')
            # Compare only observed raw bars, never substitute missing OHLC.
            high=max(b['high'] for b in bars[:3])
            first=next((b for b in bars[3:] if b['close']>high),None)
            upstream=evaluated.get('trigger')
            if bool(first) != bool(upstream): raise ValueError('raw_and_imported_trigger_disagree')
            if first and abs(first['close']-upstream['close'])>0.000001: raise ValueError('trigger_close_disagrees')
            state,reason=guard.entry_gate(evaluated,quote,first['end'] if first else None,
                observed,opening,closing-dt.timedelta(minutes=30))
            return {'symbol':sym,'retrieved_ist':stamp(observed),'source_quote_ist':stamp(quote),
                'quote_age_seconds':round(age,3),'complete_bars':len(bars),'guard_state':state,
                'qualification':reason,'raw_sha256':hashlib.sha256(raw).hexdigest()}
        with cf.ThreadPoolExecutor(max_workers=5) as pool:
            report['completed_bar_checks']=list(pool.map(check,SYMBOLS))
        STAGE = 'imported_news'
        news=command([source/'trader-news/news.py','--tickers',*SYMBOLS,'--no-sec','--no-moves',
            '--hours','24','--dry-run','--json'])
        report['news']={'item_count':len(news.get('items',[])), 'notes':news.get('notes'),
            'qualification':'RSS availability only; no material-story verification or SEC identity supplied.'}
        report['exit_simulation_sizing_risk']='NOT_EXECUTED: capability probe is not an eligible paper entry or account assessment.'
        report['status']='PUBLIC_DATA_PROBE_PASSED'
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    try: probe()
    except Exception as error:
        print(json.dumps({**REPORT,'status':'BLOCK','kind':'public_data_capability_probe',
            'checked_ist':stamp(utcnow()),'failure_type':type(error).__name__,
            'failure_stage':STAGE,'failure':str(error)[:400], 'scheduled_monitoring_enabled':False,
            'private_journal_access':'NOT_TESTED','immediate_alert_delivery':'NOT_TESTED'}))
        raise SystemExit(1)
