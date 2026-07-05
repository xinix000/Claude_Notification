# -*- coding: utf-8 -*-
"""เทสต์ notify.py — รันด้วย:  python -m unittest test_notify  (ไม่ต้องลง lib เพิ่ม)

ครอบ: การตัด markdown, สรุปไทย (heuristic + AI fallback), การดึงคำถาม/แผนจาก
PreToolUse, การแท็ก @ (mention), และ logic merge/idempotent ของ install/uninstall hook.
เทสต์ไม่แตะเน็ต (mock ai_summary) และเขียน settings ลง temp dir เท่านั้น.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify


class TestCleanMd(unittest.TestCase):
    def test_strips_markdown(self):
        self.assertEqual(notify._clean_md("## หัวข้อ"), "หัวข้อ")
        self.assertEqual(notify._clean_md("- ข้อ **เด่น**"), "ข้อ เด่น")
        self.assertEqual(notify._clean_md("ดู `code` และ [ลิงก์](http://x)"), "ดู code และ ลิงก์")
        self.assertEqual(notify._clean_md("1. หนึ่ง"), "หนึ่ง")

    def test_collapses_space(self):
        self.assertEqual(notify._clean_md("a    b\tc"), "a b c")


class TestHasThai(unittest.TestCase):
    def test_true(self):
        self.assertTrue(notify._has_thai("สวัสดี hello"))

    def test_false(self):
        self.assertFalse(notify._has_thai("hello world 123"))


class TestShortSummary(unittest.TestCase):
    def test_empty_body_uses_status(self):
        self.assertEqual(notify.short_summary("stop", ""), "งานเสร็จแล้ว")
        self.assertEqual(notify.short_summary("error", ""), "เกิดข้อผิดพลาด")

    def test_thai_body_returned_as_is(self):
        s = notify.short_summary("stop", "แก้บั๊กเรียบร้อยแล้ว")
        self.assertIn("แก้บั๊ก", s)
        self.assertTrue(notify._has_thai(s))

    def test_english_body_gets_thai_prefix(self):
        s = notify.short_summary("stop", "Fixed the login bug")
        self.assertTrue(s.startswith("งานเสร็จแล้ว"))
        self.assertIn("Fixed", s)

    def test_long_body_truncated(self):
        s = notify.short_summary("stop", "ก" * 500)
        self.assertLessEqual(len(s), 205)
        self.assertTrue(s.endswith("…"))

    def test_strips_markdown(self):
        s = notify.short_summary("stop", "## สรุป\n\n- ทำ **X** เสร็จ")
        self.assertNotIn("#", s)
        self.assertNotIn("*", s)


class TestResolveBody(unittest.TestCase):
    def test_ask_extracts_questions(self):
        payload = {"tool_input": {"questions": [
            {"question": "เอาแบบไหน?"}, {"question": "สีอะไร?"}]}}
        body = notify.resolve_body("ask", None, payload)
        self.assertIn("เอาแบบไหน?", body)
        self.assertIn("สีอะไร?", body)

    def test_ask_fallback_single_question(self):
        payload = {"tool_input": {"question": "ตกลงไหม?"}}
        self.assertEqual(notify.resolve_body("ask", None, payload), "ตกลงไหม?")

    def test_plan_extracts_plan(self):
        payload = {"tool_input": {"plan": "ขั้นที่ 1 ทำ X"}}
        self.assertEqual(notify.resolve_body("plan", None, payload), "ขั้นที่ 1 ทำ X")

    def test_text_overrides(self):
        self.assertEqual(notify.resolve_body("stop", "ข้อความมือ", {}), "ข้อความมือ")


class TestResolveSummary(unittest.TestCase):
    def test_no_key_uses_heuristic(self):
        body = "แก้บั๊ก " * 40  # ยาว > 160
        s = notify.resolve_summary("stop", body, {"anthropic_api_key": ""})
        self.assertTrue(notify._has_thai(s))

    def test_non_stop_never_calls_ai(self):
        called = []
        orig = notify.ai_summary
        notify.ai_summary = lambda *a, **k: (called.append(1), "AI!")[1]
        try:
            notify.resolve_summary("ask", "x" * 300,
                                   {"anthropic_api_key": "sk-x", "ai_summary": True})
            self.assertEqual(called, [])  # PreToolUse ต้องไม่เรียก API (กันหน่วง)
        finally:
            notify.ai_summary = orig

    def test_stop_with_key_uses_ai(self):
        orig = notify.ai_summary
        notify.ai_summary = lambda body, key, **k: "สรุปโดย AI"
        try:
            s = notify.resolve_summary("stop", "y" * 300,
                                       {"anthropic_api_key": "sk-x", "ai_summary": True})
            self.assertEqual(s, "สรุปโดย AI")
        finally:
            notify.ai_summary = orig

    def test_ai_failure_falls_back(self):
        orig = notify.ai_summary
        notify.ai_summary = lambda body, key, **k: None  # จำลอง API ล่ม
        try:
            s = notify.resolve_summary("stop", "แก้ระบบ " * 40,
                                       {"anthropic_api_key": "sk-x", "ai_summary": True})
            self.assertTrue(notify._has_thai(s))  # ต้องได้ heuristic ไทยแทน
        finally:
            notify.ai_summary = orig


class TestBuildPayload(unittest.TestCase):
    def test_basic_structure(self):
        p = notify.build_payload("stop", "เสร็จแล้ว", {"cwd": r"C:\proj\App"}, {})
        embed = p["embeds"][0]
        self.assertIn("📝", embed["description"])
        names = [f["name"] for f in embed["fields"]]
        self.assertIn("📁 Project", names)
        # ต้องไม่มี field รายละเอียดที่ดั๊มพ์ยาว ๆ อีก
        self.assertFalse(any("รายละเอียด" in n for n in names))
        self.assertNotIn("content", p)

    def test_mention_added_for_configured_event(self):
        cfg = {"mention_user_id": "123", "mention_events": ["error"]}
        p = notify.build_payload("error", "พัง", {}, cfg)
        self.assertIn("<@123>", p["content"])
        self.assertEqual(p["allowed_mentions"], {"parse": ["users"]})

    def test_no_mention_without_user_id(self):
        cfg = {"mention_user_id": "", "mention_events": ["error"]}
        p = notify.build_payload("error", "พัง", {}, cfg)
        self.assertNotIn("content", p)

    def test_no_mention_for_unlisted_event(self):
        cfg = {"mention_user_id": "123", "mention_events": ["error"]}
        p = notify.build_payload("stop", "เสร็จ", {}, cfg)
        self.assertNotIn("content", p)


class TestHookInstall(unittest.TestCase):
    def _tmp(self):
        return Path(tempfile.mkdtemp()) / "settings.json"

    def test_install_fresh(self):
        path = self._tmp()
        notify.install_hooks(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        for ev in ("Stop", "Notification", "PreToolUse"):
            self.assertIn(ev, data["hooks"])
            self.assertEqual(len(data["hooks"][ev]), 1)
        self.assertEqual(
            data["hooks"]["PreToolUse"][0]["matcher"], "AskUserQuestion|ExitPlanMode"
        )

    def test_install_idempotent(self):
        path = self._tmp()
        for _ in range(3):
            notify.install_hooks(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        for ev in ("Stop", "Notification", "PreToolUse"):
            self.assertEqual(len(data["hooks"][ev]), 1)  # รัน 3 รอบต้องไม่ซ้ำ

    def test_install_preserves_existing(self):
        path = self._tmp()
        path.write_text(json.dumps({
            "theme": "dark",
            "hooks": {"PostToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "node x.mjs"}]}]},
        }), encoding="utf-8")
        notify.install_hooks(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["theme"], "dark")
        self.assertIn("PostToolUse", data["hooks"])  # hook คนอื่นยังอยู่
        self.assertIn("Stop", data["hooks"])

    def test_uninstall_removes_only_ours(self):
        path = self._tmp()
        path.write_text(json.dumps({
            "hooks": {"PostToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "node x.mjs"}]}]},
        }), encoding="utf-8")
        notify.install_hooks(path)
        notify.uninstall_hooks(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("PostToolUse", data["hooks"])  # ของคนอื่นยังอยู่
        self.assertNotIn("Stop", data["hooks"])
        self.assertNotIn("PreToolUse", data["hooks"])


class TestResolveAuth(unittest.TestCase):
    def test_oauth_token_wins_over_api_key(self):
        self.assertEqual(
            notify.resolve_auth({"oauth_token": "oat-x", "anthropic_api_key": "sk-x"}),
            ("bearer", "oat-x"),
        )

    def test_api_key_scheme(self):
        self.assertEqual(
            notify.resolve_auth({"anthropic_api_key": "sk-x"}), ("x-api-key", "sk-x")
        )

    def test_none_when_empty(self):
        self.assertEqual(notify.resolve_auth({}), (None, ""))
        self.assertEqual(
            notify.resolve_auth({"anthropic_api_key": "", "oauth_token": ""}), (None, "")
        )

    def test_ai_summary_no_token_returns_none(self):
        # ไม่มี token → คืน None ทันที (ไม่ยิงเน็ต)
        self.assertIsNone(notify.ai_summary("x" * 300, (None, "")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
