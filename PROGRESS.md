# Project status — agent-referral

_A running summary of what this project is, what's built, and what's next._
_Last updated: 2026-06-13._

## What it is, in one paragraph

A runnable demonstrator that enforces **minimum-necessary and special-category
disclosure** between two AI agents acting for *different principals* — a referring
PCP's agent and a specialist's agent — during a healthcare referral. The boundary is
enforced in the **tool layer**, not in a prompt: the specialist's model can only read
patient data through a tool whose implementation routes every read through policy code,
so data the patient didn't consent to disclose **never enters the model's context**.
The thesis: *don't ask the model to keep a secret; don't give it the secret.*

## How the pieces relate (so we don't confuse them)

- **`grounded-agent-project-spec.md`** — an *earlier, separate* project idea (a grounded
  health-info RAG assistant + eval harness). NOT what this code implements. Different
  mechanics entirely. Kept for reference only.
- **`Enforcing HIPAA Minimum Necessary…pdf`** — a proposal document describing this
  referral idea at length. Aspirational; contains some unvalidated numbers (see below).
- **Neupane et al. (2025), "Towards a HIPAA Compliant Agentic AI System in Healthcare"**
  (arXiv:2504.17669) — the paper the PDF cites. It defines the three-pillar framework we
  build on: ABAC + hybrid regex/BERT PHI sanitization + immutable hash-chained audit. It
  reports a de-id benchmark (F1 98.4% on MIMIC-IV with synthetic PHI re-injected) but
  **releases no code**. Note: the "98.4%" figure in our PDF is *their* result — cite it
  as theirs, don't present it as ours.
- **`agent-referral/` (this repo)** — the actual working code. Implements the referral
  idea and two of Neupane's three pillars deterministically, plus a dynamic-consent
  escalation loop they don't have.

## What's built (and tested — 31 tests, no API key needed)

**1. Two disclosure gates** (`scope.py`)
- *Minimum-necessary relevance* (ordinary records): a record's `specialty_tag` must be in
  the referral's `relevant_tags`. Cardiology in; unrelated primary-care/pulmonology out.
