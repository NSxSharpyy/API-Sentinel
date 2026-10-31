
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.enforcement.evaluate_kernel_blocking_at_scale import evaluate_evidence


def valid_day19():
    return {
        "overall": "OBSERVED",
        "steps": {
            "map_dump": {
                "returncode": 0,
                "counters": {
                    "seen": 10,
                    "matched": 5,
                    "dropped": 5,
                },
            },
            "assertions": {
                "map_dump_succeeded": True,
                "matched_packets_positive": True,
                "dropped_packets_positive": True,
                "matched_equals_dropped": True,
                "client_response_timed_out": True,
                "no_http_response_received": True,
            },
            "client": {
                "received_response": False,
                "error": "response_timeout",
            },
        },
        "cleanup": {
            "filter_delete": {"returncode": 0, "stderr": ""},
            "qdisc_delete": {"returncode": 0, "stderr": ""},
            "complete": True,
        },
    }



def valid_concurrency():
    expected_ports = list(range(40000, 40100))

    return {
        "overall": "PASS",
        "evidence_type": "kernel_drop",
        "kernel_drop_proof": True,
        "concurrency_evidence": True,
        "requested_attempts": 100,
        "concurrency": 50,
        "cleanup": valid_day23_cleanup(),
        "kernel_counters": {
            "seen": 104,
            "matched": 100,
            "dropped": 100,
        },
        "source_port_evidence": {
            "expected_source_ports": expected_ports,
            "observed_source_ports": expected_ports.copy(),
            "hit_counts": {
                str(port): 1 for port in expected_ports
            },
        },
        "workload": {
            "attempts_completed": 100,
            "outcomes": {"timeout": 100},
            "results": [
                {
                    "id": index,
                    "source_port": port,
                    "outcome": "timeout",
                }
                for index, port in enumerate(expected_ports)
            ],
        },

        "cleanup": {
            "complete": True,
            "filter_delete": {"returncode": 0, "stderr": ""},
            "qdisc_delete": {"returncode": 0, "stderr": ""},
            "pin_cleanup": {"status": "ok"},
        },

        "checks": {
            "workload_completed": True,
            "all_attempts_timed_out": True,
            "drop_accuracy_passed": True,
            "source_port_coverage_passed": True,
            "cleanup_complete": True,
            "no_runtime_error": True,
        },
    }


def test_complete_concurrent_kernel_evidence_passes():
    result = evaluate_evidence(valid_day19(), valid_concurrency())

    assert result["overall"] == "PASS"
    assert result["kernel_certification"] == "PASS"
    assert result["kernel_drop_proof"] is True


def test_application_layer_simulation_cannot_certify_kernel_blocking():
    concurrency = valid_concurrency()
    concurrency["evidence_type"] = "application_layer_simulation"
    concurrency["kernel_drop_proof"] = False

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["concurrency_status"] == "PASS"
    assert result["kernel_certification"] == "FAIL"
    assert result["kernel_drop_proof"] is False


def test_day19_preflight_only_cannot_pass_kernel_gate():
    day19 = valid_day19()
    day19["overall"] = "PREFLIGHT_ONLY"

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_kernel_observation_valid"] is False
    assert result["overall"] == "FAIL"


def test_cleanup_failure_blocks_certification():
    day19 = valid_day19()
    day19["cleanup"]["complete"] = False

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["overall"] == "FAIL"
    assert result["checks"]["day19_cleanup_complete"] is False


def test_missing_concurrent_kernel_evidence_fails_closed():
    concurrency = valid_concurrency()
    concurrency.pop("concurrency_evidence")

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["overall"] == "FAIL"
    assert result["checks"]["concurrent_kernel_drop_proof_present"] is False


def test_mismatched_packet_counters_fail_kernel_gate():
    day19 = valid_day19()
    day19["steps"]["map_dump"]["counters"]["dropped"] = 4

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["overall"] == "FAIL"


def test_boolean_counter_is_not_accepted_as_integer():
    day19 = valid_day19()
    day19["steps"]["map_dump"]["counters"]["matched"] = True

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["overall"] == "FAIL"

def test_single_trivial_check_cannot_pass_workload_gate():
    concurrency = valid_concurrency()
    concurrency["checks"] = {"workload_completed": True}

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrency_workload_passed"] is False
    assert result["kernel_certification"] == "FAIL"


def test_skipped_cleanup_blocks_certification():
    day19 = valid_day19()
    day19["cleanup"]["qdisc_delete"] = {
        "skipped": True,
        "reason": "TC attachment state is ambiguous",
    }

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["kernel_certification"] == "FAIL"


def test_kernel_flag_cannot_override_failed_workload():
    concurrency = valid_concurrency()
    concurrency["overall"] = "FAIL"
    concurrency["checks"]["workload_completed"] = False

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_kernel_drop_proof_present"] is True
    assert result["checks"]["concurrency_workload_passed"] is False
    assert result["kernel_drop_proof"] is False
    assert result["overall"] == "FAIL"

def test_cleanup_nonzero_returncode_blocks_certification():
    day19 = valid_day19()
    day19["cleanup"]["filter_delete"] = {"returncode": 1}

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["overall"] == "FAIL"


def test_cleanup_error_blocks_certification():
    day19 = valid_day19()
    day19["cleanup"]["qdisc_delete"] = {"error": "deletion failed"}

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["overall"] == "FAIL"


def test_pin_cleanup_errors_block_certification():
    day19 = valid_day19()
    day19["cleanup"]["pin_cleanup_errors"] = ["pin directory remains"]

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["overall"] == "FAIL"


