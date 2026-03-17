import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    env_path_candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]
    for env_path in env_path_candidates:
        try:
            if not os.path.exists(env_path):
                continue
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            continue


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_URL = "https://integrate.bmwgroup.net"
DEFAULT_APP_CODE_ID = "fleem"
PERMISSIONS_HASH_PATH = "/core/v1alpha1/user/my/context/permissions/hash"

HARDCODED_COOKIE = (
    "_ga=GA1.1.1504591765.1763708583; _ga_0C4M1PWYZ7=GS2.1.s1763708582$o1$g0$t1763708584$j58$l0$h0; "
    "_ga_T11SF3WXX2=GS2.1.s1763708584$o1$g0$t1763708584$j60$l0$h0; "
    "_ga_K2SPJK2C73=GS2.1.s1763708584$o1$g0$t1763708584$j60$l0$h0; lbwen=01; lbweni=01; "
    "weni=9Ym9t-MvmwLYcnGtrlDpSdOQIas.*AAJTSQACMDEAAlNLABx3SkYxU0pHNXNUNTN5WXl1NGdGL29qVEFpQXM9AAR0eXBlAANDVFMAAlMxAAA.*; "
    "accessToken=6E6TGp69Kq3sUGyVk8DsTQXrtoY; userName=Tianhua%20Xie; isA3Admin=false; "
    "accessToken_uat=6E6TGp69Kq3sUGyVk8DsTQXrtoY; "
    "wen=rK_pqPvqtx-FJb0tq3fAWwphJTM.*AAJTSQACMDEAAlNLABxwT3FqVXZJbVVtNXY5Yy9vTlpuaTdiVUtZMGc9AAR0eXBlAANDVFMAAlMxAAA.*; "
    "rxVisitor=1770271058266J4AC4HI6BBUFD2VBCGFT42A6OIIGQQB9; "
    "dtCookie=v_4_srv_4_sn_520BD08AE70023B790C642C4C3EC7A4C_app-3A2579a82aa388e4a2_1_app-3A3a336dbc3f55ee1c_1_ol_0_perc_100000_mul_1_rcs-3Acss_0; "
    "dtSa=-; rxvt=1770273621022|1770271058267; "
    "dtPC=4$271122726_505h-vAQAUMADIOFWVFQNCVQDGHIRAPKJACOOQ-0e0"
)


def build_output_paths(output_dir: str, filename_prefix: str) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    return {
        "json": os.path.join(output_dir, f"{filename_prefix}.json"),
        "txt": os.path.join(output_dir, f"{filename_prefix}.txt"),
    }


def save_payload(payload: Any, raw_text: str, output_paths: Dict[str, str]) -> None:
    try:
        with open(output_paths["json"], "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logging.info(f"已保存 JSON: {output_paths['json']}")
    except Exception as e:
        logging.error(f"保存 JSON 失败: {e}")

    try:
        with open(output_paths["txt"], "w", encoding="utf-8") as f:
            f.write(raw_text)
        logging.info(f"已保存原始响应: {output_paths['txt']}")
    except Exception as e:
        logging.error(f"保存原始响应失败: {e}")


def get_cookie(cookie_arg: Optional[str]) -> str:
    if cookie_arg:
        return cookie_arg.strip()
    env_cookie = os.environ.get("INTEGRATE_COOKIE", "").strip()
    if env_cookie:
        return env_cookie
    return HARDCODED_COOKIE.strip()


def fetch_permissions_hash(
    session: requests.Session,
    app_code_id: str,
    base_url: str = BASE_URL,
    timeout_s: int = 60,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    url = urljoin(base_url, PERMISSIONS_HASH_PATH)
    resp = session.get(url, params={"appCodeId": app_code_id}, timeout=timeout_s, verify=verify_ssl)
    status = resp.status_code
    if status in (401, 403):
        raise RuntimeError(f"认证/权限失败: {status}")
    if status >= 400:
        raise RuntimeError(f"请求失败: {status}, body={resp.text[:500]}")
    try:
        payload = resp.json()
        return {"payload": payload, "raw_text": resp.text, "final_url": resp.url}
    except Exception:
        return {"payload": {"raw": resp.text}, "raw_text": resp.text, "final_url": resp.url}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-code-id", default=DEFAULT_APP_CODE_ID)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--cookie", default=None)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--verify-ssl", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(script_dir, "integrate")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_prefix = f"permissions_hash_{args.app_code_id}_{timestamp}"
    output_paths = build_output_paths(output_dir, filename_prefix)

    url = urljoin(args.base_url, PERMISSIONS_HASH_PATH)
    if args.dry_run:
        logging.info(f"dry-run: GET {url}?appCodeId={args.app_code_id}")
        logging.info(f"dry-run: output_dir={output_dir}")
        logging.info(f"dry-run: json={output_paths['json']}")
        return 0

    cookie = get_cookie(args.cookie)
    session = requests.Session()
    session.headers.update(
        {
            "cookie": cookie,
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0",
        }
    )

    result = fetch_permissions_hash(
        session=session,
        app_code_id=args.app_code_id,
        base_url=args.base_url,
        timeout_s=args.timeout,
        verify_ssl=args.verify_ssl,
    )
    payload = result["payload"]
    raw_text = result["raw_text"]
    final_url = result["final_url"]
    logging.info(f"请求成功: {final_url}")
    save_payload(payload, raw_text, output_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
