# core/day11_behavioral_velocity_profiler.py
"""
Day 11 / Issue 7: Validated Request Velocity Profiler Logic with Strict Type Protections.
"""
import json
import math

class ValidatedVelocityProfiler:
    def __init__(self):
        # Setting standard structural project burst thresholds limits
        self.max_rolling_window_limit = 150

    def evaluate_traffic_velocity(self, request_count, payload_size_bytes) -> dict:
        """
        Fix Issue 7: Validate that request counts and payload sizes are numeric, 
        finite, non-negative, and map neutral condition classification tags.
        """
        # Feature A: Input Validation Check Guard bounds
        inputs_valid = (
            isinstance(request_count, (int, float)) and 
            isinstance(payload_size_bytes, (int, float)) and
            math.isfinite(request_count) and 
            math.isfinite(payload_size_bytes) and
            request_count >= 0 and 
            payload_size_bytes >= 0
        )
        
        if not inputs_valid:
            return {
                "profiler_status": "INVALID_INPUT_PARAMETERS_REJECTED",
                "traffic_classification": "SUSPICIOUS_MALFORMED_METRICS",
                "anomaly_detected": True
            }

        # Feature B: Neutral field validation adjustment semantics mapping
        is_anomaly = request_count > self.max_rolling_window_limit

        return {
            "profiler_status": "COMPUTATION_SUCCESSFUL",
            "traffic_classification": "VOLUMETRIC_BURST_ALERT" if is_anomaly else "NORMAL_BASELINE_FLOW",
            "anomaly_detected": is_anomaly
        }

if __name__ == "__main__":
    profiler = ValidatedVelocityProfiler()
    print("Testing input checks execution telemetry payload:", json.dumps(profiler.evaluate_traffic_velocity(120, 2048), indent=4))
