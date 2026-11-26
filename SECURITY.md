# Security & Operational Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| < 0.4.0 | :x:                |

## Reporting a Vulnerability

If you discover a security issue in `kinetopus_pro` (for example, template XSS in `report.html`/`widget.html`, path traversal in `service.py`, SSRF in webhook dispatch, or dependency vulnerabilities), please report it responsibly **without opening a public GitHub Issue first**:

- **Email:** [ussaapontejuandiego@gmail.com](mailto:ussaapontejuandiego@gmail.com) (Subject: `[SECURITY] KineTopus-Analyst`)
- **GitHub:** Private Vulnerability Reporting on `JuanDie778/KineTopus-Analyst` (when enabled)

Please include steps to reproduce, affected version, and potential impact. You will receive an acknowledgment as soon as possible.

## Operational Security Notes

1. **Local-First HTTP Binding (`kinetopus-serve`):**
   - By default, `kinetopus-serve` binds to `127.0.0.1:8000` for local workstation use.
   - `POST /api/v1/analyze` is unauthenticated by design for local use (protected by a process-wide `threading.Lock` against 16 GB RAM exhaustion). **Do not expose `kinetopus-serve` directly to the public internet** without placing it behind an authenticated reverse proxy (TLS, rate limiting, and access tokens).
2. **Outgoing Webhooks (`--webhook-url`):**
   - `KineTopusAlertEngine` performs outgoing HTTP `POST` requests only when `--webhook-url` is explicitly provided by the operator. Validate destination URLs in automated deployments.
3. **Offline Reports & Assets:**
   - Generated `report.html` and `widget.html` files are self-contained (`plotly.min.js` or pure SVG) and do not phone home or load external trackers.
4. **No Financial Advice:**
   - KineTopus-Analyst is a quantitative analysis and computational physics software tool. Nothing produced by the CLI, reports, feeds, widgets, or APIs constitutes investment or financial advice.
