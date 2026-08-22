"""One-shot production boot verification.
Starts the real server, probes every live endpoint over HTTP,
then shuts down cleanly. Leaves nothing running.
"""

import subprocess
import sys
import time
import httpx

proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8021",
        "--log-level",
        "warning",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))


try:
    base = "http://127.0.0.1:8021"
    # Wait for boot (max ~20s)
    booted = False
    for _ in range(40):
        time.sleep(0.5)
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            print("SERVER DIED DURING BOOT:\n", out)
            sys.exit(1)
        try:
            r = httpx.get(f"{base}/health", timeout=1.0)
            if r.status_code == 200:
                booted = True
                break
        except Exception:
            continue
    record("boot_uvicorn", booted)
    if not booted:
        sys.exit(1)

    # 1. Health endpoint (live)
    r = httpx.get(f"{base}/health", timeout=5)
    d = r.json()
    record(
        "GET /health",
        r.status_code == 200 and d["status"] == "ok",
        f"status=200 uptime={d.get('uptime_seconds')}s env={d.get('environment')}",
    )

    # 2. Readiness probe (live)
    r = httpx.get(f"{base}/ready", timeout=5)
    d = r.json()
    record("GET /ready", r.status_code == 200 and d["target_api_configured"] is True)

    # 3. Info endpoint (live)
    r = httpx.get(f"{base}/api/info", timeout=5)
    d = r.json()
    tools = [t["name"] for t in d["mcp_tools"]]
    record(
        "GET /api/info",
        r.status_code == 200
        and set(tools)
        == {
            "execute_get",
            "execute_post",
            "execute_put",
            "execute_patch",
            "execute_delete",
        },
        f"tools={len(tools)}",
    )

    # 4. Dashboard (live HTML)
    r = httpx.get(base + "/", timeout=5)
    record(
        "GET / dashboard",
        r.status_code == 200
        and "MCP API Gateway Server" in r.text
        and "text/html" in r.headers["content-type"],
    )

    # 5. Security: unauthenticated MCP access must be rejected with 401
    r = httpx.get(f"{base}/sse", timeout=5, headers={"Accept": "text/event-stream"})
    record("SECURITY /sse no-token -> 401", r.status_code == 401)

    # 6. Security: wrong token must be rejected with 401
    r = httpx.get(
        f"{base}/sse",
        timeout=5,
        headers={"Accept": "text/event-stream", "Authorization": "Bearer wrong-token"},
    )
    record("SECURITY /sse bad-token -> 401", r.status_code == 401)

    # 7. Authenticated MCP SSE handshake must open an event stream
    events_received = False
    try:
        with httpx.stream(
            "GET",
            f"{base}/sse",
            timeout=10,
            headers={
                "Accept": "text/event-stream",
                "Authorization": "Bearer super-secret-local-token",
            },
        ) as stream:
            record(
                "SSE /sse valid-token status",
                stream.status_code == 200,
                f"http={stream.status_code}",
            )
            buf = b""
            start = time.time()
            for chunk in stream.iter_bytes():
                buf += chunk
                if b"event:" in buf and b"data:" in buf:
                    events_received = True
                    break
                if time.time() - start > 8:
                    break
    except Exception as e:
        record("SSE stream error", False, str(e)[:100])
    record(
        "SSE MCP handshake streams events",
        events_received,
        buf.decode(errors="replace")[:120].replace("\n", " ") if buf else "",
    )

    # 8. CORS preflight sanity
    r = httpx.options(
        f"{base}/health",
        timeout=5,
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    record(
        "CORS preflight handled",
        r.status_code in (200, 204),
        f"allow-origin={r.headers.get('access-control-allow-origin', '-')}",
    )

finally:
    proc.terminate()
    try:
        proc.wait(timeout=8)
        print("Server shut down cleanly.")
    except subprocess.TimeoutExpired:
        proc.kill()
        print("Server force-killed.")

failed = [r for r in results if not r[1]]
print("\n" + "=" * 60)
print(
    f"LIVE BOOT VERIFICATION: {len(results) - len(failed)}/{len(results)} checks passed"
)
sys.exit(1 if failed else 0)
