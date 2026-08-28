# Stage B — ADK case exit

**Recorded:** 2026-08-28

`make run-adk-case` ran one synthetic Appeal case through the Google ADK
`2.8.0` `Runner` at Vertex AI using Gemini `3.7-flash`. The ADK graph emitted
one event from each of the seven named roles: Intake, Denial Parser, Policy
Analyst, Evidence Miner, Argument Builder, Deadline Sentinel, and Escalation
Strategist. The input denial was an image-only synthetic PDF passed as an
`application/pdf` multimodal part. The fixture was generated in memory and
was not persisted.

The aggregate ADK and control-plane result is recorded in
[`evidence/adk-stage-b-case-exit.json`](../../evidence/adk-stage-b-case-exit.json).
It records seven ADK events, all expected role authors, four denial source
spans, a two-leaf `AND` criterion with both leaves satisfied, and zero model
dissent. The deterministic Appeal control plane then moved from
`AWAITING_CLINICIAN` to `AWAITING_DETERMINATION` after approval, cleared the
criterion tree, Evidence Floor, security, and clinician vetoes, and performed
exactly one submission mutation. The receipt ledger contained 18 events and
remains outside the repository.

Gemini supplied advisory role outputs only. The deterministic state machine,
criterion evaluator, Evidence Floor, Veto Combinator, and clinician approval
remain authoritative. The security boundary used for this case is the local
fail-closed fallback; the separate managed Model Armor and Gemma MaaS probes
are recorded in their own evidence and are not yet wired into the default
workflow.

This is the Stage B product exit on synthetic data. It is not a full Appeal
evaluation, a regulator-ground-truth comparison, or a production ADK/Agent
Runtime deployment. The real policy criterion extraction and validation item
from Stage A3 remains open.
