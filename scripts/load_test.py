"""Submit N real jobs concurrently; includes queue time and bypasses cached results."""

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_client import ROOT, run_job  # noqa: E402


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


async def load(base_url, concurrency=5, *, paper=ROOT / "fixtures/pdfs/paper1_attention.pdf"):
    results = await asyncio.gather(
        *(run_job(base_url, paper, fresh=True) for _ in range(concurrency))
    )
    durations = [result["duration_seconds"] for result in results if not result["failure"]]
    failures = [result for result in results if result["failure"]]
    summary = {
        "concurrency": concurrency,
        "completed": len(durations),
        "failures": failures,
        "p50_seconds": percentile(durations, 0.50),
        "p95_seconds": percentile(durations, 0.95),
        "demo_fixture": any(result.get("demo_fixture") for result in results),
    }
    print(json.dumps(summary))
    return int(bool(failures) or summary["demo_fixture"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("-n", "--concurrency", type=int, default=5)
    parser.add_argument("--paper", type=Path, default=ROOT / "fixtures/pdfs/paper1_attention.pdf")
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("concurrency must be positive")
    return asyncio.run(load(args.base_url, args.concurrency, paper=args.paper))


if __name__ == "__main__":
    raise SystemExit(main())
