# CI-Sense — Evidence and flakiness prediction

See [prediction setup](docs/PREDICTION.md) for central-model testing and prediction, and [Stage 2 contracts](docs/STAGE_2.md) for migration 0002 and evidence JSON. The B2_o1 prompt contains private research examples and is deliberately excluded. Provide the original prompt privately through B2_O1_PROMPT_PATH; prediction will not run without it.

Next.js / TypeScript frontend, FastAPI backend, PostgreSQL, SQLAlchemy and Alembic. GitHub-only authentication uses the GitHub App's OAuth web flow; the same app's user access token limits repository access to the intersection of the user's permissions and the app installation's selected repositories.

**Implementation status:** source is implemented; runtime verification is outstanding in the authoring session. Python is installed on the user's machine but inaccessible to the execution sandbox. npm registry access was denied with EACCES. No live OAuth, database, S3, LLM, browser, or production deployment has been verified. Do not treat this as a production-validated release. Run the checks below locally before deployment.

## Scope and reuse

- Manual JUnit upload → failure selection → Extract Evidence → persisted Evidence Review.
- Admin public-repository testing shares the exact same pipeline; its records are separated from personal project history.
- Continue to Prediction opens the selected test’s prediction controls. Prediction uses saved B2_o1 evidence and the original research prompt. Probabilities are real provider outputs between 0 and 1; failures have no fabricated result. GitHub Actions integration is not implemented.
- The original research files are unchanged. `app/services/xml_parser.py` adapts the extraction rules in `../failing_logs_XMLS/extract_test_failure_details.ps1` from a CSV-oriented PowerShell batch job into a safe upload parser. It preserves separate testcase entries, failure/error messages, original problem attributes/text, stack traces, expected/actual values and testcase output. DTDs and entities are rejected.
- `java_methods.py` reuses the comment/string-aware method extraction from `../failing_logs_XMLS/extract_test_code.py`. The current source resolver supports the Java JUnit research corpus. Unmatched, inherited or overloaded methods are marked missing/ambiguous, with a full source file when available. Other languages are not silently guessed.
- XML evidence is inspected manually; no XML LLM is configured or invoked.

## Local setup (PowerShell)

Prerequisites: Python 3.11+, Node 20.9+ (Node 24 works with this project), PostgreSQL 17 or Docker Desktop.

From the `ci-sense` directory:

```powershell
Copy-Item .env.example .env
docker compose up -d db
# Or create a PostgreSQL database and update DATABASE_URL.

$pythonExe = (Get-Command python).Source
& $pythonExe -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the generated value in ENCRYPTION_KEY in your private .env file. Fill GitHub settings and your numeric ADMIN_GITHUB_IDS. No real keys belong in source or this chat. Keep the encryption key outside database backups, and back it up in a secrets manager; losing it makes encrypted credentials unreadable. Do not replace it without migrating existing encrypted values.

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m alembic upgrade head
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

In a second terminal, from `ci-sense`:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run dev
```

Open http://localhost:3000. Use `npm.cmd` when PowerShell blocks npm.ps1. NEXT_PUBLIC_API_URL is the public backend address, never a credential. Both localhost ports share the same site for cookies.

## GitHub setup

1. Register a **GitHub App**. Set Homepage URL to your frontend.
2. Set callback URL to `http://localhost:8000/auth/callback` locally, or your deployed HTTPS backend URL plus `/auth/callback`.
3. Request repository **Contents: read-only** and Metadata (implicit read access). No Actions permission is needed.
4. Disable webhooks unless separately needed. No webhook receiver is implemented.
5. Use the app's **Client ID and client secret** as GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET. Set GITHUB_APP_SLUG to its URL slug.
6. Set ADMIN_GITHUB_IDS to explicitly authorized numeric GitHub IDs, not usernames. Empty means no administrators.
7. Authorize the app through Sign in with GitHub. Install it on selected repositories using Manage GitHub App access. Refresh repository access afterwards. Admin public testing needs login and admin authorization, but no repository installation.
8. Use normal GitHub App user access tokens. If a token expires or is revoked, sign in again; sessions expire after eight hours. Installation changes and user permissions are enforced by GitHub on repository requests.

A separate OAuth App and installation private key are not required: this uses the GitHub App's user-to-server OAuth protocol for both login and authorized repository reads. Tokens are encrypted at rest and never sent to the browser.

## Models and admin testing

