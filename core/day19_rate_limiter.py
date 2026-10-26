# core/day19_rate_limiter.py
"""
Day 19: In-Memory Rate Limiting Counters Core Implementation.
"""
import json

class InMemoryRateLimiter:
    def __init__(self):
        # Establish structural rate limiting window configuration constraints
        self.max_requests_per_window = 5  # Maximum allowed hits per evaluation block
        self.active_counters_db = {}     # In-memory session tracking table

    def process_request_rate(self, session_id: str) -> dict:
        """
        Day 19 Target: Implement in-memory counter tracking matrix to increment,
        evaluate, and throttle automated boundary bursts exceeding threshold ceilings.
        """
        if not session_id:
            return {"rate_limit_status": "REJECTED_INVALID_SESSION", "is_throttled": True}

        # Fetch or initialize the active rolling count value for the unique key
        current_hits = self.active_counters_db.get(session_id, 0)
        
        # Increment the atomic counter value inside local volatile database memory
        current_hits += 1
        self.active_counters_db[session_id] = current_hits

        # Boundary Evaluation Guard Check
        if current_hits > self.max_requests_per_window:
            return {
                "rate_limit_status": "RATE_LIMIT_EXCEEDED_HTTP_429",
                "tracked_session": session_id,
                "current_counter_value": current_hits,
                "is_throttled": True,
                "mitigation_routing": "BLOCK_AND_RETURN_HTTP_429"
            }

        return {
            "rate_limit_status": "REQUEST_ALLOWED_CLEAN",
            "tracked_session": session_id,
            "current_counter_value": current_hits,
            "is_throttled": False,
            "mitigation_routing": "FORWARD_TO_APPLICATION_PIPELINE"
        }

if __name__ == "__main__":
    limiter = InMemoryRateLimiter()
    target_session = "sess_harish_934371"

    print("Executing Day 19 In-Memory Rate Limiting Counters Iteration Test Suite...\n")
    
    # Simulate a high-velocity script firing 7 consecutive operations instantly
    for request_idx in range(1, 8):
        report = limiter.process_request_rate(target_session)
        print(f"-> Request {request_idx}: {report['rate_limit_status']} (Count: {report['current_counter_value']})")
