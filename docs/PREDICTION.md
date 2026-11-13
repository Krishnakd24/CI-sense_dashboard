# Central prediction is enabled

The admin Central Classifier card now supports Save configuration and Test saved connection. The test uses the saved endpoint, model and encrypted API key; it does not submit repository evidence.

After evidence extraction, open Continue to Prediction or the Prediction tab. Select a test and click Predict flakiness. Each test has its own saved result. The backend uses its existing immutable B2_o1 payload; it does not rerun extraction or add history.

The server reads the bundled backend/app/services/prompt_b2_o1.txt (or B2_O1_PROMPT_PATH), retains both fixed examples, replaces the target placeholder, and replaces the original output requirements with prediction_output.txt (b2_o1-reasons-v2). The bundled file is an exact copy of the research prompt and remains unchanged. It sends the result as a user message, matching the research runner. A recorded template hash mismatch prevents submission. The application repository contains both the original template and its effective output requirements; no adjacent research folder is required.

The result is exactly {"flaky_probability": number, "reasons": [string, ...]}, with finite probabilities between 0 and 1 and two to four short evidence-based reasons. The UI displays a percentage and retains the original numeric value. Reasons are displayed as bullets. This is a versioned extension of the B2_o1 output contract; the target evidence fields are unchanged. The probability scale goes from green at 0%, through yellow at 50%, to red at 100%. Results remain LLM estimates.

Prediction is explicitly requested per test. Up to 20 test predictions per user per hour are allowed, sharing two execution slots with evidence extraction. Duplicate requests are rejected. Failed attempts are saved without a probability and are not automatically retried. A new analysis can be created for a new attempt after the administrator resolves a failure. Deletion is blocked while a prediction is running.

## Apply the update

Stop the backend with Ctrl+C, then run:

```powershell
cd <repository-root>\backend
& ..\.venv\Scripts\python.exe -m alembic upgrade head
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Migration 0002 already contains the prediction tables; this update requires no later migration. Refresh the frontend. Save the central configuration before testing it: Test saved connection uses the stored values, not unsaved form edits.

Frontend TypeScript checking passes. Python tests and live provider calls remain unverified from the authoring sandbox because its Python interpreter is inaccessible. Tests use mocked providers; the application never fabricates a prediction when a provider call fails.

Existing saved predictions are retained; results produced before reasons-v2 show that reasons were not recorded. New predictions persist reasons in their component output alongside the probability record. No database migration is required for this update.
