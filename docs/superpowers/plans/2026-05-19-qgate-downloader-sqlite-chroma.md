# QGate Downloader SQLite + Chroma Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `downloaderqgate.py` so QGate downloads can dual-write to `qgate/qgate_data.db` and optionally index defect text into `qgate/chroma` while preserving current file outputs.

**Architecture:** Keep SQLite as the source of truth for structured defect and history payloads, and add Chroma as an optional semantic sidecar for defect text retrieval. Refactor `downloaderqgate.py` into small helper functions so CLI validation, defect persistence, history routing, and Chroma indexing can be tested without Octane network access.

**Tech Stack:** Python, unittest, unittest.mock, SQLite via `OctaneSQLiteStore`, ChromaDB persistent client, existing `download/octane_downloader.py` helpers.

---

### Task 1: Add CLI Storage Flags And Validation

**Files:**
- Create: `tests/test_downloaderqgate_storage.py`
- Modify: `downloaderqgate.py`
- Test: `tests/test_downloaderqgate_storage.py`

- [ ] **Step 1: Write the failing CLI parsing tests**

```python
import unittest

import downloaderqgate as dq


class TestDownloaderQgateStorage(unittest.TestCase):
    def test_parse_args_accepts_db_and_chroma_flags(self):
        args = dq.parse_args([
            "--save-db",
            "--save-chroma",
            "--skip-file-output",
        ])

        self.assertTrue(args.save_db)
        self.assertTrue(args.save_chroma)
        self.assertTrue(args.skip_file_output)
        self.assertEqual(args.qgate_db_path, "qgate/qgate_data.db")
        self.assertEqual(args.chroma_dir, "qgate/chroma")
        self.assertEqual(args.chroma_collection, "qgate_defect_cases")

    def test_validate_storage_args_rejects_chroma_without_db(self):
        args = dq.parse_args(["--save-chroma"])

        with self.assertRaises(SystemExit):
            dq.validate_storage_args(args)
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: FAIL because `parse_args()` does not accept an argv list and `validate_storage_args()` does not exist.

- [ ] **Step 3: Implement CLI parsing and validation helpers**

```python
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


def validate_storage_args(args):
    if args.save_chroma and not args.save_db:
        raise SystemExit("--save-chroma requires --save-db")
    return args
```

- [ ] **Step 4: Update `main()` to use the new parser contract**

```python
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
```

- [ ] **Step 5: Run the CLI test again to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: PASS for the two new CLI tests.

- [ ] **Step 6: Commit the CLI parsing slice**

```bash
git add tests/test_downloaderqgate_storage.py downloaderqgate.py
git commit -m "feat: add qgate storage CLI flags"
```

### Task 2: Add SQLite Routing Helpers For Defects And Histories

**Files:**
- Modify: `downloaderqgate.py`
- Modify: `tests/test_downloaderqgate_storage.py`
- Test: `tests/test_downloaderqgate_storage.py`

- [ ] **Step 1: Write failing SQLite routing tests**

```python
from unittest import mock


class TestDownloaderQgateStorage(unittest.TestCase):
    def test_save_defect_batch_writes_file_and_sqlite(self):
        store = mock.Mock()
        defects = [{"id": 101, "name": "Ticket A"}]

        with mock.patch.object(dq.d6, "save_data") as save_data:
            ids = dq.save_defect_batch(
                defect_data_list=defects,
                year_str="2026",
                team="DTSV_China",
                team_slug="DTSV_China",
                defect_dir="qgate/defect",
                save_files=True,
                save_csv=False,
                save_excel=False,
                store=store,
            )

        self.assertEqual(ids, {"101"})
        save_data.assert_called_once()
        store.upsert_payload.assert_called_once()

    def test_save_qgate_histories_uses_db_helper_when_store_present(self):
        store = mock.Mock()
        session = object()

        with mock.patch.object(dq.d6, "fetch_defect_histories_parallel") as fetch_plain, \
             mock.patch.object(dq.d6, "fetch_defect_histories_parallel_to_db") as fetch_db:
            dq.save_qgate_histories(
                defect_ids={"101", "102"},
                session=session,
                max_workers=4,
                history_dir="qgate/history",
                save_files=False,
                store=store,
                team_name="DTSV_China",
            )

        fetch_plain.assert_not_called()
        fetch_db.assert_called_once_with(
            ["101", "102"],
            session,
            4,
            store,
            "DTSV_China",
            save_files_dir=None,
        )
```

- [ ] **Step 2: Run the SQLite routing tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: FAIL because `save_defect_batch()` and `save_qgate_histories()` do not exist.

- [ ] **Step 3: Implement the SQLite helper functions**

```python
def save_defect_batch(
    *,
    defect_data_list,
    year_str,
    team,
    team_slug,
    defect_dir,
    save_files,
    save_csv,
    save_excel,
    store=None,
):
    if save_files:
        fn_defect = f"{year_str}_{team_slug}_defect"
        d6.save_data(defect_data_list, fn_defect, defect_dir, save_csv, save_excel)
    if store is not None:
        store.upsert_payload(
            kind="defects",
            team=team,
            year=int(year_str),
            spec=team_slug,
            payload={"data": defect_data_list},
        )
    return {str(item.get("id")) for item in defect_data_list if item.get("id") is not None}


