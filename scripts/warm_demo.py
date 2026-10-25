"""Upload the three demo PDFs and save their final API report URLs."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_client import PAPERS, ROOT, run_job  # noqa: E402


async def warm(base_url, output=Path("demo.json"), *, fresh=False):
    reports = {}
    failed = False
    for name in PAPERS:
        result = await run_job(base_url, ROOT / "fixtures/pdfs" / f"{name}.pdf", fresh=fresh)
        print(json.dumps(result))
        if result["job_id"]:
            reports[name] = {key: result[key] for key in ("job_id", "report_url")}
        failed |= result["failure"] is not None
        # Keep already completed jobs recoverable if a later request fails.
        output.write_text(json.dumps(reports, indent=2) + "\n")
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("demo.json"))
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    return asyncio.run(warm(args.base_url, args.output, fresh=args.fresh))


if __name__ == "__main__":
    raise SystemExit(main())
