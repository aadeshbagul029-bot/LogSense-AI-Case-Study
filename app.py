import os
import re
from collections import Counter
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="LogSense AI | Incident Analyzer", page_icon="🛠️", layout="wide")

SAMPLE_LOGS = """2026-11-21 09:14:02 INFO  [payment-api] Request received payment_id=PAY-1001
2026-11-21 09:14:04 ERROR [payment-api] Upstream request timed out after 30000ms endpoint=/v1/charge payment_id=PAY-1001
2026-11-21 09:14:05 ERROR [payment-api] Database connection failed: connection pool exhausted
2026-11-21 09:14:08 WARN  [payment-api] Retry attempt 1/3 payment_id=PAY-1001
2026-11-21 09:14:12 ERROR [payment-api] Upstream request timed out after 30000ms endpoint=/v1/charge payment_id=PAY-1002
2026-11-21 09:14:13 ERROR [payment-api] Database connection failed: connection pool exhausted
2026-11-21 09:14:17 WARN  [payment-api] Retry attempt 2/3 payment_id=PAY-1002
2026-11-21 09:14:22 ERROR [payment-api] Upstream request timed out after 30000ms endpoint=/v1/charge payment_id=PAY-1003
2026-11-21 09:14:23 CRITICAL [payment-api] Payment transaction failed payment_id=PAY-1003
2026-11-21 09:14:25 INFO  [auth-service] Health check passed
2026-11-21 09:14:28 WARN  [payment-api] Elevated response latency: 31.2s
"""

PATTERNS = {
    "Timeout": re.compile(r"\b(timeout|timed out|deadline exceeded)\b", re.I),
    "Database connection": re.compile(r"(database|db).*(connection|connect)|(connection).*(pool|database)", re.I),
    "Resource exhaustion": re.compile(r"(pool exhausted|out of memory|too many open files|resource exhausted)", re.I),
    "Authentication": re.compile(r"(unauthorized|forbidden|authentication failed|invalid token)", re.I),
    "HTTP 5xx": re.compile(r"\b5\d\d\b|internal server error|service unavailable|bad gateway", re.I),
    "HTTP 4xx": re.compile(r"\b4\d\d\b|not found|bad request", re.I),
    "Network": re.compile(r"(connection refused|host unreachable|dns|network error)", re.I),
    "Crash/restart": re.compile(r"(exception|traceback|segmentation fault|crash|restarting)", re.I),
}

