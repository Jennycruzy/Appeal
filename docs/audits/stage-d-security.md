# Stage D — managed security probe

**Recorded:** 2026-08-28

The selected Google Cloud target is `onyx-yeti-506606-i9` in
`europe-west2`. Model Armor was enabled for the project and the managed
template `appeal-tripwire-v1` was created with the supported basic sensitive-
data filter and prompt-injection/jailbreak filter. The regional malicious-URI
filter was not available in `europe-west2`, so it was not represented as a
passing capability.

`make measure-model-armor` submitted seven synthetic, labeled fixtures across
the inbound document, egress-to-Zone-C, and memory-bank surfaces. All seven
provider calls succeeded. The aggregate report is
[`evidence/model-armor-measurement.json`](../../evidence/model-armor-measurement.json):
true positives `3`, true negatives `3`, false positives `0`, false negatives
`1`, precision `1.0`, recall `0.75`, and false-positive rate `0.0`. Fixture
content is omitted from the report and `fixture_content_persisted` is false.

This is a real managed-provider measurement, but the template is not yet
wired into the default local workflow boundary. The local boundary remains
fail-closed and its fallback measurement remains separately labeled.

A synthetic Vertex AI smoke request to Gemini `3.7-flash` succeeded at the
global endpoint. Direct publisher inference for `gemma-3-1b-it` was not
available. Gemma therefore still needs a served Vertex endpoint before its
tripwire can be measured; no GPU endpoint was deployed because that creates an
ongoing billable resource and requires explicit authorization.

No real patient data or case identifiers were sent in these probes.
