# LogSense AI — Application Incident Analyzer

A small Streamlit prototype for Technology Operations teams. It accepts sample application logs, detects repeated failure patterns, estimates severity, suggests checks, and creates a shareable incident summary.

## Features
- Upload `.log` / `.txt` files or paste logs.
- Detect log levels and patterns: timeouts, database connection/pool failures, resource exhaustion, authentication, HTTP 4xx/5xx, network errors and crashes.
- Show matching evidence lines and repeated occurrences.
- Classify severity as Critical / High / Medium / Low using visible heuristic rules.
- Explain likely causes as hypotheses, with evidence and validation guidance.
- Provide prioritized troubleshooting and escalation guidance.
- Download a concise incident summary.
- Optional OpenAI explanation using the Responses API; deterministic analysis works without an API key.

## Setup
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit (usually http://localhost:8501).

## Optional AI setup
Set an API key in your terminal before launching:

**PowerShell**
```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-4.1-mini"
streamlit run app.py
```

**macOS/Linux**
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-4.1-mini"
streamlit run app.py
```

The API key is read from an environment variable; do not commit it to Git. If the key is absent or the API call fails, rule-based analysis remains available. Model availability and API access depend on the account.

## Approach
1. Parse non-empty log lines and identify severity tokens.
2. Match known patterns using regular expressions.
3. Count repeated patterns and error-level entries.
4. Apply a transparent heuristic severity rule.
5. Build evidence-led cause hypotheses and troubleshooting checks.
6. Optionally use an LLM to explain the supplied evidence. The prompt asks the model to distinguish evidence from assumptions and avoid unapproved production changes.

## AI tools/models used
- **Core analysis:** Python regex and counters (deterministic, inspectable).
- **Optional explanation:** OpenAI API via the Python SDK, default model name `gpt-4.1-mini` (configurable with `OPENAI_MODEL`).
- The AI explanation is supplementary; severity and pattern counts are computed locally.

## Assumptions
- Input is plain-text application logs, preferably one event per line.
- Log levels appear as words such as INFO, WARN, ERROR, CRITICAL or FATAL.
- Pattern matching is based on English-language error messages.
- Severity thresholds are demonstration heuristics, not an organization's approved incident policy.
- A log sample may not contain enough context to establish a confirmed root cause or customer impact.

## Testing
Manual checks to perform:
1. Paste `samples/payment_incident.log`; expect timeout and database connection patterns, repeated matches, and Critical severity due to a CRITICAL event.
2. Paste a healthy INFO-only sample; expect Low severity and no detected failure patterns.
3. Paste one isolated ERROR; expect Medium severity.
4. Upload the sample `.log` file and verify results match paste input.
5. Run with AI disabled / no API key; confirm local analysis and report download work.
6. If API access is configured, enable AI explanation and verify the response labels uncertainty rather than claiming a confirmed cause.

## Limitations
- Regex matching can miss unfamiliar messages or produce false positives.
- Severity does not currently use service criticality, SLOs, business hours, customer counts or formal incident policy.
- No correlation IDs, distributed tracing, metrics, CMDB, ticketing or alerting integration.
- LLM output may be incomplete or incorrect; always validate against logs, telemetry and runbooks.
- No production data or systems are accessed. No automatic remediation is performed.

## Demo flow (2–3 minutes)
1. Launch the app and point out the sample log input.
2. Click **Analyze incident**.
3. Show the severity and rationale.
4. Expand timeout and database evidence; explain why the likely cause is only a hypothesis.
5. Walk through recommended checks and escalation criteria.
6. Download the incident summary.
7. Briefly explain optional AI mode and limitations.

## Repository hygiene
Do not commit `.env`, API keys, customer logs, credentials or production data. Use sample/simulated logs only.
