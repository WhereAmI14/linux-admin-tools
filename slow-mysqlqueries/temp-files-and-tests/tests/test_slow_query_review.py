import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent.parent
SCRIPT_PATH = PROJECT_DIR / "slow_query_review.py"
FIXTURE_PATH = TESTS_DIR / "fixtures" / "sample_slow.log"


def load_module():
    spec = importlib.util.spec_from_file_location("slow_query_review", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SlowQueryReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_module()

    def test_parse_timeframe_variants(self):
        self.assertIsNone(self.tool.parse_timeframe("all"))
        self.assertEqual(self.tool.parse_timeframe("24h").total_seconds(), 24 * 3600)
        self.assertEqual(self.tool.parse_timeframe("3 days").total_seconds(), 3 * 86400)
        self.assertEqual(self.tool.parse_timeframe("2w").total_seconds(), 14 * 86400)

    def test_parse_interval_time_variants(self):
        parsed = self.tool.parse_interval_time("2025-08-03 00:00")
        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M:%S %Z"), "2025-08-03 00:00:00 UTC")
        parsed_z = self.tool.parse_interval_time("2025-08-03T02:06:53Z")
        self.assertEqual(parsed_z.strftime("%Y-%m-%d %H:%M:%S %Z"), "2025-08-03 02:06:53 UTC")

    def test_parse_slow_log_attributes_root_query_to_database_owner(self):
        records = self.tool.parse_slow_log(str(FIXTURE_PATH), ["easternm", "gdbltdne"])
        self.assertEqual(len(records), 3)

        first = records[0]
        self.assertEqual(first.db_user, "root")
        self.assertEqual(first.execution_owner, self.tool.SYSTEM_OWNER)
        self.assertEqual(first.attributed_owner, "easternm")
        self.assertEqual(first.owner_source, "database")

        second = records[1]
        self.assertEqual(second.execution_owner, "gdbltdne")
        self.assertEqual(second.attributed_owner, "gdbltdne")

        third = records[2]
        self.assertEqual(third.attributed_owner, self.tool.SYSTEM_OWNER)

    def test_filter_records_for_single_user_matches_legacy_and_database_owner(self):
        records = self.tool.parse_slow_log(str(FIXTURE_PATH), ["easternm", "gdbltdne"])
        filtered = self.tool.filter_records(
            records,
            since_delta=None,
            from_time=None,
            to_time=None,
            cpanel_user="easternm",
            include_system=False,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].attributed_owner, "easternm")

    def test_filter_records_for_absolute_interval(self):
        records = self.tool.parse_slow_log(str(FIXTURE_PATH), ["easternm", "gdbltdne"])
        filtered = self.tool.filter_records(
            records,
            since_delta=None,
            from_time=self.tool.parse_interval_time("2025-08-04 00:00"),
            to_time=self.tool.parse_interval_time("2025-08-04 23:59:59"),
            cpanel_user=None,
            include_system=True,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].attributed_owner, "gdbltdne")

    def test_prompt_for_target_blank_input_scans_all_users(self):
        args = self.tool.parse_args(["--log-file", str(FIXTURE_PATH), "--no-color"])
        output = io.StringIO()
        resolved = self.tool.prompt_for_target(args, input_stream=io.StringIO("\n"), output_stream=output)
        self.assertTrue(resolved.all_users)
        self.assertIsNone(resolved.user)

    def test_prompt_for_target_can_accept_single_user(self):
        args = self.tool.parse_args(["--log-file", str(FIXTURE_PATH), "--no-color"])
        output = io.StringIO()
        resolved = self.tool.prompt_for_target(
            args,
            input_stream=io.StringIO("easternm\n"),
            output_stream=output,
        )
        self.assertEqual(resolved.user, "easternm")
        self.assertFalse(resolved.all_users)

    def test_prompt_for_time_filter_blank_input_uses_all(self):
        args = self.tool.parse_args(["--all-users", "--log-file", str(FIXTURE_PATH), "--no-color"])
        output = io.StringIO()
        resolved = self.tool.prompt_for_time_filter(args, input_stream=io.StringIO("\n"), output_stream=output)
        self.assertEqual(resolved.since, "all")

    def test_prompt_for_time_filter_accepts_relative_value(self):
        args = self.tool.parse_args(["--all-users", "--log-file", str(FIXTURE_PATH), "--no-color"])
        output = io.StringIO()
        resolved = self.tool.prompt_for_time_filter(args, input_stream=io.StringIO("7d\n"), output_stream=output)
        self.assertEqual(resolved.since, "7d")

    def test_cli_all_users_output_contains_expected_sections(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--all-users",
                "--log-file",
                str(FIXTURE_PATH),
                "--no-color",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Summary", result.stdout)
        self.assertIn("cPanel accounts with slow queries", result.stdout)
        self.assertIn("Databases with the most slow queries", result.stdout)
        self.assertIn("DATABASE", result.stdout)
        self.assertIn("ACCOUNT", result.stdout)
        self.assertIn("easternm", result.stdout)
        self.assertIn("gdbltdne", result.stdout)
        self.assertIn("easternm_easternmeat", result.stdout)
        self.assertIn("The 2 slowest queries for all users during all time", result.stdout)
        self.assertNotIn("(system/root)            ", result.stdout)
        self.assertNotIn("Top query fingerprints", result.stdout)
        self.assertNotIn("Total query time:", result.stdout)
        self.assertNotIn("P95 query time:", result.stdout)
        self.assertNotIn("Rows examined total:", result.stdout)

    def test_cli_can_filter_with_absolute_interval(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--all-users",
                "--from",
                "2025-08-04 00:00",
                "--to",
                "2025-08-04 23:59:59",
                "--log-file",
                str(FIXTURE_PATH),
                "--no-color",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("2025-08-04 00:00:00 UTC -> 2025-08-04 23:59:59 UTC", result.stdout)
        self.assertIn("gdbltdne", result.stdout)
        self.assertNotIn("easternm", result.stdout)

    def test_cli_can_write_analytical_report(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--user",
                    "easternm",
                    "--log-file",
                    str(FIXTURE_PATH),
                    "--no-color",
                    "--write-user-reports",
                    "--report-dir",
                    tmp_dir,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            raw_generated = sorted(Path(tmp_dir).glob("slow-queries-*.txt"))
            self.assertEqual(len(raw_generated), 1)
            raw_report_text = raw_generated[0].read_text(encoding="utf-8")
            self.assertIn("# Time: 2025-08-03T02:06:53.286964Z", raw_report_text)
            self.assertIn("use easternm_easternmeat;", raw_report_text)
            generated = sorted(Path(tmp_dir).glob("slow-query-report-*.txt"))
            self.assertEqual(len(generated), 1)
            report_text = generated[0].read_text(encoding="utf-8")
            self.assertIn("single user (easternm)", report_text)
            self.assertIn("The 1 slowest queries for user easternm during all time", report_text)
            self.assertNotIn("Top query fingerprints", report_text)

    def test_single_user_run_writes_raw_report_for_selected_interval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--user",
                    "gdbltdne",
                    "--from",
                    "2025-08-04 00:00",
                    "--to",
                    "2025-08-04 23:59:59",
                    "--report-dir",
                    tmp_dir,
                    "--log-file",
                    str(FIXTURE_PATH),
                    "--no-color",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            raw_generated = sorted(Path(tmp_dir).glob("slow-queries-*.txt"))
            self.assertEqual(len(raw_generated), 1)
            raw_report_text = raw_generated[0].read_text(encoding="utf-8")
            self.assertIn("gdbltdne_stagingnode49", raw_report_text)
            self.assertNotIn("easternm_easternmeat", raw_report_text)


if __name__ == "__main__":
    unittest.main()
