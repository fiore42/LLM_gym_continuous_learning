import unittest

from llm_gym.shared.loops import LOOP_CONTRACTS, LoopType, new_loop_context


class LoopContractTests(unittest.TestCase):
    def test_all_loop_types_have_explicit_contracts(self):
        self.assertEqual(set(LoopType), set(LOOP_CONTRACTS))
        for loop_type, contract in LOOP_CONTRACTS.items():
            self.assertTrue(contract["trigger"])
            self.assertTrue(contract["purpose"])
            self.assertIn("stochastic", contract)
            self.assertIn("commit_after_success", contract)
        self.assertTrue(LOOP_CONTRACTS[LoopType.PROJECT_IMPROVEMENT]["commit_after_success"])
        self.assertFalse(LOOP_CONTRACTS[LoopType.AGENT_TASK]["commit_after_success"])
        self.assertTrue(LOOP_CONTRACTS[LoopType.MODEL_EVALUATION]["stochastic"])
        self.assertEqual(LOOP_CONTRACTS[LoopType.MODEL_EVALUATION]["children"], (LoopType.AGENT_TASK,))

    def test_child_context_has_parent(self):
        context = new_loop_context(LoopType.SOURCE_INGESTION, parent_run_id="parent")
        self.assertEqual(context["loop_type"], "SOURCE_INGESTION")
        self.assertEqual(context["parent_run_id"], "parent")
        self.assertTrue(context["run_id"])
