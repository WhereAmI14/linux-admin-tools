import importlib.util
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
            cpanel_user="easternm",
            include_system=False,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].attributed_owner, "easternm")

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
        self.assertIn("Top cPanel owners", result.stdout)
        self.assertIn("easternm", result.stdout)
        self.assertIn("gdbltdne", result.stdout)
        self.assertNotIn("(system/root)            ", result.stdout)

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
            generated = sorted(Path(tmp_dir).glob("slow-query-report-*.txt"))
            self.assertEqual(len(generated), 1)
            report_text = generated[0].read_text(encoding="utf-8")
            self.assertIn("single user (easternm)", report_text)
            self.assertIn("Top query fingerprints", report_text)


if __name__ == "__main__":
    unittest.main()
