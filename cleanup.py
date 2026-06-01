#!/usr/bin/env python3
"""
ESP8266 Firmware Compiler - Cleanup
Remove arduino-cli, libraries, build artifacts, config.
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.installer import run, get_arduino_cli

CONFIG_PATH = Path(__file__).parent / "config.json"
HOME = Path.home()


class C:
    """ANSI color codes."""
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[1;31m"
    GRN = "\033[1;32m"
    YLW = "\033[1;33m"
    BLU = "\033[1;34m"
    CYN = "\033[1;36m"
    WHT = "\033[1;37m"
    GRY = "\033[90m"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def banner():
    w = 60
    print()
    print(f"  {C.CYN}{'=' * w}{C.RST}")
    print(f"  {C.CYN}{C.BOLD}  ESP8266 FIRMWARE COMPILER - CLEANUP{C.RST}")
    print(f"  {C.CYN}{'=' * w}{C.RST}")
    print()


def section(title):
    print(f"\n  {C.YLW}[>]{C.RST} {C.BOLD}{title}{C.RST}")


def ok(msg):
    print(f"      {C.GRN}[+]{C.RST} {msg}")


def fail(msg):
    print(f"      {C.RED}[-]{C.RST} {msg}")


def info(msg):
    print(f"      {C.GRY}[~]{C.RST} {msg}")


def prompt_yn(msg, default=True):
    suffix = f"{C.GRN}Y{C.RST}/{C.RED}n{C.RST}" if default else f"{C.GRN}y{C.RST}/{C.RED}N{C.RST}"
    val = input(f"      {C.CYN}[?]{C.RST} {msg} [{suffix}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def divider(char="─", width=60):
    print(f"  {C.GRY}{char * width}{C.RST}")


def safe_remove(path, label=""):
    """Remove file or directory safely."""
    target = label or path
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            ok(f"Removed: {target}")
            return True
        elif os.path.isdir(path):
            shutil.rmtree(path)
            ok(f"Removed: {target}/")
            return True
    except Exception as e:
        fail(f"Failed to remove {target}: {e}")
        return False
    info(f"Not found: {target}")
    return False


def cleanup_all(cfg, interactive=True):
    """Full cleanup: binary, config, libraries, build artifacts, bashrc."""

    section("Removing arduino-cli binary")
    cli_path = get_arduino_cli(cfg)
    if cli_path:
        safe_remove(cli_path, "arduino-cli binary")
    else:
        info("arduino-cli binary not found")

    section("Removing Arduino config and data")
    arduino_dirs = [
        HOME / ".arduino15",
        HOME / ".data" / "data" / "com.termux" / "files" / "home" / ".arduino15",
        HOME / "Arduino",
    ]
    for d in arduino_dirs:
        if d.exists():
            safe_remove(str(d))

    section("Removing build output")
    output_dir = cfg.get("output", {}).get("dir", "build")
    if output_dir:
        output_path = Path(output_dir)
        if not output_path.is_absolute():
            output_path = Path(__file__).parent / output_path
        safe_remove(str(output_path))

    section("Removing library directory (optional)")
    lib_dir = cfg.get("libraries", {}).get("dir", "")
    if lib_dir and os.path.isdir(lib_dir):
        if interactive:
            if prompt_yn(f"Remove library directory {lib_dir}?", default=False):
                safe_remove(lib_dir)
            else:
                info("Skipped")
        else:
            safe_remove(lib_dir)

    section("Cleaning .bashrc")
    bashrc = HOME / ".bashrc"
    if bashrc.exists():
        content = bashrc.read_text()
        lines = content.splitlines()
        cleaned = [l for l in lines if "export PATH=$PATH:$HOME/.local/bin" not in l]
        if len(cleaned) < len(lines):
            bashrc.write_text("\n".join(cleaned) + "\n")
            ok("Cleaned PATH entry from ~/.bashrc")
        else:
            info("No PATH entry to clean")

    section("Removing config file")
    if interactive:
        if prompt_yn("Remove config.json?", default=False):
            safe_remove(str(CONFIG_PATH))
    else:
        safe_remove(str(CONFIG_PATH))

    section("Removing old compiler artifacts")
    old_files = ["compile.sh", "uninstall.sh"]
    for s in old_files:
        p = Path(__file__).parent / s
        if p.exists():
            safe_remove(str(p))


def cleanup_build_only(cfg):
    """Remove only build artifacts."""
    section("Removing build output")
    output_dir = cfg.get("output", {}).get("dir", "build")
    if output_dir:
        output_path = Path(output_dir)
        if not output_path.is_absolute():
            output_path = Path(__file__).parent / output_path
        safe_remove(str(output_path))


def cleanup_libs_only(cfg, cli_path):
    """Remove installed libraries."""
    section("Removing libraries")
    lib_dir = cfg.get("libraries", {}).get("dir", str(HOME / "Arduino" / "libraries"))
    safe_remove(lib_dir)


def main():
    parser = argparse.ArgumentParser(description="ESP8266 Compiler Cleanup")
    parser.add_argument("--all", "-a", action="store_true", help="Remove everything")
    parser.add_argument("--build-only", action="store_true", help="Remove only build output")
    parser.add_argument("--libs-only", action="store_true", help="Remove only libraries")
    parser.add_argument("--non-interactive", action="store_true", help="No prompts")
    args = parser.parse_args()

    banner()

    cfg = load_config()
    interactive = not args.non_interactive

    if args.all:
        cleanup_all(cfg, interactive)
    elif args.build_only:
        cleanup_build_only(cfg)
    elif args.libs_only:
        cli_path = get_arduino_cli(cfg)
        if cli_path:
            cleanup_libs_only(cfg, cli_path)
        else:
            fail("arduino-cli not found")
    else:
        if interactive:
            print()
            info("Select cleanup scope:")
            print(f"        {C.CYN}1{C.RST}. Build output only")
            print(f"        {C.CYN}2{C.RST}. Libraries only")
            print(f"        {C.CYN}3{C.RST}. Everything (binary + config + libs + build)")
            choice = input(f"      {C.CYN}[?]{C.RST} Choice [3]: ").strip() or "3"
            if choice == "1":
                cleanup_build_only(cfg)
            elif choice == "2":
                cli_path = get_arduino_cli(cfg)
                if cli_path:
                    cleanup_libs_only(cfg, cli_path)
            else:
                cleanup_all(cfg, interactive)
        else:
            cleanup_all(cfg, interactive)

    divider()
    print(f"  {C.GRN}{C.BOLD}  CLEANUP COMPLETE{C.RST}")
    divider()
    print()


if __name__ == "__main__":
    main()
