# Receipt-Consumer Impact Scan

Date: 2026-07-07
Branch: integrity-lane-draft
Change: VerdictReceipt gained `criteria_verdict` (Verdict|None) and `integrity` (IntegrityOutput|None), both None-optional. Top-level `verdict` now carries the combined (worst-of) value.

## Surfaces scanned

### 1. bridge._parse_cli_summary
**Status: COMPATIBLE (updated)**
Parses the last JSON object from CLI stdout. The CLI summary now includes `criteria_verdict` and `integrity` when present (added in this scan). The bridge returns the full dict, so new fields flow through automatically to return_router. No parse changes needed — `_parse_cli_summary` just does `json.loads` on the last JSON block.

### 2. cli.py summary printing
**Status: UPDATED**
Was printing only `verdict`, `criteria_confidence`, `completeness_status`, `required_next_action`. Now also prints `criteria_verdict` and `integrity` (with full findings) when present. This is what the bridge parses, so the integrity data flows to return_router and the retry loop.

### 3. receipt_sink.py
**Status: COMPATIBLE (no change needed)**
Writes the full `VerdictReceipt` pydantic model to disk as JSON. The new fields (`criteria_verdict`, `integrity`) are None-optional, so pydantic handles them transparently. Old receipts without these fields still parse — both default to None.

### 4. return_router.py
**Status: COMPATIBLE (updated by retry loop)**
Stores the bridge summary dict in `results.acceptance_check`. New fields (`criteria_verdict`, `integrity`) flow through automatically. The retry loop (item 2.4) extracts `integrity` from the verification dict for the `should_retry` check.

### 5. Existing receipts in gddp-config/verification-runtime-live/
**Status: COMPATIBLE (no change needed)**
Existing receipts were written before the `criteria_verdict`/`integrity` fields existed. Both are None-optional on `VerdictReceipt`, so old receipts parse with both fields defaulting to None. The top-level `verdict` on old receipts is unchanged (it was the criteria verdict; now it's the combined verdict, but for old receipts without integrity, combined = criteria).

### 6. test_bridge.py
**Status: UPDATED**
Existing bridge tests mock `subprocess.run` and check `verification_status`, `verdict`, `receipt_path` from the parsed summary. New tests added for `--integrity on` default and `GDDP_INTEGRITY_MODE=off` override. Existing tests still pass because the CLI summary's new fields are additional, not replacing.

### 7. test_return_router.py
**Status: COMPATIBLE (no change needed)**
Mocks `verify_job_return` with a dict that doesn't include `criteria_verdict` or `integrity`. The return_router's retry logic checks `verification.get("integrity")` which returns None for these mocks, so `should_retry` returns False and the job routes to awaiting_review as before.

## Conclusion

No breaking changes. The receipt contract change is backward-compatible (both new fields are None-optional). The CLI summary was updated to include the new fields so they flow through the bridge to the return_router and retry loop. No existing receipt consumer breaks.