def test_missing_source_port_evidence_fails_certification():
    concurrency = valid_concurrency()
    concurrency.pop("source_port_evidence")

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["kernel_certification"] == "FAIL"


def test_duplicate_observed_source_port_fails_certification():
    concurrency = valid_concurrency()
    observed = concurrency["source_port_evidence"]["observed_source_ports"]
    observed[-1] = observed[0]

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["kernel_certification"] == "FAIL"


def test_missing_observed_source_port_fails_certification():
    concurrency = valid_concurrency()
    concurrency["source_port_evidence"]["observed_source_ports"].pop()

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["overall"] == "FAIL"


def test_zero_source_port_hit_count_fails_certification():
    concurrency = valid_concurrency()
    concurrency["source_port_evidence"]["hit_counts"]["40000"] = 0

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["overall"] == "FAIL"


def test_boolean_source_port_hit_count_fails_certification():
    concurrency = valid_concurrency()
    concurrency["source_port_evidence"]["hit_counts"]["40000"] = True

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["overall"] == "FAIL"


def test_duplicate_workload_source_port_fails_certification():
    concurrency = valid_concurrency()
    results = concurrency["workload"]["results"]
    results[-1]["source_port"] = results[0]["source_port"]

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["overall"] == "FAIL"


def test_non_timeout_workload_result_fails_certification():
    concurrency = valid_concurrency()
    concurrency["workload"]["results"][0]["outcome"] = "connected"

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_source_port_evidence_valid"] is False
    assert result["overall"] == "FAIL"

def test_missing_concurrent_kernel_counters_fails_certification():
    concurrency = valid_concurrency()
    concurrency.pop("kernel_counters")

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_kernel_counters_valid"] is False
    assert result["overall"] == "FAIL"


def test_mismatched_concurrent_kernel_counters_fail_certification():
    concurrency = valid_concurrency()
    concurrency["kernel_counters"]["dropped"] = 99

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_kernel_counters_valid"] is False
    assert result["overall"] == "FAIL"


def test_boolean_concurrent_kernel_counter_fails_certification():
    concurrency = valid_concurrency()
    concurrency["kernel_counters"]["matched"] = True

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_kernel_counters_valid"] is False
    assert result["overall"] == "FAIL"


def test_zero_concurrent_kernel_counter_fails_certification():
    concurrency = valid_concurrency()
    concurrency["kernel_counters"]["dropped"] = 0

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_kernel_counters_valid"] is False
    assert result["overall"] == "FAIL"


def test_incomplete_workload_attempt_count_fails_certification():
    concurrency = valid_concurrency()
    concurrency["workload"]["attempts_completed"] = 99

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_workload_totals_valid"] is False
    assert result["overall"] == "FAIL"


def test_inconsistent_workload_outcomes_fail_certification():
    concurrency = valid_concurrency()
    concurrency["workload"]["outcomes"] = {"timeout": 99, "connected": 1}

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_workload_totals_valid"] is False
    assert result["overall"] == "FAIL"


def test_boolean_workload_count_fails_certification():
    concurrency = valid_concurrency()
    concurrency["workload"]["outcomes"]["timeout"] = True

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_workload_totals_valid"] is False
    assert result["overall"] == "FAIL"


def test_invalid_concurrency_level_fails_certification():
    concurrency = valid_concurrency()
    concurrency["concurrency"] = 0

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["concurrent_workload_totals_valid"] is False
    assert result["overall"] == "FAIL"

def valid_day23_cleanup():
    return {
        "complete": True,
        "filter_delete": {"returncode": 0, "stderr": ""},
        "qdisc_delete": {"returncode": 0, "stderr": ""},
        "pin_cleanup": {"status": "ok"},
    }


def test_concurrent_cleanup_must_be_present():
    concurrency = valid_concurrency()
    concurrency["cleanup"] = {}

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["day23_concurrency_cleanup_complete"] is False
    assert result["kernel_certification"] == "FAIL"


def test_concurrent_cleanup_failure_blocks_certification():
    concurrency = valid_concurrency()
    concurrency["cleanup"] = valid_day23_cleanup()
    concurrency["cleanup"]["filter_delete"]["returncode"] = 1

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["day23_concurrency_cleanup_complete"] is False
    assert result["kernel_certification"] == "FAIL"


def test_concurrent_pin_cleanup_failure_blocks_certification():
    concurrency = valid_concurrency()
    concurrency["cleanup"] = valid_day23_cleanup()
    concurrency["cleanup"]["pin_cleanup"]["status"] = "error"

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["day23_concurrency_cleanup_complete"] is False
    assert result["kernel_certification"] == "FAIL"


def test_complete_concurrent_cleanup_is_accepted():
    concurrency = valid_concurrency()
    concurrency["cleanup"] = valid_day23_cleanup()

    result = evaluate_evidence(valid_day19(), concurrency)

    assert result["checks"]["day23_concurrency_cleanup_complete"] is True
    assert result["kernel_certification"] == "PASS"

def test_cleanup_operation_without_success_evidence_fails():
    day19 = valid_day19()
    day19["cleanup"]["filter_delete"] = {}

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["overall"] == "FAIL"


def test_cleanup_operation_with_unknown_status_fails():
    day19 = valid_day19()
    day19["cleanup"]["filter_delete"] = {"status": "unknown"}

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_cleanup_complete"] is False
    assert result["overall"] == "FAIL"

def test_boolean_map_dump_returncode_is_rejected():
    day19 = valid_day19()
    day19["steps"]["map_dump"]["returncode"] = False

    result = evaluate_evidence(day19, valid_concurrency())

    assert result["checks"]["day19_kernel_observation_valid"] is False
    assert result["overall"] == "FAIL"
