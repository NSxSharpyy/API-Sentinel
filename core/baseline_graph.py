# core/baseline_graph.py
"""
Day 1 Core: Centralized authorization matrix repository tracking explicit user-to-object pairs.
"""

class StaticAuthorizationGraph:
    def __init__(self):
        self._acl_matrix = {}

    def register_new_object(self, user_id: str, object_id: str):
        if user_id not in self._acl_matrix:
            self._acl_matrix[user_id] = set()
        self._acl_matrix[user_id].add(object_id)

    def is_authorized(self, user_id: str, object_id: str) -> bool:
        if user_id in self._acl_matrix:
            return object_id in self._acl_matrix[user_id]
        return False

    def seed_authorization_baseline(self):
        self.register_new_object("usr_legit_owner", "obj_secure_resource_101")
        self.register_new_object("usr_legit_owner", "obj_secure_resource_102")
