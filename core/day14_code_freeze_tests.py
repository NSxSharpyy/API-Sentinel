# core/day14_code_freeze_tests.py
"""
Day 14 / Issue 9: Real Detection Engine Integration & Master Code Freeze Verification Suite.
"""
import unittest
import json
from baseline_graph import StaticAuthorizationGraph
from bola_pipeline import BolaDetectionPipeline
from day_10_bfla_detection_engine import CanonicalBFLAEngine

class TestBehavioralDetectionEngineFreeze(unittest.TestCase):
    def setUp(self):
        # Action A: Initialize the REAL BOLA baseline infrastructure graph and pipeline layers
        self.graph = StaticAuthorizationGraph()
        self.graph.seed_authorization_baseline()
        self.bola_pipeline = BolaDetectionPipeline(self.graph)
        
        # Action B: Initialize the REAL BFLA canonical protection engine layer
        self.bfla_engine = CanonicalBFLAEngine()

    def test_bola_real_engine_unauthorized_access_blocked(self):
        """Boundary R: Exercise the real BOLA engine pipeline against multi-tenant perimeter breaches."""
        # Attacker attempts to forge request path targeting Tenant data using cross-tenant inputs
        response = self.bola_pipeline.process_access_request("usr_harish", "obj_data_101", "tenant_hacker_leak")
        self.assertFalse(response["access_granted"])
        self.assertTrue(response["bola_anomaly_flag"])
        self.assertEqual(response["security_alert_status"], "CRITICAL_CROSS_TENANT_BREACH_SUSPECTED")

    def test_bfla_real_engine_standard_user_blocked(self):
        """Boundary S: Exercise the real BFLA engine layer against administrative privilege escalation."""
        # Standard user configuration maps an unprivileged session calling protected endpoints
        response = self.bfla_engine.verify_bfla_clearance("standard_user", "/api/v1/admin/management")
        self.assertFalse(response["access_authorized"])
        self.assertEqual(response["alert_status"], "UNAUTHORIZED_ADMINISTRATIVE_ACCESS_DENIED_BFLA")

if __name__ == "__main__":
    print("Executing Day 14 Behavioral Detection Engine Master Code Freeze Suite Verification...\n")
    # Execute the structured automated validation runner suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBehavioralDetectionEngineFreeze)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    freeze_log = {
        "real_tests_executed": result.testsRun,
        "failures_count": len(result.failures),
        "errors_count": len(result.errors),
        "phase_2_master_code_freeze_status": "SUCCESSFULLY_LOCKED_AND_FROZEN" if result.wasSuccessful() else "FAILED"
    }
    print("\nFinal Master Code Freeze Telemetry Report:\n", json.dumps(freeze_log, indent=4))
