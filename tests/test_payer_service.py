from __future__ import annotations

import unittest
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseStateMachine, DeadlineCatalog
from appeal_payer_service import PayerHttpApi, PayerService


class PayerServiceTests(unittest.TestCase):
    def test_private_payer_service_returns_reference_only_decision(self) -> None:
        workflow = AppealWorkflow(CaseStateMachine(DeadlineCatalog.from_path(Path("config/deadlines.yaml"))))
        result = workflow.run(demo_input(case_id="case-payer-service", tenant_id="tenant-demo-payer-service"))
        assert result.context is not None
        observations = [
            {
                "observation_id": item.observation_id,
                "leaf_criterion_id": item.leaf_criterion_id,
                "disposition": item.disposition.value,
                "evidence_type": item.evidence_type,
                "references": [
                    {"kind": ref.kind, "uri": ref.uri, "sha256": ref.sha256}
                    for ref in item.references
                ],
            }
            for item in result.context.observations
        ]

        response = PayerService().determine(
            {
                "tenant_id": "tenant-demo-payer-service",
                "case_id": "case-payer-service",
                "idempotency_key": "case-payer-service:payer:1",
                "observations": observations,
            }
        )

        self.assertEqual(response["status"], "favorable")
        self.assertEqual(response["criterion_status"], "satisfied")
        self.assertEqual(response["external_mutation_count"], 0)
        self.assertFalse(response["mutation_authority"])
        self.assertTrue(response["synthetic_only"])

    def test_payer_http_rejects_unbounded_or_malformed_input(self) -> None:
        api = PayerHttpApi()
        status, value = api.handle(
            "POST",
            "/api/payer/determine",
            {
                "tenant_id": "tenant-demo-payer-service",
                "case_id": "case-payer-service",
                "idempotency_key": "case-payer-service:payer:1",
                "observations": [],
                "chart": "must not be accepted",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(value["error"], "payer_request_rejected")

    def test_payer_health_declares_no_case_store_or_mutation_authority(self) -> None:
        status, value = PayerHttpApi().handle("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertFalse(value["case_store"])
        self.assertFalse(value["mutation_authority"])


if __name__ == "__main__":
    unittest.main()
