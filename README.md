<p align="center">
  <br>
  <img src="https://img.shields.io/badge/Platform-ESP8266%20%7C%20ESP32-000000?style=for-the-badge&logo=espressif" alt="Platform">
  <img src="https://img.shields.io/badge/Version-2.0-00D2FF?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Author-Xbibz%20Official-FF6B35?style=for-the-badge" alt="Author">
</p>

<h1 align="center">ESP Compiler</h1>

<p align="center">
  <b>Compile ESP8266 & ESP32 firmware from terminal with zero hassle</b><br>
  <sub>Auto-detect platform. Auto-install libraries. Real-time progress bar.</sub>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> &bull;
  <a href="#-features">Features</a> &bull;
  <a href="#-commands">Commands</a> &bull;
  <a href="#-configuration">Config</a> &bull;
  <a href="#-troubleshooting">Troubleshooting</a>
</p>

---

## Quick Start

**One command to install everything:**

```bash
curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/main/install.sh | bash
```

**Then restart your shell:**

```bash
source ~/.zshrc   # or source ~/.bashrc
```

**Compile your first firmware:**

```bash
cesp setup                                    # Interactive setup
cesp compile --source firmware.ino --all      # Compile
```

That's it.

---

## Features

| Feature | Description |
|---|---|
| **Auto Platform Detection** | Scans `#include` directives to detect ESP8266 or ESP32 |
| **Auto Library Install** | Finds missing libraries and installs via `arduino-cli` |
| **Real-Time Progress** | Live progress bar with file count and memory usage |
| **Board Selection** | Interactive menu for ESP8266, ESP32, ESP32-S2/S3/C3 |
| **Compatibility Check** | Warns if source code doesn't match selected board |
| **Auto-Patching** | Fixes common code issues before compilation |
| **Beautiful TUI** | Clean terminal output with colors and symbols |
| **Configurable** | All paths, boards, patches via `config.json` |

---

## Commands

### Install / Uninstall

```bash
# Install (auto-detects bash/zsh, adds 'cesp' command)
curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/main/install.sh | bash

# Uninstall (removes everything cleanly)
curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/main/uninstall.sh | bash
```

### Using `cesp`

```bash
cesp setup                          # Interactive setup (board + paths + libs)
cesp compile firmware.ino           # Compile a .ino file (all steps)
cesp compile firmware.ino --dry-run # Patch only, no compile
cesp clean                          # Cleanup build artifacts
cesp help                           # Show all commands
cesp uninstall                      # Remove compiler
```

### Direct Python

```bash
python3 setup.py                                # Interactive setup
python3 compiler.py --source firmware.ino --all  # Full compile
python3 compiler.py --source firmware.ino --dry-run
python3 compiler.py --source firmware.ino --board esp32:esp32:esp32
python3 cleanup.py --all --non-interactive
```

---

## Board Selection

| # | Platform | FQBN |
|---|---|---|
| 1 | ESP8266 Generic | `esp8266:esp8266:generic` |
| 2 | ESP32 Generic | `esp32:esp32:esp32` |
| 3 | ESP32-S2 | `esp32:esp32:esp32s2` |
| 4 | ESP32-S3 | `esp32:esp32:esp32s3` |
| 5 | ESP32-C3 | `esp32:esp32:esp32c3` |

---

## How It Works

```
                         ┌──────────────┐
                         │  .ino File   │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │    Scan #include      │
                    │  Detect ESP8266/ESP32  │
                    └───────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
    ┌─────────▼─────────┐ ┌────▼────┐ ┌─────────▼─────────┐
    │  Auto-Patch Code  │ │Install  │ │ Compatibility     │
    │  (EEPROM, etc.)   │ │Missing  │ │ Check Board       │
    └─────────┬─────────┘ │Libs     │ └─────────┬─────────┘
              │           └────┬────┘           │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  arduino-cli compile │
                    │  with progress bar   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    .ino.bin file     │
                    └─────────────────────┘
```

---

## Configuration

`config.json` — all settings in one place:

```json
{
  "platforms": {
    "esp8266": {
      "package": "esp8266:esp8266",
      "manager_url": "https://arduino.esp8266.com/stable/package_esp8266com_index.json",
      "default_fqbn": "esp8266:esp8266:generic"
    },
    "esp32": {
      "package": "esp32:esp32",
      "manager_url": "https://espressif.github.io/arduino-esp32/package_esp32_index.json",
      "default_fqbn": "esp32:esp32:esp32"
    }
  },
  "board": { "fqbn": "" },
  "source": { "file": "" },
  "libraries": { "dir": "", "auto_install": true, "extra": [] },
  "output": { "dir": "build" },
  "patches": { "auto_fix": true, "rules": [] }
}
```

### Custom Patches

Add your own auto-fix rules:

```json
{
  "patches": {
    "auto_fix": true,
    "rules": [
      {
        "id": "my_fix",
        "type": "regex_replace",
        "search": "old_pattern",
        "replace": "new_pattern",
        "auto": true
      }
    ]
  }
}
```

---

## File Structure

```
esp-compiler/
├── install.sh              # Curl-runnable installer
├── uninstall.sh            # Curl-runnable uninstaller
├── config.json             # Configuration
├── setup.py                # Interactive setup
├── compiler.py             # Interactive compiler
├── cleanup.py              # Cleanup tool
├── README.md               # This file
├── AGENTS.md               # Dev reference
├── lib/
│   ├── __init__.py
│   ├── installer.py        # Library engine
│   ├── patcher.py          # Source patcher
│   └── progress.py         # Spinner, progress bar
└── bibz/                   # Example firmware (optional)
    └── bibz.ino
```

---

## Requirements

- **Python** 3.8+
- **arduino-cli** (auto-installed)
- **Internet** (for first-time setup only)

---

## Troubleshooting

### `command not found: cesp`

```bash
source ~/.zshrc   # or source ~/.bashrc
```

### `arduino-cli: command not found`

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Library install fails

```bash
# Update arduino-cli index
arduino-cli core update-index
arduino-cli lib update-index
```

### Wrong board selected

```bash
python3 compiler.py --source firmware.ino --board esp32:esp32:esp32
```

### Compilation shows "File not found"

Make sure your `.ino` file is in a directory with the same name:
```
firmware/
└── firmware.ino    # Must match directory name
```

---

## License

MIT License - use freely in your projects.

---

## Author

**Xbibz Official**

<p align="center">
  <a href="https://github.com/XbibzOfficial">
    <img src="https://img.shields.io/badge/GitHub-XbibzOfficial-181717?style=for-the-badge&logo=github" alt="GitHub">
  </a>
  <a href="https://t.me/XbibzOfficial">
    <img src="https://img.shields.io/badge/Telegram-%40XbibzOfficial-26A5E4?style=for-the-badge&logo=telegram" alt="Telegram">
  </a>
</p>

<p align="center">
  <i>Source Code By : <b>Xbibz Official</b></i>
</p>
