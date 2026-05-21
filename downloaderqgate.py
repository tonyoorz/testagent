import argparse
import json
import os
import re
import sys
from datetime import datetime

import backfill_qgate_history_events
import data_processor
from download import octane_downloader as d6
from octane_db import OctaneSQLiteStore

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


DEFAULT_TEAMS = [
    "DTSV_China",
    "Spotlight_DTSV_China",
    "Spotlight_FIT",
    "[AT]BBA_Basis-FIT",
    "[AT]FIT_LAENDER_CHINA",
    "Plant-Dadong FIT",
    "Plant-Tiexi FIT",
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="下载指定 teams 的 defect 与 history 数据（用于 qgate 分析）")

    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument("--auth-method", choices=["sso", "cookie"], help="认证方法")
    auth_group.add_argument("--login-file", default="login_info.txt", help="SSO 用户名密码文件 (for --auth-method=sso)")
    auth_group.add_argument("--cookie-file", default="cookie.txt", help="Cookie 文件路径 (for --auth-method=cookie)")

    download_group = parser.add_argument_group("Download Options")
    current_year = datetime.now().year
    default_years = f"{current_year-1},{current_year}"
    download_group.add_argument("--year", type=int, default=None, help="仅下载单一年份（例如: 2026）")
    download_group.add_argument("--defect-years", default=default_years, help=f"年份列表 (默认: {default_years})")
    download_group.add_argument("--teams", default=",".join(DEFAULT_TEAMS), help="Team 列表（逗号分隔）")
    download_group.add_argument("--output-root", default="qgate", help="输出根目录（默认: qgate）")
    download_group.add_argument("--limit-per-page", type=int, default=d6.DEFAULT_LIMIT_PER_PAGE, help=f"分页大小 (默认: {d6.DEFAULT_LIMIT_PER_PAGE})")
    download_group.add_argument("--max-concurrent-requests", type=int, default=10, help="最大并发请求数 (默认: 10)")
    download_group.add_argument("--save-csv", action="store_true", help="同时保存为 CSV")
    download_group.add_argument("--save-excel", action="store_true", help="同时保存为 Excel (需要 openpyxl)")
    download_group.add_argument("--skip-defects", action="store_true", help="跳过 defect 下载")
    download_group.add_argument("--skip-history", action="store_true", help="跳过 history 下载")
    download_group.add_argument("--save-db", action="store_true", help="同时保存到 SQLite 数据库")
    download_group.add_argument("--qgate-db-path", default="qgate/qgate_data.db", help="QGate SQLite 文件路径")
    download_group.add_argument("--save-chroma", action="store_true", help="同时写入 Chroma 语义索引")
    download_group.add_argument("--chroma-dir", default="qgate/chroma", help="Chroma 持久化目录")
    download_group.add_argument("--chroma-collection", default="qgate_defect_cases", help="Chroma collection 名称")
    download_group.add_argument("--skip-file-output", action="store_true", help="不写 defect/history 文件，仅保留数据库输出")
    download_group.add_argument(
        "--defer-history-events",
        dest="defer_history_events",
        action="store_true",
        help="history 下载时只写原始 payload，跳过在线展开 octane_defect_history_events（qgate 默认开启）",
    )
    download_group.add_argument(
        "--sync-history-events",
        dest="defer_history_events",
        action="store_false",
        help="history 下载时同步展开 octane_defect_history_events（更慢，仅在明确需要时开启）",
    )
    download_group.add_argument(
        "--no-post-process-sync",
        action="store_true",
        help="跳过下载完成后的 defect 字段回写与 history event 轻量回填",
    )
    parser.set_defaults(defer_history_events=True)

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

    return parser.parse_args(argv)


def apply_year_override(args, cli_args):
    if args.year is None:
        return args

    current_year = datetime.now().year
    if args.year < 2000 or args.year > current_year:
        raise SystemExit(f"--year 必须在 2000 到 {current_year} 之间")

    if "--defect-years" not in cli_args:
        args.defect_years = str(args.year)

    return args


def validate_storage_args(args):
    if args.save_chroma and not args.save_db:
        raise SystemExit("--save-chroma requires --save-db")
    if args.skip_file_output and not args.save_db:
        raise SystemExit("--skip-file-output requires --save-db")
    return args


def initialize_qgate_store(db_path, defer_history_events=True):
    store = OctaneSQLiteStore(db_path, sync_history_events=not defer_history_events)
    store.create_tables()
    store.create_optimized_tables()
    return store


