"""HTTP method + path tables for the BTClock API, keyed by firmware variant.

Values are `(method, path_template)` tuples. Path templates use `{}` for
positional substitution; query strings are built from keyword arguments by
the caller, not baked into the template.
"""

from __future__ import annotations

from typing import Final

from .models import ApiVariant

type PathEntry = tuple[str, str]

# Endpoint keys used by the API client.
#
#  settings_get   – GET  /api/settings
#  settings_patch – PATCH /api/settings or /api/json/settings
#  status         – GET  /api/status
#  system_status  – GET  /api/system_status
#  events         – GET  /events (SSE)
#  timer_pause    – pause screen rotation
#  timer_start    – resume screen rotation
#  show_screen    – switch to screen index
#  show_currency  – switch to currency code (3.4.0 only)
#  screen_next    – advance to next screen (3.4.0 only)
#  screen_prev    – go to previous screen (3.4.0 only)
#  lights_get     – read LED colours
#  lights_set     – write LED array
#  lights_color   – set all LEDs to one colour
#  lights_off     – turn all LEDs off
#  identify       – flash identify pattern (3.4.0 only)
#  restart        – reboot device (3.4.0 only)
#  full_refresh   – force full EPD refresh (3.4.0 only)
#  dnd_status     – GET DND status
#  dnd_enable     – enable DND (3.4.0 only)
#  dnd_disable    – disable DND (3.4.0 only)
#  frontlight_on / off / flash / brightness / status – 3.4.0 only

LEGACY_PATHS: Final[dict[str, PathEntry]] = {
    "settings_get": ("GET", "/api/settings"),
    "settings_patch": ("PATCH", "/api/json/settings"),
    "status": ("GET", "/api/status"),
    "system_status": ("GET", "/api/system_status"),
    "events": ("GET", "/events"),
    "timer_pause": ("GET", "/api/action/pause"),
    "timer_start": ("GET", "/api/action/timer_restart"),
    "show_screen": ("GET", "/api/show/screen/{}"),
    "lights_get": ("GET", "/api/lights"),
    "lights_set": ("PATCH", "/api/lights/set"),
    "lights_color": ("GET", "/api/lights/color/{}"),
    "lights_off": ("GET", "/api/lights/off"),
    "dnd_status": ("GET", "/api/dnd/status"),
    "restart": ("GET", "/api/restart"),
    "full_refresh": ("GET", "/api/full_refresh"),
    "identify": ("GET", "/api/identify"),
}

V3_4_PATHS: Final[dict[str, PathEntry]] = {
    "settings_get": ("GET", "/api/settings"),
    "settings_patch": ("PATCH", "/api/settings"),
    "status": ("GET", "/api/status"),
    "system_status": ("GET", "/api/system_status"),
    "events": ("GET", "/events"),
    "timer_pause": ("POST", "/api/action/pause"),
    "timer_start": ("POST", "/api/action/timer_restart"),
    "show_screen": ("POST", "/api/show/screen"),  # ?s=
    "show_currency": ("POST", "/api/show/currency"),  # ?c=
    "show_text": ("POST", "/api/show/text"),  # ?t=
    "show_custom": ("POST", "/api/show/custom"),  # JSON array body
    "screen_next": ("POST", "/api/screen/next"),
    "screen_prev": ("POST", "/api/screen/previous"),
    "lights_get": ("GET", "/api/lights"),
    "lights_set": ("POST", "/api/lights/set"),
    "lights_color": ("POST", "/api/lights/color"),  # ?c=
    "lights_off": ("POST", "/api/lights/off"),
    "identify": ("POST", "/api/identify"),
    "restart": ("POST", "/api/restart"),
    "full_refresh": ("POST", "/api/full_refresh"),
    "dnd_status": ("GET", "/api/dnd/status"),
    "dnd_enable": ("POST", "/api/dnd/enable"),
    "dnd_disable": ("POST", "/api/dnd/disable"),
    "frontlight_status": ("GET", "/api/frontlight/status"),
    "frontlight_on": ("POST", "/api/frontlight/on"),
    "frontlight_off": ("POST", "/api/frontlight/off"),
    "frontlight_flash": ("POST", "/api/frontlight/flash"),
    "frontlight_bright": ("POST", "/api/frontlight/brightness"),  # ?b=
    "auto_update": ("POST", "/api/firmware/auto_update"),
    "upload_firmware": ("POST", "/upload/firmware"),
    "upload_webui": ("POST", "/upload/webui"),
}

PATHS: Final[dict[ApiVariant, dict[str, PathEntry]]] = {
    ApiVariant.LEGACY: LEGACY_PATHS,
    ApiVariant.V3_4: V3_4_PATHS,
}