def classify_line(line):
    m = re.search(r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b", line, re.I)
    return m.group(1).upper().replace("WARNING", "WARN") if m else "UNCLASSIFIED"

def analyze_logs(raw):
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    levels = Counter(classify_line(x) for x in lines)
    findings = {}
    for name, pattern in PATTERNS.items():
        matches = [line for line in lines if pattern.search(line)]
        if matches:
            findings[name] = matches
    error_lines = [x for x in lines if classify_line(x) in ("CRITICAL", "FATAL", "ERROR")]
    critical_lines = [x for x in lines if classify_line(x) in ("CRITICAL", "FATAL")]
    repeated = {k: v for k, v in findings.items() if len(v) >= 2}

    # Transparent heuristic severity: callers should validate business impact.
    if critical_lines or (len(error_lines) >= 5 and ("Timeout" in findings or "Database connection" in findings)):
        severity = "Critical"
        reason = "Critical/fatal entries are present, or multiple errors coincide with timeout/database symptoms. Confirm customer and service impact."
    elif len(error_lines) >= 3 or len(repeated) >= 2:
        severity = "High"
        reason = "Several error entries or multiple repeated failure patterns indicate a potentially significant service degradation."
    elif error_lines or findings:
        severity = "Medium"
        reason = "Errors or warning patterns are present, but the supplied sample alone does not establish widespread impact."
    else:
        severity = "Low"
        reason = "No clear error-level entries or recognized failure patterns were found in the supplied sample."

    evidence = []
    if "Timeout" in findings:
        evidence.append(f"{len(findings['Timeout'])} timeout-related log line(s) were detected.")
    if "Database connection" in findings:
        evidence.append(f"{len(findings['Database connection'])} database/connection-pool line(s) were detected.")
    if "Resource exhaustion" in findings:
        evidence.append(f"{len(findings['Resource exhaustion'])} resource-exhaustion line(s) were detected.")
    if not evidence:
        evidence.append("No matching known failure signature was detected; review the raw log context.")

    causes = []
    if "Timeout" in findings and "Database connection" in findings:
        causes.append(("Possible dependency/database saturation", "Timeouts occur alongside connection-pool failures. A saturated database or exhausted application connection pool could delay payment requests.", "This is a hypothesis, not proof of database causality. Check database health, pool metrics, query latency and upstream dependency latency."))
    elif "Timeout" in findings:
        causes.append(("Possible slow or unavailable upstream dependency", "Requests exceed the logged timeout threshold.", "The log does not identify whether the delay is in the network, upstream service, or local processing."))
    elif "Database connection" in findings:
        causes.append(("Possible database connectivity or pool issue", "Connection failures or pool exhaustion appear in the sample.", "Check database availability, connection limits, credentials, network path and pool configuration."))
    elif findings:
        causes.append(("Investigate the detected failure signature", "One or more recognized error patterns were found.", "The sample is insufficient to confirm a single root cause."))
    else:
        causes.append(("No likely cause established", "No recognized failure pattern was found.", "Collect correlated application, infrastructure and dependency logs around the incident window."))

    steps = [
        "Confirm incident time window, affected application, region and number of impacted users/transactions.",
        "Check service health, error rate, latency and request volume on the affected endpoint.",
        "Correlate application logs with database, network and upstream dependency metrics for the same timestamps.",
        "Review recent deployments, configuration changes and dependency incidents; compare against the last known healthy period.",
    ]
    if "Database connection" in findings:
        steps.insert(1, "Inspect database availability, active connections, max-connection limits, connection-pool usage and slow queries.")
    if "Timeout" in findings:
        steps.insert(2, "Check upstream service latency and timeout/retry settings; verify retries are not amplifying load.")
    escalation = "Escalate to the application owner and database/platform on-call team if failures persist, transaction loss is confirmed, or customer impact is material. Follow the organization's incident process and do not change production settings without authorization."
    return {
        "lines": lines, "levels": levels, "findings": findings, "repeated": repeated,
        "errors": error_lines, "severity": severity, "reason": reason,
        "evidence": evidence, "causes": causes, "steps": steps, "escalation": escalation
    }

def ai_enhance(raw, analysis):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "AI enhancement is disabled: OPENAI_API_KEY is not configured. Rule-based analysis is active."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f"""You are assisting a Technology Operations analyst. Analyze ONLY the supplied sample logs.
Separate observed evidence from hypotheses. Never claim a root cause is confirmed unless logs prove it.
Return concise Markdown with: summary, likely causes with evidence and uncertainty, prioritized checks, escalation trigger.
Do not recommend destructive actions or production changes without authorization.
LOGS:
{raw[:18000]}
DETERMINISTIC FINDINGS:
{analysis['evidence']}
HEURISTIC SEVERITY: {analysis['severity']}"""
        response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), input=prompt)
        return response.output_text, "AI enhancement completed using the configured OpenAI model."
    except Exception as exc:
        return None, f"AI enhancement unavailable ({type(exc).__name__}). Rule-based analysis remains available."

st.title("🛠️ LogSense AI")
st.caption("Application incident triage assistant • Evidence-first log analysis")
with st.sidebar:
    st.header("Analysis settings")
    st.markdown("**Input options**")
    st.caption("Paste logs or upload a .log/.txt file. Sample data is provided for a quick demo.")
    use_ai = st.toggle("Enable AI explanation (API key required)", value=False)
    st.divider()
    st.caption("Prototype only — validate findings with monitoring, runbooks and incident procedures.")

