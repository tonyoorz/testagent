import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Optional

import requests

# Hardcoded cookie (FOR TESTING ONLY — do not commit sensitive credentials in production)
HARDCODED_COOKIE = (
    "_ga=GA1.1.1504591765.1763708583; _ga_0C4M1PWYZ7=GS2.1.s1763708582$o1$g0$t1763708584$j58$l0$h0; "
    "_ga_T11SF3WXX2=GS2.1.s1763708584$o1$g0$t1763708584$j60$l0$h0; _ga_K2SPJK2C73=GS2.1.s1763708584$o1$g0$t1763708584$j60$l0$h0; "
    "lbwen=01; lbweni=01; weni=9Ym9t-MvmwLYcnGtrlDpSdOQIas.*AAJTSQACMDEAAlNLABx3SkYxU0pHNXNUNTN5WXl1NGdGL29qVEFpQXM9AAR0eXBlAANDVFMAAlMxAAA.*; "
    "accessToken=6E6TGp69Kq3sUGyVk8DsTQXrtoY; userName=Tianhua%20Xie; isA3Admin=false; accessToken_uat=6E6TGp69Kq3sUGyVk8DsTQXrtoY; "
    "wen=rK_pqPvqtx-FJb0tq3fAWwphJTM.*AAJTSQACMDEAAlNLABxwT3FqVXZJbVVtNXY5Yy9vTlpuaTdiVUtZMGc9AAR0eXBlAANDVFMAAlMxAAA.*; "
    "rxVisitor=1770271058266J4AC4HI6BBUFD2VBCGFT42A6OIIGQQB9; dtCookie=v_4_srv_4_sn_520BD08AE70023B790C642C4C3EC7A4C_app-3A2579a82aa388e4a2_1_app-3A3a336dbc3f55ee1c_1_ol_0_perc_100000_mul_1_rcs-3Acss_0; "
    "dtSa=-; rxvt=1770273621022|1770271058267; dtPC=4$271122726_505h-vAQAUMADIOFWVFQNCVQDGHIRAPKJACOOQ-0e0"
)

URL_TEMPLATE = (
    "https://integrate.bmwgroup.net/core/v1alpha1/user/my/context/permissions/hash?appCodeId={}"
)


def get_session(cookie: str, verify_ssl: bool = False) -> requests.Session:
    s = requests.Session()
    # Set cookie header as provided. This is a testing shortcut.
    s.headers.update({
        "Cookie": cookie,
        "User-Agent": "downloaderintegrate/1.0",
        "Accept": "application/json, text/plain, */*",
    })
    s.verify = verify_ssl
    return s


def fetch_integrate_permissions(
    session: requests.Session, app_code_id: str, retries: int = 3, backoff: float = 1.0
) -> Optional[Any]:
    url = URL_TEMPLATE.format(app_code_id)
    attempt = 0
    while attempt < retries:
        try:
            resp = session.get(url, timeout=30)
            status = resp.status_code
            logging.info(f"GET {url} -> {status}")
            if status == 200:
                try:
                    return resp.json()
                except ValueError:
                    # Not JSON; return text
                    return resp.text
            elif status in (401, 403):
                logging.error(f"Authentication error ({status}). Check cookie/session.")
                return None
            else:
                logging.warning(f"Unexpected status {status}; response length={len(resp.content)}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")

        attempt += 1
        sleep_for = backoff * (2 ** (attempt - 1))
        logging.info(f"Retrying in {sleep_for:.1f}s (attempt {attempt + 1}/{retries})...")
        time.sleep(sleep_for)

    logging.error("Exceeded max retries without success.")
    return None


def save_json(obj: Any, output_dir: str, filename: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return out_path
    except Exception as e:
        logging.error(f"Failed to save file {out_path}: {e}")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download integrate permissions for an appCodeId and save JSON to integrate/")
    parser.add_argument("--appCodeId", default="fleem", help="appCodeId to query (default: fleem)")
    parser.add_argument("--output-dir", default="integrate", help="Directory to save results (default: integrate)")
    parser.add_argument("--retries", type=int, default=3, help="Number of retries on failure")
    parser.add_argument("--verify-ssl", action="store_true", help="Enable SSL verification")

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    session = get_session(HARDCODED_COOKIE, verify_ssl=args.verify_ssl)
    result = fetch_integrate_permissions(session, args.appCodeId, retries=args.retries)
    if result is None:
        logging.error("No result received; exiting with error.")
        sys.exit(2)

    # Save result
    filename = f"{args.appCodeId}_permissions.json"
    path = save_json(result, args.output_dir, filename)
    logging.info(f"Saved permissions to: {path}")


if __name__ == "__main__":
    main()
