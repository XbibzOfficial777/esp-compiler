#!/usr/bin/env python3
"""
ESP8266/ESP32 Firmware Compiler - Setup
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.installer import (
    run, get_arduino_cli, get_installed_cores,
    get_installed_libs, install_core, install_lib, auto_install_libs
)
from lib.progress import Spinner, DownloadProgress

CONFIG_PATH = Path(__file__).parent / "config.json"
HOME = Path.home()


class C:
    RST = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[1;31m"
    GRN = "\033[1;32m"
    YLW = "\033[1;33m"
    CYN = "\033[1;36m"
    GRY = "\033[90m"


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def banner():
    print()
    print(f"  {C.CYN}{'=' * 60}{C.RST}")
    print(f"  {C.CYN}{C.BOLD}  ESP8266 / ESP32  COMPILER - SETUP{C.RST}")
    print(f"  {C.CYN}{'=' * 60}{C.RST}")
    print()


def section(title):
    print(f"\n  {C.YLW}[>]{C.RST} {C.BOLD}{title}{C.RST}")


def ok(msg):
    print(f"      {C.GRN}[+]{C.RST} {msg}")


def fail(msg):
    print(f"      {C.RED}[-]{C.RST} {msg}")


def info(msg):
    print(f"      {C.GRY}[~]{C.RST} {msg}")


def prompt(msg, default=""):
    suffix = f" {C.GRY}({default}){C.RST}" if default else ""
    val = input(f"      {C.CYN}[?]{C.RST} {msg}{suffix}: ").strip()
    return val if val else default


def prompt_yn(msg, default=True):
    s = f"{C.GRN}Y{C.RST}/{C.RED}n{C.RST}" if default else f"{C.GRN}y{C.RST}/{C.RED}N{C.RST}"
    val = input(f"      {C.CYN}[?]{C.RST} {msg} [{s}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def divider():
    print(f"  {C.GRY}{'─' * 60}{C.RST}")


def prompt_source(allow_empty=False):
    while True:
        val = prompt("Source .ino file path")
        if not val and allow_empty:
            return None
        if not val:
            continue
        p = os.path.expanduser(val)
        if not os.path.isabs(p):
            p = os.path.join(os.getcwd(), p)
        if os.path.isfile(p):
            return os.path.normpath(p)
        fail(f"File not found: {val}")
        if not prompt_yn("Try different path?", default=True):
            return None


def prompt_path(msg, default):
    while True:
        val = prompt(msg, default)
        p = os.path.expanduser(val)
        if not os.path.isabs(p):
            p = os.path.join(os.getcwd(), p)
        if os.path.isdir(p) or not os.path.exists(p):
            return val
        fail(f"Not a directory: {val}")
        if not prompt_yn("Try different path?", default=True):
            return default


def check_python():
    section("Checking Python")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        fail(f"Python 3.8+ required, found {v.major}.{v.minor}")
        return False
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
    return True


def setup_arduino_cli(cfg, interactive=True):
    section("Checking arduino-cli")
    cli_path = get_arduino_cli(cfg)
    if cli_path:
        ok(f"Found: {cli_path}")
        out, _ = run(f'"{cli_path}" version')
        if out:
            info(out)
        if interactive and not prompt_yn("Reinstall/update?", default=False):
            cfg.setdefault("arduino_cli", {})["path"] = cli_path
            return True, cli_path
    else:
        fail("arduino-cli not found")
        if not cfg.get("arduino_cli", {}).get("auto_install", True):
            return False, ""
        if interactive and not prompt_yn("Install now?", default=True):
            return False, ""

    section("Installing arduino-cli")
    install_dir = str(HOME / ".local" / "bin")
    os.makedirs(install_dir, exist_ok=True)
    cli_path = os.path.join(install_dir, "arduino-cli")

    url = "https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh"
    spinner = Spinner("Downloading installer")
    spinner.start()
    ok_dl = run(f'curl -fsSL {url} | BINDIR="{install_dir}" sh', timeout=120)
    spinner.stop()

    if not os.path.isfile(cli_path):
        fail("Install failed")
        return False, ""
    os.chmod(cli_path, 0o755)
    ok(f"Installed: {cli_path}")

    shell_name = os.path.basename(os.environ.get("SHELL", "/bin/bash"))
    bashrc = HOME / ".zshrc" if shell_name == "zsh" else HOME / ".bashrc"
    path_entry = 'export PATH=$PATH:$HOME/.local/bin'
    if bashrc.exists():
        content = bashrc.read_text()
        if path_entry not in content:
            with open(bashrc, "a") as f:
                f.write(f"\n{path_entry}\n")
            info(f"Added to {bashrc.name}")

    cfg.setdefault("arduino_cli", {})["path"] = cli_path
    return True, cli_path


def setup_core(cfg, cli_path, platform_key, interactive=True):
    platforms = cfg.get("platforms", {})
    plat = platforms.get(platform_key, {})
    package = plat.get("package", "")
    manager_url = plat.get("manager_url", "")
    if not package:
        fail(f"Unknown platform: {platform_key}")
        return False

    section(f"Checking {platform_key.upper()} core")
    cores = get_installed_cores(cli_path)
    esp_core = next((c for c in cores if c.get("id") == package), None)

    if esp_core:
        ok(f"Installed: v{esp_core.get('installed_version', '?')}")
        if interactive and not prompt_yn("Reinstall/update?", default=False):
            return True
    else:
        fail("Not installed")
        if interactive and not prompt_yn("Install now?", default=True):
            return False

    section(f"Installing {platform_key.upper()} core")
    spinner = Spinner(f"Downloading {platform_key.upper()} core")
    spinner.start()
    ok_msg, err = install_core(cli_path, package, manager_url)
    spinner.stop()
    if not ok_msg:
        fail(f"Failed: {err}")
        return False
    ok(f"{platform_key.upper()} core installed")
    return True


def select_platform_and_board(cfg, cli_path, interactive=True):
    section("Select target platform")

    cores = get_installed_cores(cli_path)
    available = []
    for c in cores:
        cid = c.get("id", "")
        if "esp8266" in cid:
            available.append(("esp8266", "ESP8266", c.get("installed_version", "?")))
        elif "esp32" in cid:
            available.append(("esp32", "ESP32", c.get("installed_version", "?")))

    if not available:
        fail("No ESP8266 or ESP32 cores installed")
        return False

    if interactive:
        for i, (key, name, ver) in enumerate(available):
            print(f"        {C.CYN}{i + 1}{C.RST}. {name} {C.GRY}v{ver}{C.RST}")
        choice = prompt("Platform", "1")
        try:
            idx = int(choice) - 1
            platform_key = available[idx][0]
        except (ValueError, IndexError):
            platform_key = available[0][0]
    else:
        platform_key = available[0][0]

    ok(f"Platform: {platform_key.upper()}")

    section(f"Select {platform_key.upper()} board")
    default_fqbn = cfg.get("platforms", {}).get(platform_key, {}).get("default_fqbn", "")

    boards = [
        ("1", "Generic",    f"{platform_key}:{platform_key}:generic" if platform_key == "esp8266" else f"{platform_key}:{platform_key}:{platform_key}"),
        ("2", "DevKit",     f"{platform_key}:{platform_key}:esp32dev" if platform_key == "esp32" else ""),
        ("3", "Custom",     ""),
    ]
    boards = [(n, nm, fq) for n, nm, fq in boards if fq]

    if interactive:
        for num, name, fqbn in boards:
            print(f"        {C.CYN}{num}{C.RST}. {name}  {C.GRY}{fqbn}{C.RST}")
        choice = prompt("Board", "1")
        fqbn = ""
        for num, name, fq in boards:
            if choice == num:
                fqbn = fq
        if not fqbn:
            fqbn = prompt("Custom FQBN", default_fqbn)
    else:
        fqbn = cfg.get("board", {}).get("fqbn", "") or default_fqbn

    if not fqbn:
        fail("No FQBN selected")
        return False

    cfg.setdefault("board", {})["fqbn"] = fqbn
    ok(f"Board: {fqbn}")
    return True


def setup_paths(cfg, interactive=True):
    section("Configuring paths")

    default_lib = str(HOME / "Arduino" / "libraries")
    lib_dir = cfg.get("libraries", {}).get("dir", "") or default_lib
    if interactive:
        lib_dir = prompt_path("Library directory", lib_dir)
    if not lib_dir:
        lib_dir = default_lib
    cfg.setdefault("libraries", {})["dir"] = lib_dir
    os.makedirs(lib_dir, exist_ok=True)
    ok(f"Libraries: {lib_dir}")

    source_file = cfg.get("source", {}).get("file", "")
    if interactive:
        info("Leave empty to skip (set later via --source)")
        source_file = prompt_source(allow_empty=True)
    if source_file:
        cfg.setdefault("source", {})["file"] = source_file
        ok(f"Source: {source_file}")
    else:
        info("No source file (set later)")

    output_dir = cfg.get("output", {}).get("dir", "build")
    if interactive:
        output_dir = prompt_path("Output directory", output_dir)
    cfg.setdefault("output", {})["dir"] = output_dir
    ok(f"Output: {output_dir}")
    return True


def setup_libraries(cfg, cli_path, interactive=True):
    section("Checking libraries")
    source_file = cfg.get("source", {}).get("file", "")
    lib_dir = cfg.get("libraries", {}).get("dir", str(HOME / "Arduino" / "libraries"))
    extra_libs = cfg.get("libraries", {}).get("extra", [])

    if source_file and os.path.isfile(source_file) and cfg.get("libraries", {}).get("auto_install", True):
        spinner = Spinner("Scanning source")
        spinner.start()
        results = auto_install_libs(cli_path, source_file, lib_dir, extra_libs)
        spinner.stop(f"Found {len(results)} missing library(ies)")
        for lib_name, status in results:
            if "failed" in status:
                fail(f"{lib_name}: {status}")
            else:
                ok(f"{lib_name}: {status}")
        if not results:
            ok("All required libraries already installed")
    else:
        installed = get_installed_libs(cli_path)
        info(f"{len(installed)} library(ies) currently installed")

    if interactive and extra_libs:
        info(f"Extra: {', '.join(extra_libs)}")
        if prompt_yn("Install extra libraries?", default=True):
            for lib in extra_libs:
                spinner = Spinner(f"Installing {lib}")
                spinner.start()
                ok_msg, err = install_lib(cli_path, lib)
                spinner.stop()
                if ok_msg:
                    ok(f"{lib}: installed")
                else:
                    fail(f"{lib}: {err}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ESP8266/ESP32 Compiler Setup")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--board", help="Set board FQBN directly")
    parser.add_argument("--source", help="Set source .ino file path")
    parser.add_argument("--lib-dir", help="Set library directory")
    parser.add_argument("--output-dir", help="Set output directory")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    banner()

    if not check_python():
        sys.exit(1)

    cfg = load_config()
    interactive = not args.non_interactive

    if args.board:
        cfg.setdefault("board", {})["fqbn"] = args.board
    if args.source:
        p = os.path.expanduser(args.source)
        if not os.path.isabs(p):
            p = os.path.join(os.getcwd(), p)
        cfg.setdefault("source", {})["file"] = os.path.normpath(p) if os.path.isfile(p) else args.source
    if args.lib_dir:
        cfg.setdefault("libraries", {})["dir"] = args.lib_dir
    if args.output_dir:
        cfg.setdefault("output", {})["dir"] = args.output_dir

    if not args.skip_install:
        ok_cli, cli_path = setup_arduino_cli(cfg, interactive)
        if not ok_cli:
            fail("arduino-cli setup failed.")
            sys.exit(1)
        save_config(cfg)

        # Install cores based on source file detection or user choice
        source_file = cfg.get("source", {}).get("file", "")
        if source_file and os.path.isfile(source_file):
            from lib.installer import detect_platform
            detected, _ = detect_platform(source_file)
            if detected == "esp32":
                setup_core(cfg, cli_path, "esp32", interactive)
            elif detected == "esp8266":
                setup_core(cfg, cli_path, "esp8266", interactive)
            else:
                # Unknown, install both
                setup_core(cfg, cli_path, "esp8266", interactive)
                setup_core(cfg, cli_path, "esp32", interactive)
        else:
            # No source file, ask or install both
            if interactive:
                section("Select platform to install")
                print(f"        1. ESP8266 only")
                print(f"        2. ESP32 only")
                print(f"        3. Both")
                choice = prompt("Choice", "3")
                if choice == "1":
                    setup_core(cfg, cli_path, "esp8266", interactive)
                elif choice == "2":
                    setup_core(cfg, cli_path, "esp32", interactive)
                else:
                    setup_core(cfg, cli_path, "esp8266", interactive)
                    setup_core(cfg, cli_path, "esp32", interactive)
            else:
                setup_core(cfg, cli_path, "esp8266", interactive)
                setup_core(cfg, cli_path, "esp32", interactive)

        select_platform_and_board(cfg, cli_path, interactive)
        save_config(cfg)
    else:
        cli_path = get_arduino_cli(cfg)
        if not cli_path:
            fail("arduino-cli not found. Run without --skip-install.")
            sys.exit(1)

    setup_paths(cfg, interactive)
    save_config(cfg)

    setup_libraries(cfg, cli_path, interactive)
    save_config(cfg)

    divider()
    print(f"  {C.GRN}{C.BOLD}  SETUP COMPLETE{C.RST}")
    divider()
    print(f"  Config : {CONFIG_PATH}")
    print(f"  Board  : {cfg.get('board', {}).get('fqbn', 'not set')}")
    print(f"  Source : {cfg.get('source', {}).get('file', 'not set')}")
    print(f"  Output : {cfg.get('output', {}).get('dir', 'build')}")
    print(f"\n  {C.GRY}Next: python3 compiler.py --source <file.ino>{C.RST}")
    divider()
    print()


if __name__ == "__main__":
    main()