1. Sign in as an explicitly configured administrator.
2. Open Model connections. Save the Git Diff Summarizer settings. Enter exact provider model identifiers.
3. OpenAI preset: `https://api.openai.com/v1`, OpenAI-compatible protocol.
4. Anthropic preset: `https://api.anthropic.com/v1`, native Anthropic Messages protocol.
5. Gemini's OpenAI-compatible endpoint can use `https://generativelanguage.googleapis.com/v1beta/openai` with the OpenAI-compatible protocol. Use the provider's documented model identifier and compatibility support.
6. Custom endpoints must be HTTPS on port 443 and on LLM_ALLOWED_HOSTS. Only add trusted provider-controlled hosts. Redirects and proxy environment inheritance are disabled for model requests. DNS must resolve to public addresses.
7. Test saved connections. Replacing a key takes effect without redeployment. Leaving the password blank retains the old key. No saved key is returned to the UI.
8. In Testing workspace, choose New extraction, enter a public repository and commit SHA, upload XML, select tests, and extract. The app saves everything automatically.
9. A summarizer failure saves a failed component status while retaining independently retrieved source and raw diff. The UI uses the requested friendly message; administrators see sanitized stage and error category/status. There are no automatic retries.

The Central Classifier supports saved connection testing and explicit per-test prediction. See docs/PREDICTION.md. Its prompt path must point to the original B2_o1 research file.

## Persistence and execution

- PostgreSQL stores users, encrypted GitHub tokens, hashed sessions, personal projects, analyses, original parsed evidence, B1-compatible report objects, diff and summary, source and line information, and encrypted global model configuration.
- Reports are stored under a random per-analysis key. Local development storage is never mounted as a public web directory. S3 uses the same private server-side interface.
- Run **one backend process**. Two execution slots and at most four running/pending analyses bound in-process work. FastAPI BackgroundTasks handles execution; no Redis/Celery required.
- On restart, interrupted running analyses are marked failed; they are not retried.
- Limits: 5 MB XML; 200 failing entries; 20 selected tests; 10 extractions/user/hour; 30 uploads/user/hour; 20 connection checks/admin/hour. Provider input is bounded and excess input fails explicitly instead of being silently truncated.
- Analysis deletion deletes its unique report object and its evidence rows. Running analyses cannot be deleted. If storage deletion fails, the record remains available for another deletion attempt.
- Source lookup always uses the fully resolved selected commit SHA. Merge comparisons use the first parent. Root commits fail clearly. Comparisons at GitHub's 300-file limit fail explicitly; omitted binary/large patches are identified in evidence.
- `GET /analyses/{id}/approved-evidence` is an owner-protected read-only handoff for future Layer 2. It does not imply an approval workflow or call a model.
- History currently returns the latest 200 analyses; older records remain accessible by their saved evidence-review URL.

## Private object storage and deployment

For production set S3_BUCKET and AWS_DEFAULT_REGION; use a workload IAM role granting GetObject/PutObject/DeleteObject only on the application bucket. Block all public access, require HTTPS and encryption at rest, and avoid public bucket policies. S3_ENDPOINT_URL is an operator-managed setting for compatible private storage. The client never receives storage credentials or signed public artifact links. For local storage, mount a durable volume and restrict its filesystem permissions.

Use a secrets manager for ENCRYPTION_KEY, GitHub client secret, database password and cloud credentials. Use strong database credentials; compose.yaml credentials are local development only.

Deploy Next.js and FastAPI separately behind HTTPS on same-site domains (for example app.example.com and api.example.com). Set FRONTEND_URL, PUBLIC_API_URL, NEXT_PUBLIC_API_URL and GitHub callback accordingly. Set COOKIE_SECURE=true. Cross-site domain deployments require a deliberate cookie/CSRF configuration change; the default uses SameSite=Lax.

Do not expose PostgreSQL publicly. Run migrations before serving traffic. Disable request-body logging and access logging on OAuth callback URLs in your reverse proxy/APM. Add an outbound firewall allowing only GitHub, storage and approved model providers; hostname allowlisting assumes operator-trusted provider DNS and is not a substitute for network egress controls. Set proxy upload limits to 6 MB and sensible connection limits. Back up the database and private artifacts together.

The supplied Sites hosting runs JavaScript Workers and does not host this Python/PostgreSQL architecture. This deliverable is repository source, not a deployed Site.

## Verification

Backend tests use SQLite and mocked GitHub/LLM transports. Mocks exist only in tests and are not a fallback in the application.

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m pytest -q
# Real PostgreSQL migration check, using your configured development database:
& ..\.venv\Scripts\python.exe -m alembic upgrade head
& ..\.venv\Scripts\python.exe -m alembic check
Set-Location ..\frontend
npm.cmd run typecheck
npm.cmd run build
```

Before deployment, verify a real public-repository extraction with your configured providers; refresh and reopen it; delete it and inspect object cleanup; test a non-admin account's 403/404 boundaries; connect an authorized private repository; revoke its app access and verify subsequent reads fail. Inspect root commits, ambiguous source methods and provider credential failures. Provider calls cost money and cannot be verified without your configured accounts.

See tests for parser fidelity, entity rejection, ownership, admin guards, CSRF, key redaction, persistence, first-parent selection, complete evidence flow with mocked providers, and saved failure states.
