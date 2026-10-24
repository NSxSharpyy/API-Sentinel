# core/baseline_graph.py
"""
Day 4 / Issue 4: Tenant Isolation Bounds Mapping Database Simulator.
"""

class StaticAuthorizationGraph:
    def __init__(self):
        self._acl_matrix = {}
        self._object_tenant_map = {}

    def register_new_object(self, user_id: str, object_id: str, tenant_id: str):
        if user_id not in self._acl_matrix:
            self._acl_matrix[user_id] = set()
        self._acl_matrix[user_id].add(object_id)
        self._object_tenant_map[object_id] = tenant_id

    def is_authorized(self, user_id: str, object_id: str, tenant_id: str) -> bool:
        expected_tenant = self._object_tenant_map.get(object_id)
        if expected_tenant and expected_tenant != tenant_id:
            return False  # Strict reject if tenant bounds are breached!

        if user_id in self._acl_matrix:
            return object_id in self._acl_matrix[user_id]
        return False

    def seed_authorization_baseline(self):
        self.register_new_object("usr_harish", "obj_data_101", "tenant_srm_engineering")
        self.register_new_object("usr_harish", "obj_data_102", "tenant_srm_engineering")
