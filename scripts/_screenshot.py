"""Drive a one-shot Home Assistant against a stub BTClock + capture PNGs.

Boots:
  * `hass` in a fresh temp config dir, frontend on 127.0.0.1:<ha_port>
  * an aiohttp stub on 127.0.0.1:<dev_port> serving the v4 fixture as if
    it were a real BTClock (settings/status/lights/dnd/frontlight)

Then drives Playwright through onboarding (creates a local user), adds
the BTClock integration via the REST API (deterministic, doesn't depend
on UI strings), and snaps screenshots of the integration page + device
page. The whole run is self-contained — every artefact lives under
`<repo>/.cache/screenshots-run/` and is wiped on next invocation.

The stub keeps responses static; this is for marketing/README screenshots,
not interactive demos. Run as `scripts/screenshot` from the repo root.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
CACHE_DIR = REPO_ROOT / ".cache" / "screenshots-run"

ONBOARDING_USER = "screenshots"
ONBOARDING_PASS = "screenshots"
ONBOARDING_NAME = "Screenshot User"


# ---- ports ------------------------------------------------------------------


def _free_port() -> int:
    """Return a free TCP port on localhost (race-window — caller must bind soon)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- scenarios --------------------------------------------------------------


@dataclass
class Scenario:
    """One end-to-end capture pass: stub config + which screenshots to take.

    `settings_overrides` lets a scenario poke at specific fields of the
    fixture before the stub serves it — used by the update-available
    scenario to pin `gitReleaseUrl` at a specific tag so the screenshot
    keeps showing 3.3.19 → 3.4.1 even after newer releases ship.
    """

    name: str
    settings_fixture: str
    status_fixture: str
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    capture_full_dashboard: bool = True
    capture_device_sections: bool = True
    capture_update_dialog: bool = False


def _scenarios() -> list[Scenario]:
    return [
        # Pass 1: v4 firmware. Full set of section crops + integration
        # overview + devices dashboard.
        Scenario(
            name="v4",
            settings_fixture="settings_v4_revb",
            status_fixture="status_v4_revb",
        ),
        # Pass 2: legacy 3.3.19 device with a 3.4.1 release available.
        # Used to capture the "Update available" more-info dialog.
        #
        # gitReleaseUrl is pinned to the *tags/3.4.1* endpoint (not
        # /releases/latest) so the screenshot keeps showing the
        # 3.3.19→3.4.1 jump even after Forgejo's "latest" rolls forward.
        # The 3.4.1 release ships with an empty `body`, so the
        # integration's compare-based fallback fetches
        # /compare/3.3.19...3.4.1 from Forgejo and synthesizes the
        # bullet list from real commit messages — that's what the
        # dialog screenshot ends up showing.
        Scenario(
            name="update",
            settings_fixture="settings_legacy",
            status_fixture="status_legacy",
            settings_overrides={
                "gitTag": "3.3.19",
                "gitRev": "abc1234",
                "hwRev": "REV_B_EPD_2_13",
                "gitReleaseUrl": (
                    "https://git.btclock.dev/api/v1/repos/btclock/"
                    "btclock_v3/releases/tags/3.4.1"
                ),
            },
            capture_full_dashboard=False,
            capture_device_sections=False,
            capture_update_dialog=True,
        ),
    ]


# ---- stub BTClock -----------------------------------------------------------


