#!/usr/bin/env python3
"""
relang-submit-safe.py
---------------------
A drop-in sibling of `relang-submit.py` that adds one fix: it tolerates
test results where stdout is None (the original script crashes on
`stdout.strip()` when tester.py returns a dict with stdout=None).

This is NOT a modification of relang-submit.py -- it's a separate file
that hits the same API endpoints with the same payload shapes. Use it
when the original crashes mid-batch on the NoneType bug.

Usage:
    cd marked/
    python target/relang-submit-safe.py "python target/marked.py"

Expected invocation from the project root so that the relative path
'relang/project_config.json' resolves correctly.
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# Same constants as relang-submit.py. The team token is part of the
# public deliverable repo; relang-submit.py embeds it in the clear.
TEAM_TOKEN = "c075f8ab26e3e2f217d91a1863f471e261bcbc5ccb8692f312055057dd26af8d"
API_BASE = "http://85.211.196.199:8080"
BATCH_SIZE = 100


def api_post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Team-Token": TEAM_TOKEN},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_get(url):
    req = urllib.request.Request(url, headers={"X-Team-Token": TEAM_TOKEN}, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tool_command>", file=sys.stderr)
        sys.exit(1)

    tool_cmd = sys.argv[1]

    config_path = os.path.join("relang", "project_config.json")
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)
    project_id = config["project_id"]

    tester_py = os.path.join("relang", "tester.py")
    if not os.path.exists(tester_py):
        print(f"Error: {tester_py} not found", file=sys.stderr)
        sys.exit(1)

    def is_rate_limited(e):
        if isinstance(e, urllib.error.HTTPError):
            return e.code == 429
        return False

    def create_session():
        try:
            return api_post(API_BASE + "/api/session/create",
                            {"projectId": project_id, "teamToken": TEAM_TOKEN})
        except urllib.error.HTTPError as e:
            if is_rate_limited(e):
                print("  Rate-limited (429) creating session. Server needs time to clear.", file=sys.stderr)
            raise

    # Retry the session creation a few times if rate-limited.
    session = None
    for attempt in range(6):
        try:
            session = create_session()
            break
        except urllib.error.HTTPError as e:
            if is_rate_limited(e) and attempt < 5:
                wait = 30 * (attempt + 1)
                print(f"  Rate-limited. Sleeping {wait}s before retry ({attempt+1}/6)...", file=sys.stderr)
                import time; time.sleep(wait)
                continue
            raise
    if session is None:
        print("Could not create session after retries.", file=sys.stderr)
        sys.exit(1)

    session_token = session["sessionToken"]
    total_tests = session["totalTests"]
    batch_size = session.get("batchSize", BATCH_SIZE)
    print(f"Session created: {total_tests} tests total")

    all_hashes = {}
    all_empty = []
    batch_num = 0

    while True:
        batch_num += 1
        print(f"\n--- Batch {batch_num} ---")

        batch = api_get(
            f"{API_BASE}/api/inputs/next-batch?session={session_token}&size={batch_size}"
        )

        if batch.get("done"):
            break

        test_cases = batch["testCases"]

        result = subprocess.run(
            [sys.executable, tester_py, tool_cmd],
            input=json.dumps(test_cases),
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            print(f"  tester.py exit code {result.returncode}", file=sys.stderr)

        try:
            results = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"  Failed to parse tester.py output: {e}", file=sys.stderr)
            print(f"  tester.py stderr: {result.stderr[:500]}", file=sys.stderr)
            sys.exit(1)

        file_hashes = {}
        empty_tests = []
        for r in results:
            # THE FIX: None default instead of "". This is the only place
            # this script differs from relang-submit.py.
            stdout = r.get("stdout") or ""
            if not stdout.strip():
                empty_tests.append(r["id"])
            h = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
            file_hashes[r["id"]] = h

        all_hashes.update(file_hashes)
        all_empty.extend(empty_tests)

        submit_resp = api_post(API_BASE + "/api/submit-hash", {
            "projectId": project_id,
            "fileHashes": file_hashes,
            "excludedTestIds": empty_tests,
        })

        passed = submit_resp["passedTestCases"]
        total = submit_resp["totalTestCases"]
        pct = (passed / total * 100) if total else 0
        score = submit_resp.get("finalScore", 0)
        failed_ids = submit_resp.get("failedTestIds", [])
        real_empty_failed = [t for t in empty_tests if t in failed_ids]
        print(f"  Batch: {passed}/{total} passed | Running: {pct:.1f}%")
        if real_empty_failed:
            print(f"  ⚠ {len(real_empty_failed)} test(s) produced empty output "
                  f"-- your tool may not be finding the input files",
                  file=sys.stderr)

        if not batch.get("done", False):
            continue
        break

    total_all = len(all_hashes)
    final_pct = 0
    final_score = 0

    if total_all > 0:
        try:
            final = api_post(API_BASE + "/api/submit-hash", {
                "projectId": project_id,
                "fileHashes": all_hashes,
                "isFinal": True,
                "excludedTestIds": all_empty,
            })
            final_pct = (final.get("passedTestCases", 0)
                         / max(final.get("totalTestCases", 1), 1) * 100)
            final_score = final.get("finalScore", 0)
        except Exception as e:
            print(f"  Final submission error: {e}", file=sys.stderr)

    print(f"\n{'='*45}")
    print(f"  FINAL: {total_all} tests")
    print(f"  SCORE: {final_score:.1f} points")
    print(f"  PASS:  {final_pct:.1f}%")
    print(f"{'='*45}")


if __name__ == "__main__":
    main()
