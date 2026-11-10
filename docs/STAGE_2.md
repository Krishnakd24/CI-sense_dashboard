# Stage 2 implementation

Historical evidence-stage design: central prediction has since been enabled. See [current prediction setup](PREDICTION.md).

This stage implements the evidence architecture, not central model inference.

## Research contract

Each ready test has a persisted, versioned B2_o1 target:

- test_code: the resolved method body at the selected full commit SHA.
- failure_reports: ordered B1 report objects. Missing/empty/NA fields are omitted; present values remain strings. Identification and application metadata are excluded.
- project_change_description: a factual paragraph describing the observed first-parent changes.

The parser remains deterministic. Its original extraction is retained separately, and the XML tab supports manual comparison with a download of the original report. Matching classname/name entries within one suite become a group with separate report objects. Entries in different suites remain separate.

The summarizer emits only project_change_description, following the descriptive style of Final_data/data_B3_v3.csv. It does not receive the UI's unverified parent-pass assumption, historical outcomes or previous analyses. Missing patches and ambiguous sources prevent a ready payload; full source files are never silently substituted for methods.

The original Final_data/prompt_b2_o1.txt stays outside the application repository. Its SHA-256 and user-message placement are recorded in payload provenance. Set B2_O1_PROMPT_PATH if the research files live elsewhere. No prompt examples are copied into published source and no classifier is called.

The future probability contract is exactly {"flaky_probability": number}, constrained to finite numeric values between 0 and 1. Booleans, strings and additional diagnosis fields are rejected. Stage 2 creates no prediction rows.

## Database upgrade

Stop the existing backend before upgrading:

```powershell
cd <repository-root>\backend
& ..\.venv\Scripts\python.exe -m alembic upgrade head
```

Migration 0002 adds component outputs, immutable evidence payloads, future 0..1 predictions, repository identities, first-parent SHAs, execution timestamps and model configuration versions. Existing analyses and original evidence are retained. Old completed analyses do not automatically gain new payloads; create a new analysis to extract Stage 2 evidence. There is no automatic rerun or retry.

## Independent execution

The coordinator resolves and freezes the repository/head/parent, retrieves the diff, retrieves selected methods, and then summarizes complete diffs once per analysis. Each stage persists independently. Source failures do not discard other tests' evidence. Summarization failures retain raw patches and retrieved source. Ready tests can be inspected even when the overall analysis is partial.

GitHub reads are cached only within an authorized analysis execution. Repository IDs detect identity changes and support reads after repository renames. Explicit GitHub rate-limit errors include available reset information and are not retried.

## Review and routes

Project, project settings/history/new-analysis, admin and analysis routes are addressable directly and restored on refresh. The evidence view provides XML, diff, source and Final B2_o1 JSON tabs. Ready JSON can be copied or downloaded independently of its provenance.

- GET /analyses/{id}/tests/{testId}/payload: exact persisted target JSON; 409 when unavailable.
- GET /analyses/{id}/report: owner-authorized original XML download.
- GET /analyses/{id}/approved-evidence: ready persisted targets only; does not invoke or imply model approval.
- POST /analyses/{id}/extract: returns 202; concurrent/double extraction is rejected.
- POST /admin/analyses: admin-only public repository upload using the same pipeline.

All artifact and payload access checks analysis ownership. Deletion removes snapshots and dependent records as well as the original report.

## Verification

Frontend TypeScript checking passed in the authoring session using --incremental false. The production build is blocked by filesystem EPERM errors in both .next and a separate build directory. Python tests cannot execute in this sandbox because the project virtual environment points to a host interpreter that is not accessible here.

Updated backend tests cover B1 projection, duplicate report handling, exact B2_o1 payload fields, no source substitution, probability validation, ownership, deletion and independent model failures. Run them locally:

```powershell
cd <repository-root>\backend
& ..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm.cmd run typecheck
npm.cmd run build
```

Live GitHub, model API, PostgreSQL migration and browser checks remain unverified in this session.
