import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        try:
            v2 = v
            if "." in v2:
                v2 = v2.split(".", 1)[0]
            return datetime.fromisoformat(v2.replace("Z", "+00:00"))
        except Exception:
            return None

def _calc_test_week(value: Any) -> Optional[str]:
    dt = _parse_iso_datetime(value)
    if not dt:
        return None
    try:
        iso = dt.isocalendar()
        return f"{int(iso.year)}-CW{int(iso.week):02d}"
    except Exception:
        return None


def default_db_path(repo_root: Optional[str] = None) -> str:
    base = repo_root or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "database", "local_data.db")


class OctaneSQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            return

    @contextmanager
    def transaction(self):
        try:
            self._conn.execute("BEGIN")
            yield
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise

    def create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS octane_payloads (
                kind TEXT NOT NULL,
                team TEXT NOT NULL,
                year INTEGER,
                spec TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (kind, team, year, spec)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS octane_defect_histories (
                defect_id TEXT NOT NULL PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_octane_payloads_kind_year_team ON octane_payloads(kind, year, team)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_octane_histories_team ON octane_defect_histories(team)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_octane_histories_team_defect ON octane_defect_histories(team, defect_id)")
        self._conn.commit()

    def upsert_payload(
        self,
        *,
        kind: str,
        team: str,
        year: Optional[int],
        spec: str,
        payload: Any,
        fetched_at: Optional[str] = None,
        commit: bool = True,
    ) -> None:
        fetched_at_val = fetched_at or _utc_now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO octane_payloads(kind, team, year, spec, payload_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, team, year, spec) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at
            """,
            (kind, team, year, spec, payload_json, fetched_at_val),
        )
        if commit:
            self._conn.commit()

    def upsert_defect_history(
        self,
        *,
        defect_id: str,
        team: str,
        payload: Any,
        total_count: Optional[int] = None,
        fetched_at: Optional[str] = None,
        commit: bool = True,
    ) -> None:
        fetched_at_val = fetched_at or _utc_now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        total = total_count
        if total is None and isinstance(payload, dict):
            try:
                total = int(payload.get("total_count")) if payload.get("total_count") is not None else None
            except Exception:
                total = None
        self._conn.execute(
            """
            INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(defect_id) DO UPDATE SET
                team=excluded.team,
                total_count=excluded.total_count,
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at
            """,
            (str(defect_id), team, total, payload_json, fetched_at_val),
        )
        if commit:
            self._conn.commit()

    def get_defect_history(self, defect_id: str) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload_json FROM octane_defect_histories WHERE defect_id = ?",
            (str(defect_id),),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def get_payload(self, *, kind: str, team: str, year: Optional[int], spec: str) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload_json FROM octane_payloads WHERE kind=? AND team=? AND year IS ? AND spec=?",
            (kind, team, year, spec),
        ).fetchone()
        if not row:
            return None
        try:
            val = json.loads(row[0])
            return val if isinstance(val, dict) else {"data": val}
        except Exception:
            return None

    def get_latest_payload_meta(self, *, kind: str, team: str, year: Optional[int], spec: str) -> Optional[Tuple[str, int]]:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT fetched_at, length(payload_json) FROM octane_payloads WHERE kind=? AND team=? AND year IS ? AND spec=?",
            (kind, team, year, spec),
        ).fetchone()
        if not row:
            return None
        return row[0], int(row[1] or 0)

    # ============ Optimized Schema Methods ============

    def create_optimized_tables(self) -> None:
        """Create optimized tables for direct defect/manual_run storage"""
        cur = self._conn.cursor()

        # Defects table - flat structure for efficient querying
        cur.execute("""
            CREATE TABLE IF NOT EXISTS octane_defects (
                defect_id TEXT PRIMARY KEY,
                name TEXT,
                creation_time TEXT,
                last_modified TEXT,
                team TEXT,
                problem_finder_team TEXT,
                program TEXT,
                author TEXT,
                aida_businesskey TEXT,
                aida_english TEXT,
                top_aida TEXT,
                product_areas TEXT,
                user_tags TEXT,
                phase TEXT,
                severity TEXT,
                problem_severity TEXT,
                status_phase TEXT,
                owner TEXT,
                detected_by TEXT,
                detected_in_release TEXT,
                software_version TEXT,
                vin TEXT,
                assigned_ecu TEXT,
                lead_model TEXT,
                ecu_no_of_changes INTEGER,
                parent_id TEXT,
                parent_child_type TEXT,
                relation_to TEXT,
                test_week TEXT,
                risk_score REAL,
                fv TEXT,
                fvp TEXT,
                tqr TEXT,
                blocking_reason TEXT,
                error_occurrence TEXT,
                solution_responsible TEXT,
                solution_cluster TEXT,
                reporting_class TEXT,
                function_responsible TEXT,
                involved_i_step TEXT,
                first_use_sop_of_function TEXT,
                tolerated_count INTEGER,
                reprel_changes INTEGER,
                raw_json TEXT NOT NULL,
                year INTEGER,
                fetched_at TEXT NOT NULL
            )
        """)

        # Manual runs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS octane_manual_runs (
                mr_id TEXT PRIMARY KEY,
                name TEXT,
                test_name TEXT,
                test_id TEXT,
                creation_time TEXT,
                last_modified TEXT,
                started TEXT,
                finished TEXT,
                defect_id TEXT,
                run_team TEXT,
                program TEXT,
                author TEXT,
                run_by TEXT,
                status TEXT,
                native_status TEXT,
                is_completed INTEGER,
                steps_num INTEGER,
                version_stamp INTEGER,
                release TEXT,
                exec_model_series TEXT,
                execution_sw_version TEXT,
                test_version TEXT,
                product_areas TEXT,
                domain TEXT,
                test_phase TEXT,
                testing_tool_type TEXT,
                taxonomies TEXT,
                set_field TEXT,
                target_ecu_conf TEXT,
                testplatformid TEXT,
                raw_json TEXT NOT NULL,
                year INTEGER,
                spec TEXT,
                fetched_at TEXT NOT NULL
            )
        """)

        # Indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_year ON octane_defects(year)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_team ON octane_defects(team)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_phase ON octane_defects(phase)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_severity ON octane_defects(severity)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_program ON octane_defects(program)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_defects_user_tags ON octane_defects(user_tags)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_manual_runs_year ON octane_manual_runs(year)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_manual_runs_release ON octane_manual_runs(release)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_manual_runs_defect ON octane_manual_runs(defect_id)")

        self._conn.commit()
        return None

    def upsert_defects_batch(self, defects: list, year: int, fetched_at: Optional[str] = None) -> int:
        """Insert or update defects in batch (optimized schema)

        Args:
            defects: List of defect dictionaries from Octane API
            year: Year of the data
            fetched_at: Timestamp of when data was fetched

        Returns:
            Number of defects inserted/updated
        """
        if not defects:
            return 0

        fetched_at_val = fetched_at or _utc_now_iso()
        count = 0

        # Load AIDA/FV mapping for FV assignment
        aida_fv_map = self._load_aida_fv_mapping()

        def safe_nested(data, *keys, default=None):
            """Safely get nested dict values"""
            result = data
            for key in keys:
                if isinstance(result, dict):
                    result = result.get(key)
                else:
                    return default
                if result is None:
                    return default
            return result

        def extract_full_name(field_value):
            """Extract full_name from a nested dict field"""
            if isinstance(field_value, dict):
                return field_value.get('full_name') or field_value.get('name')
            return field_value

        def extract_relation_to(value):
            if value is None:
                return None
            if isinstance(value, dict):
                return value.get('name') or value.get('full_name') or value.get('id')
            if isinstance(value, list):
                parts = []
                for item in value:
                    if item is None:
                        continue
                    if isinstance(item, dict):
                        v = item.get('id') or item.get('name') or item.get('full_name')
                        if v is None:
                            continue
                        parts.append(str(v))
                        continue
                    parts.append(str(item))
                return ','.join([p for p in parts if p.strip()]) if parts else None
            if isinstance(value, (int, float)):
                return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
            if isinstance(value, str):
                v = value.strip()
                return v if v else None
            return str(value)

        def extract_tags(user_tags_list):
            """Extract tag names from user_tags list"""
            if not user_tags_list or not isinstance(user_tags_list, list):
                return None
            names = []
            for tag in user_tags_list:
                if isinstance(tag, dict):
                    name = tag.get('name')
                    if name:
                        names.append(name)
            return ','.join(names) if names else None

        def extract_product_areas(pa_data):
            """Extract product area names and return as JSON string"""
            if not pa_data:
                return None
            # Handle dict format: {'total_count': n, 'data': [...]}
            if isinstance(pa_data, dict):
                data = pa_data.get('data', [])
                if isinstance(data, list):
                    names = []
                    for pa in data:
                        if isinstance(pa, dict):
                            name = pa.get('name')
                            if name:
                                names.append(name)
                    return ','.join(names) if names else None
                return None
            # Handle list format
            if isinstance(pa_data, list):
                names = []
                for pa in pa_data:
                    if isinstance(pa, dict):
                        name = pa.get('name')
                        if name:
                            names.append(name)
                return ','.join(names) if names else None
            return None

        def get_aidas_list(product_areas):
            """Get list of AIDA names from product_areas"""
            if not product_areas:
                return []
            if isinstance(product_areas, dict):
                data = product_areas.get('data', [])
                if isinstance(data, list):
                    return [pa.get('name', '') for pa in data if isinstance(pa, dict) and pa.get('name')]
                return []
            if isinstance(product_areas, list):
                return [pa.get('name', '') for pa in product_areas if isinstance(pa, dict) and pa.get('name')]
            return []

        def get_top_req(req_list):
            """Find the AIDA with shortest last word"""
            if not isinstance(req_list, list) or len(req_list) == 0:
                return ''
            top_req = ''
            len_req = 1000
            for ith_req in req_list:
                if not isinstance(ith_req, str):
                    continue
                parts = ith_req.split(' ')
                if not parts:
                    continue
                last_part = parts[-1]
                if not last_part:
                    continue
                try:
                    len_ith_req = len(last_part)
                except TypeError:
                    continue
                if len_ith_req < len_req:
                    len_req = len_ith_req
                    top_req = ith_req
            return top_req

        def extract_english(text):
            """Extract English words from text"""
            if not text or text == '':
                return 'Unknown'
            import re
            english_words = re.findall(r'[a-zA-Z]+', str(text))
            return ' '.join(english_words) if english_words else 'Unknown'

        def assign_fv_from_aida(top_aida, aida_english, aida_fv_map):
            """Assign FV based on AIDA mapping"""
            if not top_aida:
                return None
            # Try exact match with top_aida
            fv = aida_fv_map.get(str(top_aida).strip())
            if fv:
                return fv
            # Try match with aida_english
            if aida_english and aida_english != 'Unknown':
                fv = aida_fv_map.get(str(aida_english).strip())
                if fv:
                    return fv
            return None

        batch = []
        for defect in defects:
            try:
                defect_id = defect.get('id')
                if not defect_id:
                    continue

                # Basic fields
                name = defect.get('name')
                creation_time = defect.get('creation_time')
                last_modified = defect.get('last_modified')

                # Team info - extract full_name from nested dicts
                team = extract_full_name(defect.get('team'))
                problem_finder_team = extract_full_name(defect.get('problem_finder_team_udf'))
                program = extract_full_name(defect.get('program'))
                author = extract_full_name(defect.get('author'))

                # AIDA info
                aida_businesskey = defect.get('aida_businesskey_udf')

                # Tags and areas - extract from raw data
                user_tags = extract_tags(defect.get('user_tags'))
                product_areas_raw = defect.get('product_areas')
                product_areas = extract_product_areas(product_areas_raw)

                # Calculate AIDA fields
                aidas_list = get_aidas_list(product_areas_raw)
                top_aida = get_top_req(aidas_list)
                aida_english = extract_english(top_aida)

                # Status
                phase = extract_full_name(defect.get('phase'))
                severity = extract_full_name(defect.get('severity'))
                problem_severity = extract_full_name(defect.get('problem_severity_udf'))
                status_phase = f"{phase}_{severity}" if phase and severity else phase

                # Owners - extract full_name
                owner = extract_full_name(defect.get('owner'))
                detected_by = extract_full_name(defect.get('detected_by'))

                # Release info
                detected_in_release = extract_full_name(defect.get('detected_in_release'))
                software_version = defect.get('software_version_udf')

                # Vehicle/ECU
                vin = defect.get('vin_udf')
                assigned_ecu = extract_full_name(defect.get('assigned_ecu_udf'))
                lead_model = extract_full_name(defect.get('lead_model_udf'))
                ecu_no_of_changes = defect.get('ecu_no_of_changes_udf')

                # Relations
                parent_id = safe_nested(defect, 'parent', 'id')
                parent_child_type = extract_full_name(defect.get('parent_child_udf'))
                relation_to = extract_relation_to(defect.get('relation_to_udf'))

                # Other fields
                tqr_raw = defect.get('tqr_udf')
                tqr = json.dumps(tqr_raw, ensure_ascii=False) if isinstance(tqr_raw, (dict, list)) else tqr_raw

                blocking_reason_raw = defect.get('blocking_reason_udf')
                blocking_reason = extract_full_name(blocking_reason_raw) if isinstance(blocking_reason_raw, dict) else blocking_reason_raw

                error_occurrence_raw = defect.get('error_occurrence_udf')
                error_occurrence = extract_full_name(error_occurrence_raw) if isinstance(error_occurrence_raw, dict) else error_occurrence_raw

                solution_responsible = extract_full_name(defect.get('solution_responsible_udf'))
                solution_cluster = extract_full_name(defect.get('solution_cluster_udf'))
                reporting_class = extract_full_name(defect.get('reporting_class_udf'))
                function_responsible = extract_full_name(defect.get('function_responsible1_udf'))
                involved_i_step = extract_full_name(defect.get('involved_i_step1_udf'))
                first_use_sop_of_function = extract_full_name(defect.get('first_use_sop_of_function_udf'))
                tolerated_count = defect.get('tolerated_count_udf')
                reprel_changes = defect.get('reprel_changes_udf')

                test_week = _calc_test_week(creation_time)

                # Assign FV and FVP based on AIDA mapping
                fv = assign_fv_from_aida(top_aida, aida_english, aida_fv_map)
                fvp = self._get_fvp_from_fv(fv)

                # Raw JSON
                raw_json = json.dumps(defect, ensure_ascii=False)

                batch.append((
                    defect_id, name, creation_time, last_modified,
                    team, problem_finder_team, program, author,
                    aida_businesskey, aida_english, top_aida,
                    product_areas, user_tags,
                    phase, severity, problem_severity, status_phase,
                    owner, detected_by,
                    detected_in_release, software_version,
                    vin, assigned_ecu, lead_model, ecu_no_of_changes,
                    parent_id, parent_child_type, relation_to,
                    test_week, None, fv, fvp,  # risk_score computed later
                    tqr, blocking_reason, error_occurrence,
                    solution_responsible, solution_cluster, reporting_class,
                    function_responsible, involved_i_step,
                    first_use_sop_of_function, tolerated_count, reprel_changes,
                    raw_json, year, fetched_at_val
                ))

            except Exception as e:
                # Skip problematic defects but log
                print(f"Warning: Failed to process defect {defect.get('id', 'unknown')}: {e}")
                continue

        # Batch insert
        if batch:
            try:
                self._conn.executemany("""
                    INSERT OR REPLACE INTO octane_defects (
                        defect_id, name, creation_time, last_modified,
                        team, problem_finder_team, program, author,
                        aida_businesskey, aida_english, top_aida,
                        product_areas, user_tags,
                        phase, severity, problem_severity, status_phase,
                        owner, detected_by,
                        detected_in_release, software_version,
                        vin, assigned_ecu, lead_model, ecu_no_of_changes,
                        parent_id, parent_child_type, relation_to,
                        test_week, risk_score, fv, fvp,
                        tqr, blocking_reason, error_occurrence,
                        solution_responsible, solution_cluster, reporting_class,
                        function_responsible, involved_i_step,
                        first_use_sop_of_function, tolerated_count, reprel_changes,
                        raw_json, year, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                self._conn.commit()
                count = len(batch)
            except Exception as e:
                print(f"Error during batch insert: {e}")
                # Try individual inserts
                for record in batch:
                    try:
                        self._conn.execute("""
                            INSERT OR REPLACE INTO octane_defects (
                                defect_id, name, creation_time, last_modified,
                                team, problem_finder_team, program, author,
                                aida_businesskey, aida_english, top_aida,
                                product_areas, user_tags,
                                phase, severity, problem_severity, status_phase,
                                owner, detected_by,
                                detected_in_release, software_version,
                                vin, assigned_ecu, lead_model, ecu_no_of_changes,
                                parent_id, parent_child_type, relation_to,
                                test_week, risk_score, fv, fvp,
                                tqr, blocking_reason, error_occurrence,
                                solution_responsible, solution_cluster, reporting_class,
                                function_responsible, involved_i_step,
                                first_use_sop_of_function, tolerated_count, reprel_changes,
                                raw_json, year, fetched_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, record)
                        count += 1
                    except Exception as e2:
                        print(f"Failed to insert defect {record[0]}: {e2}")
                self._conn.commit()

        return count

    def upsert_manual_runs_batch(self, manual_runs: list, year: int, spec: str, fetched_at: Optional[str] = None) -> int:
        """Insert or update manual runs in batch (optimized schema)

        Args:
            manual_runs: List of manual run dictionaries from Octane API
            year: Year of the data
            spec: Release spec (e.g., "R-25-01")
            fetched_at: Timestamp of when data was fetched

        Returns:
            Number of manual runs inserted/updated
        """
        if not manual_runs:
            return 0

        fetched_at_val = fetched_at or _utc_now_iso()
        count = 0

        def safe_nested(data, *keys, default=None):
            """Safely get nested dict values"""
            result = data
            for key in keys:
                if isinstance(result, dict):
                    result = result.get(key)
                else:
                    return default
                if result is None:
                    return default
            return result

        def extract_product_areas(pa_value):
            """Extract product area names from dict({'data':[...]}) or list([{name:...}])"""
            if not pa_value:
                return None
            data = None
            if isinstance(pa_value, dict):
                data = pa_value.get('data', [])
            elif isinstance(pa_value, list):
                data = pa_value
            else:
                return None
            if not isinstance(data, list):
                return None
            names = []
            for pa in data:
                if isinstance(pa, dict):
                    name = pa.get('name')
                    if name:
                        names.append(name)
            return ','.join(names) if names else None

        def extract_taxonomies(tax_value):
            """Extract taxonomy names from dict({'data':[...]}) or list([{name:...}])"""
            if not tax_value:
                return None
            data = None
            if isinstance(tax_value, dict):
                data = tax_value.get('data', [])
            elif isinstance(tax_value, list):
                data = tax_value
            else:
                return None
            if not isinstance(data, list):
                return None
            names = []
            for tax in data:
                if isinstance(tax, dict):
                    name = tax.get('name')
                    if name:
                        names.append(name)
            return ','.join(names) if names else None

        batch = []
        for mr in manual_runs:
            try:
                mr_id = mr.get('id')
                if not mr_id:
                    continue

                # Basic fields
                name = mr.get('name')
                test_name = safe_nested(mr, 'test', 'name')
                test_id = safe_nested(mr, 'test', 'id')
                creation_time = mr.get('creation_time')
                last_modified = mr.get('last_modified')
                started = mr.get('started')
                finished = mr.get('finished_udf')

                # Relations
                defect_id = safe_nested(mr, 'defect', 'id')

                # Team info
                run_team = safe_nested(mr, 'run_team_000_udf', 'name')
                program = safe_nested(mr, 'program', 'name')
                author = safe_nested(mr, 'author', 'name')

                # Execution info
                run_by = safe_nested(mr, 'run_by', 'name')
                status = safe_nested(mr, 'status', 'name')
                native_status = safe_nested(mr, 'native_status', 'name')
                is_completed = 1 if mr.get('is_completed') else 0
                steps_num = mr.get('steps_num')
                version_stamp = mr.get('version_stamp')

                # Release info
                release = safe_nested(mr, 'release', 'name')
                exec_model_series = safe_nested(mr, 'exec_model_series_udf', 'name')
                execution_sw_version = mr.get('execution_sw_version_udf')
                test_version = safe_nested(mr, 'test_version', 'name')

                # Classification
                product_areas = extract_product_areas(mr.get('product_areas'))
                domain = safe_nested(mr, 'domain_udf', 'name')
                test_phase = safe_nested(mr, 'test_phase', 'name')
                testing_tool_type = safe_nested(mr, 'testing_tool_type', 'name')
                taxonomies = extract_taxonomies(mr.get('taxonomies'))

                # Other
                set_field = safe_nested(mr, 'set_udf', 'name')
                target_ecu_conf = mr.get('target_ecu_conf_udf')
                testplatformid = mr.get('testplatformid_udf')

                # Raw JSON
                raw_json = json.dumps(mr, ensure_ascii=False)

                batch.append((
                    mr_id, name, test_name, test_id,
                    creation_time, last_modified, started, finished,
                    defect_id,
                    run_team, program, author,
                    run_by, status, native_status, is_completed, steps_num, version_stamp,
                    release, exec_model_series, execution_sw_version, test_version,
                    product_areas, domain, test_phase, testing_tool_type,
                    taxonomies, set_field, target_ecu_conf, testplatformid,
                    raw_json, year, spec, fetched_at_val
                ))

            except Exception as e:
                print(f"Warning: Failed to process manual run {mr.get('id', 'unknown')}: {e}")
                continue

        # Batch insert
        if batch:
            try:
                self._conn.executemany("""
                    INSERT OR REPLACE INTO octane_manual_runs (
                        mr_id, name, test_name, test_id,
                        creation_time, last_modified, started, finished,
                        defect_id,
                        run_team, program, author,
                        run_by, status, native_status, is_completed, steps_num, version_stamp,
                        release, exec_model_series, execution_sw_version, test_version,
                        product_areas, domain, test_phase, testing_tool_type,
                        taxonomies, set_field, target_ecu_conf, testplatformid,
                        raw_json, year, spec, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                self._conn.commit()
                count = len(batch)
            except Exception as e:
                print(f"Error during batch insert: {e}")
                # Try individual inserts
                for record in batch:
                    try:
                        self._conn.execute("""
                            INSERT OR REPLACE INTO octane_manual_runs (
                                mr_id, name, test_name, test_id,
                                creation_time, last_modified, started, finished,
                                defect_id,
                                run_team, program, author,
                                run_by, status, native_status, is_completed, steps_num, version_stamp,
                                release, exec_model_series, execution_sw_version, test_version,
                                product_areas, domain, test_phase, testing_tool_type,
                                taxonomies, set_field, target_ecu_conf, testplatformid,
                                raw_json, year, spec, fetched_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, record)
                        count += 1
                    except Exception as e2:
                        print(f"Failed to insert manual run {record[0]}: {e2}")
                self._conn.commit()

        return count

    def _load_aida_fv_mapping(self) -> dict:
        """Load AIDA to FV mapping from Excel file

        Returns:
            Dict mapping top_aida to fv
        """
        mapping = {}
        excel_file = "aida/top_aida_project_fv_mapping.xlsx"

        if not os.path.exists(excel_file):
            return mapping

        try:
            import pandas as pd
            for sheet_name in ['IDCevo', 'IDC', 'MGU', 'App', 'RSU']:
                try:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    if 'top_aida' in df.columns and 'fv' in df.columns:
                        for _, row in df.iterrows():
                            if pd.notna(row['top_aida']) and pd.notna(row['fv']):
                                aida = str(row['top_aida']).strip()
                                fv = str(row['fv']).strip()
                                if aida and fv and fv != 'nan':
                                    mapping[aida] = fv
                                    # Also map aida_english format
                                    aida_english = self._extract_english(aida)
                                    if aida_english and aida_english != 'Unknown':
                                        mapping[aida_english] = fv
                    # Also process aida_english column if exists
                    if 'aida_english' in df.columns and 'fv' in df.columns:
                        for _, row in df.iterrows():
                            if pd.notna(row['aida_english']) and pd.notna(row['fv']):
                                aida_english = str(row['aida_english']).strip()
                                fv = str(row['fv']).strip()
                                if aida_english and fv and fv != 'nan':
                                    mapping[aida_english] = fv
                except Exception as e:
                    continue
        except Exception as e:
            print(f"Warning: Failed to load AIDA/FV mapping: {e}")

        return mapping

    def _extract_english(self, text: str) -> str:
        """Extract English words from text"""
        if not text or text == '':
            return 'Unknown'
        import re
        english_words = re.findall(r'[a-zA-Z]+', str(text))
        return ' '.join(english_words) if english_words else 'Unknown'

    def _get_fvp_from_fv(self, fv: Optional[str]) -> Optional[str]:
        """Get FVP name from FV"""
        if not fv:
            return None

        fvp_mapping = {
            'DIPS_TSP_Call_Services': 'Tianhua',
            'DIPS_TSP_CD_Updates': 'Tianhua',
            'DIPS_TSP_Remote_Services': 'Tianhua',
            'eMob': 'Tianhua',
            'DIPS_TSP_MobileApps': 'Tianhua',
            'DIPS_TSP_Enabler': 'Tianhua',
            'IuK_TSP_Navi': 'Tony',
            'IuK_TSP_AZV': 'Xu Miao',
            'IuK_TSP_Entertainment': 'Xu Miao',
            'IuK_TSP_Audio': 'Xu Miao',
            'IuK_TSP_Connectivity': 'Xu Miao',
            'IuK_TSP_HMI': 'Jerry',
            'DIPS_TSP_RSU': 'Jerry',
            'IuK_TSP_Carfunctions': 'Jerry',
            'IuK_TSP_Perso CN': 'Jerry',
            'RSU': 'Jerry',
            'Mybmw App': 'Marin'
        }

        return fvp_mapping.get(fv)
