import subprocess
import re
import os
import json
import sys
from pathlib import Path


def run(cmd, check=False, capture=True, timeout=120):
    """Run a command with error handling."""
    try:
        r = subprocess.run(
            cmd, shell=isinstance(cmd, str),
            capture_output=capture, text=True, timeout=timeout
        )
        if check and r.returncode != 0:
            return None, r.stderr.strip() if r.stderr else ""
        return r.stdout.strip() if r.stdout else "", r.stderr.strip() if r.stderr else ""
    except subprocess.TimeoutExpired:
        return None, f"Command timed out after {timeout}s"
    except Exception as e:
        return None, str(e)


def get_arduino_cli(config):
    """Find arduino-cli binary path."""
    cli_path = config.get("arduino_cli", {}).get("path", "")
    if cli_path and os.path.isfile(cli_path):
        return cli_path
    for p in [os.path.expanduser("~/.local/bin/arduino-cli"), "/usr/local/bin/arduino-cli"]:
        if os.path.isfile(p):
            return p
    out, _ = run("which arduino-cli")
    if out:
        return out
    return None


def get_installed_cores(cli_path):
    """Get list of installed board cores."""
    out, err = run(f'"{cli_path}" core list --format json')
    if not out:
        return []
    try:
        data = json.loads(out)
        platforms = data.get("platforms", data) if isinstance(data, dict) else data
        results = []
        for p in platforms:
            if not isinstance(p, dict):
                continue
            core_id = p.get("id", "")
            releases = p.get("releases", {})
            installed_ver = ""
            for ver, info in releases.items():
                if isinstance(info, dict) and info.get("installed"):
                    installed_ver = ver
                    break
            if not installed_ver:
                for ver, info in releases.items():
                    if isinstance(info, dict):
                        installed_ver = ver
                        break
            results.append({
                "id": core_id,
                "name": p.get("name", core_id),
                "installed_version": installed_ver or p.get("installed_version", "")
            })
        return results
    except json.JSONDecodeError:
        return []


def get_available_boards(cli_path, package=None):
    """Get available boards from installed core(s)."""
    cores = get_installed_cores(cli_path)
    boards = []
    for core in cores:
        core_id = core.get("id", "")
        if package and not core_id.startswith(package):
            continue
        if core_id.startswith("esp8266:") or core_id.startswith("esp32:") or core_id.startswith("arduino:esp32"):
            boards.append({
                "fqbn": core_id,
                "name": core.get("name", ""),
                "version": core.get("installed_version", ""),
                "platform": "esp32" if "esp32" in core_id else "esp8266"
            })
    return boards


def get_all_boards(cli_path):
    """Get all boards from board listall."""
    out, _ = run(f'"{cli_path}" board listall --format json')
    if not out:
        return []
    try:
        data = json.loads(out)
        boards = data.get("boards", data) if isinstance(data, dict) else data
        results = []
        for b in boards:
            if not isinstance(b, dict):
                continue
            fqbn = b.get("fqbn", "")
            name = b.get("name", "")
            platform = "esp32" if "esp32" in fqbn else "esp8266" if "esp8266" in fqbn else "other"
            results.append({"fqbn": fqbn, "name": name, "platform": platform})
        return results
    except json.JSONDecodeError:
        return []


def get_installed_libs(cli_path):
    """Get list of installed libraries."""
    out, _ = run(f'"{cli_path}" lib list --format json')
    if not out:
        return []
    try:
        data = json.loads(out)
        libs = data.get("installed_libraries", data) if isinstance(data, dict) else data
        names = []
        for item in libs:
            if isinstance(item, dict):
                lib = item.get("library", item)
                name = lib.get("name", "") if isinstance(lib, dict) else ""
                if name:
                    names.append(name)
        return names
    except json.JSONDecodeError:
        return []


def search_lib(cli_path, name):
    """Search for a library by name."""
    out, _ = run(f'"{cli_path}" lib search --name "{name}" --format json')
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def install_lib(cli_path, name, extra_index_url=""):
    """Install a library. Returns (success, message)."""
    idx_flag = f'--git-url "{extra_index_url}"' if extra_index_url else ''
    out, err = run(f'"{cli_path}" lib install "{name}" {idx_flag}', timeout=180)
    if err and "Error" in err:
        if "already exists" in err:
            return True, "already installed"
        return False, err
    return True, out or "Installed"


def install_core(cli_path, package, manager_url=""):
    """Install a board core. Returns (success, message)."""
    out, err = run(
        f'"{cli_path}" config init --overwrite && '
        f'"{cli_path}" config set board_manager.additional_urls "{manager_url}" && '
        f'"{cli_path}" core update-index && '
        f'"{cli_path}" core install {package}',
        timeout=300
    )
    if err and "Error" in err:
        return False, err
    return True, "Core installed"


def scan_includes(source_file):
    """Parse .ino file for #include directives. Returns list of header names."""
    includes = []
    try:
        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.match(r'\s*#include\s*[<"]([^>"]+)[>"]', line)
                if m:
                    includes.append(m.group(1))
    except FileNotFoundError:
        pass
    return includes


