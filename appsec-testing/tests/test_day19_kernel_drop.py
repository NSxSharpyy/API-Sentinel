"""Safe unit tests for Day 19 kernel-drop preflight checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.enforcement.kernel_drop_preflight import inspect_preflight


ALL_TOOLS = {"clang", "tc", "bpftool"}


def test_preflight_passes_when_tools_exist_and_clsact_is_absent():
    report = inspect_preflight(
        interface="lo",
        available_tools=ALL_TOOLS,
        qdisc_output="qdisc noqueue 0: root refcnt 2\n",
    )

    assert report["overall"] == "PASS"
    assert all(report["checks"].values())
    assert report["existing_clsact_detected"] is False


def test_preflight_fails_if_required_tool_is_missing():
    report = inspect_preflight(
        interface="lo",
        available_tools={"tc", "bpftool"},
        qdisc_output="qdisc noqueue 0: root refcnt 2\n",
    )

    assert report["overall"] == "FAIL"
    assert report["missing_tools"] == ["clang"]
    assert report["checks"]["required_tools_available"] is False


def test_preflight_refuses_existing_clsact():
    report = inspect_preflight(
        interface="lo",
        available_tools=ALL_TOOLS,
        qdisc_output=(
            "qdisc noqueue 0: root refcnt 2\n"
            "qdisc clsact ffff: parent ffff:fff1\n"
        ),
    )

    assert report["overall"] == "FAIL"
    assert report["existing_clsact_detected"] is True
    assert report["checks"]["interface_has_no_existing_clsact"] is False


def test_preflight_fails_when_qdisc_query_fails():
    report = inspect_preflight(
        interface="lo",
        available_tools=ALL_TOOLS,
        qdisc_output="",
        qdisc_returncode=1,
    )

    assert report["overall"] == "FAIL"
    assert report["checks"]["qdisc_query_succeeded"] is False
    assert report["checks"]["interface_has_no_existing_clsact"] is False


def test_parse_stats_reads_little_endian_counters():
    import json
    from scripts.enforcement.run_day19_kernel_drop import parse_stats

    def encode_u64(value):
        return [f"{byte:02x}" for byte in value.to_bytes(8, "little")]

    raw_value = (
        encode_u64(20) + encode_u64(5) + encode_u64(5)
    )
    report = parse_stats(json.dumps([{
        "key": ["00", "00", "00", "00"],
        "value": raw_value,
    }]))

    assert report == {"seen": 20, "matched": 5, "dropped": 5}


def test_parse_stats_rejects_unexpected_map_shape():
    import json
    import pytest
    from scripts.enforcement.run_day19_kernel_drop import parse_stats

    with pytest.raises(ValueError):
        parse_stats(json.dumps([]))


def test_parse_stats_accepts_formatted_bpftool_output():
    import json
    from scripts.enforcement.run_day19_kernel_drop import parse_stats

    raw = json.dumps([{
        "key": ["0x00", "0x00", "0x00", "0x00"],
        "value": ["0x48"] + ["0x00"] * 7
                 + ["0x09"] + ["0x00"] * 7
                 + ["0x09"] + ["0x00"] * 7,
        "formatted": {
            "key": 0,
            "value": {"seen": 72, "matched": 9, "dropped": 9},
        },
    }])

    assert parse_stats(raw) == {
        "seen": 72, "matched": 9, "dropped": 9
    }


def test_parse_stats_accepts_prefixed_hex_raw_bytes():
    import json
    from scripts.enforcement.run_day19_kernel_drop import parse_stats

    raw = json.dumps([{
        "key": ["0x00"] * 4,
        "value": (
            ["0x14"] + ["0x00"] * 7
            + ["0x05"] + ["0x00"] * 7
            + ["0x05"] + ["0x00"] * 7
        ),
    }])

    assert parse_stats(raw) == {
        "seen": 20, "matched": 5, "dropped": 5
    }


def test_cleanup_succeeds_when_attempted_operations_succeed():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "filter_delete": {"returncode": 0, "stderr": ""},
        "qdisc_delete": {"returncode": 0, "stderr": ""},
    }) is True


def test_cleanup_fails_when_command_raises_exception():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "filter_delete": {"error": "RuntimeError: tc failed"},
    }) is False


def test_cleanup_fails_when_operation_is_skipped():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "qdisc_delete": {"skipped": True, "reason": "Other filters detected"},
    }) is False


def test_cleanup_fails_when_ambiguous_state_preserves_pins_and_qdisc():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "qdisc_delete": {
            "skipped": True,
            "reason": "TC attachment state is ambiguous",
        },
        "pin_cleanup": {
            "skipped": True,
            "reason": "TC attachment state is ambiguous",
        },
    }) is False


def test_cleanup_fails_when_pin_cleanup_is_skipped():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "pin_cleanup": {
            "skipped": True,
            "reason": "Possible attached program",
        },
    }) is False


def test_cleanup_fails_when_pin_cleanup_has_errors():
    from scripts.enforcement.run_day19_kernel_drop import cleanup_succeeded

    assert cleanup_succeeded({
        "pin_cleanup_errors": ["/sys/fs/bpf/example: Permission denied"],
    }) is False

def test_filter_preference_parser_finds_matching_preference():
    import json
    from scripts.enforcement.run_day19_kernel_drop import (
        filter_preference_present,
    )

    output = json.dumps([{"kind": "bpf", "pref": 49152}])
    assert filter_preference_present(output) is True


def test_filter_preference_parser_accepts_empty_filter_list():
    from scripts.enforcement.run_day19_kernel_drop import (
        filter_preference_present,
    )

    assert filter_preference_present("[]") is False


def test_filter_preference_parser_rejects_invalid_json():
    import pytest
    from scripts.enforcement.run_day19_kernel_drop import (
        filter_preference_present,
    )

    with pytest.raises(ValueError):
        filter_preference_present("not-json")


def test_filter_preference_parser_rejects_unexpected_structure():
    import pytest
    from scripts.enforcement.run_day19_kernel_drop import (
        filter_preference_present,
    )

    with pytest.raises(ValueError):
        filter_preference_present('{"pref": 49152}')

def test_observation_succeeds_with_positive_drop_evidence():
    from scripts.enforcement.run_day19_kernel_drop import (
        observation_succeeded,
    )

    assert observation_succeeded(
        stats_returncode=0,
        parsed_stats={"seen": 8, "matched": 5, "dropped": 5},
        client_error="response_timeout",
        received_response=False,
    ) is True


def test_nonfunctional_enforcer_fails_observation_gate():
    """A nonfunctional enforcer must never be reported as observed."""
    from scripts.enforcement.run_day19_kernel_drop import (
        observation_succeeded,
    )

    assert observation_succeeded(
        stats_returncode=0,
        parsed_stats={"seen": 8, "matched": 0, "dropped": 0},
        client_error=None,
        received_response=True,
    ) is False


def test_observation_fails_when_matched_and_dropped_counters_differ():
    from scripts.enforcement.run_day19_kernel_drop import (
        observation_succeeded,
    )

    assert observation_succeeded(
        stats_returncode=0,
        parsed_stats={"seen": 8, "matched": 5, "dropped": 4},
        client_error="response_timeout",
        received_response=False,
    ) is False
