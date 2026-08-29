"""Unit and integration tests for the Antigravity Telegram Bot bridge."""

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from agy_bot.config import Config
from agy_bot.formatting import (
    escape_html,
    format_duration,
    format_progress_message,
    format_stats_footer,
    format_tokens,
    format_tool_call_summary,
    split_text_smartly,
)
from agy_bot.session_manager import SessionManager, UserSession
from agy_bot.agy_client import AgyClient


class TestFormatting(unittest.TestCase):
    def test_escape_html(self):
        self.assertEqual(escape_html("<b>Test & 123</b>"), "&lt;b&gt;Test &amp; 123&lt;/b&gt;")

    def test_format_tokens(self):
        self.assertEqual(format_tokens(500), "500")
        self.assertEqual(format_tokens(1500), "1.5k")
        self.assertEqual(format_tokens(2500000), "2.5M")

    def test_format_duration(self):
        self.assertEqual(format_duration(0.45), "450ms")
        self.assertEqual(format_duration(4.2), "4.2s")
        self.assertEqual(format_duration(65.0), "1m 5s")

    def test_format_tool_call_summary(self):
        self.assertIn("git status", format_tool_call_summary("run_command", {"CommandLine": "git status"}))
        self.assertIn("main.py", format_tool_call_summary("view_file", {"AbsolutePath": "/test/path/main.py"}))
        self.assertIn("search", format_tool_call_summary("search_web", {"Query": "python telegram bot"}))

    def test_split_text_smartly(self):
        short_text = "Hello world"
        self.assertEqual(split_text_smartly(short_text, max_chunk_size=100), [short_text])

        long_text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        chunks = split_text_smartly(long_text, max_chunk_size=20)
        self.assertTrue(len(chunks) >= 2)
        rejoined = "\n\n".join(chunks)
        self.assertEqual(rejoined, long_text)

    def test_format_stats_footer(self):
        footer = format_stats_footer(
            duration=3.5,
            usage={"total_tokens": 14500, "thinking_tokens": 800},
            conversation_id="3edf79bf-71c8-4384-80e7-08416e6ef1c4",
            model="gemini-3.7-flash-high",
        )
        self.assertIn("3.5s", footer)
        self.assertIn("14.5k tokens", footer)
        self.assertIn("3edf79bf", footer)


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.mgr = SessionManager(state_file=self.state_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_and_modify_session(self):
        user_id = 999888
        sess = self.mgr.get_session(user_id)
        self.assertEqual(sess.user_id, user_id)
        self.assertIsNone(sess.active_conversation_id)

        # Set conversation id
        self.mgr.set_active_conversation(user_id, "test-conv-uuid")
        self.assertEqual(sess.active_conversation_id, "test-conv-uuid")

        # Set model
        self.mgr.set_model(user_id, "claude-sonnet-4-6")
        self.assertEqual(sess.model, "claude-sonnet-4-6")

        # Set effort
        self.mgr.set_effort(user_id, "low")
        self.assertEqual(sess.effort, "low")

        # Set mode
        self.mgr.set_mode(user_id, "plan")
        self.assertEqual(sess.mode, "plan")

        # Reset session
        self.mgr.reset_conversation(user_id)
        self.assertIsNone(sess.active_conversation_id)

    def test_working_dir_change(self):
        user_id = 1234
        ok, res = self.mgr.set_working_dir(user_id, self.temp_dir)
        self.assertTrue(ok)
        self.assertEqual(res, self.temp_dir)

        # Test non-existent path
        ok_fail, res_fail = self.mgr.set_working_dir(user_id, "/non/existent/path/xyz")
        self.assertFalse(ok_fail)


class TestAgyClient(unittest.TestCase):
    def test_build_command_args(self):
        client = AgyClient(agy_bin="/usr/local/bin/agy")
        session = UserSession(
            user_id=123,
            active_conversation_id="conv-123",
            model="gemini-3.7-flash-high",
            effort="high",
            mode="accept-edits",
            auto_approve=True,
        )

        args = client.build_command_args("What is 2+2?", session)
        self.assertEqual(args[0], "/usr/local/bin/agy")
        self.assertIn("-p", args)
        self.assertIn("What is 2+2?", args)
        self.assertIn("--output-format", args)
        self.assertIn("stream-json", args)
        self.assertIn("--conversation", args)
        self.assertIn("conv-123", args)
        self.assertIn("--model", args)
        self.assertIn("gemini-3.7-flash-high", args)
        self.assertIn("--effort", args)
        self.assertIn("high", args)
        self.assertIn("--mode", args)
        self.assertIn("accept-edits", args)
        self.assertIn("--dangerously-skip-permissions", args)


if __name__ == "__main__":
    unittest.main()
