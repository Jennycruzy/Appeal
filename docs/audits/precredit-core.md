# Pre-credit deterministic core audit

Audit date: 2026-08-25

This is local work permitted by the specification's pre-credit workstream. It
does not claim that Phase 1 has started or that Phase 0 is complete.

## Evidence

- `src/appeal_core/state_machine.py` contains the explicit state graph,
  immutable case records, idempotency handling, clinician-signature gate,
  evidence references, decision source, and deadline lookup.
- `config/deadlines.yaml` is a JSON-compatible YAML document loaded at runtime.
  The only executable statutory clocks currently recorded are the CMS-0057-F
  seven-calendar-day standard decision window and 72-hour expedited decision
  window, with official CMS citations.
- Program-specific appeal deadlines are represented as `unverified` and throw
  `UnverifiedDeadline` if code attempts to calculate them. No appeal deadline
  was guessed.
- `tests/test_state_machine.py` ran with:

  ```text
  PYTHONPATH=src python3.12 -m unittest discover -s tests -v
  ```

  Result: 7 tests ran and all passed. The tests cover valid workflow order,
  invalid transitions, the clinician signature gate, abstention, reachable
  abandoned-deadline state, duplicate delivery idempotency and conflict,
  verified versus unverified deadlines, serialization, and stable fingerprints.
- `python3.12 -m py_compile` passed for the core and test modules.

## Gaps

- `mypy` is not installed on this Mac, so the strict static check has not yet
  run. The repository includes strict configuration in `pyproject.toml`; the
  dependency must be installed before the CI gate can be meaningful.
- The case state machine has no persistence adapter yet. Firestore integration
  remains a cloud-dependent task after Phase 0 model and component discovery.
- The receipt ledger and hash-chain verifier are not yet implemented.

## Blockers

- The exact appeal clocks are program-specific and have not been verified from
  a selected governing program. The state machine intentionally refuses to
  calculate them instead of using a remembered number.
- Phase 0 billing/model discovery and real-corpus access remain blocked in
  `docs/audits/phase-0.md`.

## Exit status

The deterministic workflow core is locally tested. The cloud, corpus, and
statutory-appeal-clock work is not complete and must not be represented as
complete in the README or demo.
