"""Render a Wokwi diagram.json to PNG with the official part graphics.

It is a preview for documentation and review: parts come from
@wokwi/elements (npm), board and module SVGs from wokwi-boards and
wokwi-docs, wires follow the diagram.json placement language. The real
simulator may differ in small details (wire corners, fonts).

usage: python tools/wokwi/render_diagram.py firmware/diagram.json docs/img/wokwi_diagram.png
needs: playwright (python) and a Chromium; assets are cached in tools/wokwi/.cache
"""
import asyncio
import html
import json
import os
import pathlib
import sys
import tarfile
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from geometry import GEOM, Part  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / ".cache"
ASSETS = {
    "elements.tgz": "https://registry.npmjs.org/@wokwi/elements/-/elements-1.9.2.tgz",
    "esp32.svg": "https://raw.githubusercontent.com/wokwi/wokwi-boards/main/boards/esp32-devkit-c-v4/board.svg",
    "ssd1306.svg": "https://raw.githubusercontent.com/wokwi/wokwi-boards/main/boards/ssd1306/board.svg",
    "a4988.svg": "https://raw.githubusercontent.com/wokwi/wokwi-docs/main/docs/parts/wokwi-a4988.svg",
    "relay.svg": "https://raw.githubusercontent.com/wokwi/wokwi-docs/main/docs/parts/wokwi-relay-module.svg",
}
IMAGES = {"board-esp32-devkit-c-v4": "esp32.svg", "board-ssd1306": "ssd1306.svg",
          "wokwi-a4988": "a4988.svg", "wokwi-relay-module": "relay.svg"}
CHROMIUM = os.environ.get("POLARIS_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def fetch_assets():
    CACHE.mkdir(exist_ok=True)
    for name, url in ASSETS.items():
        dest = CACHE / name
        if not dest.exists():
            with urllib.request.urlopen(url, timeout=60) as r:
                dest.write_bytes(r.read())
    bundle = CACHE / "wokwi-elements.bundle.js"
    if not bundle.exists():
        with tarfile.open(CACHE / "elements.tgz") as t:
            m = t.getmember("package/dist/wokwi-elements.bundle.js")
            bundle.write_bytes(t.extractfile(m).read())


def wire_points(diagram_parts, conn):
    a, b, color, instr = (conn + [[]])[:4]
    pa, pina = a.split(":", 1)
    pb, pinb = b.split(":", 1)
    x, y = diagram_parts[pa].pin(pina)
    tx, ty = diagram_parts[pb].pin(pinb)
    pts = [(x, y)]
    pre, post = instr, []
    if "*" in instr:
        k = instr.index("*")
        pre, post = instr[:k], instr[k + 1:]
    for s in pre:
        v = float(s[1:])
        x, y = (x + v, y) if s[0] == "h" else (x, y + v)
        pts.append((x, y))
    tail = [(tx, ty)]
    for s in reversed(post):
        v = float(s[1:])
        tx, ty = (tx + v, ty) if s[0] == "h" else (tx, ty + v)
        tail.append((tx, ty))
    if abs(x - tx) > 0.5 and abs(y - ty) > 0.5:
        pts.append((tx, y))  # horizontal first, then vertical
    pts += list(reversed(tail))
    return color, pts


def build_html(diagram):
    dparts = {}
    body = []
    for p in diagram["parts"]:
        part = Part(p["id"], p["type"], p["left"], p["top"], p.get("rotate", 0), p.get("attrs", {}))
        dparts[part.id] = part
    xs, ys = [], []
    for part in dparts.values():
        if part.type == "wokwi-text":
            xs += [part.left, part.left + 300]
            ys += [part.top, part.top + 30]
            continue
        x0, y0, x1, y1 = part.bbox()
        xs += [x0, x1]
        ys += [y0, y1]
    for conn in diagram["connections"]:
        _, pts = wire_points(dparts, conn)
        xs += [x for x, _ in pts]
        ys += [y for _, y in pts]
    pad = 30
    ox, oy = min(xs) - pad, min(ys) - pad
    width, height = max(xs) - ox + pad, max(ys) - oy + pad
    for part in dparts.values():
        style = (f"position:absolute;left:{part.left - ox}px;top:{part.top - oy}px;"
                 f"transform:rotate({part.rotate}deg);transform-origin:center center;")
        g = GEOM[part.type]
        if part.type == "wokwi-text":
            a = part.attrs
            body.append(f'<div style="{style}font:600 {a.get("fontSize", "16")}px Arial,sans-serif;'
                        f'color:{a.get("color", "#222")};white-space:pre">{html.escape(a["text"])}</div>')
        elif part.type in IMAGES:
            body.append(f'<img src="{IMAGES[part.type]}" style="{style}width:{g["w"]}px;height:{g["h"]}px">')
        else:
            attrs = " ".join(f'{k}="{html.escape(str(v))}"' for k, v in part.attrs.items())
            body.append(f'<div style="{style}width:{g["w"]}px;height:{g["h"]}px">'
                        f'<{part.type} {attrs}></{part.type}></div>')
    svg = [f'<svg style="position:absolute;left:0;top:0" width="{width}" height="{height}">']
    for conn in diagram["connections"]:
        color, pts = wire_points(dparts, conn)
        if not color:
            continue
        d = " ".join(f"{x - ox:.1f},{y - oy:.1f}" for x, y in pts)
        svg.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2.4" '
                   f'stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>')
        for x, y in (pts[0], pts[-1]):
            svg.append(f'<circle cx="{x - ox:.1f}" cy="{y - oy:.1f}" r="2.2" fill="{color}"/>')
    svg.append("</svg>")
    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<script src='wokwi-elements.bundle.js'></script></head>"
            f"<body style='margin:0;background:#fff'><div style='position:relative;width:{width}px;"
            f"height:{height}px'>{''.join(body)}{''.join(svg)}</div></body></html>")
    return page, width, height


async def render(diagram_path, out_png, scale=1.5):
    fetch_assets()
    diagram = json.loads(pathlib.Path(diagram_path).read_text())
    page, w, h = build_html(diagram)
    (CACHE / "diagram.html").write_text(page)
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROMIUM)
        pg = await b.new_page(viewport={"width": int(w), "height": int(h)}, device_scale_factor=scale)
        await pg.goto((CACHE / "diagram.html").as_uri())
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=str(out_png), full_page=True)
        await b.close()
    print(f"{out_png}: {int(w)}x{int(h)} px")


if __name__ == "__main__":
    asyncio.run(render(sys.argv[1], sys.argv[2]))