def _build_stub_app(scenario: Scenario, dev_port: int) -> web.Application:
    settings = json.loads((FIXTURES / f"{scenario.settings_fixture}.json").read_text())
    status = json.loads((FIXTURES / f"{scenario.status_fixture}.json").read_text())
    settings.update(scenario.settings_overrides)

    fl_status = {"flStatus": [1024] * settings.get("numScreens", 7)}
    sys_status = {
        "espFreeHeap": 180_000,
        "espHeapSize": 327_680,
        "espFreePsram": 6_000_000,
        "espPsramSize": 8_388_608,
        "fsUsedBytes": 1_500_000,
        "fsTotalBytes": 8_000_000,
        "rssi": -52,
        "txPower": 78,
    }
    dnd_status = status.get("dnd", {})

    app = web.Application()

    async def empty_ok(_):
        return web.Response(status=204)

    app.router.add_get("/api/settings", lambda r: web.json_response(settings))
    app.router.add_patch("/api/settings", empty_ok)
    app.router.add_get("/api/status", lambda r: web.json_response(status))
    app.router.add_get("/api/system_status", lambda r: web.json_response(sys_status))
    app.router.add_get(
        "/api/frontlight/status", lambda r: web.json_response(fl_status)
    )
    app.router.add_get("/api/lights", lambda r: web.json_response(status["leds"]))
    app.router.add_get("/api/dnd/status", lambda r: web.json_response(dnd_status))

    async def sse_handler(request: web.Request) -> web.StreamResponse:
        # Polling mode is what the screenshot run uses — but ship a working
        # SSE just in case a future call wires push mode through here.
        resp = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
        )
        await resp.prepare(request)
        body = json.dumps(status)
        await resp.write(f"event: status\ndata: {body}\n\n".encode())
        # Hold open until the client disconnects.
        try:
            while not request.transport.is_closing():
                await asyncio.sleep(5)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        return resp

    app.router.add_get("/events", sse_handler)
    return app


