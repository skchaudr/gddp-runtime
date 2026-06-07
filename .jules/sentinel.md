## 2026-06-08 - Enforce HTTPS for API Requests
**Vulnerability:** The application was making API requests to `http://export.arxiv.org` over plain HTTP instead of HTTPS, exposing it to potential Man-in-the-Middle (MITM) attacks where an attacker could intercept or modify the data in transit.
**Learning:** External API dependencies and endpoints must always be accessed securely using HTTPS by default to ensure data integrity and confidentiality. Sometimes developers default to HTTP during early testing and forget to update it.
**Prevention:** Always verify that URLs in code and configurations use the `https://` protocol scheme. Consider implementing automated linting rules or code scanning tools that flag any `http://` URLs in source code to prevent regressions.
