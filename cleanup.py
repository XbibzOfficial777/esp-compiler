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
from lib.installer import run, get_arduino_cli, get_default_output_dir

CONFIG_PATH = Path(__file__).parent / "config.json"
HOME = Path.home()

# SAFETY: Paths that must NEVER be deleted, even if they match a lib/output dir
# IMPORTANT: /sdcard and its subdirectories are HIGH RISK on Android/Termux
PROTECTED_PATHS = {
    "/sdcard", "/sdcard/", "/storage", "/storage/",
    "/mnt", "/mnt/", "/home", "/home/",
    "/", "/root", "/tmp",
    os.path.expanduser("~"), os.path.expanduser("~") + "/",
}

# SAFETY: Path prefixes that are protected — any path starting with these is blocked
# This prevents deleting /sdcard/anything, /storage/anything, etc.
PROTECTED_PREFIXES = {
    "/sdcard/", "/storage/emulated/",
}


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


# FIX #9: Add JSONDecodeError handling to load_config()
def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
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


def warn(msg):
    print(f"      {C.YLW}[!]{C.RST} {msg}")


def prompt_yn(msg, default=True):
    suffix = f"{C.GRN}Y{C.RST}/{C.RED}n{C.RST}" if default else f"{C.GRN}y{C.RST}/{C.RED}N{C.RST}"
    val = input(f"      {C.CYN}[?]{C.RST} {msg} [{suffix}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def divider(char="─", width=60):
    print(f"  {C.GRY}{char * width}{C.RST}")


def is_protected_path(path):
    """Check if a path is protected and should never be deleted.
    HIGH RISK: /sdcard and /storage paths are ALWAYS blocked to prevent
    accidental data loss on Android/Termux systems."""
    abs_path = os.path.abspath(os.path.normpath(path))

    # CRITICAL: Block any path under /sdcard or /storage/emulated (Android/Termux)
    # These contain user data, photos, downloads — NEVER delete them
    for prefix in PROTECTED_PREFIXES:
        prefix_norm = os.path.abspath(os.path.normpath(prefix))
        if abs_path.startswith(prefix_norm):
            return True

    # Block exact matches for other protected paths
    for protected in PROTECTED_PATHS:
        prot_norm = os.path.abspath(os.path.normpath(protected))
        if abs_path == prot_norm:
            return True
        # Block shallow subdirectories (1 level) of home/root/etc
        if abs_path.startswith(prot_norm + os.sep):
            depth_diff = abs_path[len(prot_norm):].count(os.sep)
            if depth_diff <= 1:
                return True
    return False


def safe_remove(path, label=""):
    """Remove file or directory safely.
    FIX #12: Check for symlinks BEFORE isdir() to prevent data loss via symlink targets.
    SAFETY: Never delete protected paths like /sdcard, /home, /, etc."""
    target = label or path

    # SAFETY: Check protected paths
    if is_protected_path(path):
        fail(f"BLOCKED: Refusing to delete protected path: {target}")
        warn("This path is protected to prevent accidental data loss")
        return False

    try:
        # FIX #12: Check for symlinks FIRST — remove symlink, not its target
        if os.path.islink(path):
            os.remove(path)  # Remove the symlink itself, not the target directory
            ok(f"Removed: {target} (symlink)")
            return True
        elif os.path.isfile(path):
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
        d_str = str(d)
        # SAFETY: Check if path resolves to /sdcard (symlink to sdcard)
        if os.path.islink(d_str):
            real_target = os.path.realpath(d_str)
            if is_protected_path(real_target):
                warn(f"Skipping {d}: symlink points to protected path {real_target}")
                continue
        if d.exists():
            safe_remove(d_str)

    section("Removing build output")
    output_dir = get_default_output_dir()
    safe_remove(output_dir)

    section("Removing library directory (optional)")
    lib_dir = cfg.get("libraries", {}).get("dir", "")
    if lib_dir and os.path.isdir(lib_dir):
        if interactive:
            if prompt_yn(f"Remove library directory {lib_dir}?", default=False):
                safe_remove(lib_dir)
            else:
                info("Skipped")
        else:
            # SAFETY: In non-interactive mode, still prompt for library dir deletion
            # to prevent accidental data loss
            warn(f"Would remove library directory: {lib_dir}")
            info("Skipping library directory in non-interactive mode for safety")
            info("Use --libs-only with explicit confirmation to remove libraries")

    section("Cleaning shell config")
    marker = "# ESP-Compiler (XbibzOfficial)"
    cleaned_any = False
    for rc_name in [".bashrc", ".zshrc", ".profile"]:
        rc = HOME / rc_name
        if rc.exists() and marker in rc.read_text():
            lines = rc.read_text().splitlines()
            new_lines = []
            skip = False
            for line in lines:
                if marker in line:
                    skip = True
                    continue
                if skip and "# End ESP-Compiler" in line:
                    skip = False
                    continue
                if not skip:
                    new_lines.append(line)
            rc.write_text("\n".join(new_lines) + "\n")
            ok(f"Cleaned: ~/{rc_name}")
            cleaned_any = True
    if not cleaned_any:
        info("No shell config entries found")

    # Remove cesp binary
    safe_remove(str(HOME / ".local" / "bin" / "cesp"), "cesp binary")

    section("Removing config file")
    if interactive:
        if prompt_yn("Remove config.json?", default=False):
            safe_remove(str(CONFIG_PATH))
    else:
        safe_remove(str(CONFIG_PATH))

    section("Removing old compiler artifacts")
    old_files = ["compile.sh"]
    for s in old_files:
        p = Path(__file__).parent / s
        if p.exists():
            safe_remove(str(p))


def cleanup_build_only(cfg):
    """Remove only build artifacts."""
    section("Removing build output")
    output_dir = get_default_output_dir()
    safe_remove(output_dir)


def cleanup_libs_only(cfg, cli_path):
    """Remove installed libraries.
    FIX #20: Use arduino-cli lib uninstall for each auto-installed library
    instead of deleting the entire library directory."""
    section("Removing auto-installed libraries")
    lib_dir = cfg.get("libraries", {}).get("dir", str(HOME / "Arduino" / "libraries"))

    # Check if we have a record of auto-installed libraries
    auto_installed = cfg.get("libraries", {}).get("auto_installed", [])

    if auto_installed:
        info(f"Found {len(auto_installed)} auto-installed library record(s)")
        for lib_name in auto_installed:
            out, err = run(f'"arduino-cli" lib uninstall "{lib_name}"', timeout=60)
            if err:
                warn(f"{lib_name}: {err}")
            else:
                ok(f"Uninstalled: {lib_name}")
    else:
        warn("No auto-install records found in config.json")
        warn("Cannot safely determine which libraries were installed by esp-compiler")
        info("To remove ALL libraries manually, delete the library directory:")
        info(f"  rm -rf \"{lib_dir}\"")


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
