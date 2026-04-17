import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from download import octane_downloader


class OctaneDownloaderPostSyncTests(unittest.TestCase):
    def test_run_post_download_data_processor_sync_invokes_data_processor_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "data_processor.py").write_text("print('ok')\n", encoding="utf-8")

            with patch("download.octane_downloader.subprocess.run") as run_mock:
                run_mock.return_value.returncode = 0
                run_mock.return_value.stdout = "done"
                run_mock.return_value.stderr = ""

                ok = octane_downloader.run_post_download_data_processor_sync(
                    repo_root_path=str(repo_root),
                    db_path="database/test.db",
                    timeout_seconds=0,
                )

            self.assertTrue(ok)
            self.assertTrue(run_mock.called)
            cmd = run_mock.call_args.args[0]
            self.assertIn("--sync-processed-fields-to-db", cmd)
            self.assertIn("--db-path", cmd)
            self.assertIn("database/test.db", cmd)

    def test_run_post_download_data_processor_sync_returns_false_when_script_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = octane_downloader.run_post_download_data_processor_sync(
                repo_root_path=tmpdir,
                db_path=None,
                timeout_seconds=0,
            )
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
