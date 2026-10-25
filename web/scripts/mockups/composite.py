"""Detect clean chroma displays and composite only real app captures.

python3 web/scripts/mockups/composite.py --sheet
python3 web/scripts/mockups/composite.py --select s1-1 s2-1 s3-1 s4-1 s5-1
"""
import argparse
import base64
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

WORK = Path(__file__).parent / "work"
PUBLIC = Path(__file__).resolve().parents[2] / "public/mockups"
CAPTURES = {"s1": "report-desktop", "s2": "report-mobile", "s3": "claim-graph", "s4": "live-check"}


def green_quad(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (42, 110, 90), (85, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError("No green display found")
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < rgb.shape[0] * rgb.shape[1] * .025:
        raise ValueError("Display is too small for a readable composite")
    perimeter = cv2.arcLength(contour, True)
    quad = next((q for epsilon in [.008, .012, .018, .025] if len(q := cv2.approxPolyDP(contour, epsilon * perimeter, True)) == 4), None)
    if quad is None or not cv2.isContourConvex(quad) or area / cv2.contourArea(quad) < .94:
        raise ValueError("No clean four-corner display; choose another candidate")
    points = quad.reshape(4, 2).astype(np.float32)
    total, delta = points.sum(axis=1), np.diff(points, axis=1).ravel()
    ordered = points[[total.argmin(), delta.argmin(), total.argmax(), delta.argmax()]]
    if len(np.unique(ordered, axis=0)) != 4:
        raise ValueError("Ambiguous display corners")
    # Fit the straight middle of each edge; rounded display corners otherwise
    # pull approxPolyDP's vertices inward and leave a chroma rim.
    lines = []
    boundary = contour.reshape(-1, 2).astype(float)
    for i in range(4):
        a, b = ordered[i], ordered[(i + 1) % 4]
        direction = b - a
        offset = boundary - a
        position = (offset * direction).sum(axis=1) / (direction ** 2).sum()
        distance = np.abs(direction[0] * offset[:, 1] - direction[1] * offset[:, 0]) / np.linalg.norm(direction)
        edge = boundary[(position > .2) & (position < .8) & (distance < 18)]
        if len(edge) < 2:
            raise ValueError("Display edge is occluded")
        vx, vy, x, y = cv2.fitLine(edge.astype(np.float32), cv2.DIST_L2, 0, .01, .01).ravel()
        lines.append((np.array([x, y]), np.array([vx, vy])))
    refined = []
    for i in range(4):
        a, u = lines[i - 1]
        b, v = lines[i]
        t = np.linalg.solve(np.column_stack((u, -v)), b - a)[0]
        refined.append(a + t * u)
    display = np.zeros_like(mask)
    cv2.drawContours(display, [contour], -1, 255, cv2.FILLED)
    return np.float32(refined), display


def composite(scene, capture):
    rgb = np.array(scene.convert("RGB"))
    quad, green = green_quad(rgb)
    center = quad.mean(axis=0)
    inset = center + (quad - center) * .996
    screen = np.array(capture.convert("RGB"), dtype=np.float32)
    h, w = screen.shape[:2]
    y, x = np.mgrid[0:h, 0:w]
    glare = .06 * (1 - y / h) * (1 - .35 * x / w)
    vignette = .04 * np.clip(((x / w - .5) ** 2 + (y / h - .5) ** 2) * 2, 0, 1)
    screen = np.uint8(np.clip((screen * (1 - glare[..., None]) + 255 * glare[..., None]) * (1 - vignette[..., None]), 0, 255))
    transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]), inset)
    size = (rgb.shape[1], rgb.shape[0])
    warped = cv2.warpPerspective(screen, transform, size, flags=cv2.INTER_LANCZOS4)
    alpha = cv2.warpPerspective(np.full((h, w), 255, np.uint8), transform, size)
    alpha = cv2.GaussianBlur(cv2.bitwise_and(alpha, green), (3, 3), .5).astype(float) / 255
    bezel = np.zeros(rgb.shape[:2], np.uint8)
    cv2.fillConvexPoly(bezel, np.int32(quad), 255)
    bezel = cv2.dilate(cv2.bitwise_or(bezel, green), np.ones((7, 7), np.uint8))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hsv[..., 1][(green > 0) & (bezel > 0)] = 0
    clean = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return Image.fromarray(np.uint8(np.clip(warped * alpha[..., None] + clean * (1 - alpha[..., None]), 0, 255)))


def sheet(paths, destination):
    result = Image.new("RGB", (1200, ((len(paths) + 1) // 2) * 440), "#FAF9F6")
    draw = ImageDraw.Draw(result)
    for i, path in enumerate(paths):
        thumb = ImageOps.contain(Image.open(path).convert("RGB"), (576, 390))
        x, y = (i % 2) * 600 + 12, (i // 2) * 440 + 12
        result.paste(thumb, (x + (576 - thumb.width) // 2, y))
        draw.text((x, y + 398), path.stem, fill="#141414", font_size=22)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.save(destination, quality=88)


def export(image, name):
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for factor, width in [(1, 768), (2, 1536)]:
        size = (width, round(image.height * width / image.width))
        resized = image.resize(size, Image.Resampling.LANCZOS)
        resized.save(PUBLIC / f"{name}@{factor}x.avif", quality=65)
        resized.save(PUBLIC / f"{name}@{factor}x.webp", quality=86)
    image.save(PUBLIC / f"{name}.webp", quality=86)
    buffer = io.BytesIO()
    ImageOps.contain(image, (24, 24)).save(buffer, "WEBP", quality=40)
    return {"width": image.width, "height": image.height, "blurDataURL": "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()}


def og_image(hero, font_path, destination):
    canvas = ImageOps.fit(hero.convert("RGB"), (1200, 630))
    overlay = Image.new("RGBA", canvas.size)
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1200, 630), fill=(15, 15, 14, 120))
    font = ImageFont.truetype(str(font_path), 74)
    for y, text in [(65, "Read your paper like"), (145, "Reviewer 2 would.")]:
        draw.text((600, y), text, font=font, fill="#FAF9F6", anchor="mt")
    Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB").save(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", action="store_true")
    parser.add_argument("--select", nargs="+")
    parser.add_argument("--og-font", type=Path)
    args = parser.parse_args()
    if args.sheet:
        sheet(sorted(WORK.glob("s?-?.png")), WORK / "scene-contact-sheet.webp")
    if args.select:
        manifest = {}
        for name in args.select:
            scene = name.split("-")[0]
            photo = Image.open(WORK / f"{name}.png")
            final = composite(photo, Image.open(WORK / "captures" / f"{CAPTURES[scene]}.png")) if scene in CAPTURES else photo.convert("RGB")
            manifest[scene] = export(final, scene)
        (PUBLIC / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        sheet([PUBLIC / f"{s}.webp" for s in manifest], PUBLIC.parents[1] / "docs/d15/mockups-contact-sheet.webp")
    if args.og_font:
        og_image(Image.open(PUBLIC / "s1.webp"), args.og_font, PUBLIC.parent / "brand/og-image.png")
