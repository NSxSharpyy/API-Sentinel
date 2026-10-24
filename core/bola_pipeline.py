# core/bola_pipeline.py
"""
Day 2 / Issue 2: Hardening the BOLA Detection Against Anonymous Access Bypasses.
"""
from baseline_graph import StaticAuthorizationGraph

class BolaDetectionPipeline:
    def __init__(self, auth_graph_instance: StaticAuthorizationGraph):
        self.graph = auth_graph_instance

    def process_access_request(self, user_id: str, object_id: str) -> dict:
        """
        Enforces object access validations while explicitly blocking missing 
        or anonymous identity signatures from accessing protected fields.
        """
        # Fix Issue #2: Explicitly reject unauthenticated identities or anonymous access profiles
        if not user_id or user_id.upper() == "ANONYMOUS":
            return {
                "access_granted": False,
                "bola_anomaly_flag": True,
                "mitigation_routing": "BLOCK_REQUEST",
                "security_alert_status": "DENIED_UNAUTHENTICATED_ANONYMOUS_SESSION"
            }

        # Call verified graph contract lookup check
        has_access_clearance = self.graph.is_authorized(user_id, object_id)
        
        if not has_access_clearance:
            return {
                "access_granted": False,
                "bola_anomaly_flag": True,
                "mitigation_routing": "BLOCK_REQUEST",
                "security_alert_status": "BOLA_INTRUSION_ATTEMPT_SUSPECTED"
            }
            
        return {
            "access_granted": True,
            "bola_anomaly_flag": False,
            "mitigation_routing": "ALLOW_TRAFFIC",
            "security_alert_status": "AUTHORIZED_ACCESS_CLEARED"
        }
