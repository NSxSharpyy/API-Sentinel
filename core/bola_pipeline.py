import uuid
from typing import Dict, Any, Tuple
from schemas.auth_context import AuthorizationContext
from core.identity_parser import parse_actor_identity
from core.baseline_graph import StaticAuthorizationGraph

class BOLAHeuristicPipeline:
    def __init__(self, graph_baseline: StaticAuthorizationGraph):
        self.graph = graph_baseline

    def process_request(self, transport_log: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Core BOLA Heuristic Rule validation engine. Logs anomalies if a user 
        attempts to cross-access an object without explicitly verified graph ownership records.
        """
        headers = transport_log.get("headers", {})
        
        # 1. Parse identity using Day 2 logic layers
        identity = parse_actor_identity(headers)
        user_id = identity.get("user_id", "ANONYMOUS")
        
        # 2. Structure data into Day 1 validation layout schema format
        auth_data = {
            "user_id": user_id,
            "tenant_id": identity.get("tenant_id", "DEFAULT"),
            "role": transport_log.get("role", "guest"),
            "object_id": transport_log.get("object_id", "unknown"),
            "action": transport_log.get("action", "GET")
        }
        
        ctx = AuthorizationContext(**auth_data)
        
        # 3. Intercept request against Day 3 baseline graph database rules
        is_bola_anomaly = False
        alert_metadata = {}
        
        if user_id != "ANONYMOUS":
            has_ownership = self.graph.check_ownership(ctx.user_id, ctx.object_id)
            if not has_ownership:
                is_bola_anomaly = True
                alert_metadata = {
                    "alert_type": "BOLA_VIOLATION_DETECTED",
                    "severity": "HIGH",
                    "msg": f"User {ctx.user_id} attempted unauthorized access to Object {ctx.object_id}"
                }

        processed_log = {
            "request_id": str(uuid.uuid4()),
            "user_context": ctx.dict(),
            "bola_anomaly_flag": is_bola_anomaly,
            "security_alerts": alert_metadata
        }
        
        return processed_log, is_bola_anomaly
