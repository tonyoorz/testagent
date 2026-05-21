# QGate Downloader SQLite + Chroma Design

## Goal

Extend `downloaderqgate.py` so QGate defect and history downloads are written into a SQLite database under `qgate/` as the primary structured store, with an optional ChromaDB semantic index under `qgate/` for later AI retrieval, while preserving the current file-based outputs used by existing QGate analysis and report generation flows.

## Scope

In scope:

- Add database output support to `downloaderqgate.py`
- Add optional ChromaDB output support for AI-oriented retrieval
- Reuse the existing SQLite schema and storage helpers from `octane_db.py`
- Reuse the existing history-to-database path already implemented in `download/octane_downloader.py`
- Reuse repository-local Chroma/embedding patterns where practical, instead of inventing a second AI indexing pattern
- Keep file output compatible with current consumers in `qgate.py` and `report/generate_qgate_kpi_dashboard.py`
- Add focused automated tests for the new CLI behavior and DB write routing

Out of scope:

- Changing `qgate.py` to read from DB
- Migrating QGate analysis logic from file-first to DB-first
- Replacing SQLite with ChromaDB as the source of truth
- Changing report generation inputs
- Refactoring shared downloader infrastructure beyond the minimum needed for reuse

## Current State

`downloaderqgate.py` currently:

- downloads defect payloads per team and year
- saves defect payloads to `qgate/defect/*.json`
- downloads defect histories for the union of scoped defect IDs
- saves histories to `qgate/history/*_history.json`

This creates two practical gaps:

- non-local-team QGate data may exist only as files, not in SQLite
- downstream tooling that expects DB-backed history coverage cannot reuse QGate downloads directly

It also leaves a future AI gap:

- there is no dedicated semantic retrieval index for QGate defect text, so later AI features would need to rebuild one from raw files or raw SQLite payloads

The repository already has the missing primitives:

- `octane_db.py` defines `OctaneSQLiteStore`, `octane_payloads`, and `octane_defect_histories`
- `download/octane_downloader.py` already implements `fetch_defect_histories_parallel_to_db(...)`
- `requirements.txt` already includes `chromadb`
- `duplicate_issue_finder.py` already demonstrates local Chroma persistence and embedding-related conventions in this repository

## Proposed Behavior

### CLI additions

Add the following arguments to `downloaderqgate.py`:

- `--save-db`
  - Enables SQLite writes for downloaded QGate data
- `--qgate-db-path`
  - Default: `qgate/qgate_data.db`
  - Allows explicit DB file override
- `--save-chroma`
   - Enables semantic indexing of downloaded QGate defect text into ChromaDB
- `--chroma-dir`
   - Default: `qgate/chroma`
   - Allows explicit Chroma persistence directory override
- `--chroma-collection`
   - Default: `qgate_defect_cases`
   - Allows explicit collection naming when multiple experiments coexist
- `--skip-file-output`
  - Optional compatibility switch for DB-only operation

### Effective modes

1. Default mode
   - No DB writes
   - Existing file behavior remains unchanged

2. SQLite dual-write mode
   - Enabled with `--save-db`
   - Writes both files and DB records
   - This is the minimum recommended operational mode

3. SQLite + Chroma mode
   - Enabled with `--save-db --save-chroma`
   - Writes files, SQLite records, and Chroma semantic documents
   - This is the recommended mode for teams planning AI retrieval features

4. DB-only mode
   - Enabled with `--save-db --skip-file-output`
   - Writes only SQLite records
   - Supported for future workflows, but not required by existing QGate analysis scripts

Behavioral rule:

- `--save-chroma` requires `--save-db`
- Chroma is an index sidecar, not an alternative source of truth

## Storage Model

### Primary structured store

Use a dedicated SQLite file under the QGate working directory:

- default path: `qgate/qgate_data.db`

This keeps QGate-specific downloaded data isolated from the main application database while reusing the same schema contract.

### Semantic index location

Use a dedicated Chroma persistence directory under the QGate working directory:

- default path: `qgate/chroma`

This keeps the semantic index co-located with the QGate dataset while separating retrieval artifacts from the SQLite source of truth.

### SQLite table usage

