"""Safety regression checks only; these examples are never market assessments."""
import copy
import datetime as dt
import unittest
from decision_alerts import NY, alert_key, eligible, week

class SafetyChecks(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,19,10,0,20,tzinfo=NY)
        self.j={'new_setup_alerts_enabled':True,'replacement_status':'local_fallback_paused_confirmed',
                'account':{'positions':[],'user_confirmed_executions':[]},'decision_alerts':[]}
        self.c=dict(action='BUY',ticker='TEST',setup='orb',session='2026-11-19',
          trigger_epoch=(self.now-dt.timedelta(seconds=20)).timestamp(),quote_time=self.now,
          valid_until=self.now+dt.timedelta(minutes=4),entry_open=self.now.replace(hour=9,minute=45),
          entry_cutoff=self.now.replace(hour=15,minute=30),calendar_verified=True,
          material_news_verified=True,data_verified=True,plan_fingerprint='checked',
          risk_checked_fingerprint='checked',risk_passed=True,shares=1,
          session_open=self.now.replace(hour=9,minute=30),session_close=self.now.replace(hour=16,minute=0))
    def test_valid_decision_does_not_mutate_account(self):
        before=copy.deepcopy(self.j);self.assertTrue(eligible(self.c,self.j,self.now)[0]);self.assertEqual(before,self.j)
    def test_expired_trigger_cannot_be_revived(self):
        self.c['trigger_epoch']=(self.now-dt.timedelta(minutes=5)).timestamp()
        self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_unchanged_or_uncertain_delivery_stays_quiet(self):
        self.j['decision_alerts']=[{'alert_key':alert_key(self.c),'delivery_status':'unknown'}]
        self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_weekly_cap_includes_uncertain_delivery(self):
        self.j['decision_alerts']=[{'kind':'NEW','week_key':week(self.now),'delivery_status':s} for s in ['delivered','unknown']]
        self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_unverified_news_cannot_produce_buy(self):
        self.c['material_news_verified']=False;self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_changed_order_invalidates_checked_plan(self):
        self.c['plan_fingerprint']='changed';self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_buy_alert_does_not_authorize_sell(self):
        self.c['action']='SELL';self.j['decision_alerts']=[{'kind':'NEW','ticker':'TEST'}]
        self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_simulated_holding_does_not_authorize_sell(self):
        self.c['action']='SELL';self.j['account']['positions']=[{'ticker':'TEST','shares':1,'user_confirmed':False}]
        self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_fallback_hold_blocks_new_buy_alerts(self):
        self.j['new_setup_alerts_enabled']=False;self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_current_session_and_quote_are_required(self):
        self.c['quote_time']=self.now-dt.timedelta(seconds=121);self.assertFalse(eligible(self.c,self.j,self.now)[0])
    def test_legacy_buy_key_is_unchanged(self):
        import hashlib,json
        values=['TEST','orb','2026-11-19',int(self.c['trigger_epoch'])]
        self.assertEqual(alert_key(self.c),hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest())
    def test_after_hours_cannot_produce_a_decision(self):
        self.c['session_close']=self.now
        self.assertFalse(eligible(self.c,self.j,self.now)[0])

if __name__=='__main__':unittest.main()
