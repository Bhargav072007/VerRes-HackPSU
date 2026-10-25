"""Offline regression checks using generated image fixtures and stub HTTP."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("generate", HERE / "generate.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


@pytest.fixture
def images(tmp_path):
    scene = Image.new("RGB", (600, 400), "#332211")
    ImageDraw.Draw(scene).rounded_rectangle((110, 70, 490, 330), radius=16, fill="#00ff00")
    scene.save(tmp_path / "scene.png")
    Image.new("RGB", (380, 260), "#f8f8f8").save(tmp_path / "capture.png")
    return tmp_path


def test_composite_preserves_scene_and_removes_green(images):
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from composite import composite, green_quad, sheet, export, og_image
from PIL import Image
from pathlib import Path
import numpy as np
p=Path(sys.argv[2]); photo=Image.open(p/'scene.png')
quad,mask=green_quad(np.array(photo)); assert quad.shape==(4,2)
result=composite(photo,Image.open(p/'capture.png')); result.save(p/'result.png')
sheet([p/'result.png'], p/'sheet.webp')
import composite as module
module.PUBLIC=p/'public'; info=export(result,'fixture')
assert info['blurDataURL'].startswith('data:image/webp;base64,')
assert len(list(module.PUBLIC.glob('*.avif')))==2
font=Path(sys.argv[1])/'work/Newsreader.ttf'
if font.exists():
 og_image(result,font,p/'og.png'); assert Image.open(p/'og.png').size==(1200,630)
"""
    subprocess.run(["/usr/bin/python3", "-c", code, str(HERE.resolve()), str(images)], check=True, capture_output=True)
    result = Image.open(images / "result.png")
    assert result.getpixel((10, 10)) == (51, 34, 17)
    assert min(result.getpixel((300, 200))) > 220
    assert not any(g > r + 50 and g > b + 50 for r, g, b in result.getdata())


def test_missing_quad_fails_loudly(images):
    code = "import sys; sys.path.insert(0, sys.argv[1]); from composite import green_quad; import numpy as np; green_quad(np.zeros((100,100,3),dtype=np.uint8))"
    result = subprocess.run(["/usr/bin/python3", "-c", code, str(HERE.resolve())], capture_output=True, text=True)
    assert result.returncode != 0
    assert "No green display found" in result.stderr


def test_cost_estimate_requires_reported_usage():
    assert generator.estimate("gpt-image-2", None) is None
    assert generator.estimate("gpt-image-2", {"input_tokens": 200, "output_tokens": 1000}) == .0155


def test_generation_cap_survives_reruns(tmp_path, monkeypatch):
    class Gateway:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, provider, path, **kwargs):
            assert path == "models", "No generation request may pass the cap"
            return SimpleNamespace(error=None, status=200, json=lambda: {"data": []})

    monkeypatch.setattr(generator, "WORK", tmp_path)
    monkeypatch.setattr(generator, "Gateway", Gateway)
    monkeypatch.setattr(generator, "os", SimpleNamespace(environ=SimpleNamespace(get=lambda _: "test-only")))
    (tmp_path / "generation-ledger.json").write_text(json.dumps([{"name": str(i)} for i in range(12)]))
    assert asyncio.run(generator.run(argparse.Namespace(model=None, discover=False, scenes=["s1"]))) == 1