def initialize_chroma_collection(chroma_dir, collection_name):
    if chromadb is None:
        raise SystemExit("chromadb is required for --save-chroma")

    os.makedirs(chroma_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_dir)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def normalize_defect_text(value):
    if value is None:
        return ""

    try:
        if value != value:
            return ""
    except Exception:
        pass

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text


def build_chroma_documents(defect_data_list, team, team_slug, year_str, fetched_at):
    ids = []
    documents = []
    metadatas = []
    year_value = int(year_str)
    optional_fields = [
        ("Name", "name"),
        ("Description", "description"),
        ("Phase", "phase"),
        ("Severity", "severity"),
        ("Owner", "owner"),
        ("Release Vehicle", "release_vehicle"),
    ]
    metadata_fields = {"name", "phase", "severity", "owner", "release_vehicle"}

    for defect_row in defect_data_list or []:
        defect_id = defect_row.get("id")
        if defect_id is None:
            continue

        defect_id_str = str(defect_id)
        document_id = f"{team_slug}:{year_str}:{defect_id_str}"
        metadata = {
            "defect_id": defect_id_str,
            "team": team,
            "team_slug": team_slug,
            "year": year_value,
            "fetched_at": fetched_at,
        }
        document_lines = [
            f"Defect {defect_id_str}",
            f"Team: {team}",
            f"Year: {year_str}",
        ]

        for label, key in optional_fields:
            value = normalize_defect_text(defect_row.get(key))
            if not value:
                continue
            document_lines.append(f"{label}: {value}")
            if key in metadata_fields:
                metadata[key] = value

        ids.append(document_id)
        documents.append("\n".join(document_lines))
        metadatas.append(metadata)

    return ids, documents, metadatas


def upsert_defects_to_chroma(collection, defect_data_list, team, team_slug, year_str, fetched_at):
    ids, documents, metadatas = build_chroma_documents(
        defect_data_list,
        team=team,
        team_slug=team_slug,
        year_str=year_str,
        fetched_at=fetched_at,
    )
    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return {
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
    }


def save_defect_batch(
    defect_data_list,
    *,
    team,
    year_str,
    team_slug,
    defect_dir,
    save_csv=False,
    save_excel=False,
    save_files=True,
    store=None,
    fetched_at=None,
):
    if save_files:
        filename = f"{year_str}_{team_slug}_defect"
        d6.save_data(defect_data_list, filename, defect_dir, save_csv, save_excel)

    if store is not None:
        payload_kwargs = {
            "kind": "defects",
            "team": team,
            "year": int(year_str),
            "spec": team_slug,
            "payload": {"data": defect_data_list},
        }
        if fetched_at is not None:
            payload_kwargs["fetched_at"] = fetched_at

        defects_kwargs = {
            "year": int(year_str),
        }
        if fetched_at is not None:
            defects_kwargs["fetched_at"] = fetched_at

        store.upsert_payload(
            **payload_kwargs,
        )
        store.upsert_defects_batch(
            defect_data_list,
            **defects_kwargs,
        )

    return {
        str(item.get("id"))
        for item in (defect_data_list or [])
        if item.get("id") is not None
    }


def save_qgate_histories(
    *,
    defect_ids,
    session,
    max_workers,
    history_dir,
    team,
    store=None,
    save_files=True,
    save_csv=False,
):
    if defect_ids is None:
        normalized_defect_ids = []
    elif isinstance(defect_ids, (str, int)):
        normalized_defect_ids = [str(defect_ids)]
    else:
        normalized_defect_ids = sorted(
            str(defect_id)
            for defect_id in defect_ids
            if defect_id is not None
        )

    if not normalized_defect_ids:
        return [], []

    if store is not None:
        return d6.fetch_defect_histories_parallel_to_db(
            normalized_defect_ids,
            session,
            max_workers,
            store,
            team,
            save_files_dir=history_dir if save_files else None,
            save_csv_hist=save_csv,
        )

    return d6.fetch_defect_histories_parallel(
        normalized_defect_ids,
        session,
        max_workers,
        history_dir,
        save_csv,
    )


def run_post_download_qgate_sync(db_path):
    if not db_path:
        print("未提供 qgate 数据库路径，跳过后处理同步。")
        return False

    if not os.path.exists(db_path):
        print(f"QGate 数据库不存在，跳过后处理同步: {db_path}")
        return False

    try:
        stats = data_processor.sync_processed_fields_to_db(
            db_path=db_path,
            sync_manual_runs=False,
        )
    except Exception as exc:
        print(f"QGate defect 下载后字段同步失败: {exc}")
        return False

    print(
        "QGate defect 下载后字段同步完成: "
        f"db_path={db_path}, defect_updates={int(stats.get('defect_updates') or 0)}"
    )
    return True


