# core/bola_pipeline.py
"""
Day 4 / Issue 4: Strict Multi-Tenant Aware BOLA Detection Pipeline.
"""
from baseline_graph import StaticAuthorizationGraph

class BolaDetectionPipeline:
    def __init__(self, auth_graph_instance: StaticAuthorizationGraph):
        self.graph = auth_graph_instance

    def process_access_request(self, user_id: str, object_id: str, tenant_id: str) -> dict:
        if not user_id or user_id.upper() == "ANONYMOUS":
            return {
                "access_granted": False,
                "bola_anomaly_flag": True,
                "mitigation_routing": "BLOCK_REQUEST",
                "security_alert_status": "DENIED_UNAUTHENTICATED_ANONYMOUS_SESSION"
            }

        has_access_clearance = self.graph.is_authorized(user_id, object_id, tenant_id)
        
        if not has_access_clearance:
            return {
                "access_granted": False,
                "bola_anomaly_flag": True,
                "mitigation_routing": "BLOCK_REQUEST",
                "security_alert_status": "CRITICAL_CROSS_TENANT_BREACH_SUSPECTED"
            }
            
        return {
            "access_granted": True,
            "bola_anomaly_flag": False,
            "mitigation_routing": "ALLOW_TRAFFIC",
            "security_alert_status": "AUTHORIZED_ACCESS_CLEARED"
        }
