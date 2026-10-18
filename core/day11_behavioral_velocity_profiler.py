# Day 11: Behavioral Request Velocity Profiling Core Engine
import time
import json

class BehavioralVelocityProfiler:
    def __init__(self):
        # Setting baseline threshold parameters for request validation
        self.max_allowed_requests_per_minute = 100
        self.max_payload_bytes_threshold = 50000  # ~50 KB max individual request
        self.error_rate_anomaly_trigger = 5        # More than 5 errors allowed in window

    def evaluate_velocity_profile(self, user_session_history, incoming_request_payload):
        """
        Day 11 Target: Build statistical baseline models tracking user request frequencies,
        payload sizes, and typical error rates to detect anomalous access spikes.
        """
        current_request_count = user_session_history.get("request_count_last_60s", 0)
        incoming_payload_size = incoming_request_payload.get("payload_bytes", 0)
        recent_error_count = user_session_history.get("error_count_last_60s", 0)

        # Assertion Check A: Evaluate request count speed frequency baseline
        if current_request_count > self.max_allowed_requests_per_minute:
            return {
                "velocity_anomaly_detected": True,
                "reason": "HIGH_REQUEST_FREQUENCY_SPIKE",
                "risk_assessment": "FLAG_RATE_LIMIT"
            }

        # Assertion Check B: Evaluate structural payload mass deviation limits
        if incoming_payload_size > self.max_payload_bytes_threshold:
            return {
                "velocity_anomaly_detected": True,
                "reason": "ABNORMAL_PAYLOAD_SIZE_DEVIATION",
                "risk_assessment": "SUSPECTED_DATA_EXFILTRATION"
            }

        # Assertion Check C: Evaluate fuzzing indicator metrics via error rates
        if recent_error_count > self.error_rate_anomaly_trigger:
            return {
                "velocity_anomaly_detected": True,
                "reason": "HIGH_ERROR_RATE_FUZZING_SPIKE",
                "risk_assessment": "BLOCK_MALICIOUS_SCAN"
            }

        return {
            "velocity_anomaly_detected": False,
            "reason": "LEGITIMATE_STATISTICAL_BEHAVIOR",
            "risk_assessment": "ALLOW"
        }

if __name__ == "__main__":
    profiler = BehavioralVelocityProfiler()
    
    # Simulate an attacking automated scraping script hit matching malicious metrics
    mock_attacker_history = {"request_count_last_60s": 145, "error_count_last_60s": 1}
    mock_request = {"payload_bytes": 1024}
    
    assessment = profiler.evaluate_velocity_profile(mock_attacker_history, mock_request)
    print("Executing Day 11 Velocity Evaluation Output:\n", json.dumps(assessment, indent=4))
