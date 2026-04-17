import unittest

from analysis_snapshot import page_filename_from_url, should_download_asset, transform_snapshot_html


class TestAnalysisSnapshot(unittest.TestCase):
    def test_page_filename_from_url_handles_root_and_query(self):
        self.assertEqual(page_filename_from_url("http://localhost:8051/"), "index.html")
        self.assertEqual(
            page_filename_from_url("http://localhost:8051/risk_analysis?team=DTSV_China"),
            "risk_analysis_team_DTSV_China.html",
        )

    def test_transform_snapshot_html_rewrites_assets_and_removes_scripts(self):
        html = (
            '<html><head><link rel="stylesheet" href="/assets/style.css">'
            '<script src="/assets/app.js"></script></head><body>'
            '<img src="/pic/logo.png"><script>console.log("x")</script></body></html>'
        )

        transformed = transform_snapshot_html(
            html=html,
            page_url="http://localhost:8051/risk_analysis",
            local_asset_map={
                "http://localhost:8051/assets/style.css": "assets/style.css",
                "http://localhost:8051/pic/logo.png": "assets/pic/logo.png",
            },
            export_note="Snapshot",
        )

        self.assertIn('href="assets/style.css"', transformed)
        self.assertIn('src="assets/pic/logo.png"', transformed)
        self.assertIn("Snapshot", transformed)
        self.assertNotIn("<script", transformed)

    def test_should_download_asset_defaults_to_same_origin_only(self):
        allowed = {"127.0.0.1:8051"}
        self.assertTrue(
            should_download_asset(
                "http://127.0.0.1:8051/assets/style.css",
                allowed_hosts=allowed,
                download_external_assets=False,
            )
        )
        self.assertFalse(
            should_download_asset(
                "https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/dist/css/bootstrap.min.css",
                allowed_hosts=allowed,
                download_external_assets=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
