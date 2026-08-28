# Stage C — managed-service boundary probe

**Recorded:** 2026-08-28

The repository is ready for managed-service adapters. The workspace has an
attached authorized-user ADC credential: it refreshed successfully on
2026-08-28 and passed a read-only Resource Manager check for
`appeal-fleet-2026-0825` (`APPEAL Fleet 2026`, ACTIVE); the same credential
also passed a read-only check for the documented target
`onyx-yeti-506606-i9` (`My Project 27960`, ACTIVE). The active `gcloud` CLI
profile has no selected account, but its project is now set to the documented
target. Google ADK `2.8.0` is installed in the project `.venv` and the ADK
graph builds successfully. A synthetic seven-agent ADK workflow smoke run
succeeded with Gemini `3.7-flash` at the global endpoint; its aggregate result
is recorded in `evidence/adk-workflow-smoke.json`. A managed Model Armor
template was configured and measured in a separate probe. No Cloud Run, Agent
Runtime, Firestore, Pub/Sub, Gemma endpoint, or external payer deployment has
been claimed.

The local exit remains runnable through `make run-local-runtime`. Its platform
interfaces identify the future seams for case storage, event delivery,
case-scoped memory, payer separation, security inspection, and reversibility.
The next managed-service step is to wire the measured Model Armor boundary
into the workflow and decide whether to incur the cost of serving Gemma. The
scoring handoff remains deferred and uncommitted.