Reuse existing tables from `octane_db.py` exactly as-is.

#### Defect payloads

Store defect downloads in `octane_payloads` with:

- `kind="defects"`
- `team=<team name>`
- `year=<download year>`
- `spec=<team_slug>`
- `payload={"data": defect_data_list}`

Rationale:

- keeps parity with the existing octane downloader payload storage pattern
- preserves original JSON payload fidelity
- avoids prematurely flattening QGate defect payloads into a second schema

#### Defect histories

Store per-defect history in `octane_defect_histories` with:

- `defect_id=<defect id>`
- `team=<team name>`
- `payload=<raw history response>`
- `total_count=<raw_history_data.total_count>`

Rationale:

- this is already the repository-standard location for raw defect history payloads
- it matches the current `fetch_defect_histories_parallel_to_db(...)` implementation

### Chroma collection usage

Use a single defect-oriented collection in v1:

- collection name default: `qgate_defect_cases`

Each Chroma document represents one defect or ticket case using defect payload text, not raw history blobs.

Recommended document shape:

- `id=<defect id>`
- `document=<normalized defect text assembled from name, description, team, release, and other concise textual fields>`
- `metadata={team, year, team_slug, defect_id, fetched_at, has_history}`

Rationale:

- semantic retrieval is most useful on concise defect text, not raw JSON history payloads
- KPI and trend analysis still rely on SQLite, where exact filters and aggregations are strong
- keeping Chroma focused on case retrieval avoids overloading it with raw event storage that belongs in SQLite

## Implementation Design

### Downloader initialization

When `--save-db` is set:

1. Resolve the DB path from `--qgate-db-path`
2. Instantiate `OctaneSQLiteStore`
3. Call `create_tables()` before any write path executes
4. Close the store at process end via `finally`

When `--save-chroma` is also set:

1. Resolve the Chroma path from `--chroma-dir`
2. Instantiate a persistent Chroma client bound to that directory
3. Get or create the configured collection
4. Reuse existing repository embedding conventions where practical, but keep the first version focused on stable local persistence rather than advanced ranking logic

When `--save-db` is not set:

- no database object is created
- no existing behavior changes

### Defect write path

For each `(team, year)` defect batch:

1. Fetch defect payloads from Octane as today
2. If file output is enabled, continue saving JSON/CSV/Excel exactly as today
3. If DB mode is enabled, write the same payload batch to `octane_payloads`
4. If Chroma mode is enabled, upsert one semantic document per defect into the configured collection

Behavioral constraint:

- DB writes must not replace file writes unless `--skip-file-output` is explicitly provided
- Chroma writes do not replace SQLite writes
- raw defect payloads stay in SQLite even when Chroma is enabled

### History write path

For the union of defect IDs:

1. If DB mode is disabled, continue using `fetch_defect_histories_parallel(...)`
2. If DB mode is enabled, switch to `fetch_defect_histories_parallel_to_db(...)`
3. Pass `save_files_dir=None` when `--skip-file-output` is set
4. Otherwise pass the existing `history_dir` so history continues to be saved as files as well

Chroma behavior for history in v1:

- do not store raw history payloads in Chroma
- optionally update `has_history` metadata when history ingestion succeeds
- leave richer history summarization for a later AI-focused phase

### File output gating

Current code always creates and writes to `defect_dir` and `history_dir`.

Update that behavior so:

- directories are still resolvable under `qgate/`
- actual `save_data(...)` calls are skipped when `--skip-file-output` is enabled
- history helper receives no save directory in DB-only mode

This avoids unnecessary file churn while keeping current defaults unchanged.

## Data Flow

### Defects

Octane API -> `downloaderqgate.py` -> optional JSON/CSV/Excel files in `qgate/defect` -> optional `octane_payloads` row in `qgate/qgate_data.db` -> optional semantic document in `qgate/chroma`

### Histories

Octane API -> `downloaderqgate.py` -> optional JSON files in `qgate/history` -> optional `octane_defect_histories` rows in `qgate/qgate_data.db`

Semantic retrieval path in v1:

SQLite raw data -> normalized defect text -> Chroma collection for AI retrieval

## Error Handling

### DB unavailable

