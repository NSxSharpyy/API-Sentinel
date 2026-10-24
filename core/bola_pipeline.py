# core/bola_pipeline.py
"""
Day 1 Pipeline: Processes access metrics via the verified unified is_authorized() interface contract.
"""
from baseline_graph import StaticAuthorizationGraph

class BolaDetectionPipeline:
    def __init__(self, auth_graph_instance: StaticAuthorizationGraph):
        self.graph = auth_graph_instance

    def process_access_request(self, user_id: str, object_id: str) -> dict:
        """
        Enforces object access validations through the verified graph contract interface.
        """
        # Call verified consistent method name contract
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
