import importlib.util
import pathlib
import subprocess
import unittest
from unittest import mock


def _load_octane_downloader_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "download" / "octane_downloader.py"
    spec = importlib.util.spec_from_file_location("octane_downloader_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


octane_downloader = _load_octane_downloader_module()


class TestPostDownloadDataProcessorSync(unittest.TestCase):
    @mock.patch.object(octane_downloader.os.path, "exists", return_value=True)
    @mock.patch.object(octane_downloader.subprocess, "run")
    def test_post_sync_forces_utf8_child_io(self, mock_run, _mock_exists):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "data_processor.py"],
            returncode=0,
            stdout="同步完成",
            stderr="",
        )

        repo_root = str(pathlib.Path(__file__).resolve().parents[1])
        db_path = str(pathlib.Path(repo_root) / "database" / "local_data_rebuilt.db")

        ok = octane_downloader.run_post_download_data_processor_sync(
            repo_root_path=repo_root,
            db_path=db_path,
        )

        self.assertTrue(ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")


if __name__ == "__main__":
    unittest.main()