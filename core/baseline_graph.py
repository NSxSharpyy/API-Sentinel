from typing import Dict, Set, Any

class AuthorizationGraph:
    def __init__(self):
        # Maps user_id -> set of authorized object_ids
        self.graph: Dict[str, Set[str]] = {}

    def is_authorized(self, user_id: str, object_id: str) -> bool:
        if user_id not in self.graph:
            return False
        return object_id in self.graph[user_id]

    # FIX: Add register_new_object to dynamically handle POST/PUT creations
    def register_new_object(self, user_id: str, new_object_id: str) -> None:
        if user_id not in self.graph:
            self.graph[user_id] = set()
        self.graph[user_id].add(new_object_id)

    def load_static_baseline(self, baseline_data: Dict[str, Any]) -> None:
        for user_id, objects in baseline_data.items():
            self.graph[user_id] = set(objects)
