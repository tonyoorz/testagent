import unittest
from unittest.mock import MagicMock, patch

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
        self.assertTrue(args.defer_history_events)
        self.assertEqual(args.qgate_db_path, "qgate/qgate_data.db")
        self.assertEqual(args.chroma_dir, "qgate/chroma")
        self.assertEqual(args.chroma_collection, "qgate_defect_cases")
        self.assertFalse(args.no_post_process_sync)

    def test_run_post_download_qgate_sync_calls_data_processor_for_defects_only(self):
        with patch.object(dq.os.path, "exists", return_value=True), \
             patch.object(dq.data_processor, "sync_processed_fields_to_db", return_value={"defect_updates": 12}) as sync_mock:
            ok = dq.run_post_download_qgate_sync("qgate/qgate_data.db")

        self.assertTrue(ok)
        sync_mock.assert_called_once_with(
            db_path="qgate/qgate_data.db",
            sync_manual_runs=False,
        )

    def test_run_post_download_qgate_history_event_sync_calls_backfill(self):
        with patch.object(dq.os.path, "exists", return_value=True), \
             patch.object(dq.backfill_qgate_history_events, "backfill_qgate_history_events", return_value={"events_upserted": 34}) as backfill_mock:
            ok = dq.run_post_download_qgate_history_event_sync("qgate/qgate_data.db")

        self.assertTrue(ok)
        backfill_mock.assert_called_once_with("qgate/qgate_data.db")

    def test_parse_args_can_enable_online_history_event_sync(self):
        args = dq.parse_args(["--sync-history-events"])

        self.assertFalse(args.defer_history_events)

    def test_validate_storage_args_rejects_chroma_without_db(self):
        args = dq.parse_args(["--save-chroma"])

        with self.assertRaises(SystemExit):
            dq.validate_storage_args(args)

    def test_validate_storage_args_rejects_skip_file_output_without_db(self):
        args = dq.parse_args(["--skip-file-output"])

        with self.assertRaises(SystemExit):
            dq.validate_storage_args(args)

    def test_save_defect_batch_writes_optional_file_and_store_and_returns_ids(self):
        store = MagicMock()
        defect_rows = [
            {"id": 101, "name": "A"},
            {"id": "202", "name": "B"},
            {"name": "missing-id"},
        ]

        with patch.object(dq.d6, "save_data") as save_data:
            result = dq.save_defect_batch(
                defect_rows,
                team="DTSV_China",
                year_str="2026",
                team_slug="DTSV_China",
                defect_dir="qgate/defect",
                save_csv=True,
                save_excel=False,
                save_files=True,
                store=store,
            )

        self.assertEqual(result, {"101", "202"})
        save_data.assert_called_once_with(
            defect_rows,
            "2026_DTSV_China_defect",
            "qgate/defect",
            True,
            False,
        )
        store.upsert_payload.assert_called_once_with(
            kind="defects",
            team="DTSV_China",
            year=2026,
            spec="DTSV_China",
            payload={"data": defect_rows},
        )

    def test_save_defect_batch_persists_to_store_without_writing_files(self):
        store = MagicMock()
        defect_rows = [{"id": 101, "name": "A"}]

        with patch.object(dq.d6, "save_data") as save_data:
            result = dq.save_defect_batch(
                defect_rows,
                team="DTSV_China",
                year_str="2026",
                team_slug="DTSV_China",
                defect_dir="qgate/defect",
                save_csv=True,
                save_excel=False,
                save_files=False,
                store=store,
            )

        self.assertEqual(result, {"101"})
        save_data.assert_not_called()
        store.upsert_payload.assert_called_once_with(
            kind="defects",
            team="DTSV_China",
            year=2026,
            spec="DTSV_China",
            payload={"data": defect_rows},
        )

    def test_save_qgate_histories_routes_to_db_helper_and_skips_file_dir_when_disabled(self):
        store = MagicMock()

        with patch.object(dq.d6, "fetch_defect_histories_parallel_to_db", return_value=(["101"], [])) as to_db, \
             patch.object(dq.d6, "fetch_defect_histories_parallel") as to_files:
            result = dq.save_qgate_histories(
                defect_ids=["101"],
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=store,
                save_files=False,
                save_csv=False,
            )

        self.assertEqual(result, (["101"], []))
        to_db.assert_called_once_with(
            ["101"],
            unittest.mock.ANY,
            8,
            store,
            "DTSV_China",
            save_files_dir=None,
            save_csv_hist=False,
        )
        to_files.assert_not_called()

    def test_save_qgate_histories_routes_to_db_helper_with_file_dir_when_enabled(self):
        store = MagicMock()

        with patch.object(dq.d6, "fetch_defect_histories_parallel_to_db", return_value=(["101"], [])) as to_db, \
             patch.object(dq.d6, "fetch_defect_histories_parallel") as to_files:
            result = dq.save_qgate_histories(
                defect_ids=["101"],
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=store,
                save_files=True,
                save_csv=False,
            )

        self.assertEqual(result, (["101"], []))
        to_db.assert_called_once_with(
            ["101"],
            unittest.mock.ANY,
            8,
            store,
            "DTSV_China",
            save_files_dir="qgate/history",
            save_csv_hist=False,
        )
        to_files.assert_not_called()

    def test_save_qgate_histories_normalizes_ids_to_sorted_strings_before_db_helper(self):
        store = MagicMock()

        with patch.object(dq.d6, "fetch_defect_histories_parallel_to_db", return_value=([], [])) as to_db, \
             patch.object(dq.d6, "fetch_defect_histories_parallel") as to_files:
            dq.save_qgate_histories(
                defect_ids={20, "3", 11},
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=store,
                save_files=True,
                save_csv=False,
            )

        to_db.assert_called_once_with(
            ["11", "20", "3"],
            unittest.mock.ANY,
            8,
            store,
            "DTSV_China",
            save_files_dir="qgate/history",
            save_csv_hist=False,
        )
        to_files.assert_not_called()

    def test_save_qgate_histories_routes_to_file_helper_without_store(self):
        with patch.object(dq.d6, "fetch_defect_histories_parallel", return_value=(["101"], [])) as to_files, \
             patch.object(dq.d6, "fetch_defect_histories_parallel_to_db") as to_db:
            result = dq.save_qgate_histories(
                defect_ids=["101"],
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=None,
                save_files=True,
                save_csv=True,
            )

        self.assertEqual(result, (["101"], []))
        to_files.assert_called_once_with(
            ["101"],
            unittest.mock.ANY,
            8,
            "qgate/history",
            True,
        )
        to_db.assert_not_called()

    def test_save_qgate_histories_routes_to_file_helper_without_store_even_when_files_disabled(self):
        with patch.object(dq.d6, "fetch_defect_histories_parallel", return_value=(["101"], [])) as to_files, \
             patch.object(dq.d6, "fetch_defect_histories_parallel_to_db") as to_db:
            result = dq.save_qgate_histories(
                defect_ids=["101"],
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=None,
                save_files=False,
                save_csv=True,
            )

        self.assertEqual(result, (["101"], []))
        to_files.assert_called_once_with(
            ["101"],
            unittest.mock.ANY,
            8,
            "qgate/history",
            True,
        )
        to_db.assert_not_called()

    def test_save_qgate_histories_short_circuits_empty_ids_before_downstream_calls(self):
        with patch.object(dq.d6, "fetch_defect_histories_parallel") as to_files, \
             patch.object(dq.d6, "fetch_defect_histories_parallel_to_db") as to_db:
            result = dq.save_qgate_histories(
                defect_ids=set(),
                session=object(),
                max_workers=8,
                history_dir="qgate/history",
                team="DTSV_China",
                store=MagicMock(),
                save_files=True,
                save_csv=True,
            )

        self.assertEqual(result, ([], []))
        to_files.assert_not_called()
        to_db.assert_not_called()

    def test_initialize_qgate_store_creates_tables(self):
        with patch("downloaderqgate.OctaneSQLiteStore") as store_cls:
            store = dq.initialize_qgate_store("qgate/qgate_data.db")

        store_cls.assert_called_once_with("qgate/qgate_data.db", sync_history_events=False)
        store_cls.return_value.create_tables.assert_called_once_with()
        store_cls.return_value.create_optimized_tables.assert_called_once_with()
        self.assertIs(store, store_cls.return_value)

    def test_initialize_qgate_store_can_enable_online_history_event_sync(self):
        with patch("downloaderqgate.OctaneSQLiteStore") as store_cls:
            store = dq.initialize_qgate_store("qgate/qgate_data.db", defer_history_events=False)

        store_cls.assert_called_once_with("qgate/qgate_data.db", sync_history_events=True)
        store_cls.return_value.create_tables.assert_called_once_with()
        store_cls.return_value.create_optimized_tables.assert_called_once_with()
        self.assertIs(store, store_cls.return_value)

    def test_save_defect_batch_dual_writes_payload_and_optimized_defects(self):
        store = MagicMock()
        defect_rows = [{"id": 101, "name": "A"}]

        with patch.object(dq.d6, "save_data") as save_data:
            result = dq.save_defect_batch(
                defect_rows,
                team="DTSV_China",
                year_str="2026",
                team_slug="DTSV_China",
                defect_dir="qgate/defect",
                save_csv=False,
                save_excel=False,
                save_files=False,
                store=store,
                fetched_at="2026-05-19T10:00:00Z",
            )

        self.assertEqual(result, {"101"})
        save_data.assert_not_called()
        store.upsert_payload.assert_called_once_with(
            kind="defects",
            team="DTSV_China",
            year=2026,
            spec="DTSV_China",
            payload={"data": defect_rows},
            fetched_at="2026-05-19T10:00:00Z",
        )
        store.upsert_defects_batch.assert_called_once_with(
            defect_rows,
            year=2026,
            fetched_at="2026-05-19T10:00:00Z",
        )

    def test_initialize_chroma_collection_creates_persistent_cosine_collection(self):
        client = MagicMock()
        chromadb_module = MagicMock()
        chromadb_module.PersistentClient.return_value = client

        with patch.object(dq, "chromadb", chromadb_module):
            collection = dq.initialize_chroma_collection("qgate/chroma", "qgate_defect_cases")

        chromadb_module.PersistentClient.assert_called_once_with(path="qgate/chroma")
        client.get_or_create_collection.assert_called_once_with(
            name="qgate_defect_cases",
            metadata={"hnsw:space": "cosine"},
        )
        self.assertIs(collection, client.get_or_create_collection.return_value)

    def test_initialize_chroma_collection_exits_when_chromadb_is_unavailable(self):
        with patch.object(dq, "chromadb", None):
            with self.assertRaises(SystemExit):
                dq.initialize_chroma_collection("qgate/chroma", "qgate_defect_cases")

    def test_normalize_defect_text_returns_clean_string(self):
        self.assertEqual(dq.normalize_defect_text(None), "")
        self.assertEqual(dq.normalize_defect_text("  Alpha\n\tBeta   "), "Alpha Beta")
        self.assertEqual(dq.normalize_defect_text(123), "123")
        self.assertEqual(dq.normalize_defect_text(float("nan")), "")

    def test_build_chroma_documents_returns_ids_documents_and_metadatas(self):
        defect_rows = [
            {
                "id": 101,
                "name": " Brake issue ",
                "description": "  pedal vibration\nunder load ",
                "phase": "Open",
                "severity": "High",
                "owner": "Alice",
                "release_vehicle": "G60",
            },
            {
                "id": "202",
                "name": "Missing description",
                "description": None,
            },
        ]

        ids, documents, metadatas = dq.build_chroma_documents(
            defect_rows,
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T10:00:00Z",
        )

        self.assertEqual(ids, ["DTSV_China:2026:101", "DTSV_China:2026:202"])
        self.assertEqual(
            documents,
            [
                "Defect 101\nTeam: DTSV_China\nYear: 2026\nName: Brake issue\nDescription: pedal vibration under load\nPhase: Open\nSeverity: High\nOwner: Alice\nRelease Vehicle: G60",
                "Defect 202\nTeam: DTSV_China\nYear: 2026\nName: Missing description",
            ],
        )
        self.assertEqual(
            metadatas,
            [
                {
                    "defect_id": "101",
                    "team": "DTSV_China",
                    "team_slug": "DTSV_China",
                    "year": 2026,
                    "fetched_at": "2026-05-19T10:00:00Z",
                    "name": "Brake issue",
                    "phase": "Open",
                    "severity": "High",
                    "owner": "Alice",
                    "release_vehicle": "G60",
                },
                {
                    "defect_id": "202",
                    "team": "DTSV_China",
                    "team_slug": "DTSV_China",
                    "year": 2026,
                    "fetched_at": "2026-05-19T10:00:00Z",
                    "name": "Missing description",
                },
            ],
        )

    def test_build_chroma_documents_skips_rows_without_ids(self):
        ids, documents, metadatas = dq.build_chroma_documents(
            [{"name": "missing id"}, {"id": 7, "name": "kept"}],
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T10:00:00Z",
        )

        self.assertEqual(ids, ["DTSV_China:2026:7"])
        self.assertEqual(documents, ["Defect 7\nTeam: DTSV_China\nYear: 2026\nName: kept"])
        self.assertEqual(
            metadatas,
            [
                {
                    "defect_id": "7",
                    "team": "DTSV_China",
                    "team_slug": "DTSV_China",
                    "year": 2026,
                    "fetched_at": "2026-05-19T10:00:00Z",
                    "name": "kept",
                }
            ],
        )

    def test_upsert_defects_to_chroma_builds_documents_and_calls_upsert(self):
        collection = MagicMock()
        defect_rows = [{"id": 101, "name": "Brake issue"}]

        result = dq.upsert_defects_to_chroma(
            collection,
            defect_rows,
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T10:00:00Z",
        )

        collection.upsert.assert_called_once_with(
            ids=["DTSV_China:2026:101"],
            documents=["Defect 101\nTeam: DTSV_China\nYear: 2026\nName: Brake issue"],
            metadatas=[
                {
                    "defect_id": "101",
                    "team": "DTSV_China",
                    "team_slug": "DTSV_China",
                    "year": 2026,
                    "fetched_at": "2026-05-19T10:00:00Z",
                    "name": "Brake issue",
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "ids": ["DTSV_China:2026:101"],
                "documents": ["Defect 101\nTeam: DTSV_China\nYear: 2026\nName: Brake issue"],
                "metadatas": [
                    {
                        "defect_id": "101",
                        "team": "DTSV_China",
                        "team_slug": "DTSV_China",
                        "year": 2026,
                        "fetched_at": "2026-05-19T10:00:00Z",
                        "name": "Brake issue",
                    }
                ],
            },
        )

    def test_upsert_defects_to_chroma_skips_upsert_when_no_documents_exist(self):
        collection = MagicMock()

        result = dq.upsert_defects_to_chroma(
            collection,
            [{"name": "missing id"}],
            team="DTSV_China",
            team_slug="DTSV_China",
            year_str="2026",
            fetched_at="2026-05-19T10:00:00Z",
        )

        collection.upsert.assert_not_called()
        self.assertEqual(result, {"ids": [], "documents": [], "metadatas": []})

    def test_main_routes_defect_batches_through_store_and_chroma_helpers(self):
        session = object()
        store = MagicMock()
        collection = MagicMock()
        defect_rows_2025 = [{"id": 101, "name": "Ticket A"}]
        defect_rows_2026 = [{"id": 202, "name": "Ticket B"}]
        defect_dir = dq.os.path.join(dq.os.path.dirname(dq.os.path.abspath(dq.__file__)), "qgate", "defect")
        history_dir = dq.os.path.join(dq.os.path.dirname(dq.os.path.abspath(dq.__file__)), "qgate", "history")

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store) as init_store, \
             patch.object(dq, "initialize_chroma_collection", return_value=collection) as init_chroma, \
               patch.object(dq, "run_post_download_qgate_sync", return_value=True) as post_sync, \
             patch.object(dq.d6, "fetch_octane_data_parallel", side_effect=[defect_rows_2025, defect_rows_2026]), \
             patch.object(dq, "save_defect_batch", side_effect=[{"101"}, {"202"}]) as save_batch, \
             patch.object(dq, "upsert_defects_to_chroma") as upsert_chroma, \
             patch.object(dq, "save_qgate_histories") as save_histories, \
             patch.object(dq.os, "makedirs") as makedirs, \
             patch("builtins.open", unittest.mock.mock_open()) as open_mock:
            dq.main([
                "--teams", "DTSV_China",
                "--defect-years", "2025,2026",
                "--save-db",
                "--qgate-db-path", "qgate/qgate_data.db",
                "--save-chroma",
                "--chroma-dir", "qgate/chroma",
                "--chroma-collection", "qgate_defect_cases",
                "--skip-file-output",
                "--skip-history",
            ])

        init_store.assert_called_once_with("qgate/qgate_data.db", defer_history_events=True)
        init_chroma.assert_called_once_with("qgate/chroma", "qgate_defect_cases")
        self.assertEqual(save_batch.call_count, 2)
        self.assertEqual(
            save_batch.call_args_list,
            [
                unittest.mock.call(
                    defect_rows_2025,
                    team="DTSV_China",
                    year_str="2025",
                    team_slug="DTSV_China",
                    defect_dir=defect_dir,
                    save_csv=False,
                    save_excel=False,
                    save_files=False,
                    store=store,
                    fetched_at=unittest.mock.ANY,
                ),
                unittest.mock.call(
                    defect_rows_2026,
                    team="DTSV_China",
                    year_str="2026",
                    team_slug="DTSV_China",
                    defect_dir=defect_dir,
                    save_csv=False,
                    save_excel=False,
                    save_files=False,
                    store=store,
                    fetched_at=unittest.mock.ANY,
                ),
            ],
        )
        self.assertEqual(upsert_chroma.call_count, 2)
        self.assertEqual(upsert_chroma.call_args_list[0].kwargs["fetched_at"], upsert_chroma.call_args_list[1].kwargs["fetched_at"])
        self.assertEqual(upsert_chroma.call_args_list[0].kwargs["team"], "DTSV_China")
        self.assertEqual(upsert_chroma.call_args_list[1].kwargs["team"], "DTSV_China")
        self.assertEqual(upsert_chroma.call_args_list[0].kwargs["year_str"], "2025")
        self.assertEqual(upsert_chroma.call_args_list[1].kwargs["year_str"], "2026")
        self.assertNotIn(unittest.mock.call(defect_dir, exist_ok=True), makedirs.call_args_list)
        self.assertNotIn(unittest.mock.call(history_dir, exist_ok=True), makedirs.call_args_list)
        open_mock.assert_not_called()
        save_histories.assert_not_called()
        store.close.assert_called_once_with()
        post_sync.assert_called_once_with("qgate/qgate_data.db")

    def test_main_runs_post_sync_even_when_history_is_skipped(self):
        session = object()
        store = MagicMock()

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store), \
             patch.object(dq.d6, "fetch_octane_data_parallel", return_value=[{"id": 101, "name": "Ticket A"}]), \
             patch.object(dq, "save_defect_batch", return_value={"101"}), \
             patch.object(dq, "run_post_download_qgate_sync", return_value=True) as post_sync, \
             patch.object(dq, "save_qgate_histories") as save_histories:
            dq.main([
                "--teams", "DTSV_China",
                "--defect-years", "2026",
                "--save-db",
                "--skip-file-output",
                "--skip-history",
            ])

        save_histories.assert_not_called()
        store.close.assert_called_once_with()
        post_sync.assert_called_once_with("qgate/qgate_data.db")

    def test_main_runs_history_event_backfill_after_deferred_history_download(self):
        session = object()
        store = MagicMock()
        history_dir = dq.os.path.join(dq.os.path.dirname(dq.os.path.abspath(dq.__file__)), "qgate", "history")

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store), \
             patch.object(dq.d6, "fetch_octane_data_parallel", return_value=[{"id": 101, "name": "Ticket A"}]), \
             patch.object(dq, "save_defect_batch", return_value={"101"}), \
             patch.object(dq, "save_qgate_histories", return_value=(['101'], [])) as save_histories, \
             patch.object(dq, "run_post_download_qgate_sync", return_value=True) as post_sync, \
             patch.object(dq, "run_post_download_qgate_history_event_sync", return_value=True) as post_history_sync:
            dq.main([
                "--teams", "DTSV_China",
                "--defect-years", "2026",
                "--save-db",
                "--skip-file-output",
            ])

        save_histories.assert_called_once_with(
            defect_ids={"101"},
            session=session,
            max_workers=50,
            history_dir=history_dir,
            team="DTSV_China",
            store=store,
            save_files=False,
            save_csv=False,
        )
        store.close.assert_called_once_with()
        post_sync.assert_called_once_with("qgate/qgate_data.db")
        post_history_sync.assert_called_once_with("qgate/qgate_data.db")

    def test_main_skips_history_event_backfill_when_online_history_sync_is_enabled(self):
        session = object()
        store = MagicMock()

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store), \
             patch.object(dq.d6, "fetch_octane_data_parallel", return_value=[{"id": 101, "name": "Ticket A"}]), \
             patch.object(dq, "save_defect_batch", return_value={"101"}), \
             patch.object(dq, "save_qgate_histories", return_value=(['101'], [])), \
             patch.object(dq, "run_post_download_qgate_sync", return_value=True) as post_sync, \
             patch.object(dq, "run_post_download_qgate_history_event_sync", return_value=True) as post_history_sync:
            dq.main([
                "--teams", "DTSV_China",
                "--defect-years", "2026",
                "--save-db",
                "--skip-file-output",
                "--sync-history-events",
            ])

        store.close.assert_called_once_with()
        post_sync.assert_called_once_with("qgate/qgate_data.db")
        post_history_sync.assert_not_called()

    def test_main_preserves_team_specific_history_routing_when_fallback_query_is_used(self):
        session = object()
        store = MagicMock()
        history_dir = dq.os.path.join(dq.os.path.dirname(dq.os.path.abspath(dq.__file__)), "qgate", "history")

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1", "Spotlight_FIT": "team-2"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store), \
             patch.object(dq.d6, "fetch_octane_data_parallel", side_effect=[[], []]), \
             patch.object(dq, "build_defect_ids_query", side_effect=["query-team-1", "query-team-2"]) as build_query, \
             patch.object(dq.d6, "fetch_octane_data", side_effect=[[{"id": "101"}, {"id": 102}], [{"id": "201"}]]) as fetch_ids, \
             patch.object(dq, "save_defect_batch") as save_batch, \
             patch.object(dq, "save_qgate_histories") as save_histories, \
             patch("builtins.open", unittest.mock.mock_open()):
            dq.main([
                "--teams", "DTSV_China,Spotlight_FIT",
                "--defect-years", "2026",
                "--save-db",
                "--skip-file-output",
            ])

        save_batch.assert_not_called()
        self.assertEqual(
            build_query.call_args_list,
            [
                unittest.mock.call("team-1", unittest.mock.ANY, unittest.mock.ANY, "creation_time"),
                unittest.mock.call("team-2", unittest.mock.ANY, unittest.mock.ANY, "creation_time"),
            ],
        )
        self.assertEqual(fetch_ids.call_count, 2)
        self.assertEqual(
            save_histories.call_args_list,
            [
                unittest.mock.call(
                    defect_ids={"101", "102"},
                    session=session,
                    max_workers=50,
                    history_dir=history_dir,
                    team="DTSV_China",
                    store=store,
                    save_files=False,
                    save_csv=False,
                ),
                unittest.mock.call(
                    defect_ids={"201"},
                    session=session,
                    max_workers=50,
                    history_dir=history_dir,
                    team="Spotlight_FIT",
                    store=store,
                    save_files=False,
                    save_csv=False,
                ),
            ],
        )
        store.close.assert_called_once_with()

    def test_main_runs_history_fallback_only_for_teams_missing_downloaded_defects(self):
        session = object()
        store = MagicMock()
        history_dir = dq.os.path.join(dq.os.path.dirname(dq.os.path.abspath(dq.__file__)), "qgate", "history")

        with patch.object(dq.d6, "get_authenticated_session", return_value=session), \
             patch.object(dq, "fetch_team_name_to_id", return_value={"DTSV_China": "team-1", "Spotlight_FIT": "team-2"}), \
             patch.object(dq, "initialize_qgate_store", return_value=store), \
             patch.object(dq.d6, "fetch_octane_data_parallel", side_effect=[[{"id": 101, "name": "Downloaded"}], []]), \
             patch.object(dq, "save_defect_batch", return_value={"101"}) as save_batch, \
             patch.object(dq, "build_defect_ids_query", return_value="query-team-2") as build_query, \
             patch.object(dq.d6, "fetch_octane_data", return_value=[{"id": "201"}]) as fetch_ids, \
             patch.object(dq, "save_qgate_histories") as save_histories, \
             patch("builtins.open", unittest.mock.mock_open()):
            dq.main([
                "--teams", "DTSV_China,Spotlight_FIT",
                "--defect-years", "2026",
                "--save-db",
                "--skip-file-output",
            ])

        save_batch.assert_called_once()
        build_query.assert_called_once_with("team-2", unittest.mock.ANY, unittest.mock.ANY, "creation_time")
        fetch_ids.assert_called_once_with(
            session,
            dq.d6.EP_DEFECT,
            ("id",),
            "query-team-2",
            limit_per_page=dq.d6.DEFAULT_LIMIT_PER_PAGE,
            api_url=dq.d6.API_BASE_URL,
        )
        self.assertEqual(
            save_histories.call_args_list,
            [
                unittest.mock.call(
                    defect_ids={"101"},
                    session=session,
                    max_workers=50,
                    history_dir=history_dir,
                    team="DTSV_China",
                    store=store,
                    save_files=False,
                    save_csv=False,
                ),
                unittest.mock.call(
                    defect_ids={"201"},
                    session=session,
                    max_workers=50,
                    history_dir=history_dir,
                    team="Spotlight_FIT",
                    store=store,
                    save_files=False,
                    save_csv=False,
                ),
            ],
        )
        store.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()