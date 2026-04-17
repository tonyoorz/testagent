#!/usr/bin/env python3
"""
Static analysis snapshot exporter for Dash pages.

This script captures rendered Dash pages with Playwright, downloads static assets,
and writes a portable static site that can be shared as plain HTML files.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import parse_qsl, urljoin, urlparse

import requests


@dataclass
class SnapshotPage:
    url: str
    filename: str
    title: str


def sanitize_token(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "page"


def page_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_token = sanitize_token(parsed.path.strip("/"))
    if not path_token or path_token == "page":
        path_token = "index"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    if not query_pairs:
        if path_token == "index":
            return "index.html"
        return f"{path_token}.html"

    query_token = "_".join(
        f"{sanitize_token(k)}_{sanitize_token(v)}" for k, v in query_pairs if k and v
    )
    if query_token:
        return f"{path_token}_{query_token}.html"
    return f"{path_token}.html"


def target_urls(base_url: str, urls: Optional[List[str]], routes: Optional[List[str]]) -> List[str]:
    if urls:
        return [u.strip() for u in urls if u and u.strip()]

    route_list = routes or ["/"]
    normalized: List[str] = []
    for route in route_list:
        route = route.strip()
        if not route:
            continue
        if route.startswith("http://") or route.startswith("https://"):
            normalized.append(route)
        else:
            normalized.append(urljoin(base_url.rstrip("/") + "/", route.lstrip("/")))
    return normalized


def ensure_local_asset_path(parsed_asset_url) -> str:
    cleaned = parsed_asset_url.path.lstrip("/")
    cleaned = cleaned or "assets/resource.bin"
    if parsed_asset_url.query:
        cleaned = f"{cleaned}_{sanitize_token(parsed_asset_url.query)}"
    return f"assets/{cleaned}"


def collect_asset_urls(html: str, page_url: str) -> List[str]:
    assets: List[str] = []

    stylesheet_pattern = re.compile(
        r"<link[^>]*rel=[\"'][^\"']*stylesheet[^\"']*[\"'][^>]*href=[\"']([^\"']+)[\"'][^>]*>",
        flags=re.IGNORECASE,
    )
    img_pattern = re.compile(r"<img[^>]*src=[\"']([^\"']+)[\"'][^>]*>", flags=re.IGNORECASE)

    for href in stylesheet_pattern.findall(html):
        assets.append(urljoin(page_url, href))

    for src in img_pattern.findall(html):
        assets.append(urljoin(page_url, src))

    return list(dict.fromkeys(assets))


def allowed_hosts_from_urls(urls: List[str]) -> Set[str]:
    hosts: Set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.netloc:
            hosts.add(parsed.netloc.lower())
    return hosts


def should_download_asset(asset_url: str, allowed_hosts: Set[str], download_external_assets: bool) -> bool:
    parsed = urlparse(asset_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if download_external_assets:
        return True
    return parsed.netloc.lower() in allowed_hosts


def download_assets(
    asset_urls: Iterable[str],
    output_dir: Path,
    timeout_sec: int = 30,
    allowed_hosts: Optional[Set[str]] = None,
    download_external_assets: bool = False,
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    session = requests.Session()
    skipped_external = 0

    allowed = allowed_hosts or set()

    for asset_url in asset_urls:
        parsed = urlparse(asset_url)
        if not should_download_asset(
            asset_url=asset_url,
            allowed_hosts=allowed,
            download_external_assets=download_external_assets,
        ):
            if parsed.scheme in {"http", "https"} and allowed and parsed.netloc.lower() not in allowed:
                skipped_external += 1
            continue

        local_rel_path = ensure_local_asset_path(parsed)
        local_abs_path = output_dir / local_rel_path
        local_abs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = session.get(asset_url, timeout=timeout_sec)
            response.raise_for_status()
            local_abs_path.write_bytes(response.content)
            mapping[asset_url] = local_rel_path.replace("\\", "/")
        except Exception as exc:
            print(f"[WARN] Failed to download asset: {asset_url} ({exc})")

    if skipped_external > 0:
        print(f"[INFO] Skipped external assets: {skipped_external} (kept as original CDN links)")

    return mapping


def transform_snapshot_html(
    html: str,
    page_url: str,
    local_asset_map: Dict[str, str],
    export_note: str,
) -> str:
    script_pattern = re.compile(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", re.IGNORECASE | re.DOTALL)
    transformed = script_pattern.sub("", html)

    def _replace_attr(match: re.Match) -> str:
        original_value = match.group(2)
        absolute = urljoin(page_url, original_value)
        local_value = local_asset_map.get(absolute, original_value)
        return f"{match.group(1)}{local_value}{match.group(3)}"

    href_pattern = re.compile(r"(href=[\"'])([^\"']+)([\"'])", re.IGNORECASE)
    src_pattern = re.compile(r"(src=[\"'])([^\"']+)([\"'])", re.IGNORECASE)

    transformed = href_pattern.sub(lambda m: _replace_attr(m), transformed)
    transformed = src_pattern.sub(lambda m: _replace_attr(m), transformed)

    note_html = (
        "<div style=\"position:sticky;top:0;z-index:9999;padding:8px 12px;"
        "background:#f5f5f5;border-bottom:1px solid #ddd;"
        "font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#333;\">"
        f"{export_note}</div>"
    )

    body_tag = re.search(r"<body[^>]*>", transformed, flags=re.IGNORECASE)
    if body_tag:
        insert_at = body_tag.end()
        transformed = transformed[:insert_at] + note_html + transformed[insert_at:]
    else:
        transformed = note_html + transformed

    return transformed


def write_site_index(output_dir: Path, pages: List[SnapshotPage]) -> None:
    items = "\n".join(
        f'<li><a href="{p.filename}">{p.title}</a> <small>({p.url})</small></li>' for p in pages
    )
    html = f"""<!doctype html>
