"""Web server for POLARIS Ground Station: serves the page and bridges the
GroundStation hub to every open browser tab over a WebSocket."""
import asyncio
import json
import pathlib
import weakref

from aiohttp import WSMsgType, web

from .hub import GroundStation

PKG = pathlib.Path(__file__).resolve().parent
WEB = PKG / "web"
ASSETS = PKG / "assets"

HUB = web.AppKey("hub", GroundStation)
CLIENTS = web.AppKey("clients", weakref.WeakSet)


def create_app(link="sim", db_path=None, online_tle=False):
    app = web.Application()
    clients = weakref.WeakSet()
    app[CLIENTS] = clients

    state = {"loop": None, "tasks": []}

    def emit(msg):
        # called from the link thread or the event loop
        loop = state["loop"]
        if loop is None or loop.is_closed():
            return
        text = json.dumps(msg, separators=(",", ":"))
        loop.call_soon_threadsafe(_fanout, clients, text)

    hub = GroundStation(emit, db_path=db_path, online_tle=online_tle)
    app[HUB] = hub

    async def on_startup(app):
        state["loop"] = asyncio.get_running_loop()
        hub.connect(link)
        state["tasks"] = [asyncio.create_task(_every(0.05, hub.tick_vehicle)),
                        asyncio.create_task(_every(0.5, hub.tick_slow, in_thread=True))]

    async def on_cleanup(app):
        for t in state["tasks"]:
            t.cancel()
        hub.stop()
        for q in list(clients):
            q.put_nowait(None)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", _index)
    app.router.add_get("/ws", _ws)
    app.router.add_static("/static/", WEB)
    app.router.add_static("/assets/", ASSETS)
    return app


def _fanout(clients, text):
    for q in list(clients):
        if q.qsize() < 2000:   # a stalled tab must not eat memory
            q.put_nowait(text)


async def _every(period, fn, in_thread=False):
    loop = asyncio.get_running_loop()
    while True:
        try:
            if in_thread:
                await loop.run_in_executor(None, fn)
            else:
                fn()
        except Exception as e:  # noqa: BLE001 - keep the station running
            print(f"[polaris] {fn.__name__}: {e!r}")
        await asyncio.sleep(period)


async def _index(request):
    return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


async def _ws(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    hub = request.app[HUB]
    q = asyncio.Queue()
    for msg in hub.snapshot():
        q.put_nowait(json.dumps(msg, separators=(",", ":")))
    request.app[CLIENTS].add(q)

    async def writer():
        while True:
            text = await q.get()
            if text is None or ws.closed:
                break
            await ws.send_str(text)

    wtask = asyncio.create_task(writer())
    try:
        async for m in ws:
            if m.type == WSMsgType.TEXT:
                try:
                    msg = json.loads(m.data)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict):
                    if msg.get("op") == "link":
                        # reconnecting stops a thread: keep it off the event loop
                        await asyncio.get_running_loop().run_in_executor(None, hub.handle, msg)
                    else:
                        hub.handle(msg)
            elif m.type == WSMsgType.ERROR:
                break
    finally:
        wtask.cancel()
        request.app[CLIENTS].discard(q)
    return ws