def save_qgate_histories(*, defect_ids, session, max_workers, history_dir, save_files, store=None, team_name=None):
    sorted_ids = sorted(str(defect_id) for defect_id in defect_ids)
    if not sorted_ids:
        return
    if store is not None:
        d6.fetch_defect_histories_parallel_to_db(
            sorted_ids,
            session,
            max_workers,
            store,
            team_name,
            save_files_dir=history_dir if save_files else None,
        )
        return
    d6.fetch_defect_histories_parallel(sorted_ids, session, max_workers, history_dir)
```

- [ ] **Step 4: Implement SQLite store initialization helpers**

```python
from octane_db import OctaneSQLiteStore


def initialize_qgate_store(db_path):
    store = OctaneSQLiteStore(db_path)
    store.create_tables()
    return store
```

- [ ] **Step 5: Run the SQLite routing tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: PASS for CLI tests plus the two new SQLite routing tests.

- [ ] **Step 6: Commit the SQLite routing slice**

```bash
git add tests/test_downloaderqgate_storage.py downloaderqgate.py
git commit -m "feat: add qgate sqlite persistence routing"
```

### Task 3: Add Chroma Defect Document Indexing

**Files:**
- Modify: `downloaderqgate.py`
- Modify: `tests/test_downloaderqgate_storage.py`
- Test: `tests/test_downloaderqgate_storage.py`

- [ ] **Step 1: Write failing Chroma document tests**

```python
class TestDownloaderQgateStorage(unittest.TestCase):
    def test_build_chroma_documents_creates_text_and_metadata(self):
        records = dq.build_chroma_documents(
            defect_data_list=[{
                "id": 101,
                "name": "Audio crash",
                "description": "Player exits during startup",
                "detected_in_release": {"name": "25-11"},
            }],
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T12:00:00Z",
        )

        self.assertEqual(records["ids"], ["101"])
        self.assertIn("Audio crash", records["documents"][0])
        self.assertEqual(records["metadatas"][0]["team"], "DTSV_China")
        self.assertEqual(records["metadatas"][0]["year"], 2026)
        self.assertEqual(records["metadatas"][0]["has_history"], False)

    def test_upsert_defects_to_chroma_uses_collection_upsert(self):
        collection = mock.Mock()
        defects = [{"id": 101, "name": "Audio crash", "description": "Player exits during startup"}]

        dq.upsert_defects_to_chroma(
            collection=collection,
            defect_data_list=defects,
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T12:00:00Z",
        )

        collection.upsert.assert_called_once()
```

- [ ] **Step 2: Run the Chroma tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: FAIL because `build_chroma_documents()` and `upsert_defects_to_chroma()` do not exist.

- [ ] **Step 3: Implement Chroma initialization and document builders**

```python
try:
    import chromadb
except Exception:
    chromadb = None


def initialize_chroma_collection(chroma_dir, collection_name):
    if chromadb is None:
        raise SystemExit("chromadb is required when --save-chroma is enabled")
    os.makedirs(chroma_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_dir)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _normalize_defect_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("full_name") or value.get("value") or ""
    return str(value).strip()


def build_chroma_documents(*, defect_data_list, team, team_slug, year_str, fetched_at):
    ids = []
    documents = []
    metadatas = []
    year_val = int(year_str)
    for item in defect_data_list:
        defect_id = str(item.get("id") or "").strip()
        if not defect_id:
            continue
        name = _normalize_defect_text(item.get("name"))
        description = _normalize_defect_text(item.get("description"))
        release = _normalize_defect_text(item.get("detected_in_release"))
        document = "\n".join([
            f"team: {team}",
            f"year: {year_val}",
            f"title: {name}",
            f"release: {release}",
            f"description: {description}",
        ]).strip()
        ids.append(defect_id)
        documents.append(document)
        metadatas.append({
            "team": team,
            "team_slug": team_slug,
            "year": year_val,
            "defect_id": defect_id,
            "fetched_at": fetched_at,
            "has_history": False,
        })
    return {"ids": ids, "documents": documents, "metadatas": metadatas}


def upsert_defects_to_chroma(*, collection, defect_data_list, team, team_slug, year_str, fetched_at):
    records = build_chroma_documents(
        defect_data_list=defect_data_list,
        team=team,
        team_slug=team_slug,
        year_str=year_str,
        fetched_at=fetched_at,
    )
    if not records["ids"]:
        return
    collection.upsert(
        ids=records["ids"],
        documents=records["documents"],
        metadatas=records["metadatas"],
    )
