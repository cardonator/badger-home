"""One-slot GitHub app store; downloaded apps never write to /system."""

import json
import os
import sys

APP_DIR = next(path for path in (
    "/remote/apps/app_store", "/system/apps/app_store", "/apps/app_store",
) if is_dir(path))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

from store_storage import Slot, validate_catalog

PREVIEW = sys.platform == "webassembly"
badge.mode(HIRES | VSYNC)
screen.font = font.sins
BACKGROUND = color.rgb(13, 17, 23)
WHITE = color.rgb(240, 246, 252)
MUTED = color.rgb(160, 174, 190)
GREEN = color.rgb(95, 237, 131)
WARNING = color.rgb(255, 164, 120)
apps = []
index = 0
tab = 0
page = "browse"
message = ""
progress = 0
job = None
slot = None
source = None
demo_presses = 0


class DemoSlot:
    """Simulator-only state; no filesystem or network activity."""

    def __init__(self):
        self.current = None

    def clear(self):
        self.current = None


def load_preview_catalog():
    with open(APP_DIR + "/catalog.json") as handle:
        return validate_catalog(json.load(handle))

try:
    if PREVIEW:
        apps = load_preview_catalog()
        slot = DemoSlot()
    else:
        slot = Slot()
except (OSError, ValueError, KeyError, TypeError) as error:
    print("APP_STORE: startup:", error)
    message = str(error)
    page = "error"


def wrapped(text, x, y, width, lines=4):
    line = ""
    count = 0
    for word in text.split():
        candidate = line + (" " if line else "") + word
        if screen.measure_text(candidate)[0] > width and line:
            screen.text(line, x, y)
            y += 21
            count += 1
            if count >= lines:
                return
            line = word
        else:
            line = candidate
    screen.text(line, x, y)


def connect():
    import missing_details

    if missing_details.missing("WIFI_SSID"):
        raise ValueError("Set Wi-Fi details in secrets.py using USB")
    import wifi

    start = badge.ticks
    while not wifi.is_connected():
        if badge.ticks - start > 20000:
            raise OSError("Wi-Fi timed out; check connection and retry")
        if wifi.connect():
            return
        yield "Connecting to Wi-Fi"


def refresh():
    global apps, source, index
    if PREVIEW:
        yield from demo_wait("Demo: loading bundled catalog", 500)
        apps = load_preview_catalog()
        index = 0
        return
    from store_network import Source

    yield "Connecting to Wi-Fi"
    yield from connect()
    candidate = Source()
    yield "Reading GitHub catalog"
    loaded = candidate.catalog()
    apps = loaded
    source = candidate
    index = 0


def demo_wait(label, duration):
    start = badge.ticks
    while badge.ticks - start < duration:
        yield label


def download():
    global progress, tab
    if PREVIEW:
        app = apps[index]
        yield from demo_wait("Demo: connecting", 350)
        slot.clear()
        for value in (0, 25, 50, 75, 100):
            progress = value
            yield from demo_wait("Demo download %s%%" % value, 180)
        slot.current = {"id": app["id"], "title": app["title"]}
        tab = 1
        return
    if source is None or slot is None:
        raise ValueError("Refresh the catalog before downloading")
    app = apps[index]
    yield "Connecting to Wi-Fi"
    yield from connect()
    transfer = slot.install(app, lambda path: source.chunks(app["id"], path))
    try:
        for done, total in transfer:
            progress = done * 100 // max(1, total)
            yield "Downloading %s%%" % progress
    finally:
        transfer.close()
    tab = 1


def begin(task):
    global job, page, message, progress
    job = task
    progress = 0
    message = "Preparing"
    page = "busy"


def on_exit():
    global job
    if job is not None:
        job.close()
        job = None


