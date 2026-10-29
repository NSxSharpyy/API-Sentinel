# tests/test_bola_pipeline.py
"""
Day 15 / Issue 11: Master Integration Test Suite for the Complete BOLA Pipeline Chain.
"""
import unittest
import base64
from core.baseline_graph import StaticAuthorizationGraph
from core.bola_pipeline import BolaDetectionPipeline
from core.identity_parser import SecureIdentityParser

class TestCompleteBolaPipelineIntegration(unittest.TestCase):
    def setUp(self):
        # Initialize the complete security infrastructure topology chain
        self.graph = StaticAuthorizationGraph()
        self.graph.seed_authorization_baseline()
        self.pipeline = BolaDetectionPipeline(self.graph)
        self.parser = SecureIdentityParser()

    def _generate_mock_token(self, user_id: str, tenant_id: str, signature: str) -> str:
        """Helper method to construct token envelopes for integration checks."""
        payload_str = f'{{"user_id": "{user_id}", "tenant_id": "{tenant_id}"}}'
        payload_b64 = base64.b64encode(payload_str.encode()).decode().replace("=", "")
        return f"mock_header.{payload_b64}.{signature}"

    def test_full_chain_legitimate_flow_approved(self):
        """Case A: Valid crypto token + matching resource mapping must be allowed smoothly."""
        valid_token = self._generate_mock_token("usr_harish", "tenant_srm_engineering", "secure_signature_hash_99529")
        
        # 1. Identity Parsing Stage
        identity = self.parser.parse_and_verify_token(valid_token)
        self.assertTrue(identity["is_authenticated"])
        
        # 2. Decision Pipeline Stage
        decision = self.pipeline.process_access_request(identity["user_id"], "obj_data_101", identity["tenant_id"])
        self.assertTrue(decision["access_granted"])
        self.assertFalse(decision["bola_anomaly_flag"])
        self.assertEqual(decision["security_alert_status"], "AUTHORIZED_ACCESS_CLEARED")

    def test_full_chain_cross_tenant_breach_detected(self):
        """Case B: Valid user structure passing foreign tenant identifiers must trigger a critical block alert."""
        rogue_token = self._generate_mock_token("usr_harish", "tenant_malicious_attacker_corp", "secure_signature_hash_99529")
        
        identity = self.parser.parse_and_verify_token(rogue_token)
        self.assertTrue(identity["is_authenticated"])
        
        decision = self.pipeline.process_access_request(identity["user_id"], "obj_data_101", identity["tenant_id"])
        self.assertFalse(decision["access_granted"])
        self.assertTrue(decision["bola_anomaly_flag"])
        self.assertEqual(decision["security_alert_status"], "CRITICAL_CROSS_TENANT_BREACH_SUSPECTED")

    def test_full_chain_anonymous_access_denied(self):
        """Case C: Anonymous or unauthenticated sessions must be completely denied access to protected fields."""
        decision = self.pipeline.process_access_request("ANONYMOUS", "obj_data_101", "tenant_srm_engineering")
        self.assertFalse(decision["access_granted"])
        self.assertTrue(decision["bola_anomaly_flag"])
        self.assertEqual(decision["security_alert_status"], "DENIED_UNAUTHENTICATED_ANONYMOUS_SESSION")

if __name__ == "__main__":
    unittest.main()