@contextlib.asynccontextmanager
async def stub_btclock(scenario: Scenario, port: int):
    runner = web.AppRunner(_build_stub_app(scenario, port), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield
    finally:
        await runner.cleanup()


# ---- HA temp config ---------------------------------------------------------


def _write_ha_config(config_dir: Path, ha_port: int) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    cc_dir = config_dir / "custom_components"
    cc_dir.mkdir()
    os.symlink(REPO_ROOT / "custom_components" / "btclock", cc_dir / "btclock")

    (config_dir / "configuration.yaml").write_text(
        "default_config:\n"
        "logger:\n"
        "  default: warning\n"
        "  logs:\n"
        "    custom_components.btclock: warning\n"
        "http:\n"
        "  server_host: 127.0.0.1\n"
        f"  server_port: {ha_port}\n"
        "frontend:\n"
    )


async def _wait_for_ha(base_url: str, *, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    async with aiohttp.ClientSession() as s:
        while time.monotonic() < deadline:
            try:
                async with s.get(f"{base_url}/manifest.json") as r:
                    if r.status == 200:
                        return
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(1)
    raise RuntimeError(f"Home Assistant did not come up at {base_url}")


# ---- onboarding + integration setup over REST ------------------------------


async def _onboard_and_get_token(base_url: str) -> str:
    """Walk HA's onboarding REST endpoints and return a long-lived access token.

    Mirrors the steps the frontend takes on first boot. Skipping the UI here
    keeps the script resilient to frontend redesigns.
    """
    async with aiohttp.ClientSession() as s:
        # 1. Create the owner user.
        async with s.post(
            f"{base_url}/api/onboarding/users",
            json={
                "client_id": base_url + "/",
                "name": ONBOARDING_NAME,
                "username": ONBOARDING_USER,
                "password": ONBOARDING_PASS,
                "language": "en",
            },
        ) as r:
            if r.status not in (200, 403):
                raise RuntimeError(f"users onboarding failed: {r.status} {await r.text()}")
            payload = await r.json() if r.status == 200 else {}
        auth_code = payload.get("auth_code")
        if not auth_code:
            # Already-onboarded environment — fetch a fresh code via auth login.
            auth_code = await _login_and_get_code(s, base_url)

        # 2. Exchange the auth code for a refresh + access token pair.
        async with s.post(
            f"{base_url}/auth/token",
            data={
                "client_id": base_url + "/",
                "grant_type": "authorization_code",
                "code": auth_code,
            },
        ) as r:
            tokens = await r.json()
            if "access_token" not in tokens:
                raise RuntimeError(f"token exchange failed: {tokens}")
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]
        headers = {"Authorization": f"Bearer {access}"}

        # 3. Walk the rest of onboarding so the dashboard renders without
        # a blocking modal. Each step is a no-op if already done. The
        # `integration` step in particular (HA 2025+) shows a "we found
        # compatible devices" screen if it isn't POSTed properly — it
        # requires both client_id AND redirect_uri.
        step_bodies: dict[str, dict[str, str]] = {
            "core_config": {},
            "analytics": {},
            "integration": {"client_id": base_url + "/", "redirect_uri": base_url + "/"},
        }
        for step, body in step_bodies.items():
            with contextlib.suppress(aiohttp.ClientError):
                async with s.post(
                    f"{base_url}/api/onboarding/{step}",
                    headers=headers,
                    json=body,
                ) as r:
                    if r.status >= 400:
                        print(
                            f"[screenshot] WARN onboarding/{step} → {r.status}: "
                            f"{await r.text()}",
                            file=sys.stderr,
                        )

        return refresh


async def _login_and_get_code(s: aiohttp.ClientSession, base_url: str) -> str:
    """Used when onboarding is already complete on a re-run — log in via the
    homeassistant auth provider and pull an authorization_code."""
    async with s.post(
        f"{base_url}/auth/login_flow",
        json={
            "client_id": base_url + "/",
            "handler": ["homeassistant", None],
            "redirect_uri": base_url + "/",
        },
    ) as r:
        flow = await r.json()
    flow_id = flow["flow_id"]
    async with s.post(
        f"{base_url}/auth/login_flow/{flow_id}",
        json={
            "client_id": base_url + "/",
            "username": ONBOARDING_USER,
            "password": ONBOARDING_PASS,
        },
    ) as r:
        result = await r.json()
    code = result.get("result")
    if not code:
        raise RuntimeError(f"login_flow did not yield a code: {result}")
    return code


async def _add_btclock_entry(base_url: str, refresh_token: str, dev_host: str) -> None:
    """Drive the BTClock config_flow through HA's flow REST API."""
    async with aiohttp.ClientSession() as s:
        # Trade refresh token for a fresh access token.
        async with s.post(
            f"{base_url}/auth/token",
            data={
                "client_id": base_url + "/",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as r:
            access = (await r.json())["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        async with s.post(
            f"{base_url}/api/config/config_entries/flow",
            headers=headers,
            json={"handler": "btclock", "show_advanced_options": False},
        ) as r:
            flow = await r.json()
        flow_id = flow["flow_id"]
        # The flow may walk multiple steps before creating the entry
        # (`user` → `update_mode` → done). Auto-fill each step from a
        # canned response map and re-POST until we hit `create_entry`.
        step_responses = {
            "user": {"host": dev_host},
            # Polling > push for screenshots — deterministic and avoids a
            # long-lived SSE connection holding the test browser open.
            "update_mode": {"update_mode": "polling", "scan_interval": 30},
        }
        for _ in range(6):  # cap iterations to avoid an infinite loop
            async with s.post(
                f"{base_url}/api/config/config_entries/flow/{flow_id}",
                headers=headers,
                json=step_responses.get(flow.get("step_id", "user"), {"host": dev_host}),
            ) as r:
                flow = await r.json()
            if flow.get("type") == "create_entry":
                return
            if flow.get("type") != "form":
                raise RuntimeError(f"config_flow yielded unexpected response: {flow}")
        raise RuntimeError(f"config_flow stuck after 6 steps: {flow}")


# ---- Playwright -------------------------------------------------------------


async def _capture_screenshots(
    base_url: str, refresh_token: str, out_dir: Path, scenario: Scenario
) -> list[Path]:
    from playwright.async_api import async_playwright

    # Mint a fresh access token from the refresh token; we'll seed both
    # into localStorage so the frontend skips the login screen entirely.
    # Trying to drive HA's <ha-textfield>-based login form across shadow
    # roots is brittle and breaks on minor frontend updates.
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{base_url}/auth/token",
            data={
                "client_id": base_url + "/",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as r:
            tokens = await r.json()
    access = tokens["access_token"]
    expires_in = int(tokens.get("expires_in", 1800))
    hass_tokens_js = json.dumps(
        {
            "access_token": access,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "expires": (int(time.time()) + expires_in) * 1000,
            "hassUrl": base_url,
            "clientId": base_url + "/",
            "ha_auth_provider": "homeassistant",
        }
    )

    saved: list[Path] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            device_scale_factor=2,
        )
        # Inject the token before any page script runs so the frontend's
        # auth bootstrap finds an authenticated session on first paint.
        await context.add_init_script(
            "window.localStorage.setItem('hassTokens', "
            + json.dumps(hass_tokens_js)
            + ");"
            "window.localStorage.setItem('selectedLanguage', '\"en\"');"
        )
        page = await context.new_page()

        if scenario.capture_full_dashboard:
            await page.goto(
                f"{base_url}/config/integrations/integration/btclock",
                wait_until="networkidle",
            )
            await page.wait_for_timeout(2500)
            out = out_dir / "integration_overview.png"
            await page.screenshot(path=str(out), full_page=True)
            saved.append(out)

        device_id = await _find_btclock_device_id(base_url, access)
        if device_id and scenario.capture_device_sections:
            await page.goto(
                f"{base_url}/config/devices/device/{device_id}",
                wait_until="networkidle",
            )
            saved.extend(await _capture_device_page(page, out_dir))
        elif not device_id:
            print("[screenshot] WARN no btclock device found", file=sys.stderr)

        if scenario.capture_full_dashboard:
            await page.goto(
                f"{base_url}/config/devices/dashboard?domain=btclock",
                wait_until="networkidle",
            )
            await page.wait_for_timeout(2000)
            out = out_dir / "devices_dashboard.png"
            await page.screenshot(path=str(out), full_page=True)
            saved.append(out)

        if scenario.capture_update_dialog and device_id:
            saved.extend(
                await _capture_update_dialog(page, base_url, access, device_id, out_dir)
            )

        await browser.close()
    return saved


async def _capture_update_dialog(
    page, base_url: str, access_token: str, device_id: str, out_dir: Path
) -> list[Path]:
    """Open the Firmware update entity's more-info dialog and screenshot it.

    Triggers HA's `hass-more-info` event with the firmware update entity
    id so the standard update dialog (current → latest, release notes,
    Install button) opens. We also snap the device page for context, so
    the docs can show both the in-card "Update available" hint and the
    full dialog the user lands in when they click it.
    """
    saved: list[Path] = []

    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base_url}/api/states", headers=headers) as r:
            states = await r.json() if r.status < 400 else []
    update_entity = next(
        (
            st["entity_id"]
            for st in states
            if st["entity_id"].startswith("update.btclock")
        ),
        None,
    )
    if not update_entity:
        print("[screenshot] WARN no update entity found", file=sys.stderr)
        return saved

    # Device-page shot first — establishes the entry point users click.
    # Viewport tall enough to fit the device page; the device card crop
    # itself stays bounded by HA's own card layout.
    await page.set_viewport_size({"width": 1400, "height": 1600})
    await page.goto(
        f"{base_url}/config/devices/device/{device_id}", wait_until="networkidle"
    )
    await page.wait_for_timeout(2500)
    out = out_dir / "update_device_card.png"
    await page.screenshot(path=str(out))
    saved.append(out)

    # Drop to a narrow viewport for the dialog shot — HA renders the
    # more-info modal at a fixed CSS width and pins it to the top of the
    # viewport, so a smaller frame yields a tightly-cropped doc image
    # without any after-the-fact PIL cropping. The host element itself
    # has zero size (it portals its content), which is why
    # element-screenshot via locator was unreliable.
    #
    # Height tuned so the synthesized release-notes bullet list (one line
    # per commit between installed↔latest, currently ~39 commits for
    # 3.3.19→3.4.1) fits without internal scrolling. Bump if a future
    # release widens the diff further.
    await page.set_viewport_size({"width": 720, "height": 1400})
    await page.wait_for_timeout(500)
    await page.evaluate(
        "(eid) => { document.querySelector('home-assistant').dispatchEvent("
        "new CustomEvent('hass-more-info', "
        "{bubbles: true, composed: true, detail: {entityId: eid}})); }",
        update_entity,
    )
    try:
        await page.wait_for_function(
            "!!document.querySelector('home-assistant')?.shadowRoot"
            "?.querySelector('ha-more-info-dialog')",
            timeout=10_000,
        )
    except Exception:
        print("[screenshot] WARN update dialog did not mount", file=sys.stderr)
    # Release-notes fetch + dialog open animation; 2s is the comfortable
    # floor across observed runs.
    await page.wait_for_timeout(2000)

    out = out_dir / "update_dialog.png"
    await page.screenshot(path=str(out))
    saved.append(out)
    return saved


async def _capture_device_page(page, out_dir: Path) -> list[Path]:
    """Take a full-page device shot, then crop each section card out of it.

    HA's device page lays out one `ha-device-entities-card` per
    EntityCategory (Controls / Sensors / Configuration / Diagnostic) plus
    a Device-info card at the top. Each card lives inside a shadow root,
    so we walk the DOM in JS to find their document-relative bounding
    rects, then PIL-crop the full-page PNG. Doing it client-side after
    the screenshot avoids brittle Playwright shadow-DOM selectors.

    HA's frontend scrolls inside an internal container, so Playwright's
    `full_page=True` only captures the visible viewport. Resize the
    viewport tall enough to fit every card before snapping — the device
    page tops out around 5000 CSS px, so 6000 leaves headroom.
    """
    from PIL import Image

    await page.set_viewport_size({"width": 1400, "height": 6000})
    # Re-render after the resize: the entity cards lay themselves out
    # against the new viewport, so we wait for layout to settle before
    # measuring rects.
    await page.wait_for_timeout(2500)

    saved: list[Path] = []
    full = out_dir / "device_page.png"
    await page.screenshot(path=str(full), full_page=True)
    saved.append(full)

    # device_scale_factor=2 means 1 CSS px = 2 PNG px; rects come back in
    # CSS px so we multiply when slicing.
    rects = await page.evaluate(_DEVICE_PAGE_RECTS_JS)
    if not rects:
        print(
            "[screenshot] WARN device page yielded no card rects — skipping crops",
            file=sys.stderr,
        )
        return saved

    img = Image.open(full).convert("RGBA")
    scale = 2  # matches context device_scale_factor
    pad = 8  # CSS px breathing room around each crop
    for header, r in rects.items():
        left = max(0, int((r["x"] - pad) * scale))
        top = max(0, int((r["y"] - pad) * scale))
        right = min(img.width, int((r["x"] + r["w"] + pad) * scale))
        bottom = min(img.height, int((r["y"] + r["h"] + pad) * scale))
        if right <= left or bottom <= top:
            print(
                f"[screenshot] WARN bad rect for {header!r}: "
                f"({left},{top},{right},{bottom}) — skipping",
                file=sys.stderr,
            )
            continue
        crop = img.crop((left, top, right, bottom))
        slug = "".join(c if c.isalnum() else "_" for c in header.lower()).strip("_")
        path = out_dir / f"section_{slug}.png"
        crop.save(path)
        saved.append(path)
    return saved


_DEVICE_PAGE_RECTS_JS = r"""
() => {
    // Walk every device-page card and report the document-relative rect of
    // each one we recognise by header. Pierce shadow roots iteratively —
    // HA's frontend nests a few layers deep below `<home-assistant>`.
    // Only the cards that document the BTClock integration. The
    // Notifications / Automations / Scenes / Scripts cards are HA-managed
    // and identical across every device — capturing them just adds noise
    // to the docs.
    const wanted = new Set([
        'Device info', 'Controls', 'Sensors', 'Configuration', 'Diagnostic',
    ]);
    const seen = new Set();
    const out = {};

    function* walk(root) {
        const stack = [root];
        while (stack.length) {
            const node = stack.pop();
            if (!node || seen.has(node)) continue;
            seen.add(node);
            yield node;
            if (node.shadowRoot) stack.push(node.shadowRoot);
            if (node.children) for (const c of node.children) stack.push(c);
        }
    }

    function readHeader(el) {
        if (!el) return null;
        // 1. Property / attribute on ha-device-entities-card etc.
        if (typeof el.header === 'string' && el.header.trim()) return el.header.trim();
        const attr = el.getAttribute && el.getAttribute('header');
        if (attr) return attr.trim();
        // 2. ha-card with a slot=header child
        const slotted = el.querySelector && el.querySelector(':scope > [slot="header"], :scope > .card-header');
        if (slotted && slotted.textContent.trim()) return slotted.textContent.trim();
        // 3. Look one shadow level deeper for a `.card-header` div.
        if (el.shadowRoot) {
            const inner = el.shadowRoot.querySelector('.card-header, [slot="header"]');
            if (inner && inner.textContent.trim()) return inner.textContent.trim();
        }
        return null;
    }

    for (const node of walk(document.body)) {
        if (!(node instanceof Element)) continue;
        const tag = node.tagName.toLowerCase();
        if (!tag.startsWith('ha-')) continue;
        if (!tag.includes('card') && !tag.includes('related')) continue;
        const header = readHeader(node);
        if (!header || !wanted.has(header)) continue;
        if (out[header]) continue;  // first hit wins (outer card vs inner ha-card)
        const r = node.getBoundingClientRect();
        if (r.width < 50 || r.height < 50) continue;
        out[header] = {
            x: r.x + window.scrollX,
            y: r.y + window.scrollY,
            w: r.width,
            h: r.height,
        };
    }
    return out;
}
"""


async def _find_btclock_device_id(base_url: str, access_token: str) -> str | None:
    """Resolve the BTClock device id via /api/states + /api/template.

    `device_entries('btclock') | first` returned empty in practice (the
    template helper expects a config_entry id, not a domain). Going
    through a known entity is more reliable: pick any `sensor.btclock_*`
    state and ask `device_id('that')`.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base_url}/api/states", headers=headers) as r:
            if r.status >= 400:
                return None
            states = await r.json()
        sample = next(
            (
                st["entity_id"]
                for st in states
                if st["entity_id"].startswith(("sensor.btclock", "switch.btclock"))
            ),
            None,
        )
        if sample is None:
            return None
        async with s.post(
            f"{base_url}/api/template",
            headers=headers,
            json={"template": "{{ device_id('" + sample + "') }}"},
        ) as r:
            if r.status >= 400:
                return None
            text = (await r.text()).strip()
    return text if text and text != "None" else None


# ---- entry point ------------------------------------------------------------


async def _run_scenario(scenario: Scenario, out_dir: Path) -> list[Path]:
    """Boot a fresh HA + stub for one scenario and return the captured paths."""
    config_dir = CACHE_DIR / scenario.name
    if config_dir.exists():
        shutil.rmtree(config_dir)

    ha_port = _free_port()
    dev_port = _free_port()
    while dev_port == ha_port:
        dev_port = _free_port()

    base_url = f"http://127.0.0.1:{ha_port}"
    dev_host = f"127.0.0.1:{dev_port}"

    _write_ha_config(config_dir, ha_port)

    print(
        f"[screenshot] scenario={scenario.name} "
        f"HA={ha_port} stub={dev_port} cfg={config_dir}"
    )

    async with stub_btclock(scenario, dev_port):
        hass_proc = subprocess.Popen(
            [
                str(REPO_ROOT / ".venv" / "bin" / "hass"),
                "-c",
                str(config_dir),
            ],
            stdout=(CACHE_DIR / f"hass-{scenario.name}.log").open("wb"),
            stderr=subprocess.STDOUT,
        )
        try:
            await _wait_for_ha(base_url)
            print(f"[screenshot/{scenario.name}] HA is up — onboarding…")
            refresh = await _onboard_and_get_token(base_url)
            print(f"[screenshot/{scenario.name}] adding BTClock integration…")
            await _add_btclock_entry(base_url, refresh, dev_host)
            # Update entities only refresh on a 24h cadence by default;
            # poke a refresh so the latest_version is populated before
            # we try to capture the dialog. Harmless on the v4 scenario.
            await asyncio.sleep(2)
            await _trigger_update_refresh(base_url, refresh)
            await asyncio.sleep(2)
            print(f"[screenshot/{scenario.name}] capturing…")
            return await _capture_screenshots(base_url, refresh, out_dir, scenario)
        finally:
            hass_proc.terminate()
            try:
                hass_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                hass_proc.kill()
                hass_proc.wait()


async def _trigger_update_refresh(base_url: str, refresh_token: str) -> None:
    """Force HA to re-poll every Update entity so latest_version populates."""
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{base_url}/auth/token",
            data={
                "client_id": base_url + "/",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as r:
            access = (await r.json())["access_token"]
        with contextlib.suppress(aiohttp.ClientError):
            async with s.post(
                f"{base_url}/api/services/homeassistant/update_entity",
                headers={"Authorization": f"Bearer {access}"},
                json={"entity_id": "all"},
            ):
                pass


async def _amain(out_dir: Path) -> int:
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True)

    for scenario in _scenarios():
        saved = await _run_scenario(scenario, out_dir)
        for s in saved:
            try:
                rel = s.resolve().relative_to(REPO_ROOT)
                print(f"[screenshot/{scenario.name}] wrote {rel}")
            except ValueError:
                print(f"[screenshot/{scenario.name}] wrote {s}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "screenshots",
        help="Directory to write PNGs into (default: docs/screenshots)",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_amain(args.output))


if __name__ == "__main__":
    sys.exit(main())