def draw():
    screen.pen = BACKGROUND
    screen.rectangle(screen.clip)
    screen.pen = GREEN
    screen.text("App Store", 14, 12)
    screen.pen = MUTED
    screen.text("DEMO / NO WI-FI" if PREVIEW else "ONE APP SLOT", 168, 12)
    screen.pen = WHITE
    screen.text("Store Probe" if page == "demo_app" else
                ("Browse" if tab == 0 else "Downloaded"), 14, 47)
    screen.pen = MUTED
    screen.text("<  >", screen.width - 56, 47)
    screen.line(14, 73, screen.width - 14, 73)

    screen.pen = WHITE
    if page == "demo_app":
        screen.text("App is running (demo)", 14, 94)
        screen.pen = GREEN
        screen.text("Select presses: %s" % demo_presses, 14, 126)
        screen.pen = MUTED
        wrapped("Simulated launch. No downloaded code is executed.",
                14, 158, screen.width - 28, 2)
        footer = "Back / Left+Up: store"
    elif page == "error":
        screen.pen = WARNING
        wrapped(message, 14, 89, screen.width - 28, 5)
        footer = "Back: return   Menu: retry"
    elif page == "busy":
        wrapped(message, 14, 94, screen.width - 28)
        screen.pen = GREEN
        screen.rectangle(14, 170, (screen.width - 28) * progress // 100, 4)
        footer = "Back: cancel"
    elif page in ("confirm", "delete"):
        wrapped("Clear downloaded app?" if page == "delete" else
                "Download %s?" % apps[index]["title"], 14, 89, screen.width - 28, 2)
        screen.pen = MUTED
        wrapped("Demo only: no files or network. Replaces the demo slot." if PREVIEW else
                "Only this store's slot is cleared. Saved app state is kept.",
                14, 138, screen.width - 28, 3)
        footer = "Select: confirm   Back: cancel"
    elif tab == 1:
        current = slot.current if slot else None
        screen.text(current["title"] if current else "Slot is empty", 14, 94)
        screen.pen = MUTED
        wrapped(("Demo slot in memory only. Select to try the launch experience."
                 if PREVIEW else "One runtime copy. No archive or catalog cache.") if current else
                "Choose an app in Browse." + (" Try the simulated download and launch."
                 if PREVIEW else " Only its runtime files will be saved."),
                14, 126, screen.width - 28, 3)
        footer = "Select: run   Back: clear" if current else "Left: browse"
    elif apps:
        app = apps[index]
        screen.text(app["title"], 14, 89)
        screen.pen = MUTED
        wrapped(app["description"], 14, 119, screen.width - 28, 3)
        size = sum(entry["size"] for entry in app["files"])
        screen.text("%s B  /  %s of %s" % (size, index + 1, len(apps)), 14, 184)
        footer = "Up/Down: browse   Select: get"
    else:
        screen.text("Small apps. No firmware flash.", 14, 94)
        screen.pen = MUTED
        wrapped("Load the curated GitHub catalog over Wi-Fi. Nothing is cached yet.",
                14, 126, screen.width - 28, 3)
        footer = "Select: load catalog"
    screen.pen = MUTED
    screen.text(footer, 14, screen.height - 23)


def update():
    global job, page, message, tab, index, demo_presses
    if page == "demo_app":
        left_up = (
            (badge.held(BUTTON_LEFT) or badge.pressed(BUTTON_LEFT)) and
            (badge.held(BUTTON_UP) or badge.pressed(BUTTON_UP)) and
            (badge.pressed(BUTTON_LEFT) or badge.pressed(BUTTON_UP))
        )
        if badge.pressed(BUTTON_BACK) or left_up:
            page = "browse"
        elif badge.pressed(BUTTON_SELECT):
            demo_presses += 1
    elif page == "busy":
        try:
            if badge.pressed(BUTTON_BACK):
                job.close()
                job = None
                page = "browse"
            else:
                message = next(job)
        except StopIteration:
            job = None
            page = "browse"
        except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
            print("APP_STORE:", error)
            job.close()
            job = None
            message = str(error)
            page = "error"
    elif page in ("confirm", "delete"):
        if badge.pressed(BUTTON_BACK):
            page = "browse"
        elif badge.pressed(BUTTON_SELECT):
            if page == "confirm":
                begin(download())
            else:
                try:
                    slot.clear()
                    page = "browse"
                except OSError as error:
                    print("APP_STORE: clear:", error)
                    message = str(error)
                    page = "error"
    elif page == "error":
        if badge.pressed(BUTTON_BACK):
            page = "browse"
        elif badge.pressed(BUTTON_MENU):
            begin(refresh())
    else:
        if badge.pressed(BUTTON_LEFT) or badge.pressed(BUTTON_RIGHT):
            tab = 1 - tab
        if badge.pressed(BUTTON_MENU):
            begin(refresh())
        elif tab == 0:
            if apps:
                if badge.pressed(BUTTON_UP):
                    index = (index - 1) % len(apps)
                if badge.pressed(BUTTON_DOWN):
                    index = (index + 1) % len(apps)
                if badge.pressed(BUTTON_SELECT):
                    page = "confirm"
            elif badge.pressed(BUTTON_SELECT):
                begin(refresh())
        elif slot is not None and slot.current:
            if badge.pressed(BUTTON_BACK):
                page = "delete"
            elif badge.pressed(BUTTON_SELECT):
                if PREVIEW:
                    demo_presses = 0
                    page = "demo_app"
                else:
                    return slot.path
    draw()
    return None


selected = run(update).result
while selected is not None:
    print("APP_STORE: launching", selected)
    try:
        launch(selected)
        break
    except (OSError, ValueError, ImportError) as error:
        print("APP_STORE: launch failed:", error)
        message = "Launch failed: " + str(error)
        page = "error"
        selected = run(update).result
