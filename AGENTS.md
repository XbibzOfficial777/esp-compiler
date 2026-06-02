# esp-compiler — ESP8266 / ESP32 Firmware Compiler Toolchain

Android/Termux toolchain that auto-installs `arduino-cli`, manages cores/libraries, patches source, and compiles `.ino` firmware with a real-time progress bar.

---

## Architecture

```
esp-compiler/
├── config.json          # Persisted after every setup/compile/clean run
├── setup.py             # Interactive: Python check → arduino-cli → cores → board → paths → libs
├── compiler.py          # Interactive: validate source → detect platform → compat check → patch → libs → compile
├── cleanup.py           # Safe removal: build artifacts / libs / all (protected-path aware)
├── install.sh           # curl-pipe-bash entrypoint: downloads repo, installs arduino-cli, creates `cesp` command
├── uninstall.sh         # Reverses install.sh: removes dir, shell entries, optionally arduino-cli + Arduino data
└── lib/
    ├── __init__.py      # Empty package marker
    ├── installer.py     # arduino-cli finder, core/lib install, include scanner, platform detection, compat check
    ├── patcher.py       # Source patching engine: 3 default patches + custom regex_replace/insert_after rules from config
    └── progress.py      # TUI: Spinner, ProgressBar, DownloadProgress, CompileProgress (parses arduino-cli verbosely)
```

## Commands

### Install
```bash
curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/main/install.sh | bash
source ~/.zshrc   # or ~/.bashrc
```
Installs to `~/.esp-compiler/`, binary at `~/.local/bin/cesp`, adds shell function to RC file.

### cesp
```bash
cesp setup                              # Interactive: all steps
cesp compile firmware.ino               # Full pipeline (patch + libs + compile)
cesp compile firmware.ino --dry-run     # Patch only, no libs/compile
cesp compile firmware.ino --no-patch    # Skip patching
cesp compile firmware.ino --no-libs     # Skip library check
cesp compile firmware.ino --board esp32:esp32:esp32 -v  # Override board, verbose output
cesp clean                              # Interactive cleanup menu
cesp clean --all                        # Full cleanup
cesp clean --build-only                 # Build artifacts only
cesp uninstall                          # Full removal
```

### Direct Python
```bash
python3 setup.py --platform esp32       # Install ESP32 core only
python3 setup.py --board esp32:esp32:esp32 --source firmware.ino
python3 compiler.py -s firmware.ino -b esp8266:esp8266:generic --dry-run
python3 cleanup.py -a --non-interactive
```

## Key Execution Flow (compiler.py)

1. **Config loading** — `config.json` auto-saved after every run. Always check for stale FQBN.
2. **Source validation** — `.ino` file must exist; warns if folder name != `.ino` basename (Arduino requirement).
3. **Platform detection** — scans `#include` directives and `#ifdef` guards, scores ESP8266 vs ESP32.
4. **Compatibility check** — if source uses `ESP8266WiFi.h` but board is ESP32, fails (unless confidence < 40%).
5. **Step selection** — interactive unless flags (`--dry-run`, `--no-patch`, `--no-libs`, `--all`) are given.
   - `--dry-run` runs patching in dry mode, skips libs + compile entirely.
   - No flags + no `--all` = interactive menu.
6. **Patching** — default patches fix common issues (EEPROM include, global scope, typo). Backups created as `.bak` before modification.
7. **Library check** — scans includes, maps via `HEADER_TO_LIB` dict, skips built-in headers (`SKIPPED_LIBS`). Unknown headers return `None` (not installed).
8. **Compile** — clears `~/.cache/arduino/sketches` and `output_dir` before each build. Validates FQBN format via regex (`vendor:arch:board`).

## Platform Detection & Compatibility

| Header | Signal | Platform |
|---|---|---|
| `ESP8266WiFi.h`, `ESP8266WebServer.h`, `ESP8266HTTPClient.h` | +2 | ESP8266 |
| `ESPAsyncTCP.h` | +2 | ESP8266 |
| `WiFi.h`, `BluetoothSerial.h`, `Preferences.h` | +2 | ESP32 |
| `AsyncTCP.h` | +2 | ESP32 |
| `#ifdef ESP8266` / `#ifdef ESP32` | +3 | detected |
| `ARDUINO_ARCH_ESP8266` / `ARDUINO_ARCH_ESP32` | +2 | detected |