HEADER_TO_LIB = {
    "ArduinoJson.h": "ArduinoJson",
    "DHT.h": "DHT sensor library",
    "Adafruit_Sensor.h": "Adafruit Unified Sensor",
    "BH1750.h": "BH1750",
    "LiquidCrystal_I2C.h": "LiquidCrystal I2C",
    "FastLED.h": "FastLED",
    "MFRC522.h": "MFRC522",
    "OneWire.h": "OneWire",
    "DallasTemperature.h": "DallasTemperature",
    "PubSubClient.h": "PubSubClient",
    "NTPClient.h": "NTPClient",
    "TimeLib.h": "Time",
    "TFT_eSPI.h": "TFT_eSPI",
    "U8g2lib.h": "U8g2",
    "Adafruit_GFX.h": "Adafruit GFX Library",
    "Adafruit_ST7735.h": "Adafruit ST7735 and ST7789 Library",
    "Adafruit_SSD1306.h": "Adafruit SSD1306",
    "ESPAsyncTCP.h": "ESPAsyncTCP",
    "ESPAsyncWebServer.h": "ESPAsyncWebServer",
}

# Headers that are part of the platform core, not installable separately
SKIPPED_LIBS = {
    "Arduino.h", "WProgram.h", "wiring_private.h",
    "avr/pgmspace.h", "avr/interrupt.h", "avr/wdt.h",
    "string.h", "stdio.h", "stdlib.h", "math.h",
    "ctype.h", "inttypes.h", "stdint.h",
    "ESP8266WiFi.h", "ESP8266WebServer.h", "WebServer.h",
    "EEPROM.h", "LittleFS.h", "FS.h", "SPI.h", "Wire.h",
    "SoftwareSerial.h", "ESP8266mDNS.h", "Hash.h",
    # ESP32 built-in
    "WiFi.h", "WiFiClient.h", "WiFiServer.h", "WiFiUdp.h",
    "BluetoothSerial.h", "ESP.h", "esp_wifi.h", "esp_event.h",
    "driver/gpio.h", "driver/uart.h", "soc/soc.h",
    "Update.h", "WebServer.h", "HTTPClient.h", "HTTPUpdate.h",
    "ArduinoOTA.h", "ESPmDNS.h", "Preferences.h",
}


def resolve_lib_name(header):
    """Map a header file name to an installable library name."""
    if header in SKIPPED_LIBS:
        return None
    if header in HEADER_TO_LIB:
        return HEADER_TO_LIB[header]
    base = header.replace(".h", "").replace(".hpp", "")
    return base


# ============================================================
# Board compatibility detection
# ============================================================

# ESP8266-specific headers
ESP8266_HEADERS = {
    "ESP8266WiFi.h", "ESP8266WebServer.h", "ESP8266HTTPClient.h",
    "ESP8266mDNS.h", "ESP8266httpUpdate.h",
    "ESPAsyncTCP.h", "ESPAsyncWebServer.h",
}

# ESP32-specific headers
ESP32_HEADERS = {
    "WiFi.h", "WiFiClient.h", "WiFiServer.h",
    "BluetoothSerial.h", "ESP.h",
    "esp_wifi.h", "esp_event.h", "esp_system.h",
    "driver/gpio.h", "driver/uart.h", "soc/soc.h",
    "ArduinoOTA.h", "ESPmDNS.h", "Preferences.h",
    "HTTPClient.h", "HTTPUpdate.h",
    "esp_task_wdt.h", "esp_timer.h",
}


def detect_platform(source_file):
    """Detect target platform from source file includes.
    Returns ("esp8266", confidence) or ("esp32", confidence) or ("unknown", 0)."""
    includes = scan_includes(source_file)
    esp8266_score = 0
    esp32_score = 0

    for header in includes:
        if header in ESP8266_HEADERS:
            esp8266_score += 2
        if header in ESP32_HEADERS:
            esp32_score += 2

    # Check for platform-specific defines
    try:
        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            if re.search(r'#if\s+.*ESP8266', content):
                esp8266_score += 3
            if re.search(r'#if\s+.*ESP32', content):
                esp32_score += 3
            if "ARDUINO_ARCH_ESP8266" in content:
                esp8266_score += 2
            if "ARDUINO_ARCH_ESP32" in content:
                esp32_score += 2
    except FileNotFoundError:
        pass

    total = esp8266_score + esp32_score
    if total == 0:
        return "unknown", 0

    if esp8266_score > esp32_score:
        conf = int((esp8266_score / total) * 100)
        return "esp8266", conf
    elif esp32_score > esp8266_score:
        conf = int((esp32_score / total) * 100)
        return "esp32", conf
    else:
        return "unknown", 50


def check_compatibility(source_file, board_fqbn):
    """Check if source file is compatible with selected board.
    Returns (compatible: bool, message: str)."""
    detected, confidence = detect_platform(source_file)

    if detected == "unknown":
        return True, "Could not detect platform (generic code?)"

    board_platform = "esp32" if "esp32" in board_fqbn else "esp8266"

    if detected == board_platform:
        return True, f"Source matches board platform ({detected}, {confidence}% confidence)"

    if confidence < 40:
        return True, f"Low confidence detection ({detected} {confidence}%), proceeding anyway"

    return False, (
        f"Platform mismatch: source uses {detected} ({confidence}%) "
        f"but board is {board_platform}. "
        f"Use --board to select the correct platform."
    )


def auto_install_libs(cli_path, source_file, lib_dir, extra_libs=None, extra_index_url=""):
    """Scan source file for includes and install missing libraries.
    Returns list of (lib_name, status) tuples."""
    includes = scan_includes(source_file)
    installed = get_installed_libs(cli_path)
    results = []
    to_install = set()

    for header in includes:
        lib_name = resolve_lib_name(header)
        if not lib_name:
            continue
        if lib_name not in installed:
            to_install.add(lib_name)

    if extra_libs:
        for lib in extra_libs:
            if lib and lib not in installed:
                to_install.add(lib)

    for lib_name in sorted(to_install):
        ok, msg = install_lib(cli_path, lib_name, extra_index_url)
        status = "installed" if ok else f"failed: {msg}"
        results.append((lib_name, status))

    return results
