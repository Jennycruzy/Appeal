# Agent Registry fleet audit

Recorded: 2026-08-29

All seven discoverable Appeal roles are now manually registered in the
regional Agent Registry at `europe-west2`. Each managed record points to a
live role route on Cloud Run revision `appeal-backend-00018-w7f`:

```text
https://appeal-backend-835653516606.europe-west2.run.app/api/agents/{role}
```

The records carry the role's version, service-account principal, capability
scope, data scope, and explicit restrictions. The deployed route reads the
same validated `config/agent_registry.json` manifest; it is not a hard-coded
dashboard-only list.

The registered roles are Intake, Denial Parser, Policy Analyst, Evidence
Miner, Argument Builder, Deadline Sentinel, and Escalation Strategist. The
Submission Gate is intentionally not registered as a discoverable reasoning
agent. It remains the internal single mutation authority.

The managed resource IDs, service IDs, principals, endpoints, and aggregate
checks are recorded in
[`evidence/agent-registry-fleet.json`](../../evidence/agent-registry-fleet.json).
The MCP service/tool registration is audited separately in
[`docs/audits/mcp-governance.md`](mcp-governance.md).

## Scope proof

The live route responses expose the same scopes used by the local MCP policy
layer. In particular, Policy Analyst has no `clinical-chart.read` capability
and no external mutation capability, while Evidence Miner has a patient-scoped
`clinical-chart.read` capability and only reference-only evidence access.

The direct MCP allow/deny proof using the corresponding verified service
accounts is in the MCP audit. The remaining governance step is to send the
MCP interaction through the Agent Gateway/IAP policy path and capture the
authorization records there before promoting enforcement.
