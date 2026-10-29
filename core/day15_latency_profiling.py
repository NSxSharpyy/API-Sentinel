# core/day15_latency_profiling.py
"""
Day 15 / Issue 10: Production-Grade High-Precision Latency Profiling Engine.
"""
import time
import json
import statistics
from baseline_graph import StaticAuthorizationGraph
from bola_pipeline import BolaDetectionPipeline

class SecurityPipelineProfiler:
    def __init__(self, pipeline_instance):
        self.pipeline = pipeline_instance
        self.target_threshold_ms = 2.0

    def execute_performance_profile(self, user_id: str, object_id: str, tenant_id: str, iterations: int = 100) -> dict:
        latency_records_ms = []

        for _ in range(10):
            self.pipeline.process_access_request(user_id, object_id, tenant_id)

        for _ in range(iterations):
            start_time_ns = time.perf_counter_ns()
            self.pipeline.process_access_request(user_id, object_id, tenant_id)
            end_time_ns = time.perf_counter_ns()
            
            elapsed_ms = (end_time_ns - start_time_ns) / 1_000_000.0
            latency_records_ms.append(elapsed_ms)

        median_latency = statistics.median(latency_records_ms)
        sorted_latencies = sorted(latency_records_ms)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]

        is_compliant = p95_latency <= self.target_threshold_ms

        return {
            "profiling_status": "REAL_PIPELINE_MEASUREMENT_COMPLETE",
            "total_samples_evaluated": iterations,
            "measured_median_latency_ms": round(median_latency, 5),
            "measured_p95_latency_ms": round(p95_latency, 5),
            "performance_target_limit_ms": self.target_threshold_ms,
            "is_under_2ms_target_limit": is_compliant,
            "environment_conditions": "Python Finite High-Precision Telemetry Clock Layer"
        }

if __name__ == "__main__":
    graph = StaticAuthorizationGraph()
    graph.seed_authorization_baseline()
    pipeline = BolaDetectionPipeline(graph)
    profiler = SecurityPipelineProfiler(pipeline)

    print("Running Day 15 Real Pipeline Performance Profiling...")
    legit_report = profiler.execute_performance_profile("usr_harish", "obj_data_101", "tenant_srm_engineering")
    print(json.dumps(legit_report, indent=4))
