"""Integration handoff: verify a reviewed export before an explicitly authorized run."""

from pathlib import Path

from api.app.eval.bakeoff import run_bakeoff
from api.app.eval.reviews import verify_export
from api.app.verify.model import Model


async def run_reviewed_bakeoff(
    export: Path,
    reviews: Path,
    models: list[Model],
    *,
    dataset_version: str,
    output: Path,
    live_calls_authorized: bool = False,
) -> dict:
    if live_calls_authorized is not True:
        raise ValueError("live model calls require explicit authorization before execution")
    if output.exists():
        raise ValueError("output already exists; preserve previous run evidence")
    pairs = verify_export(export, reviews)
    output.parent.mkdir(parents=True, exist_ok=True)
    return await run_bakeoff(pairs, models, dataset_version=dataset_version, output=output)
