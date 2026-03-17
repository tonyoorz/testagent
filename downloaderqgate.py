import argparse
import json
import os
import re
from datetime import datetime

import downloader6 as d6


DEFAULT_TEAMS = [
    "DTSV_China",
    "Spotlight_DTSV_China",
    "Spotlight_FIT",
    "[AT]BBA_Basis-FIT",
    "[AT]FIT_LAENDER_CHINA",
    "[AT]W71-FIT",
    "[AT]W72-FIT",
]


def slugify_team_name(team_name: str) -> str:
    if not team_name:
        return "UNKNOWN_TEAM"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", team_name.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "UNKNOWN_TEAM"


def escape_octane_query_string_value(value: str) -> str:
    if value is None:
        return ""
    s = str(value)
    s = s.replace("'", "\\'")
    s = s.replace("[", "\\[")
    s = s.replace("]", "\\]")
    return s


def build_defect_query(team_id: str, year_str: str) -> str:
    start_t_str, end_t_str = f"{year_str}-01-01T00:00:00Z", f"{year_str}-12-31T23:59:59Z"
    time_query_part = f"creation_time>='{start_t_str}';creation_time<='{end_t_str}'"
    team_query_part = f"problem_finder_team_udf={{id='{team_id}'}}"
    q_defect_inner = f"({time_query_part});({team_query_part})"
    return f'"({q_defect_inner})"'


def build_defect_ids_query(team_id: str, start_date: str, end_date: str, filter_field: str) -> str:
    start_date_formatted = f"{start_date}T00:00:00Z"
    end_date_formatted = f"{end_date}T23:59:59Z"
    parts = [
        f"problem_finder_team_udf={{id='{team_id}'}}",
        f"{filter_field}>='{start_date_formatted}'",
        f"{filter_field}<='{end_date_formatted}'",
    ]
    return f'"({";".join(parts)})"'


def fetch_team_name_to_id(session):
    all_rows = []
    offset = 0
    limit = 5000
    while True:
        resp = session.get(
            f"{d6.API_BASE_URL}/teams",
            params={"fields": "id,name,logical_name", "limit": limit, "offset": offset},
            verify=False,
            allow_redirects=True,
            timeout=60,
        )
        if resp.status_code >= 400:
            break
        payload = resp.json()
        batch = payload.get("data", []) or []
        all_rows.extend(batch)
        total_count = payload.get("total_count")
        if isinstance(total_count, int) and len(all_rows) >= total_count:
            break
        if len(batch) < limit:
            break
        offset += limit

    team_rows = all_rows
    mapping = {}
    for item in team_rows or []:
        name = item.get("name")
        tid = item.get("id")
        if name and tid:
            mapping[str(name)] = str(tid)
    return mapping


