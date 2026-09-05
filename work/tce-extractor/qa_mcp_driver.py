"""Local-only QA helper: file inbox -> actual Chrome DevTools MCP stdio.

Not distributed in the portable kit. No HTTP listener or credentials exported.
Place JSON-RPC methods in inbox/*.json; responses are written to outbox.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    for folder in ("inbox", "outbox"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    with (root / "server.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([
            "node", args.server, "--categoryExtensions", "--no-usage-statistics",
            "--no-performance-crux", "--no-page-id-routing", "--allowUnrestrictedPaths",
            f"--userDataDir={root / 'profile'}",
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)

        def rpc(request):
            process.stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
            process.stdin.flush()
            if "id" not in request:
                return None
            for line in process.stdout:
                response = json.loads(line)
                if response.get("id") == request["id"]:
                    return response
            raise RuntimeError("MCP server exited")

        rpc({"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "TCE-local-QA", "version": "1.0"}}})
        rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        print("Chrome DevTools MCP ready; file inbox is local only.", flush=True)
        try:
            while not (root / "STOP").exists():
                for source in sorted((root / "inbox").glob("*.json")):
                    target = root / "outbox" / source.name
                    if target.exists():
                        continue
                    request = json.loads(source.read_text(encoding="utf-8-sig"))
                    request.update(jsonrpc="2.0", id=source.stem)
                    result = rpc(request)
                    temporary = target.with_suffix(".tmp")
                    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    temporary.replace(target)
                    print(f"Completed {source.stem}: {request['method']}", flush=True)
                time.sleep(0.2)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()


if __name__ == "__main__":
    main()
