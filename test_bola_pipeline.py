import unittest
import base64
import json
from core.baseline_graph import StaticAuthorizationGraph
from core.bola_pipeline import BOLAHeuristicPipeline

class TestBOLAHeuristicPipeline(unittest.TestCase):

    def setUp(self):
        self.graph = StaticAuthorizationGraph()
        mock_config = {
            "users_ownership": {
                "usr_harish77": ["doc_01", "report_srm_02"]
            },
            "roles_capabilities": {
                "student": ["GET", "POST"]
            }
        }
        self.graph.seed_authorization_baseline(mock_config)
        self.pipeline = BOLAHeuristicPipeline(self.graph)

        payload = {"user_id": "usr_harish77", "tenant_id": "axlero_corp", "scopes": ["student"]}
        payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        self.mock_token = f"abc.{payload_b64}.xyz"

    def test_valid_bola_access(self):
        log_input = {
            "headers": {"Authorization": f"Bearer {self.mock_token}"},
            "role": "student",
            "object_id": "doc_01",
            "action": "GET"
        }
        processed, is_anomaly = self.pipeline.process_request(log_input)
        self.assertFalse(is_anomaly)

    def test_invalid_bola_violation(self):
        log_input = {
            "headers": {"Authorization": f"Bearer {self.mock_token}"},
            "role": "student",
            "object_id": "doc_secret_99",
            "action": "GET"
        }
        processed, is_anomaly = self.pipeline.process_request(log_input)
        self.assertTrue(is_anomaly)
        self.assertEqual(processed["security_alerts"]["alert_type"], "BOLA_VIOLATION_DETECTED")

if __name__ == "__main__":
    unittest.main()
