# Store Probe

Store Probe checks whether a downloaded app can run from the badge's writable storage.

## Usage

Launch **Store Probe** through App Store's Downloaded tab to test running code
from `/state/app_store/slot`. SELECT increments a visible counter and logs to
USB serial. HOME should return to the badge menu; reopen App Store to launch
the cached probe again without Wi-Fi.

It also runs as a normal installed app or in the simulator, but neither proves
writable-storage launching. It has no assets, dependencies, saved state, or
hard-coded app paths. `store.json` opts only `__init__.py` into the store catalog.
Wi-Fi is needed by App Store for the initial download, not by this probe.