- *Specific-authorization gate* (protected records): substance-use (42 CFR Part 2),
  psychotherapy notes (HIPAA §164.508(a)(2)), and HIV status (state statutes) are withheld
  **regardless of relevance** unless the patient signed a specific authorization for that
  category. This is where real granular patient consent legally lives — and it's the gate
  that makes the demo legally grounded rather than redundant (a routine treatment referral
  wouldn't otherwise require minimum-necessary trimming at all).

**2. Dynamic escalation / "clinical drift"** (`request_additional_scope`, `evaluate_escalation`)
- When the specialist surfaces an off-pathway concern, it can *ask* the patient's consent
  policy to widen scope — but it can never widen its own access. The policy grants only
  pre-consented ordinary specialties (e.g. pulmonology) and **always refuses protected
  categories** (those need a signed authorization an agent can't substitute for). Granting
  broadens the referral so the *next* read discloses more — still through `scope.py`.

**3. Stage-1 sanitization** (`sanitize.py`) — *new*
- Regex Safe Harbor de-identification on the text of records cleared for disclosure
  (SSN, phone, MRN, dates, email → labelled placeholders). Defense-in-depth: even a
  disclosed cardiology note gets its structured identifiers stripped. Deterministic, no
  dependencies. Honest limitation: regex can't reliably catch *names* — that's Stage 2.

**4. Hash-chained decision ledger** (`audit.py`) — *upgraded*
- Every decision (disclosure OR escalation, granted OR denied) is recorded as a structured,
  attributable entry — not just break-glass. Entries are sha256 hash-chained, so any later
  edit or reorder is detectable via `verify()`. Implements Neupane's "decision logs secured
  via cryptographic hashing" and HIPAA's accountability/retention expectation (45 CFR 164.316).

**5. Two agents + handoff** (`agent.py`, `pcp_agent.py`, `router.py`)
- Hand-written tool-calling loops (not the SDK auto-runner — on purpose, to see the cycle).
- PCP agent consults the specialist agent through a one-directional, depth-1 router.

**6. Eval harness** (`eval_harness.py`) — *new*
- A suite of 8 labeled scenarios whose ground-truth disclosure sets are authored from
  legal/clinical *intent* (not read back out of `scope.py`), so agreement is real signal.
  Scores and prints a results table. Current numbers:

  | metric | result |
  |---|---|
  | scenarios passed (exact disclosure set) | 8/8 |
  | **leak rate** (must-withhold disclosed) | **0.0%** (0/20) |
  | over-withhold rate (must-disclose held) | 0.0% (0/9) |
  | redaction recall (Safe Harbor masked) | 80% (4/5) |

  The 80% is deliberate honesty: regex masks the 4 structured identifiers but misses a
  name — so the harness *quantifies* exactly what the deferred Stage-2 (BERT) layer buys.
  (The harness already caught one real bug in its own fixtures — a patient/consent id
  mismatch that was silently inflating recall — which is the point of having it.)

**See it run:** `python demo.py` (no API key) walks the whole story —
`2 disclosed / 5 withheld` → identifiers redacted in the disclosed text → pulmonology
escalation GRANTED → substance-use escalation DENIED (Part 2) → re-disclosure → the full
verified ledger.

## Mapping to Neupane's three pillars

| Pillar | Their version | Ours |
|---|---|---|
| Access control (ABAC) | role/dept/clearance × resource × env | **consent-scoped, cross-principal, purpose-scoped** gates (richer in the dimension that matters) |
| Sanitization | regex (Stage 1) + BERT NER (Stage 2) | **Stage 1 built**; Stage 2 deferred |
| Audit | immutable crypto-hashed logs | **built** (hash-chained ledger + `verify()`) |

We add a fourth thing they don't: the **dynamic escalation loop** with policy-bounded
re-disclosure.

## Honest open issues

- **Label circularity (partly addressed).** For *ordinary* records we still hand-author the
  `specialty_tag` that decides relevance — so those labels are asserted, not validated. For
  *protected* records this is already fixed: the withhold reason is an objective legal rule
  (protected category + no signed authorization), not our opinion.
- **Empirical numbers now exist** (eval harness): 0% leak rate, 80% redaction recall over 8
  scenarios. Still small — needs more scenarios and an adversarial set to be convincing.
- **Stage 2 (BERT NER) not built.** Names and free-text contextual PHI aren't caught yet —
  the harness pins this at the missing 20% of redaction recall.

## Next steps (priority order)

1. **Adversarial scenarios in the harness** — plant an exfiltration instruction inside a
   *withheld* record; assert it never appears in disclosed output (boundary holds because the
   data was never in context). Adds a leak-under-attack column to the table.
2. **Code-derived relevance** — map ICD-10/SNOMED → specialty so ordinary-record labels stop
   being self-authored (closes the circularity on the other half).
3. **Grow the scenario suite** — more synthetic patients/referrals so the 0%/80% numbers are
   over a convincing N, ideally sourced from **Synthea** (no MIMIC credentials needed).
4. **Stage 2 sanitization (optional, opt-in)** — BERT/NER for names + contextual PHI, paired
   with the recall eval already in place (it will move the 80% upward, measurably).
5. Firestore swap; Cloud Run deploy.

## UI

A **Streamlit dashboard** (`app.py`) is built as a **case gallery → conversation** view (no
API key). Pick one of several sample cases (`samples.py`) at the top; see the PCP's request and
the patient's consent; then read the back-and-forth as a chat (`conversation.py`) — PCP agent →
specialist requests records → enforcement layer shows what's disclosed/withheld and *why* →
escalation granted/denied → assessment. The disclosure decisions are **real** (computed by
`scope.py`, recorded in the hash-chained ledger shown as "sealed ✓"); only the agents' wording
is templated, so it needs no key. A second tab runs the eval harness and renders the results
table. Run: `streamlit run app.py`.

A **"How it works"** explainer page leads the dashboard (the *why* behind it). Sample cases (8):
standard cardiology (+ pulmonology escalation granted), HIV specifically authorized, oncology
with genetic data withheld (+ escalation denied), consent denied, emergency break-glass,
demographics-only scheduling intake, substance-use specifically authorized, and an off-scope
request (manual-review denial).

Interactive feature (deterministic, no key):
- **What-if** — re-run a case under different consent and watch it re-decide.

The Cases tab also shows the **audit log** (the hash-chained record of every decision) with an
integrity-verified badge. The tamper-evidence itself (hash chain + `verify()`) is proven in
`test_audit.py` rather than performed as a UI gimmick; the interactive "edit the log" demo was
removed for being more confusing than illuminating. Injection-resistance is likewise proven in
`test_attack.py` (the payload sits in a withheld record and never reaches disclosed output).

To deploy a public URL (portfolio): push to GitHub → connect **Streamlit Community Cloud** →
it serves `backend/app.py`. The deterministic view is safe to expose (synthetic data, no key).
A polished full-stack FastAPI + React version with a live streaming two-agent flow is the next
UI step if wanted.

## Positioning

Build and present this as a **portfolio / demonstrator (or demo-paper) artifact** — its value
is the runnable, measurable enforcement of cross-principal, special-category consent, which
nobody has shipped. It is **not** a novel-framework research paper: ABAC, tool-layer authz,
and regex/BERT de-id are established; cite Neupane for the framework and their numbers. Keep
the code's honesty; resist the PDF's overreach (the cosine-similarity relevance gate, the
borrowed benchmark figures, the federated-learning section).