def run_post_download_qgate_history_event_sync(db_path):
    if not db_path:
        print("未提供 qgate 数据库路径，跳过 history event 后处理同步。")
        return False

    if not os.path.exists(db_path):
        print(f"QGate 数据库不存在，跳过 history event 后处理同步: {db_path}")
        return False

    try:
        summary = backfill_qgate_history_events.backfill_qgate_history_events(db_path)
    except Exception as exc:
        print(f"QGate history event 后处理同步失败: {exc}")
        return False

    print(
        "QGate history event 后处理同步完成: "
        f"db_path={db_path}, events_upserted={int(summary.get('events_upserted') or 0)}"
    )
    return True


def main(argv=None):
    cli_args = list(argv) if argv is not None else sys.argv[1:]
    args = parse_args(cli_args)
    args = apply_year_override(args, cli_args)
    args = validate_storage_args(args)

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
    save_files = not args.skip_file_output

    if save_files:
        os.makedirs(output_root_dir, exist_ok=True)
        os.makedirs(defect_dir, exist_ok=True)
        os.makedirs(history_dir, exist_ok=True)

    store = None
    chroma_collection = None
    run_fetched_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    teams = [t.strip() for t in (args.teams or "").split(",") if t.strip()]
    years_list_defect = [y.strip() for y in (args.defect_years or "").split(",") if y.strip().isdigit() and len(y.strip()) == 4]

    team_name_to_id = fetch_team_name_to_id(session_active)

    defect_ids_union = set()
    per_team_defect_ids = {}
    downloaded_defects = False
    downloaded_histories = False

    try:
        if args.save_db:
            store_parent = os.path.dirname(args.qgate_db_path)
            if store_parent:
                os.makedirs(store_parent, exist_ok=True)
            store = initialize_qgate_store(
                args.qgate_db_path,
                defer_history_events=args.defer_history_events,
            )

        if args.save_chroma:
            chroma_collection = initialize_chroma_collection(args.chroma_dir, args.chroma_collection)

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

                    ids = save_defect_batch(
                        defect_data_list,
                        team=team,
                        year_str=year_str,
                        team_slug=team_slug,
                        defect_dir=defect_dir,
                        save_csv=args.save_csv,
                        save_excel=args.save_excel,
                        save_files=save_files,
                        store=store,
                        fetched_at=run_fetched_at,
                    )
                    downloaded_defects = True
                    per_team_defect_ids[team].update(ids)
                    defect_ids_union.update(ids)

                    if chroma_collection is not None:
                        upsert_defects_to_chroma(
                            chroma_collection,
                            defect_data_list,
                            team=team,
                            team_slug=team_slug,
                            year_str=year_str,
                            fetched_at=run_fetched_at,
                        )

            if save_files:
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

        if not args.skip_history:
            current_year = datetime.now().year
            default_start_date = f"{current_year-1}-01-01"
            default_end_date = datetime.now().strftime("%Y-%m-%d")
            hist_start_date = args.history_start_date or default_start_date
            hist_end_date = args.history_end_date or default_end_date
            hist_max_workers_val = min(max(1, args.history_max_workers), 50)

            for team in teams:
                team_defect_ids = per_team_defect_ids.get(team) or set()
                if team_defect_ids:
                    continue

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
                per_team_defect_ids[team] = {
                    str(item.get("id"))
                    for item in (resp_data or [])
                    if item.get("id") is not None
                }

            for team in teams:
                team_defect_ids = per_team_defect_ids.get(team) or set()
                if not team_defect_ids:
                    continue
                save_qgate_histories(
                    defect_ids=team_defect_ids,
                    session=session_active,
                    max_workers=hist_max_workers_val,
                    history_dir=history_dir,
                    team=team,
                    store=store,
                    save_files=save_files,
                    save_csv=args.save_csv,
                )
                downloaded_histories = True
    finally:
        if store is not None:
            store.close()

    should_post_process_sync = (
        args.save_db
        and (not args.no_post_process_sync)
        and downloaded_defects
    )
    if should_post_process_sync:
        run_post_download_qgate_sync(args.qgate_db_path)

    should_post_history_event_sync = (
        args.save_db
        and (not args.no_post_process_sync)
        and (not args.skip_history)
        and args.defer_history_events
        and downloaded_histories
    )
    if should_post_history_event_sync:
        run_post_download_qgate_history_event_sync(args.qgate_db_path)


if __name__ == "__main__":
    main()