<html lang=\"en\"> 
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Analysis Snapshot Index</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; line-height: 1.5; }}
    h1 {{ margin-bottom: 6px; }}
    .meta {{ color: #666; margin-bottom: 20px; }}
  </style>
</head>
<body>
  <h1>Analysis Snapshot</h1>
  <div class=\"meta\">Generated at {datetime.now().isoformat(timespec='seconds')}</div>
  <ul>
    {items}
  </ul>
</body>
</html>
"""
    (output_dir / "site_index.html").write_text(html, encoding="utf-8")


def export_snapshot_site(
    output_dir: Path,
    urls: List[str],
    wait_ms: int,
    timeout_sec: int,
    headless: bool,
    download_external_assets: bool,
) -> List[SnapshotPage]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required. Install with: pip install playwright && playwright install chromium"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    raw_pages: List[Dict[str, str]] = []
    all_assets: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        for url in urls:
            print(f"[INFO] Capturing: {url}")
            page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
            if wait_ms > 0:
                time.sleep(wait_ms / 1000.0)

            title = page.title() or page_filename_from_url(url)
            html = page.content()
            assets = collect_asset_urls(html, url)
            all_assets.extend(assets)
            raw_pages.append({"url": url, "title": title, "html": html})

        browser.close()

    allowed_hosts = allowed_hosts_from_urls(urls)
    asset_map = download_assets(
        asset_urls=all_assets,
        output_dir=output_dir,
        timeout_sec=timeout_sec,
        allowed_hosts=allowed_hosts,
        download_external_assets=download_external_assets,
    )

    exported_pages: List[SnapshotPage] = []
    used_names: Dict[str, int] = {}

    for raw in raw_pages:
        filename = page_filename_from_url(raw["url"])
        if filename in used_names:
            used_names[filename] += 1
            stem = filename[:-5] if filename.endswith(".html") else filename
            filename = f"{stem}_{used_names[filename]}.html"
        else:
            used_names[filename] = 1

        note = f"Static snapshot generated from {raw['url']} at {datetime.now().isoformat(timespec='seconds')}"
        final_html = transform_snapshot_html(
            html=raw["html"],
            page_url=raw["url"],
            local_asset_map=asset_map,
            export_note=note,
        )
        (output_dir / filename).write_text(final_html, encoding="utf-8")

        exported_pages.append(SnapshotPage(url=raw["url"], filename=filename, title=raw["title"]))

    write_site_index(output_dir=output_dir, pages=exported_pages)
    return exported_pages


def parse_routes(routes_csv: str) -> List[str]:
    return [x.strip() for x in routes_csv.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export rendered Dash pages as a static snapshot site")
    parser.add_argument("--base-url", default="http://127.0.0.1:8051", help="Base URL of running dashboard")
    parser.add_argument(
        "--routes",
        default="/",
        help="Comma-separated relative routes, e.g. /,/risk_analysis,/test_coverage",
    )
    parser.add_argument(
        "--urls",
        nargs="*",
        help="Optional absolute URLs. When provided, --routes is ignored.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Default: report/analysis_snapshots/<timestamp>",
    )
    parser.add_argument("--wait-ms", type=int, default=4000, help="Extra wait time after page load")
    parser.add_argument("--timeout-sec", type=int, default=45, help="Page and download timeout")
    parser.add_argument(
        "--download-external-assets",
        action="store_true",
        help="Also download external CDN assets (default: only same-origin assets)",
    )
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("report") / "analysis_snapshots" / stamp

    urls = target_urls(args.base_url, args.urls, parse_routes(args.routes))
    if not urls:
        print("[ERROR] No URLs to export")
        return 2

    print(f"[INFO] Export destination: {output_dir}")
    for u in urls:
        print(f"[INFO] Target: {u}")

    try:
        pages = export_snapshot_site(
            output_dir=output_dir,
            urls=urls,
            wait_ms=args.wait_ms,
            timeout_sec=args.timeout_sec,
            headless=not args.headed,
            download_external_assets=args.download_external_assets,
        )
    except Exception as exc:
        print(f"[ERROR] Snapshot export failed: {exc}")
        return 1

    print(f"[OK] Exported {len(pages)} pages")
    print(f"[OK] Open: {(output_dir / 'site_index.html').as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