def parse_args():
    parser = argparse.ArgumentParser(description="下载指定 teams 的 defect 与 history 数据（用于 qgate 分析）")

    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument("--auth-method", choices=["sso", "cookie"], help="认证方法")
    auth_group.add_argument("--login-file", default="login_info.txt", help="SSO 用户名密码文件 (for --auth-method=sso)")
    auth_group.add_argument("--cookie-file", default="cookie.txt", help="Cookie 文件路径 (for --auth-method=cookie)")

    download_group = parser.add_argument_group("Download Options")
    current_year = datetime.now().year
    default_years = f"{current_year-1},{current_year}"
    download_group.add_argument("--defect-years", default=default_years, help=f"年份列表 (默认: {default_years})")
    download_group.add_argument("--teams", default=",".join(DEFAULT_TEAMS), help="Team 列表（逗号分隔）")
    download_group.add_argument("--output-root", default="qgate", help="输出根目录（默认: qgate）")
    download_group.add_argument("--limit-per-page", type=int, default=d6.DEFAULT_LIMIT_PER_PAGE, help=f"分页大小 (默认: {d6.DEFAULT_LIMIT_PER_PAGE})")
    download_group.add_argument("--max-concurrent-requests", type=int, default=10, help="最大并发请求数 (默认: 10)")
    download_group.add_argument("--save-csv", action="store_true", help="同时保存为 CSV")
    download_group.add_argument("--save-excel", action="store_true", help="同时保存为 Excel (需要 openpyxl)")
    download_group.add_argument("--skip-defects", action="store_true", help="跳过 defect 下载")
    download_group.add_argument("--skip-history", action="store_true", help="跳过 history 下载")

    history_group = parser.add_argument_group("History Download Options")
    history_group.add_argument("--history-max-workers", type=int, default=50, help="并行下载历史线程数 (1-50, 默认: 50)")
    history_group.add_argument("--history-start-date", default=None, help="开始日期 YYYY-MM-DD (默认: 当年-1 的 1月1日)")
    history_group.add_argument("--history-end-date", default=None, help="结束日期 YYYY-MM-DD (默认: 今天)")
    history_group.add_argument(
        "--history-filter-field",
        choices=["creation_time", "last_modified"],
        default="creation_time",
        help="历史筛选字段 (默认: creation_time)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    auth_method_selected = args.auth_method or "cookie"
    if auth_method_selected == "sso":
        session_active = d6.get_authenticated_session(auth_method_selected, sso_login_file=args.login_file)
    else:
        session_active = d6.get_authenticated_session(auth_method_selected, cookie_file_path=args.cookie_file)
    if not session_active:
        raise SystemExit(2)

    script_dir_path = os.path.dirname(os.path.abspath(__file__))
    output_root_dir = os.path.join(script_dir_path, args.output_root)
    defect_dir = os.path.join(output_root_dir, "defect")
    history_dir = os.path.join(output_root_dir, "history")
    os.makedirs(output_root_dir, exist_ok=True)
    os.makedirs(defect_dir, exist_ok=True)
    os.makedirs(history_dir, exist_ok=True)

    teams = [t.strip() for t in (args.teams or "").split(",") if t.strip()]
    years_list_defect = [y.strip() for y in (args.defect_years or "").split(",") if y.strip().isdigit() and len(y.strip()) == 4]

    team_name_to_id = fetch_team_name_to_id(session_active)

    defect_ids_union = set()
    per_team_defect_ids = {}

    if not args.skip_defects:
        for team in teams:
            team_slug = slugify_team_name(team)
            per_team_defect_ids.setdefault(team, set())
            team_id = team_name_to_id.get(team)
            if not team_id:
                continue
            for year_str in years_list_defect:
                q_defect = build_defect_query(team_id, year_str)
                defect_data_list = d6.fetch_octane_data_parallel(
                    session_active,
                    d6.EP_DEFECT,
                    d6.DEFAULT_F_DEFECT_MAIN,
                    q_defect,
                    order_by="creation_time",
                    limit_per_page=args.limit_per_page,
                    max_workers=args.max_concurrent_requests,
                )
                if not defect_data_list:
                    continue
                fn_defect = f"{year_str}_{team_slug}_defect"
                d6.save_data(defect_data_list, fn_defect, defect_dir, args.save_csv, args.save_excel)
                ids = {str(item.get("id")) for item in defect_data_list if "id" in item}
                per_team_defect_ids[team].update(ids)
                defect_ids_union.update(ids)

        index_path = os.path.join(defect_dir, "qgate_defect_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "teams": teams,
                    "defect_years": years_list_defect,
                    "defect_counts_by_team": {t: len(per_team_defect_ids.get(t, set())) for t in teams},
                    "defect_ids_total_unique": len(defect_ids_union),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    if args.skip_history:
        return

    current_year = datetime.now().year
    default_start_date = f"{current_year-1}-01-01"
    default_end_date = datetime.now().strftime("%Y-%m-%d")
    hist_start_date = args.history_start_date or default_start_date
    hist_end_date = args.history_end_date or default_end_date
    hist_max_workers_val = min(max(1, args.history_max_workers), 50)

    if defect_ids_union:
        d6.fetch_histories_parallel_integrated(sorted(defect_ids_union), session_active, hist_max_workers_val, history_dir)
        return

    for team in teams:
        team_id = team_name_to_id.get(team)
        if not team_id:
            continue
        query = build_defect_ids_query(team_id, hist_start_date, hist_end_date, args.history_filter_field)
        resp_data = d6.fetch_octane_data(
            session_active,
            d6.EP_DEFECT,
            ("id",),
            query,
            limit_per_page=args.limit_per_page,
            api_url=d6.API_BASE_URL,
        )
        defect_ids_union.update({str(item.get("id")) for item in (resp_data or []) if item.get("id") is not None})

    if defect_ids_union:
        d6.fetch_histories_parallel_integrated(sorted(defect_ids_union), session_active, hist_max_workers_val, history_dir)


if __name__ == "__main__":
    main()