If `--save-db` is requested but SQLite store initialization fails:

- fail fast with a clear error
- do not silently continue in file-only mode

Reason: the user explicitly requested DB persistence, so silent downgrade would hide data integrity problems.

### Chroma unavailable

If `--save-chroma` is requested but Chroma initialization fails:

- fail fast with a clear error
- do not silently continue in SQLite-only mode

Reason: the user explicitly requested semantic indexing, so silent downgrade would hide missing AI preparation work.

### Partial DB write failures

If a defect payload or history payload fails to write:

- log the concrete team or defect ID
- treat the item as failed for the downloader run summary
- continue processing other items when possible

If a Chroma defect document fails to upsert:

- log the defect ID and team
- treat the document as failed for the semantic-index step
- do not treat Chroma success as a substitute for SQLite success

### Existing file compatibility

If DB writes succeed but file writes fail in dual-write mode:

- preserve current file-write error behavior
- report file write failure explicitly
- do not suppress the failure just because DB succeeded

Reason: current QGate analysis still depends on file inputs.

## Testing Strategy

Add focused unit tests under `tests/` covering:

1. CLI parsing
   - `--save-db` toggles DB mode
   - `--save-chroma` toggles Chroma mode
   - `--save-chroma` without `--save-db` is rejected
   - `--skip-file-output` is accepted
   - default `--qgate-db-path` resolves to `qgate/qgate_data.db`
   - default `--chroma-dir` resolves to `qgate/chroma`

2. Defect routing
   - with DB mode off, no DB write helper is called
   - with DB mode on, `upsert_payload(...)` is called for defect batches
   - with Chroma mode on, Chroma upsert helper is called for defect batches

3. History routing
   - with DB mode off, downloader uses `fetch_defect_histories_parallel(...)`
   - with DB mode on, downloader uses `fetch_defect_histories_parallel_to_db(...)`
   - with DB-only mode, `save_files_dir` is passed as `None`

4. Backward compatibility
   - existing year override behavior remains unchanged

These tests should use mocks or stubs for network calls and DB writers. No live Octane access is needed.

## Implementation Steps

1. Add failing tests for the new CLI flags and routing behavior
2. Extend `parse_args()` with DB- and Chroma-related options
3. Add validation that `--save-chroma` requires `--save-db`
4. Add SQLite store initialization and teardown in `main()`
5. Add Chroma initialization and collection setup in `main()`
6. Add defect batch writes to `octane_payloads`
7. Add defect-document upserts to Chroma when enabled
8. Route history downloads through the DB-capable helper when enabled
9. Add file-output gating for DB-only mode
10. Run focused tests for `downloaderqgate.py`

## Risks and Non-Goals

### Risks

- dual-write mode may expose existing file write assumptions more clearly because success can now diverge between file and DB outputs
- storing full defect payload batches in `octane_payloads` increases DB size, but this is acceptable for raw-ingest parity
- Chroma indexing adds another persistence layer that must stay aligned with SQLite records
- embedding-related behavior can become environment-sensitive if the first implementation tries to do too much

### Non-goals for this change

- no backfill job for existing historical JSON files into DB
- no backfill job for existing SQLite rows into Chroma in this first change
- no immediate switch of QGate analytics from file-only to DB-backed reads
- no schema redesign beyond the existing `octane_db.py` contract

## Architecture Principle

SQLite is the system of record for QGate structured data.

ChromaDB is a retrieval sidecar for AI use cases such as:

- similar defect lookup
- semantic recall over downloaded QGate cases
- future RAG support for QGate guidance and dashboard assistants

ChromaDB is not used for:

- KPI aggregation
- exact filtering by team, year, status, or phase
- trend computation
- raw history event storage

## Recommendation

Implement the downloader with SQLite as the required primary store and Chroma as an optional sidecar when `--save-chroma` is supplied. This gives immediate operational value with minimal risk because:

- current file-based QGate tooling continues to work unchanged
- QGate history becomes available in SQLite for later DB-backed analytics
- the implementation reuses repository-standard storage code instead of inventing a parallel schema
- later AI features can retrieve semantically similar QGate cases without forcing Chroma to become the analytics database