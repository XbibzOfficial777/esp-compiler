# `compiler/` — ESP8266 / ESP32 Firmware Compiler

Arduino-cli toolchain for compiling ESP8266 and ESP32 firmware on Android/Termux.

## Supported Platforms

| Platform | Package | Default Board |
|---|---|---|
| ESP8266 | `esp8266:esp8266` | `esp8266:esp8266:generic` |
| ESP32 | `esp32:esp32` | `esp32:esp32:esp32` |

## Architecture

```
compiler/
├── config.json          # Paths, board, platform settings, patch rules
├── setup.py             # Interactive: arduino-cli + cores + board select + libs
├── compiler.py          # Interactive: detect platform + compat check + patch + compile
├── cleanup.py           # Interactive: build/libs/all cleanup
├── install.sh           # Curl-runnable entrypoint
└── lib/
    ├── __init__.py
    ├── installer.py     # Library engine, board detection, compatibility check
    ├── patcher.py       # Source auto-patcher (extensible rules)
    └── progress.py      # Spinner, progress bar, compile output parser
```

## Commands

```bash
# Curl install
bash install.sh                          # Full interactive setup
bash install.sh --setup                  # Setup only
bash install.sh --compile                # Compile only

# Direct
python3 setup.py                         # Interactive setup (both ESP8266 + ESP32 cores)
python3 compiler.py --source bibz.ino    # Detect platform + compat check + compile
python3 compiler.py --source bibz.ino --board esp32:esp32:esp32 -a
python3 compiler.py --source bibz.ino --dry-run   # Patch only
python3 cleanup.py --all --non-interactive
```

## Key Features

### Board Selection
Interactive menu to select platform (ESP8266/ESP32) and board variant.
Quick select: `1` ESP8266, `2` ESP32, `3` ESP32-S2, `4` ESP32-S3, `5` ESP32-C3.

### Compatibility Check
Auto-detects target platform from `#include` directives and `#ifdef` guards.
Warns if source uses ESP8266 headers but board is ESP32 (or vice versa).

### Real-Time Progress
- Spinner during library scanning
- Progress bar during compilation (tracks file count, linking, memory %)
- Parses `arduino-cli --verbose` output for real compilation steps

### Auto-Patching
Default patches in `lib/patcher.py`. Custom rules in `config.json` → `patches.rules[]`.
Types: `regex_replace`, `insert_after`.

### Auto Library Install
Scans `.ino` for `#include`, maps to library names, installs missing via `arduino-cli lib install`.
ESP8266/ESP32 built-in headers skipped automatically.

## Config (`config.json`)

```json
{
  "platforms": {
    "esp8266": { "package": "esp8266:esp8266", "manager_url": "...", "default_fqbn": "..." },
    "esp32": { "package": "esp32:esp32", "manager_url": "...", "default_fqbn": "..." }
  },
  "board": { "fqbn": "" },
  "source": { "file": "" },
  "libraries": { "dir": "", "auto_install": true, "extra": [] },
  "output": { "dir": "build" },
  "patches": { "auto_fix": true, "rules": [] }
}
```

## Gotchas

- **`--verbose` flag**: compiler always passes `--verbose` to arduino-cli for real-time progress parsing.
- **Built-in libs skipped**: ESP8266WiFi, ESP8266WebServer, WiFi.h, HTTPClient.h, etc. are core libraries.
- **Compatibility mismatch**: source with ESP8266 headers + ESP32 board = warning/fail. Use `--board` to fix.
- **Path resolution**: tries absolute → CWD → compiler dir. User paths like `bibz/bibz.ino` resolve from CWD.
- **Termux**: uses `pkg`, binary at `$HOME/.local/bin`. Uninstaller cleans secondary Termux path.
- **`config.json` auto-saved**: after each setup/compiler run. Edit manually or use flags.
