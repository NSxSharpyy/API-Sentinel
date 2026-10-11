from typing import Dict, Set, Any

class StaticAuthorizationGraph:
    def __init__(self):
        # Memory baseline mappings: { user_id: { object_ids } }
        self.user_to_object_map: Dict[str, Set[str]] = {}
        # Memory baseline mappings: { role: { actions } }
        self.role_to_action_map: Dict[str, Set[str]] = {}

    def seed_authorization_baseline(self, config: Dict[str, Any]) -> None:
        """Loads static authorization blueprint criteria profiles seamlessly into memory structures."""
        users_config = config.get("users_ownership", {})
        for user_id, objects in users_config.items():
            if user_id not in self.user_to_object_map:
                self.user_to_object_map[user_id] = set()
            self.user_to_object_map[user_id].update(objects)

        roles_config = config.get("roles_capabilities", {})
        for role, actions in roles_config.items():
            if role not in self.role_to_action_map:
                self.role_to_action_map[role] = set()
            self.role_to_action_map[role].update({act.strip().upper() for act in actions})

    def check_ownership(self, user_id: str, object_id: str) -> bool:
        """Checks if the tracked calling actor holds absolute target resource ownership configurations."""
        if user_id in self.user_to_object_map:
            return object_id in self.user_to_object_map[user_id]
        return False
