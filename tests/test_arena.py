import datetime as dt
import json
import unittest
from unittest.mock import patch

from arena.build import compile_board
from arena.core import TZ, issue_body, parse_body, validate
from arena.sparkdash import endpoint, summarize
from arena.client import owned, run

NOW = dt.datetime(2026, 10, 20, 0, 20, tzinfo=TZ)
DAY = dt.date(2026, 10, 19)


def report(**kwargs):
    return {"version": 1, "kind": "usage", "consent_public": True,
            "date": DAY.isoformat(), "timezone": "Asia/Shanghai", "coverage": "recorded-window",
            "models": [{"model": "model/a", "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 80}], **kwargs}


def issue(number, payload, uid=1, state="open"):
    return {"number": number, "user": {"id": uid, "login": f"user{uid}", "type": "User"},
            "state": state, "body": issue_body(payload), "updated_at": f"2026-10-20T00:00:{number:02}Z"}


def history(rows):
    return {"generatedAt": NOW.timestamp()*1000, "retention": {"hours": 72}, "hour": rows}


def row(hour, model="model/a", spark="s1", value=100):
    return {"t": hour, "modelId": model, "sparkId": spark, "port": 8000,
            "promptTokens": value, "completionTokens": 10, "cachedTokens": 80}


class ContractTests(unittest.TestCase):
    def test_cache_is_not_added_twice_and_unknown_fields_removed(self):
        clean=validate(report(secret="never", url="http://private"), NOW.date())
        self.assertEqual(clean["models"][0]["total_tokens"],110)
        self.assertNotIn("secret",clean)
        self.assertNotIn("url",clean)

    def test_consent_and_strict_numeric_bounds(self):
        for key, value in (("consent_public",False),("timezone","UTC"),("date","2026-10-20")):
            with self.assertRaises(ValueError): validate(report(**{key:value}),NOW.date())
        for value in (True,-1,1.1,float("nan"),10**13):
            p=report();p["models"][0]["input_tokens"]=value
            with self.assertRaises(ValueError): validate(p,NOW.date())
        p=report();p["models"][0]["cached_input_tokens"]=101
        with self.assertRaises(ValueError): validate(p,NOW.date())

    def test_duplicate_model_rejected(self):
        p=report();p["models"]*=2
        with self.assertRaises(ValueError): validate(p,NOW.date())

    def test_wire_body_roundtrip(self):
        self.assertEqual(parse_body(issue_body(report())),validate(report()))

    def test_timezone_boundaries_and_same_model_across_endpoints(self):
        rows=[row("2026-10-18T15"),row("2026-10-18T16"),row("2026-10-19T15"),
              row("2026-10-19T15",spark="s2"),row("2026-10-19T16")]
        result=summarize(history(rows),DAY,NOW)
        self.assertEqual(result["models"][0]["input_tokens"],300)
        self.assertEqual(result["models"][0]["total_tokens"],330)
        self.assertEqual(result["coverage"],"recorded-window")

    def test_partial_history_not_claimed_complete(self):
        self.assertEqual(summarize(history([row("2026-10-19T12")]),DAY,NOW)["coverage"],"partial")
        self.assertEqual(summarize(history([]),DAY,NOW)["coverage"],"partial")

    def test_expired_stale_duplicate_or_missing_hourly_history_fail_closed(self):
        for value in ({"generatedAt":0}, {"generatedAt":NOW.timestamp()*1000,"retention":{"hours":1}},
                      history([row("2026-10-19T12")]*2)):
            with self.assertRaises(ValueError): summarize(value,DAY,NOW)
        with self.assertRaises(ValueError): summarize(history([]),DAY-dt.timedelta(days=5),NOW)

    def test_url_has_no_query_credentials_and_no_ui_path(self):
        self.assertEqual(endpoint("https://example.com/prefix/tokens"),"https://example.com/prefix/api/llm-token-totals/history")
        for url in ("file:///etc/passwd","https://user:pass@example.com","https://example.com/?token=secret"):
            with self.assertRaises(ValueError): endpoint(url)


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.profile={"version":1,"kind":"participant","consent_public":True,"wechat_name":"测试用户"}

    def test_unenrolled_report_not_published(self):
        self.assertEqual(compile_board([issue(1,report())],"owner/repo")["reports"],[])

    def test_identity_from_author_not_body_and_duplicate_last_wins(self):
        older=issue(2,report(github="fake",id="999",url="secret"))
        board=compile_board([issue(1,self.profile),older,issue(3,report())],"owner/repo")
        self.assertEqual(len(board["reports"]),1)
        self.assertEqual(board["reports"][0]["github"],"user1")
        self.assertNotIn("secret",json.dumps(board))

    def test_closed_enrollment_and_closed_report_removed(self):
        self.assertEqual(compile_board([issue(1,self.profile,state="closed"),issue(2,report())],"owner/repo")["reports"],[])
        self.assertEqual(compile_board([issue(1,self.profile),issue(2,report()),issue(3,report(),state="closed")],"owner/repo")["reports"],[])

    def test_two_authors_same_nickname_stay_separate(self):
        board=compile_board([issue(1,self.profile),issue(2,self.profile,uid=2),issue(3,report()),issue(4,report(),uid=2)],"owner/repo")
        self.assertEqual(len(board["reports"]),2)

    def test_malformed_issue_is_ignored(self):
        self.assertEqual(compile_board([{"body":"nonsense"}],"owner/repo")["rejected_issues"],1)

    def test_deep_untrusted_json_cannot_block_board_rebuild(self):
        malicious={"body":"```json\n"+'['*20000+'0'+']'*20000+"\n```"}
        board=compile_board([malicious,issue(1,self.profile),issue(2,report())],"owner/repo")
        self.assertEqual(board['rejected_issues'],1)
        self.assertEqual(len(board['reports']),1)

    def test_owned_uses_numeric_identity(self):
        self.assertEqual(len(owned([issue(1,self.profile),issue(2,self.profile,uid=2)],1,"participant")),1)


if __name__ == "__main__":
    unittest.main()
