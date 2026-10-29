import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "badge/apps/app_store"
sys.path.insert(0, str(APP))
import store_network
import store_storage


def manifest(files=None):
    files = files or {"__init__.py": b"print('hello')\n"}
    return {
        "id": "test_app",
        "title": "Test App",
        "description": "A test app.",
        "files": [
            {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in files.items()
        ],
    }


def chunks(data):
    for offset in range(0, len(data), 1024):
        yield data[offset:offset + 1024]


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.slot = store_storage.Slot(str(self.root / "store"))

    def install(self, files=None):
        files = files or {"__init__.py": b"print('hello')\n"}
        app = manifest(files)
        list(self.slot.install(app, lambda path: chunks(files[path])))
        return app

    def test_only_runtime_and_tiny_marker_persist(self):
        files = {"__init__.py": b"pass\n", "assets/picture.bin": b"x" * 2500}
        self.install(files)
        actual = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")
                        if path.is_file())
        self.assertEqual(actual, [
            "store/installed.json", "store/slot/__init__.py", "store/slot/assets/picture.bin",
        ])
        self.assertLess(Path(self.slot.record).stat().st_size, 80)
        reopened = store_storage.Slot(self.slot.root)
        self.assertEqual(reopened.current["id"], "test_app")
        self.assertEqual(Path(reopened.path, "assets/picture.bin").read_bytes(),
                         files["assets/picture.bin"])

    def test_replacement_retains_no_old_files_or_other_state(self):
        unrelated = self.root / "game_save.json"
        unrelated.write_text('{"score":42}')
        self.install({"__init__.py": b"pass\n", "old.bin": b"old"})
        self.install()
        self.assertFalse(Path(self.slot.path, "old.bin").exists())
        self.assertEqual(unrelated.read_text(), '{"score":42}')

    def test_bad_checksum_and_short_or_large_download_cleanup(self):
        for data in (b"wrong checksum", b"", b"x" * 1024):
            with self.subTest(data=len(data)):
                with self.assertRaises(ValueError):
                    list(self.slot.install(manifest(), lambda path: chunks(data)))
                self.assertIsNone(self.slot.current)
                self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_cancellation_closes_stream_and_cleans_slot(self):
        closed = []

        def stream(path):
            try:
                yield b"x" * 1024
                yield b"x" * 1024
            finally:
                closed.append(True)

        transfer = self.slot.install(manifest({"__init__.py": b"x" * 2048}), stream)
        self.assertEqual(next(transfer), (1024, 2048))
        transfer.close()
        self.assertEqual(closed, [True])
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_network_failure_cleans_slot(self):
        def stream(path):
            yield b"p"
            raise OSError("network down")

        with self.assertRaisesRegex(OSError, "network down"):
            list(self.slot.install(manifest(), stream))
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_low_space_keeps_state_reserve(self):
        stats = (4096, 4096, 256, 16, 16, 0, 0, 0, 0, 255)
        with patch.object(store_storage.os, "statvfs", return_value=stats):
            with self.assertRaisesRegex(ValueError, "64 KiB"):
                self.install()
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_app_at_limit_and_one_byte_above(self):
        app = manifest({"__init__.py": b"x" * store_storage.MAX_APP_BYTES})
        self.assertEqual(store_storage.validate_catalog({"schema": 1, "apps": [app]}), [app])
        app["files"][0]["size"] += 1
        with self.assertRaises(ValueError):
            list(self.slot.install(app, lambda path: chunks(b"")))

    def test_oversized_chunk_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "1 KiB"):
            list(self.slot.install(manifest({"__init__.py": b"x" * 2048}),
                                   lambda path: iter_stream(b"x" * 2048)))
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_interrupted_transfer_recovered_on_open(self):
        Path(self.slot.path).mkdir()
        Path(self.slot.path, "__init__.py").write_bytes(b"partial")
        Path(self.slot.record + ".tmp").write_text('{"id":')
        reopened = store_storage.Slot(self.slot.root)
        self.assertIsNone(reopened.current)
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_corrupt_marker_recovered_on_open(self):
        self.install()
        Path(self.slot.record).write_text('{"id":')
        self.assertIsNone(store_storage.Slot(self.slot.root).current)
        self.assertEqual(list(Path(self.slot.root).iterdir()), [])

    def test_unsafe_duplicate_and_conflicting_paths_rejected_before_deletion(self):
        self.install()
        for path in ("../outside", "/absolute", "a//b", "a/./b", "a\\b", "bad?path"):
            app = manifest()
            app["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                list(self.slot.install(app, lambda path: chunks(b"")))
            self.assertIsNotNone(self.slot.current)
        app = manifest()
        app["files"].append(copy.copy(app["files"][0]))
        with self.assertRaises(ValueError):
            store_storage.validate_catalog({"schema": 1, "apps": [app]})
        app = manifest({"__init__.py": b"", "a": b"", "a/b": b""})
        with self.assertRaises(ValueError):
            store_storage.validate_catalog({"schema": 1, "apps": [app]})

    def test_generated_catalog_matches_runtime_files(self):
        spec = importlib.util.spec_from_file_location(
            "build_store_catalog", ROOT / ".github/scripts/build_store_catalog.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual((APP / "catalog.json").read_text(), module.build())
        store_storage.validate_catalog(json.loads(module.build()))


def iter_stream(data):
    yield data


class Response:
    def __init__(self, content=b"", status=200):
        self.raw = io.BytesIO(content)
        self.status_code = status
        self.closed = False

    def close(self):
        self.closed = True


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.responses = []
        self.urls = []
        self.requests = types.SimpleNamespace(get=self.get)
        self.patcher = patch.dict(sys.modules, {"requests": self.requests})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def get(self, url, timeout):
        self.urls.append(url)
        self.assertEqual(timeout, 8)
        return self.responses.pop(0)

    def test_catalog_and_runtime_pinned_to_same_commit(self):
        sha = "a" * 40
        self.responses = [
            Response(json.dumps({"object": {"sha": sha}}).encode()),
            Response(json.dumps({"schema": 1, "apps": [manifest()]}).encode()),
            Response(b"pass\n"),
        ]
        source = store_network.Source()
        source.catalog()
        self.assertEqual(b"".join(source.chunks("test_app", "__init__.py")), b"pass\n")
        self.assertIn("/" + sha + "/", self.urls[1])
        self.assertIn("/" + sha + "/", self.urls[2])

    def test_metadata_limit_closes_response(self):
        result = Response(b"x" * 4097)
        self.responses = [result]
        with self.assertRaisesRegex(ValueError, "size limit"):
            store_network.read_json("https://example.test", 4096)
        self.assertTrue(result.closed)

    def test_http_failure_closes_response(self):
        result = Response(status=404)
        self.responses = [result]
        with self.assertRaisesRegex(OSError, "404"):
            store_network.read_json("https://example.test", 4096)
        self.assertTrue(result.closed)

    def test_cancel_download_closes_response(self):
        result = Response(b"x" * 2048)
        self.responses = [result]
        source = store_network.Source()
        source.revision = "a" * 40
        stream = source.chunks("test_app", "__init__.py")
        self.assertEqual(len(next(stream)), 1024)
        stream.close()
        self.assertTrue(result.closed)


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.pressed = set()
        self.held = set()
        badge = types.SimpleNamespace(
            mode=lambda mode: None, pressed=lambda button: button in self.pressed,
            held=lambda button: button in self.held,
            ticks=0,
        )
        screen = types.SimpleNamespace(
            width=320, height=240, clip=None,
            text=lambda *args: None, line=lambda *args: None,
            rectangle=lambda *args: None, measure_text=lambda text: (len(text) * 6, 8),
        )
        self.env = {
            "badge": badge, "screen": screen, "is_dir": lambda path: True,
            "font": types.SimpleNamespace(sins=None), "HIRES": 1, "VSYNC": 2,
            "color": types.SimpleNamespace(rgb=lambda *args: args),
            "run": lambda update: types.SimpleNamespace(result=None),
        }
        for button in ("BACK", "SELECT", "MENU", "UP", "DOWN", "LEFT", "RIGHT"):
            self.env["BUTTON_" + button] = button
        real_open = open

        def mapped_open(path, *args, **kwargs):
            return real_open(APP / "catalog.json"
                             if str(path).endswith("/catalog.json") else path,
                             *args, **kwargs)

        with patch("os.chdir"), patch("sys.platform", "webassembly"), \
                patch("builtins.open", side_effect=mapped_open):
            exec(compile((APP / "__init__.py").read_text(), "__init__.py", "exec"), self.env)

    def press(self, button):
        self.pressed.clear()
        self.pressed.add(button)
        return self.env["update"]()

    def test_preview_confirmation_cancel_and_navigation(self):
        self.assertTrue(self.env["PREVIEW"])
        self.assertEqual(self.env["apps"][0]["id"], "store_probe")
        self.assertIsNone(self.env["slot"].current)
        self.press("SELECT")
        self.assertEqual(self.env["page"], "confirm")
        self.press("BACK")
        self.assertEqual(self.env["page"], "browse")
        self.press("RIGHT")
        self.assertEqual(self.env["tab"], 1)

    def finish_job(self):
        for _ in range(20):
            self.env["badge"].ticks += 250
            self.press("")
            if self.env["job"] is None:
                return
        self.fail("Demo task did not finish")

    def test_preview_download_launch_and_return(self):
        self.press("SELECT")
        self.press("SELECT")
        self.finish_job()
        self.assertEqual(self.env["page"], "browse")
        self.assertEqual(self.env["tab"], 1)
        self.assertEqual(self.env["slot"].current["id"], "store_probe")
        self.assertEqual(self.env["progress"], 100)
        self.assertIsNone(self.press("SELECT"))
        self.assertEqual(self.env["page"], "demo_app")
        self.press("SELECT")
        self.assertEqual(self.env["demo_presses"], 1)
        self.press("BACK")
        self.assertEqual(self.env["page"], "browse")

    def test_preview_cancel_and_refresh(self):
        self.press("SELECT")
        self.press("SELECT")
        self.press("")
        self.press("BACK")
        self.assertEqual(self.env["page"], "browse")
        self.assertIsNone(self.env["slot"].current)
        content = (APP / "catalog.json").read_text()
        with patch("builtins.open", side_effect=lambda *args: io.StringIO(content)):
            self.press("MENU")
            self.finish_job()
        self.assertEqual(self.env["apps"][0]["id"], "store_probe")

    def test_preview_return_chord_in_either_order(self):
        for first, second in (("LEFT", "UP"), ("UP", "LEFT")):
            with self.subTest(first=first):
                self.held.clear()
                self.env["page"] = "demo_app"
                self.env["tab"] = 1
                self.press(first)
                self.assertEqual(self.env["page"], "demo_app")
                self.held.add(first)
                self.press(second)
                self.assertEqual(self.env["page"], "browse")
                self.assertEqual(self.env["tab"], 1)
                self.assertIsNone(self.env["job"])

    def test_preview_return_chord_simultaneous(self):
        self.env["page"] = "demo_app"
        self.pressed.update(("LEFT", "UP"))
        self.env["update"]()
        self.assertEqual(self.env["page"], "browse")

    def test_cached_launch_does_not_need_network(self):
        self.env["PREVIEW"] = False
        self.env["slot"] = types.SimpleNamespace(current={"title": "Probe"}, path="/state/test")
        self.env["tab"] = 1
        self.assertIsNone(self.env["source"])
        self.assertEqual(self.press("SELECT"), "/state/test")

    def test_clear_requires_confirmation(self):
        cleared = []
        self.env["slot"] = types.SimpleNamespace(
            current={"title": "Probe"}, clear=lambda: cleared.append(True))
        self.env["tab"] = 1
        self.press("BACK")
        self.assertEqual(self.env["page"], "delete")
        self.assertEqual(cleared, [])
        self.press("BACK")
        self.assertEqual(cleared, [])
        self.press("BACK")
        self.press("SELECT")
        self.assertEqual(cleared, [True])


if __name__ == "__main__":
    unittest.main()
