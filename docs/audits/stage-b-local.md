# Stage B — local fleet and control-plane audit

**Recorded:** 2026-08-28

The local product path now executes a synthetic case through the seven named
roles and the deterministic controls that surround them:

- Intake blocks an instruction-bearing denial before parsing and moves the case
  to `QUARANTINED`.
- Denial Parser, Policy Analyst, Evidence Miner, and Argument Builder produce
  source spans, a versioned criterion match, scoped FHIR references, and an
  Evidence-Floor-checked draft.
- The Veto Combinator evaluates the criterion tree, Evidence Floor,
  Model-Armor/Gemma placeholder boundary, and clinician veto. No model result
  grants permission to file.
- The clinician co-signature is required before the single local submission
  mutation; the receipt ledger records it once.
- Deadline Sentinel binds each case to the configured statutory clock and can
  close an expired case as `CLOSED_ABANDONED_DEADLINE`.
- An unfavorable determination is handed to Escalation Strategist, which
  rebuilds the argument from current evidence rather than reusing old prose.

The local platform adapter adds a reference-only event spine with duplicate
delivery idempotency, optimistic case storage, exact tenant/case memory
scoping, a separate payer criterion copy that receives observations only, and
an append-only reversibility journal. The end-to-end synthetic runtime closes
the favorable path and writes only public metadata plus hashes to its output.

The local security measurement harness also runs labeled synthetic controls and
attack fixtures across inbound, egress, and memory surfaces. Its report is
explicitly labeled `local_deterministic_fallback`; it is preparation for, not a
substitute for, managed Model Armor and Gemma measurements.

The role boundary is also recorded in `config/agent_policies.json` and parsed
by `AgentPolicyRegistry`: Policy Analyst has no chart capability, Evidence
Miner is patient-scoped, and only Submission Gate can perform an external
mutation. This is a local policy assertion, not a deployed IAM proof.

`LocalAppealService` exposes the case-board lifecycle as separate operations:
open a case, pause for clinician approval, approve through the gate, and later
receive a payer determination. A test advances the determination six hours
after submission and still records exactly one submission mutation.

`LocalHttpApi` and `scripts/run_local_api.py` expose the same lifecycle on
loopback for integration testing. The endpoint explicitly reports
`authenticated: false`; Firebase/Auth/IAM must be added before any network
deployment.

This local path is now paired with a real synthetic ADK case exit. The ADK
`Runner` executed all seven roles with an image-only PDF input, and the
aggregate result is recorded in `evidence/adk-stage-b-case-exit.json`, with
the audit narrative in `docs/audits/stage-b-adk-exit.md`. It does not turn the
Cloud Run facade into a managed Agent Runtime deployment or a full Appeal
evaluation. The separate managed Model Armor and Gemma MaaS measurements are
recorded in `evidence/model-armor-measurement.json` and
`evidence/gemma-tripwire-measurement.json`; neither replaces the local
security boundary in the default workflow. The scoring handoff remains
intentionally deferred and uncommitted.