```

- [ ] **Step 4: Run the Chroma tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: PASS for CLI, SQLite, and Chroma helper tests.

- [ ] **Step 5: Commit the Chroma indexing slice**

```bash
git add tests/test_downloaderqgate_storage.py downloaderqgate.py
git commit -m "feat: add qgate chroma defect indexing"
```

### Task 4: Wire The Main Flow And Validate End-To-End Routing

**Files:**
- Modify: `downloaderqgate.py`
- Modify: `tests/test_downloaderqgate_storage.py`
- Test: `tests/test_downloaderqgate_storage.py`

- [ ] **Step 1: Write a failing main-flow routing test**

```python
class TestDownloaderQgateStorage(unittest.TestCase):
    @mock.patch.object(dq, "save_qgate_histories")
    @mock.patch.object(dq, "save_defect_batch", return_value={"101"})
    @mock.patch.object(dq, "initialize_chroma_collection", return_value=mock.Mock())
    @mock.patch.object(dq, "initialize_qgate_store", return_value=mock.Mock())
    @mock.patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1"})
    @mock.patch.object(dq.d6, "fetch_octane_data_parallel", return_value=[{"id": 101, "name": "Ticket A"}])
    @mock.patch.object(dq.d6, "get_authenticated_session", return_value=object())
    def test_main_wires_store_and_chroma_helpers(
        self,
        _session,
        _fetch_parallel,
        _team_map,
        init_store,
        init_chroma,
        save_defect_batch,
        save_histories,
    ):
        dq.main([
            "--teams", "DTSV_China",
            "--defect-years", "2026",
            "--save-db",
            "--save-chroma",
            "--skip-history",
        ])

        init_store.assert_called_once()
        init_chroma.assert_called_once()
        save_defect_batch.assert_called_once()
        save_histories.assert_not_called()
```

- [ ] **Step 2: Run the routing test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_storage.py -q`

Expected: FAIL because `main()` still writes directly instead of using the new helpers.

- [ ] **Step 3: Refactor `main()` to use the new helper pipeline**

```python
from collections import defaultdict


def main(argv=None):
    cli_args = list(argv) if argv is not None else sys.argv[1:]
    args = validate_storage_args(apply_year_override(parse_args(cli_args), cli_args))

    auth_method_selected = args.auth_method or "cookie"
    session_active = d6.get_authenticated_session(
        auth_method_selected,
        sso_login_file=args.login_file if auth_method_selected == "sso" else None,
        cookie_file_path=args.cookie_file if auth_method_selected != "sso" else None,
    )
    if not session_active:
        raise SystemExit(2)

    script_dir_path = os.path.dirname(os.path.abspath(__file__))
    output_root_dir = os.path.join(script_dir_path, args.output_root)
    defect_dir = os.path.join(output_root_dir, "defect")
    history_dir = os.path.join(output_root_dir, "history")
    os.makedirs(output_root_dir, exist_ok=True)
    if not args.skip_file_output:
        os.makedirs(defect_dir, exist_ok=True)
        os.makedirs(history_dir, exist_ok=True)

    store = initialize_qgate_store(os.path.join(script_dir_path, args.qgate_db_path)) if args.save_db else None
    chroma_collection = initialize_chroma_collection(
        os.path.join(script_dir_path, args.chroma_dir),
        args.chroma_collection,
    ) if args.save_chroma else None
    defect_ids_by_team = defaultdict(set)
    save_files = not args.skip_file_output
    run_fetched_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    try:
        for team in teams:
            team_slug = slugify_team_name(team)
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
                    defect_data_list=defect_data_list,
                    year_str=year_str,
                    team=team,
                    team_slug=team_slug,
                    defect_dir=defect_dir,
                    save_files=save_files,
                    save_csv=args.save_csv,
                    save_excel=args.save_excel,
                    store=store,
                )
                defect_ids_by_team[team].update(ids)
                if chroma_collection is not None:
                    upsert_defects_to_chroma(
                        collection=chroma_collection,
                        defect_data_list=defect_data_list,
                        team=team,
                        team_slug=team_slug,
                        year_str=year_str,
                        fetched_at=run_fetched_at,
                    )
    finally:
        if store is not None:
            store.close()
```

- [ ] **Step 4: Add the per-team history download loop inside `main()`**

```python
if not args.skip_history:
    if not any(defect_ids_by_team.values()):
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
            defect_ids_by_team[team].update(
                {
                    str(item.get("id"))
                    for item in (resp_data or [])
                    if item.get("id") is not None
                }
            )

    for team, defect_ids in defect_ids_by_team.items():
        if not defect_ids:
            continue
        save_qgate_histories(
            defect_ids=defect_ids,
            session=session_active,
            max_workers=hist_max_workers_val,
            history_dir=history_dir,
            save_files=save_files,
            store=store,
            team_name=team,
        )
```

- [ ] **Step 5: Run focused validation for the whole slice**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_downloaderqgate_year.py tests/test_downloaderqgate_storage.py -q`

Expected: PASS for the existing year override tests and the new storage-routing tests.

- [ ] **Step 6: Run a narrow syntax validation**

Run: `./.venv/Scripts/python.exe -m py_compile downloaderqgate.py`

Expected: no output, exit code 0.

- [ ] **Step 7: Commit the wired implementation**

```bash
git add tests/test_downloaderqgate_year.py tests/test_downloaderqgate_storage.py downloaderqgate.py
git commit -m "feat: add qgate sqlite and chroma persistence"
```