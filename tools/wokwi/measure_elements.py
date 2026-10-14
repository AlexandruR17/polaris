"""Measure wokwi-elements sizes and pin positions in Chromium (writes sizes.json).
Used once to produce geom_elements.json; needs measure.html with the bundle."""
import json, asyncio, pathlib
from playwright.async_api import async_playwright
TAGS = {"wokwi-stepper-motor": {"size": "17"}, "wokwi-mpu6050": {}, "wokwi-lcd2004": {"pins": "i2c"},
        "wokwi-ky-040": {}, "wokwi-potentiometer": {}, "wokwi-pushbutton": {}, "wokwi-slide-switch": {},
        "wokwi-led": {}, "wokwi-buzzer": {}, "wokwi-resistor": {}, "wokwi-pushbutton-6mm": {}}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        pg = await b.new_page()
        await pg.goto(pathlib.Path("measure.html").resolve().as_uri())
        out = {}
        for tag, attrs in TAGS.items():
            r = await pg.evaluate("""async ([tag, attrs]) => {
              const el = document.createElement(tag);
              for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, v);
              document.getElementById('root').appendChild(el);
              await el.updateComplete;
              const s = el.shadowRoot && el.shadowRoot.querySelector('svg'); const bb = (s||el).getBoundingClientRect();
              const pins = (el.pinInfo||[]).map(p => [p.name, p.x, p.y]);
              el.remove();
              return {w: bb.width, h: bb.height, pins};
            }""", [tag, attrs])
            out[tag] = r
        print(json.dumps(out, indent=0))
        json.dump(out, open("sizes.json", "w"))
        await b.close()
asyncio.run(main())
