"""Record a completed real job, selecting paper1/2/3 by its uploaded PDF digest."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.app.providers.http import get_client  # noqa: E402
from api.app.routes.demo import RECORDINGS, recording_name, validate_recording  # noqa: E402


async def record(job_id, base_url="http://localhost:8000", *, directory=RECORDINGS, client=None):
    client = client or get_client("demo-tools")
    try:
        job_id = UUID(str(job_id))
        response = await client.get(f"{base_url.rstrip('/')}/jobs/{UUID(str(job_id))}", timeout=30)
        if response.status_code != 200:
            print(f"Recording incomplete: snapshot returned HTTP {response.status_code}")
            return 1
        snapshot = response.json()
        if snapshot.get("demo_fixture") or snapshot["job"].get("demo_fixture"):
            print("Recording refused: this job already contains demo fixture data.")
            return 1
        name = recording_name(snapshot["job"]["input"])
        events = snapshot["events"]
        validated = validate_recording(events)
        if not name or isinstance(validated, str) or not validated[-1].payload.paper:
            print("Recording incomplete: expected a completed real run of one of the demo PDFs.")
            return 1
        if str(validated[-1].job_id) != str(job_id):
            print("Recording refused: journal belongs to another job.")
            return 1
        review = validated[-1].payload.review
        if review and review.warning and "stub" in review.warning.lower():
            print("Recording refused: run with STUBS disabled first.")
            return 1
        digest = snapshot["job"]["input"]["sha256"]
        text = "".join(
            json.dumps({**event.model_dump(mode="json"), "input_sha256": digest}) + "\n"
            for event in validated
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.jsonl"
        temporary = directory / f".{name}.tmp"
        temporary.write_text(text)
        temporary.replace(path)
        print(f"Recorded {len(validated)} events to {path}")
        return 0
    except Exception as error:
        print(f"Recording incomplete ({type(error).__name__})")
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", type=Path, default=RECORDINGS)
    args = parser.parse_args()
    return asyncio.run(record(args.job_id, args.base_url, directory=args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
