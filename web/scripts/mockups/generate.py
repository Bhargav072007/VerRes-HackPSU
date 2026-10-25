"""D15 scene generator. Raw scenes and the resumable ledger stay ignored.

Run with the API project's Python environment from the repository root.
Generation requests have no automatic retries: every attempt consumes the cap.
"""
import argparse
import asyncio
import base64
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from api.app.providers.http import Gateway, Policy  # noqa: E402

WORK = Path(__file__).parent / "work"
SCENES = {
    "s1": 'A 14-inch silver laptop, three-quarter view, on a light oak desk in a university library at golden hour. A printed paper with red pen annotations and a coffee cup sit beside it. The laptop is the large central subject, its display fully visible, landscape frame.',
    "s2": 'A hand holding a modern phone in portrait over an open printed journal article, overcast daylight. The phone display is fully visible and occupies most of the frame, portrait frame.',
    "s3": 'Two hands holding a tablet in landscape at a café table, dark moody light. The entire tablet display is visible, large in the frame, landscape frame.',
    "s4": 'A laptop, straight-on and slightly elevated, on a dark desk with a desk lamp. The screen is fully visible and large in the frame, landscape frame.',
    "s5": 'A close-up of a printed manuscript page with red-pen margin notes, no device. Printed journal columns and hand-drawn underlines, a restrained editorial still life, landscape frame. The green-screen requirement applies only if a device is present: do not add a device or green area to this scene.',
}
REQUIREMENTS = 'the device screen is a perfectly flat, evenly lit, solid pure green (#00FF00) rectangle filling the entire display area, no reflections, no UI, no text, no logos. photorealistic, editorial product photography, 50mm, shallow depth of field, natural window light, muted warm palette, no brand logos on devices. All four corners of any display must be visible, straight edges, no fingers over the display. No floating graphics or captions.'
MODELS = ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2", "gpt-image-1.5", "gpt-image-1"]


def estimate(model, usage):
    """Token estimate from official pricing; exclude unknown usage explicitly."""
    rates = (5, 40) if model == "gpt-image-1" else (5, 32) if model == "gpt-image-1.5" else (5, 30) if "2.5" in model else (2.5, 15)
    return round((usage.get("input_tokens", 0) * rates[0] + usage.get("output_tokens", 0) * rates[1]) / 1_000_000, 6) if usage else None


async def run(args):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("CHECK_INCOMPLETE: image API credential is unavailable.")
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "generation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger_path = WORK / "generation-ledger.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        headers = {"Authorization": f"Bearer {key}"}
        async with Gateway({"images": Policy("https://api.openai.com/v1/", 5, 60, 1)}, attempts=1) as gateway:
            available = await gateway.request("images", "models", headers=headers)
            if available.error or available.status != 200:
                print(f"CHECK_INCOMPLETE: model discovery failed (HTTP {available.status}).")
                return 1
            ids = {m["id"] for m in available.json().get("data", [])}
            model = args.model or next((m for m in MODELS if m in ids), "gpt-image-1")
            print(f"Image model: {model}", flush=True)
            if args.discover:
                return 0
            for scene in args.scenes:
                for candidate in [1, 2]:
                    name = f"{scene}-{candidate}"
                    if any(r["name"] == name and r.get("complete") for r in ledger):
                        continue
                    if len(ledger) >= 12:
                        print("CHECK_INCOMPLETE: hard cap of 12 generation attempts reached.")
                        return 1
                    record = {"name": name, "model": model, "complete": False}
                    ledger.append(record)
                    ledger_path.write_text(json.dumps(ledger, indent=2))
                    print(f"Generating {name}; attempt {len(ledger)}/12", flush=True)
                    result = await gateway.request("images", "images/generations", method="POST", timeout=600, headers=headers, json={"model": model, "prompt": SCENES[scene] + " " + REQUIREMENTS, "quality": "high", "size": "1024x1536" if scene == "s2" else "1536x1024", "n": 1})
                    if result.error or result.status != 200:
                        print(f"CHECK_INCOMPLETE: generation failed (HTTP {result.status}); response withheld.")
                        return 1
                    try:
                        payload = result.json()
                        (WORK / f"{name}.png").write_bytes(base64.b64decode(payload["data"][0]["b64_json"], validate=True))
                    except (ValueError, KeyError, IndexError, TypeError):
                        print("CHECK_INCOMPLETE: invalid image response; response withheld.")
                        return 1
                    record.update(complete=True, usage=payload.get("usage"), estimated_usd=estimate(model, payload.get("usage")))
                    ledger_path.write_text(json.dumps(ledger, indent=2))
                    print(f"Saved {name}. Estimated spend so far: ${sum(r.get('estimated_usd') or 0 for r in ledger):.4f}; unknown usage: {sum(r.get('estimated_usd') is None for r in ledger)} attempts.", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", nargs="+", choices=SCENES, default=list(SCENES))
    parser.add_argument("--model")
    parser.add_argument("--discover", action="store_true")
    try:
        sys.exit(asyncio.run(run(parser.parse_args())))
    except Exception as error:
        print(f"CHECK_INCOMPLETE: {type(error).__name__}; details withheld.")
        sys.exit(1)
