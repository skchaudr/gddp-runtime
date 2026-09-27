## 2025-06-03 - [Fail-Open Webhook Signature Verification]
**Vulnerability:** The webhook signature verification in `scripts/intake_server.py` failed-open when the secret was not configured, returning `True` and thus accepting all payloads when `WEBHOOK_SECRET` was missing.
**Learning:** Returning early or providing a bypass for unconfigured security secrets creates a severe fail-open vulnerability, especially in components exposed via webhooks.
**Prevention:** Always enforce a fail-closed paradigm for signature and authentication verifications. If a mandatory security configuration is missing, explicitly fail the check.
