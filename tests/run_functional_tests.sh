#!/usr/bin/env bash
set -euo pipefail

NS="apisentinel-test"
HOST_VETH="as-test-host"
NS_VETH="as-test-ns"
HOST_IP="10.20.20.1"
BLOCKED_IP="10.20.20.2"
ALLOWED_IP="10.20.20.3"
BIN="./target/release/api-sentinel-ebpf"
LOG="test_run.log"

echo "[*] Cleaning up any stale test environment..."
sudo ip netns del "$NS" 2>/dev/null || true
sudo ip link del "$HOST_VETH" 2>/dev/null || true
rm -f "$LOG"

cleanup() {
    echo "[*] Running teardown..."
    sudo kill -SIGINT "$SENTINEL_PID" 2>/dev/null || true
    kill -9 "$HTTP_PID" 2>/dev/null || true
    sudo ip netns del "$NS" 2>/dev/null || true
    sudo ip link del "$HOST_VETH" 2>/dev/null || true
    rm -f "$LOG"
    echo "[+] Cleanup complete."
}
trap cleanup EXIT

echo "[1/5] Setting up isolated network namespace..."
sudo ip netns add "$NS"
sudo ip link add "$HOST_VETH" type veth peer name "$NS_VETH"
sudo ip link set "$NS_VETH" netns "$NS"

sudo ip addr add "${HOST_IP}/24" dev "$HOST_VETH"
sudo ip link set "$HOST_VETH" up

sudo ip netns exec "$NS" ip addr add "${BLOCKED_IP}/24" dev "$NS_VETH"
sudo ip netns exec "$NS" ip addr add "${ALLOWED_IP}/24" dev "$NS_VETH"
sudo ip netns exec "$NS" ip link set "$NS_VETH" up
sudo ip netns exec "$NS" ip link set lo up

echo "[2/5] Starting API-Sentinel in test mode..."
sudo env API_SENTINEL_TEST_MODE=1 API_SENTINEL_INTERFACE="$HOST_VETH" "$BIN" > "$LOG" 2>&1 &
SENTINEL_PID=$!
sleep 2

echo "[3/5] Verifying blocklist drop enforcement..."
if ping -c 1 -W 1 "$BLOCKED_IP" >/dev/null 2>&1; then
    echo "[-] FAILED: Ping to blocked IP succeeded!"
    exit 1
else
    echo "[+] PASSED: Blocked IP traffic dropped cleanly."
fi

echo "[4/5] Starting mock HTTP receiver in namespace..."
sudo ip netns exec "$NS" python3 -m http.server 8080 --bind "$ALLOWED_IP" >/dev/null 2>&1 &
HTTP_PID=$!
sleep 1

echo "[5/5] Testing HTTP classification and ring buffer telemetry..."
curl -s -m 2 "http://${ALLOWED_IP}:8080/api/v1/sentinel-test" >/dev/null || true
sleep 1

if grep -q "HTTP_REQUEST method=GET" "$LOG" && grep -q "client_id=1001" "$LOG"; then
    echo "[+] PASSED: HTTP request classified and client ID mapped successfully."
else
    echo "[-] FAILED: Telemetry event missing in logs."
    cat "$LOG"
    exit 1
fi

echo ""
echo "==========================================="
echo "  ALL FUNCTIONAL & KERNEL TESTS PASSED!    "
echo "==========================================="
