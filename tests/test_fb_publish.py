"""發布契約回歸測試：所有設定、HTTP 與 Sheet 均為 mock。"""

import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# 載入模組也不可讀取 .env。
with patch("dotenv.load_dotenv"):
    from scripts import fb_api as fb
    from scripts import sheets_api as sheets
    from scripts import publish_ui as ui


TOKEN = "FAKE_TOKEN_abc"
NOW = datetime(2026, 10, 20, 12, tzinfo=fb.TAIPEI)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def response(payload, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    return result


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("dotenv.load_dotenv", side_effect=AssertionError("不可讀 .env")))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("禁止網路")))
        self.stack.enter_context(patch.object(sheets, "_get_client", side_effect=AssertionError("禁止真實 Sheet")))
        self.secret = self.stack.enter_context(patch.object(
            sheets, "_get_secret", side_effect=lambda key, default="": {
                "FB_PAGE_ID": "123", "FB_PAGE_ACCESS_TOKEN": TOKEN,
            }.get(key, default),
        ))
        self.stack.enter_context(patch.object(fb, "datetime", FixedDateTime))
        self.post = self.stack.enter_context(patch("scripts.fb_api.requests.post", return_value=response({"id": "123_456"})))
        self.get = self.stack.enter_context(patch("scripts.fb_api.requests.get", return_value=response({"data": []})))
        self.delete = self.stack.enter_context(patch("scripts.fb_api.requests.delete", return_value=response({"success": True})))
        self.record = self.stack.enter_context(patch.object(sheets, "get_post_row", return_value={
            "post_content": "編輯後內容", "original_content": "AI 原版",
            "material_row": "9", "publish_status": "", "fb_post_id": "", "publish_time": "",
        }))
        self.update = self.stack.enter_context(patch.object(sheets, "update_post_publish", return_value=True))
        self.mark = self.stack.enter_context(patch.object(sheets, "mark_used", return_value=True))

    def test_immediate_feed(self):
        result = fb.publish_post("  你好  ", link="https://example.com")
        args, kwargs = self.post.call_args
        self.assertTrue(args[0].endswith("/123/feed"))
        self.assertEqual(kwargs["data"]["message"], "你好")
        self.assertEqual(kwargs["data"]["link"], "https://example.com")
        self.assertNotIn("published", kwargs["data"])
        self.assertNotIn("scheduled_publish_time", kwargs["data"])
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(result, {"post_id": "123_456", "status": "published", "publish_time": NOW.isoformat()})

    def test_schedule_twenty_days_naive_taipei(self):
        result = fb.publish_post("排程", scheduled_at=datetime(2026, 11, 9, 12))
        data = self.post.call_args.kwargs["data"]
        self.assertEqual(data["published"], "false")
        self.assertEqual(data["scheduled_publish_time"], 1794196800)
        self.assertEqual(result["publish_time"], "2026-11-09T12:00:00+08:00")
        self.assertEqual(result["status"], "scheduled")

    def test_schedule_aware_timezone(self):
        fb.publish_post("排程", scheduled_at=datetime(2026, 11, 9, 4, tzinfo=timezone.utc))
        self.assertEqual(self.post.call_args.kwargs["data"]["scheduled_publish_time"], 1794196800)

    def test_schedule_invalid_window(self):
        for delta in [timedelta(minutes=5), timedelta(days=29)]:
            with self.subTest(delta=delta), self.assertRaises(fb.FBPublishError) as error:
                fb.publish_post("排程", scheduled_at=NOW + delta)
            self.assertIsNone(error.exception.code)
            self.assertIn("10 分鐘", str(error.exception))
            self.assertIn("28 天", str(error.exception))
        self.post.assert_not_called()

    def test_schedule_inclusive_boundaries(self):
        for delta in [timedelta(minutes=10), timedelta(days=28)]:
            fb.publish_post("排程", scheduled_at=NOW + delta)
        self.assertEqual(self.post.call_count, 2)

    def test_local_image_and_post_id(self):
        self.post.return_value = response({"id": "photo_id", "post_id": "123_post"})
        with tempfile.NamedTemporaryFile(suffix=".png") as fh:
            fh.write(b"mock image")
            fh.flush()
            result = fb.publish_post("圖片", image_path=fh.name)
        args, kwargs = self.post.call_args
        self.assertTrue(args[0].endswith("/123/photos"))
        self.assertIn("source", kwargs["files"])
        self.assertTrue(kwargs["files"]["source"].closed)
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(result["post_id"], "123_post")

    def test_image_url_schedule(self):
        fb.publish_post("圖片", image_url="https://example.com/a.png", scheduled_at=NOW + timedelta(days=20))
        args, kwargs = self.post.call_args
        self.assertTrue(args[0].endswith("/123/photos"))
        self.assertEqual(kwargs["data"]["url"], "https://example.com/a.png")
        self.assertEqual(kwargs["data"]["published"], "false")
        self.assertNotIn("files", kwargs)
        self.assertEqual(kwargs["timeout"], 60)

    def test_invalid_content_and_image_pair(self):
        with self.assertRaises(ValueError):
            fb.publish_post(" \n ")
        with self.assertRaises(ValueError):
            fb.publish_post("圖片", image_path="x", image_url="y")
        self.post.assert_not_called()

    def test_fb_error_redacted(self):
        self.post.return_value = response({"error": {"code": 190, "message": f"錯誤 access_token={TOKEN}&x=1 {TOKEN}"}})
        with self.assertRaises(fb.FBPublishError) as error:
            fb.publish_post("內容")
        self.assertEqual(error.exception.code, 190)
        self.assertNotIn(TOKEN, str(error.exception))
        self.assertEqual(error.exception.message, str(error.exception))

    def test_connection_error_redacted(self):
        self.post.side_effect = fb.requests.ConnectionError(f"連線失敗 {TOKEN}")
        with self.assertRaises(fb.FBPublishError) as error:
            fb.publish_post("內容")
        self.assertNotIn(TOKEN, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_http_error_and_invalid_json(self):
        self.post.return_value = response({}, 503)
        with self.assertRaises(fb.FBPublishError):
            fb.publish_post("內容")
        self.post.return_value.json.side_effect = ValueError(TOKEN)
        with self.assertRaises(fb.FBPublishError) as error:
            fb.publish_post("內容")
        self.assertNotIn(TOKEN, str(error.exception))

    def test_redact_delimiters_and_raw_token(self):
        for ending in ["&x=1", " next", '"next', "'next"]:
            self.assertEqual(fb.redact_token(f"access_token=OTHER{ending}"), f"access_token=***{ending}")
        self.assertEqual(fb.redact_token(f"before {TOKEN} after"), "before *** after")

    def test_secrets_loaded_at_call_time(self):
        self.assertTrue(fb.is_configured())
        self.secret.side_effect = lambda key, default="": ""
        self.assertFalse(fb.is_configured())
        with self.assertRaises(fb.FBPublishError):
            fb.publish_post("內容")
        self.post.assert_not_called()

    def test_publish_edited_record_and_mark_used(self):
        result = fb.publish_record(3)
        self.assertEqual(self.post.call_args.kwargs["data"]["message"], "編輯後內容")
        self.update.assert_called_once_with(3, fb_post_id="123_456", status="published", publish_time=result["publish_time"])
        self.mark.assert_called_once_with(9)

    def test_publish_sheet_failure_does_not_retry(self):
        self.update.side_effect = RuntimeError(f"Sheet {TOKEN}")
        result = fb.publish_record(3)
        self.assertIn("sheet_error", result)
        self.assertNotIn(TOKEN, result["sheet_error"])
        self.post.assert_called_once()
        self.assertEqual(result["post_id"], "123_456")

    def test_false_sheet_result_and_material_failure(self):
        self.update.return_value = False
        self.mark.side_effect = RuntimeError(TOKEN)
        result = fb.publish_record(3)
        self.assertIn("sheet_error", result)
        self.assertNotIn(TOKEN, result["sheet_error"])
        self.post.assert_called_once()

    def test_skip_invalid_material_rows(self):
        for value in ["", None, "abc", "2,3", "²", "0"]:
            self.record.return_value["material_row"] = value
            fb.publish_record(3)
        self.mark.assert_not_called()

    def test_duplicate_and_changed_content_rejected(self):
        for status in ["published", "scheduled"]:
            self.record.return_value["publish_status"] = status
            with self.assertRaises(fb.FBPublishError):
                fb.publish_record(3)
        self.record.return_value["publish_status"] = ""
        with self.assertRaises(fb.FBPublishError):
            fb.publish_record(3, expected_content="不同內容")
        self.post.assert_not_called()

    def test_cancel_only_scheduled(self):
        with self.assertRaises(fb.FBPublishError):
            fb.cancel_scheduled(3)
        self.delete.assert_not_called()
        self.record.return_value.update(publish_status="scheduled", fb_post_id="123_456", publish_time="2026-11-09T12:00:00+08:00")
        self.assertTrue(fb.cancel_scheduled(3))
        self.assertTrue(self.delete.call_args.args[0].endswith("/123_456"))
        self.update.assert_called_once_with(
            3, fb_post_id="123_456", status="cancelled", publish_time="2026-11-09T12:00:00+08:00",
        )

    def test_cancel_sheet_failure_preserves_fb_outcome(self):
        self.record.return_value.update(publish_status="scheduled", fb_post_id="123_456")
        self.update.side_effect = RuntimeError(TOKEN)
        with self.assertRaises(fb.FBPublishError) as error:
            fb.cancel_scheduled(3)
        self.assertIn("已取消但紀錄沒更新", str(error.exception))
        self.assertNotIn(TOKEN, str(error.exception))
        self.delete.assert_called_once()

    def test_cancel_false_no_sheet_write(self):
        self.record.return_value.update(publish_status="scheduled", fb_post_id="123_456")
        self.delete.return_value = response({"success": False})
        self.assertFalse(fb.cancel_scheduled(3))
        self.update.assert_not_called()

    def test_cancel_elapsed_schedule_does_not_delete_published_post(self):
        self.record.return_value.update(
            publish_status="scheduled", fb_post_id="123_456",
            publish_time=(NOW - timedelta(minutes=1)).isoformat(),
        )
        with self.assertRaises(fb.FBPublishError):
            fb.cancel_scheduled(3)
        self.delete.assert_not_called()
        self.update.assert_not_called()

    def test_scheduled_and_delete_errors(self):
        self.get.return_value = response({"data": [{"id": "1"}]})
        self.assertEqual(fb.get_scheduled_posts(), [{"id": "1"}])
        self.assertTrue(self.get.call_args.args[0].endswith("/123/scheduled_posts"))
        self.assertEqual(self.get.call_args.kwargs["params"]["fields"], "id,message,scheduled_publish_time")
        self.delete.return_value = response({"error": {"code": 190, "message": TOKEN}}, 400)
        with self.assertRaises(fb.FBPublishError) as error:
            fb.delete_post("1")
        self.assertNotIn(TOKEN, str(error.exception))

    def run_cli(self, args, tty=False, answer="n"):
        out = io.StringIO()
        with patch("sys.argv", ["fb_api.py", *args]), patch("sys.stdin.isatty", return_value=tty), \
                patch("builtins.input", return_value=answer), redirect_stdout(out), redirect_stderr(out):
            code = 0
            try:
                fb.main()
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_cli_non_tty_needs_yes(self):
        code, output = self.run_cli(["--publish", "3"])
        self.assertEqual(code, 2)
        self.assertIn("非互動環境請加 --yes", output)
        self.assertIn("編輯後內容", output)
        self.post.assert_not_called()

    def test_cli_tty_no_is_default(self):
        code, output = self.run_cli(["--publish", "3"], tty=True, answer="")
        self.assertEqual(code, 0)
        self.assertIn("已取消發布", output)
        self.post.assert_not_called()

    def test_cli_tty_yes(self):
        code, _ = self.run_cli(["--publish", "3"], tty=True, answer="y")
        self.assertEqual(code, 0)
        self.post.assert_called_once()

    def test_cli_yes_with_schedule_image(self):
        code, output = self.run_cli(["--publish", "3", "--at", "2026-11-09 12:00", "--image", "https://example.com/a.png", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("已排程", output)
        self.assertEqual(self.post.call_args.kwargs["data"]["scheduled_publish_time"], 1794196800)

    def test_cli_redacts_argument_errors_and_sheet_errors(self):
        code, output = self.run_cli(["--publish", TOKEN])
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, output)
        self.update.side_effect = RuntimeError(TOKEN)
        code, output = self.run_cli(["--publish", "3", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("123_456", output)
        self.assertIn("人工補登", output)
        self.assertNotIn(TOKEN, output)

    def test_cli_scheduled_cancel_help(self):
        self.get.return_value = response({"data": [{"id": "123_456", "scheduled_publish_time": 1794196800, "message": "內容"}]})
        code, output = self.run_cli(["--scheduled"])
        self.assertEqual(code, 0)
        self.assertIn("2026-11-09 12:00 台北", output)
        self.record.return_value.update(publish_status="scheduled", fb_post_id="123_456")
        self.assertEqual(self.run_cli(["--cancel", "3"])[0], 0)
        self.assertIn("--publish", self.run_cli(["--help"])[1])

    def test_legacy_read_errors_redacted(self):
        out = io.StringIO()
        self.get.return_value = response({"error": {"message": TOKEN}})
        with redirect_stdout(out):
            self.assertEqual(fb.get_page_posts(), [])
            self.assertEqual(fb.get_post_insights("1"), {})
        self.assertNotIn(TOKEN, out.getvalue())

    def fake_ui(self):
        st = MagicMock()
        st.session_state = {}
        st.radio.return_value = "立即發布"
        st.file_uploader.return_value = None
        st.checkbox.return_value = True
        st.button.return_value = True
        self.stack.enter_context(patch.object(ui, "st", st))
        return st

    def test_ui_not_configured(self):
        st = self.fake_ui()
        self.secret.side_effect = lambda key, default="": ""
        ui.render_publish_panel(3, "內容", "gen_3")
        st.info.assert_called_once()
        st.radio.assert_not_called()
        self.post.assert_not_called()

    def test_ui_confirmation_required_and_widget_keys(self):
        st = self.fake_ui()
        st.checkbox.return_value = False
        ui.render_publish_panel(3, "內容", "gen_3")
        self.post.assert_not_called()
        self.assertTrue(st.button.call_args.kwargs["disabled"])
        self.assertTrue(st.text_area.call_args.kwargs["disabled"])
        for name in ["radio", "file_uploader", "text_area", "checkbox", "button"]:
            self.assertTrue(getattr(st, name).call_args.kwargs["key"].startswith("gen_3"))

    def test_ui_temp_removed_on_failure(self):
        st = self.fake_ui()
        st.file_uploader.return_value = MagicMock()
        st.file_uploader.return_value.name = "photo.png"
        st.file_uploader.return_value.getvalue.return_value = b"mock image"
        seen = []
        def fail(row, **kwargs):
            seen.append(kwargs["image_path"])
            self.assertTrue(Path(seen[0]).exists())
            raise fb.FBPublishError(TOKEN)
        with patch.object(ui, "publish_record", side_effect=fail):
            ui.render_publish_panel(3, "內容", "gen_3")
        self.assertFalse(Path(seen[0]).exists())
        self.assertNotIn(TOKEN, st.error.call_args.args[0])

    def test_ui_success_stored_prevents_repeat_and_warns(self):
        st = self.fake_ui()
        self.update.side_effect = RuntimeError(TOKEN)
        ui.render_publish_panel(3, "編輯後內容", "gen_3")
        ui.render_publish_panel(3, "編輯後內容", "history_3")
        self.post.assert_called_once()
        self.assertIn("人工補登", st.warning.call_args.args[0])
        self.assertNotIn(TOKEN, st.warning.call_args.args[0])

    def test_ui_changed_preview_requires_new_confirmation_key(self):
        st = self.fake_ui()
        st.button.return_value = False
        ui.render_publish_panel(3, "內容 A", "gen_3")
        first_key = st.checkbox.call_args.kwargs["key"]
        ui.render_publish_panel(3, "內容 B", "gen_3")
        self.assertNotEqual(first_key, st.checkbox.call_args.kwargs["key"])


class SheetTests(unittest.TestCase):
    def setUp(self):
        self.ws = MagicMock()
        self.patch = patch.object(sheets, "_get_or_create_sheet", return_value=self.ws)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_publish_columns_and_invalidation(self):
        with patch.object(sheets, "invalidate_cache") as invalidate:
            self.assertTrue(sheets.update_post_publish(7, fb_post_id="123_456", status="scheduled", publish_time="time"))
        self.ws.batch_update.assert_called_once_with([
            {"range": "H7", "values": [["123_456"]]},
            {"range": "Q7:R7", "values": [["scheduled", "time"]]},
        ], value_input_option="RAW")
        invalidate.assert_called_once_with("post_records")
        self.assertEqual(sheets.POST_HEADERS[7], "FB貼文ID")
        self.assertEqual(sheets.POST_HEADERS[16:18], ["發布狀態", "發布時間"])

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            sheets.update_post_publish(7, fb_post_id="", status="draft", publish_time="")
        self.ws.batch_update.assert_not_called()

    def test_legacy_row_missing_fields(self):
        self.ws.get_all_values.return_value = [sheets.POST_HEADERS, [""] * 13]
        record = sheets._load_post_records_uncached()[0]
        self.assertEqual(record["publish_status"], "")
        self.assertEqual(record["publish_time"], "")

    def test_single_row_has_publish_fields_and_edited_content(self):
        values = [""] * 18
        for col, value in {2: "9", 4: "編輯版", 7: "123_456", 13: "原版", 16: "scheduled", 17: "time"}.items():
            values[col] = value
        self.ws.row_values.return_value = values
        record = sheets.get_post_row(3)
        self.assertEqual(record["post_content"], "編輯版")
        self.assertEqual(record["material_row"], "9")
        self.assertEqual(record["fb_post_id"], "123_456")
        self.assertEqual(record["publish_status"], "scheduled")
        self.assertEqual(record["publish_time"], "time")


if __name__ == "__main__":
    unittest.main()
