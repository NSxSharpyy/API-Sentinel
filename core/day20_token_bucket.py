# core/day20_token_bucket.py
"""
Day 20: Behavioral Token Bucket Rate Limiter & Resource Allocation Engine.
"""
import time
import json

class BehavioralTokenBucket:
    def __init__(self, bucket_capacity: int = 5, refill_rate_per_sec: float = 1.0):
        # Establish structural capacity bounds constraints
        self.capacity = float(bucket_capacity)
        self.refill_rate = refill_rate_per_sec
        
        # State metrics tracking records in volatile memory database counters
        self.tokens = self.capacity
        self.last_refill_timestamp = time.time()

    def process_incoming_request(self, session_id: str) -> dict:
        """
        Day 20 Target: Implement high-performance Token Bucket rate limiting logic 
        with dynamic accumulation tracking to protect infrastructure perimeters.
        """
        current_time = time.time()
        time_delta = current_time - self.last_refill_timestamp
        
        # Action A: Dynamically refill bucket space matrix based on elapsed epoch window
        generated_tokens = time_delta * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + generated_tokens)
        self.last_refill_timestamp = current_time

        # Action B: Evaluate current resource allocation boundary values
        if self.tokens >= 1.0:
            self.tokens -= 1.0  # Consume token allocation unit
            return {
                "rate_limiter_status": "REQUEST_ALLOWED_CLEAN",
                "active_session": session_id,
                "available_tokens_remaining": round(self.tokens, 2),
                "mitigation_routing": "FORWARD_TO_APPLICATION_PIPELINE"
            }
            
        return {
            "rate_limiter_status": "RATE_LIMIT_EXCEEDED_HTTP_429",
            "active_session": session_id,
            "available_tokens_remaining": round(self.tokens, 2),
            "mitigation_routing": "BLOCK_AND_RETURN_HTTP_429"
        }

if __name__ == "__main__":
    limiter = BehavioralTokenBucket(bucket_capacity=3, refill_rate_per_sec=1.0)
    mock_session = "sess_harish_934371"

    print("Executing Day 20 Token Bucket Volumetric Simulation Test Suite...\n")
    
    # 1. Simulate an intense bursts trigger sequence firing 4 requests instantly
    print("--- Firing Rapid Volumetric Session Burst ---")
    for idx in range(1, 5):
        report = limiter.process_incoming_request(mock_session)
        print(f"Request {idx}: {report['rate_limiter_status']} (Tokens: {report['available_tokens_remaining']})")
        
    # 2. Introduce an intentional delay epoch execution path to test dynamic time refill locks
    print("\n--- Simulating 2-Second System Cooldown Intermission Window ---")
    time.sleep(2.0)
    
    # 3. Fire a trailing request post-refill calculation sequence
    print("--- Firing Trailing Session Verification Query ---")
    post_refill_report = limiter.process_incoming_request(mock_session)
    print(f"Request 5: {post_refill_report['rate_limiter_status']} (Tokens: {post_refill_report['available_tokens_remaining']})")