tab1, tab2 = st.tabs(["Analyze logs", "How it works"])
with tab1:
    uploaded = st.file_uploader("Upload application logs", type=["log", "txt"])
    default_text = SAMPLE_LOGS
    if uploaded:
        try:
            default_text = uploaded.getvalue().decode("utf-8", errors="replace")
        except Exception:
            st.error("Could not read the uploaded file.")
    raw = st.text_area("Or paste logs here", value=default_text, height=260, help="One log event per line works best.")
    analyze = st.button("Analyze incident", type="primary", use_container_width=True)
    if analyze:
        if not raw.strip():
            st.warning("Please upload or paste some logs first.")
        else:
            result = analyze_logs(raw)
            st.session_state["result"] = result
            st.session_state["raw"] = raw
            st.session_state.pop("ai_text", None)
            if use_ai:
                with st.spinner("Generating AI explanation..."):
                    ai_text, status = ai_enhance(raw, result)
                    st.session_state["ai_text"] = ai_text
                    st.session_state["ai_status"] = status

    if "result" in st.session_state:
        r = st.session_state["result"]
        st.divider()
        st.subheader("Incident overview")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Severity", r["severity"])
        col2.metric("Log entries", len(r["lines"]))
        col3.metric("Errors / critical", len(r["errors"]))
        col4.metric("Patterns detected", len(r["findings"]))
        st.info(f"**Severity rationale:** {r['reason']}")
        left, right = st.columns([1, 1])
        with left:
            st.markdown("#### Log level distribution")
            counts = pd.DataFrame([{"Level": k, "Count": v} for k, v in r["levels"].items()])
            if not counts.empty:
                st.plotly_chart(px.bar(counts, x="Level", y="Count", color="Level"), use_container_width=True)
        with right:
            st.markdown("#### Detected patterns")
            if r["findings"]:
                for name, matches in r["findings"].items():
                    st.write(f"**{name}** — {len(matches)} occurrence(s)")
            else:
                st.write("No recognized patterns found.")
        st.markdown("#### Key evidence")
        for item in r["evidence"]:
            st.write("• " + item)
        for name, matches in r["findings"].items():
            with st.expander(f"{name} — {len(matches)} matching line(s)"):
                for line in matches[:12]:
                    st.code(line)
        st.markdown("#### Likely cause (hypothesis, not confirmation)")
        for title, evidence, uncertainty in r["causes"]:
            st.markdown(f"**{title}**")
            st.write("Evidence: " + evidence)
            st.caption("Uncertainty / validation: " + uncertainty)
        st.markdown("#### Recommended next steps")
        for i, step in enumerate(r["steps"], 1):
            st.write(f"{i}. {step}")
        st.warning("**Escalation guidance:** " + r["escalation"])
        if st.session_state.get("ai_text"):
            st.markdown("#### AI-generated explanation")
            st.caption(st.session_state.get("ai_status", ""))
            st.markdown(st.session_state["ai_text"])
        elif st.session_state.get("ai_status"):
            st.caption(st.session_state["ai_status"])
        # Shareable concise report
        report = f"""LOGSENSE AI — INCIDENT SUMMARY
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Severity: {r['severity']}
Reason: {r['reason']}

KEY EVIDENCE
""" + "\n".join("- " + x for x in r["evidence"]) + "\n\nLIKELY CAUSE (HYPOTHESIS)\n" + "\n".join(f"- {x[0]}: {x[1]} Validation: {x[2]}" for x in r["causes"]) + "\n\nNEXT STEPS\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(r["steps"], 1)) + "\n\nESCALATION\n" + r["escalation"] + "\n\nNote: This is a decision-support prototype. Verify against telemetry and operational runbooks."
        st.download_button("Download incident summary (.txt)", report, file_name="incident_summary.txt", mime="text/plain")
with tab2:
    st.subheader("Analysis approach")
    st.markdown("""
1. **Ingestion:** read uploaded or pasted text logs.
2. **Normalization:** split into non-empty lines and identify severity tokens.
3. **Pattern detection:** match known signatures such as timeouts, database connection errors, HTTP 5xx and resource exhaustion.
4. **Triage:** apply transparent heuristic severity rules based on observed signals and error counts.
5. **Explanation:** optionally ask an LLM to produce a concise explanation while explicitly separating evidence from hypotheses.
6. **Action:** provide prioritized checks, escalation guidance and a downloadable summary.
    """)
    st.info("Severity is a prototype heuristic, not an ITIL policy or an automatic production incident declaration.")
    st.markdown("**Safety controls:** sample data only; no production connectivity; no automated remediation; AI output must be reviewed by an engineer.")
