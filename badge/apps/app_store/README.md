# App Store

App Store downloads one small app at a time into writable storage without replacing firmware.

## Usage

Install this app once using USB Disk Mode. Set the normal badge Wi-Fi details
in `secrets.py` on the device; never commit them. Open **App Store**, then press
SELECT to fetch the catalog. UP/DOWN selects an app; SELECT opens a download
confirmation. LEFT/RIGHT switches between Browse and Downloaded. MENU refreshes.
In Downloaded, SELECT launches the app; BACK asks to clear the slot. HOME returns
to the badge menu, not to the store. Reopen the store to run the cached app offline.

The simulator starts on the bundled catalog with a **DEMO / NO WI-FI** label.
SELECT opens confirmation, SELECT again simulates download progress, and the
Downloaded tab then offers an interactive Store Probe demo. SELECT increments
its counter; BACK or LEFT+UP held together returns to the store. Clearing and replacing the slot can also
be tried. MENU reloads the bundled catalog. All demo state is in memory and
resets with HOME/reload; no network requests, downloaded files, or downloaded
code execution occur. It demonstrates the experience, not hardware capability.
Actual Wi-Fi downloads, writable launch, and HOME/reopen still need physical
verification.

The demo's return controls belong to the simulated screen inside App Store.
They are not a global input wrapper: real downloaded apps launched with
`launch()` currently own their controls, and HOME returns to the badge menu.
Returning directly to the store would require a cooperative app lifecycle or
a separately verified runtime wrapper; this prototype does not provide that.

## Minimal storage

Only one app's explicitly listed runtime files are retained in
`/state/app_store/slot`, plus a tiny ID/title commit marker. No downloaded icons,
READMEs, archives, catalog, HTTP cache, or previous app versions are saved.
The installed app remains available offline until explicitly replaced or cleared.
Clearing the slot does not delete the downloaded app's separately saved state.

Downloads stream in 1 KiB chunks, verify exact sizes and SHA-256, and reserve
64 KiB of free space for other state. Apps are capped at 256 KiB and 32 runtime
files; catalog responses at 24 KiB. Replacement removes the old app first, after
confirmation. A failed, cancelled, or interrupted transfer leaves no launchable
partial app and is cleaned up immediately or on the next store opening.
There is deliberately no second copy for rollback.

Network operations have an 8-second per-request timeout. Input is serviced between
files/chunks, not during DNS, TLS, or a blocking socket read. The store uses the
firmware's HTTPS client; TLS certificate-validation behavior must be checked on
the target firmware. Checksums detect mismatches, not a compromised repository.
Only install code you trust: downloaded Python apps have full badge privileges.

## GitHub backing and compatible apps

`store_network.py` selects `cardonator/badger-home`, branch `main`. The prototype
files must be published there before hardware downloads work, or change BRANCH
to a published development branch. Catalog and file URLs are pinned to the same
resolved Git commit. Private repositories are not supported; no token is stored.

The initial catalog offers only **Store Probe**, a tiny path-independent app.
It is a launch experiment, not evidence that arbitrary existing apps are portable.
The main badge menu is unchanged; downloads appear only inside this store.

To opt an app in, add `store.json` with `title`, `description`, and a `files`
list relative to its directory. List only runtime Python/assets, including
`__init__.py`. The app must work from the current launch directory, must not
hard-code its `/system/apps/<name>` installation path, and must list any local
modules/assets it needs. Firmware-provided shared assets can remain in `/system`.
Do not opt system/launcher apps into this experimental store.

Regenerate sizes and checksums after changing any opted-in runtime files:

```sh
python3 .github/scripts/build_store_catalog.py
python3 .github/scripts/build_store_catalog.py --check
python3 -m unittest discover -s .github/scripts/tests -p 'test_app_store.py'
```

Before calling this hardware-ready, verify Wi-Fi errors and a successful download,
launch from `/state`, SELECT input, HOME, offline reopening, cancellation, low
space, and interrupted-transfer cleanup on a badge. No firmware or menu
modifications are needed by the prototype.