- `ESPAsyncWebServer.h` works on **both** platforms (not in either header set).
- `source uses ESP8266 + board is ESP32` → fails at >40% confidence.
- `ESP8266_HEADERS` and `ESP32_HEADERS` sets are in `lib/installer.py`.

## Default Patches (lib/patcher.py)

| ID | What it fixes |
|---|---|
| `eeprom_include` | Insert `#include <EEPROM.h>` after first `ESP8266WiFi.h` or `WiFi.h` include |
| `web_password_scope` | Move `String web_password = "";` to global scope |
| `server_on_typo` | Fix `server._catchAllHandleron` → `server.on` |

Custom rules in `config.json` → `patches.rules[]`. Types: `regex_replace`, `insert_after`.

## Config (config.json)

- **Auto-saved** after every `cesp setup`, `cesp compile`, and `cesp clean` run.
- `board.fqbn` must be `vendor:arch:board` format (validated by regex before compile).
- `libraries.dir` defaults to `~/Arduino/libraries`. Extra libs in `libraries.extra[]`.
- `patches.auto_fix: true` enables default patching.
- `board.auto_detect: true` enables platform detection from source.

## Library Management

- Built-in headers (`SKIPPED_LIBS` in `installer.py`) are never auto-installed.
- `HEADER_TO_LIB` maps 20+ common headers (including `WebSocketsServer.h`) to `arduino-cli lib install` names.
- `HEADER_TO_GIT` maps headers to GitHub repo URLs as fallback when `arduino-cli lib install` fails.
  - `WebSocketsServer.h` → `https://github.com/Links2004/arduinoWebSockets.git`
- **Install flow**: arduino-cli first → if error + git_url exists → `git clone --depth 1` into lib_dir.
- Unknown headers are **silently skipped** (assumed to be project-local files).
- Add custom library requirements via `config.json` → `libraries.extra[]`.
- `auto_installed` list in config tracks what was auto-installed (used by `cleanup --libs-only`).

## Cleanup Safety

- **Protected path enforcement**: `/sdcard/`, `/storage/emulated/`, `/home`, `/root`, `/` and their shallow subdirs are **never** deleted.
- Symlinks are removed without following the target.
- Library directory deletion is always interactive (even in `--non-interactive` mode) to prevent data loss on Android.
- `--libs-only` uses `arduino-cli lib uninstall` per library rather than deleting the whole directory.

## Gotchas

- **`.ino` folder rule**: Arduino requires `firmware/firmware.ino` (folder name matches file basename). Compiler warns but doesn't block.
- **Backups**: Patching creates `source.ino.bak` if it doesn't exist. Never overwrites existing `.bak`.
- **Output dir hardcoded**: `/sdcard/sandbox/hasil_c` on Android, `~/Downloads/hasil_c` on Linux. NOT configurable (no `--output` flag, ignored in config).
- **`get_default_output_dir()`** in `lib/installer.py` detects platform via `/sdcard` path existence.
- **Cache cleared before compile**: `~/.cache/arduino/sketches` and output dir are deleted before each build.
- **FQBN injection protection**: Validated against `^[a-zA-Z0-9_]+:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+$`.
- **Shell RC**: installer auto-detects zsh vs bash; adds `cesp` shell function + PATH to RC file.
- **`--verbose`** is OFF by default. Pass `-v` to see arduino-cli verbose output.
- **`warn()` was originally missing** in `compiler.py` (FIX #1) — currently defined at line 76. Do not remove.
- **Platform selective install**: `python3 setup.py --platform esp32` installs ESP32 only. Default is both.
- **ESPAsyncWebServer.h** is treated as cross-platform (not in ESP8266_HEADERS or ESP32_HEADERS).
- **`config init` does not use `--overwrite`** — additional manager URLs accumulate via `config add`.
