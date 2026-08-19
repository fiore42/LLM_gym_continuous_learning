import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.eval_validate_suite import get_answer_case, validate_retrieval_cases, validate_suite


class AgentEvalSuiteTests(unittest.TestCase):
    def test_case_selector_returns_one_case_without_changing_validation(self):
        payload = json.loads(Path("config/agent_eval_suite.json").read_text(encoding="utf-8"))
        case = get_answer_case(payload, "independent_evaluation")
        self.assertEqual(case["case_id"], "independent_evaluation")
        self.assertEqual(case["expected_outcome"], "CONFLICTING_EVIDENCE")
        with self.assertRaisesRegex(ValueError, "unknown answer case_id"):
            get_answer_case(payload, "does_not_exist")

    def test_project_suite_resolves_against_local_index(self):
        payload = json.loads(Path("config/agent_eval_suite.json").read_text(encoding="utf-8"))
        result = validate_suite(payload, index_path="data/evidence.sqlite3")
        self.assertEqual(result["answer_cases"], 13)
        self.assertEqual(result["trajectory_cases"], 7)
        self.assertGreaterEqual(result["unique_evidence_references"], 10)
        self.assertEqual(result["split_counts"], {"development": 10, "holdout": 3})
        self.assertEqual(result["benchmark_status"], "PENDING_HUMAN_REVIEW")
        self.assertTrue(result["index_signature"])
        # Every answer and trajectory case is now individually reviewed. The
        # suite-level status stays PENDING_HUMAN_REVIEW until the benchmark
        # owner signs off on the suite as a whole; per-case review is a
        # prerequisite for that decision, not the decision itself.
        self.assertEqual(result["review_counts"]["answer_cases_reviewed"], 13)
        self.assertEqual(result["review_counts"]["answer_cases_total"], 13)
        self.assertEqual(result["review_counts"]["trajectory_cases_reviewed"], 7)
        self.assertEqual(result["review_counts"]["trajectory_cases_total"], 7)

    def test_optional_retrieval_expectations_resolve_against_local_index(self):
        payload = json.loads(Path("config/agent_eval_suite.json").read_text(encoding="utf-8"))
        result = validate_retrieval_cases(payload, "data/evidence.sqlite3")
        self.assertGreaterEqual(result["retrieval_cases_checked"], 3)
        self.assertEqual(result["retrieval_missing"], 0)
        self.assertTrue(result["index_signature"])

    def test_validator_rejects_unknown_required_citation(self):
        payload = {
            "evaluation_contract": {
                "required_answer_evaluations": [
                    {"name": name} for name in (
                        "evidence_relevant", "claims_supported", "citations_valid", "answer_complete")
                ]
            },
            "answer_cases": [{
                "case_id": "case",
                "split": "development",
                "review_status": "pending",
                "target_failure_modes": ["invalid_citation"],
                "expected_outcome": "SUPPORTED",
                "evidence": [{"evidence_id": "e1", "canonical_url": "https://example.test", "snippet": "text"}],
                "required_citation_ids": ["missing"],
            }],
            "trajectory_cases": [{"case_id": "trajectory"}],
        }
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_suite(payload)

    def test_validator_requires_holdout_case(self):
        payload = {
            "evaluation_contract": {
                "required_answer_evaluations": [
                    {"name": name} for name in (
                        "evidence_relevant", "claims_supported", "citations_valid", "answer_complete")
                ]
            },
            "answer_cases": [{
                "case_id": "case",
                "split": "development",
                "review_status": "pending",
                "target_failure_modes": ["unsupported_claim"],
                "expected_outcome": "SUPPORTED",
                "evidence": [{"evidence_id": "e1", "canonical_url": "https://example.test", "snippet": "text"}],
            }],
            "trajectory_cases": [{"case_id": "trajectory"}],
        }
        with self.assertRaisesRegex(ValueError, "holdout"):
            validate_suite(payload)

    def test_validator_rejects_answer_constraints_in_required_claims(self):
        """required_claims must assert what the evidence supports.

        A constraint on the answer's wording cannot be mapped to a snippet
        during review, so it belongs in forbidden_overclaims instead.
        """
        payload = json.loads(Path("config/agent_eval_suite.json").read_text(encoding="utf-8"))
        payload["answer_cases"][0]["required_claims"].append(
            "The answer must not invent a numeric result."
        )
        with self.assertRaisesRegex(ValueError, "move answer constraints"):
            validate_suite(payload)

    def test_project_suite_separates_claims_from_constraints(self):
        payload = json.loads(Path("config/agent_eval_suite.json").read_text(encoding="utf-8"))
        for case in payload["answer_cases"]:
            for claim in case["required_claims"]:
                self.assertNotRegex(
                    claim, r"(?i)must not|must avoid|should not|^the answer must",
                    f"{case['case_id']} states an answer constraint as a required claim",
                )


if __name__ == "__main__":
    unittest.main()
