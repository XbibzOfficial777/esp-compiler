#!/usr/bin/env python3
"""
ESP8266/ESP32 Firmware Compiler
"""

import os
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.installer import (
    run, get_arduino_cli, get_installed_cores,
    auto_install_libs, scan_includes, check_compatibility, detect_platform
)
from lib.patcher import apply_patches, build_patches_from_config
from lib.progress import (
    Spinner, ProgressBar, CompileProgress, run_compile_with_progress
)

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
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def banner():
    print()
    print(f"  {C.CYN}{'=' * 60}{C.RST}")
    print(f"  {C.CYN}{C.BOLD}  ESP8266 / ESP32  FIRMWARE COMPILER{C.RST}")
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


def warn(msg):
    print(f"      {C.YLW}[!]{C.RST} {msg}")


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


def resolve_path(p):
    if not p:
        return p
    p = os.path.expanduser(p)
    if os.path.isabs(p) and os.path.isfile(p):
        return os.path.normpath(p)
    cwd = os.path.join(os.getcwd(), p)
    if os.path.isfile(cwd):
        return os.path.normpath(cwd)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), p)
    if os.path.isfile(script):
        return os.path.normpath(script)
    return os.path.normpath(p)


def prompt_source(allow_empty=False):
    """Prompt user for source file path with retry loop."""
    while True:
        val = prompt("Source .ino file path")
        if not val and allow_empty:
            return None
        if not val:
            continue
        resolved = resolve_path(val)
        if os.path.isfile(resolved):
            return resolved
        fail(f"File not found: {val}")
        info(f"Tried: {resolved}")
        if not prompt_yn("Try different path?", default=True):
            return None


def prompt_board():
    """Prompt user for board FQBN with quick select."""
    section("Select board platform")

    choices = [
        ("1", "ESP8266 Generic",   "esp8266:esp8266:generic"),
        ("2", "ESP32 Generic",     "esp32:esp32:esp32"),
        ("3", "ESP32-S2",          "esp32:esp32:esp32s2"),
        ("4", "ESP32-S3",          "esp32:esp32:esp32s3"),
        ("5", "ESP32-C3",          "esp32:esp32:esp32c3"),
    ]

    info("Quick select:")
    for num, name, fqbn in choices:
        print(f"        {C.CYN}{num}{C.RST}. {name}  {C.GRY}{fqbn}{C.RST}")

    while True:
        choice = prompt("Board", "1")
        for num, name, fqbn in choices:
            if choice == num:
                return fqbn
        if ":" in choice:
            return choice
        fail("Invalid choice, try again")


def run_patching(source_file, cfg, dry_run=False):
    section("Patching source code")
    if not cfg.get("patches", {}).get("auto_fix", True):
        info("Auto-fix disabled in config")
        return True
    patches = build_patches_from_config(cfg)
    results = apply_patches(source_file, patches, dry_run=dry_run)
    all_ok = True
    for pid, applied, detail in results:
        if applied:
            ok(f"{pid}: {detail}")
        else:
            info(f"{pid}: {detail}")
            if "failed" in detail.lower():
                all_ok = False
    if dry_run:
        info("Dry run - no changes made")
    return all_ok


def run_library_check(cli_path, source_file, cfg):
    section("Checking libraries")
    lib_dir = cfg.get("libraries", {}).get("dir", str(HOME / "Arduino" / "libraries"))
    extra_libs = cfg.get("libraries", {}).get("extra", [])
    if not cfg.get("libraries", {}).get("auto_install", True):
        info("Auto-install disabled")
        return True

    spinner = Spinner("Scanning includes")
    spinner.start()
    includes = scan_includes(source_file)
    spinner.stop(f"Found {len(includes)} #include(s)")

    results = auto_install_libs(cli_path, source_file, lib_dir, extra_libs)
    if not results:
        ok("All libraries satisfied")
        return True

    all_ok = True
    for lib_name, status in results:
        if "failed" in status:
            fail(f"{lib_name}: {status}")
            all_ok = False
        else:
            ok(f"{lib_name}: {status}")
    return all_ok


def run_compile(cli_path, source_file, cfg):
    section("Compiling")
    fqbn = cfg.get("board", {}).get("fqbn", "")
    if not fqbn:
        fail("No board FQBN configured. Run setup.py first.")
        return False

    lib_dir = cfg.get("libraries", {}).get("dir", str(HOME / "Arduino" / "libraries"))
    output_dir = cfg.get("output", {}).get("dir", "build")
    output_dir = resolve_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    cmd = (
        f'"{cli_path}" compile '
        f'--fqbn {fqbn} '
        f'--libraries "{lib_dir}" '
        f'--output-dir "{output_dir}" '
        f'--verbose '
        f'"{source_file}"'
    )

    info(f"FQBN    : {fqbn}")
    info(f"Source  : {source_file}")
    info(f"Output  : {output_dir}")
    print()

    success, _, stderr, elapsed = run_compile_with_progress(cmd)

    if not success and stderr:
        print()
        for line in stderr.split("\n"):
            if line.strip():
                print(f"        {C.RED}{line}{C.RST}")

    if success:
        src = os.path.basename(source_file)
        bin_name = src.replace(".ino", ".ino.bin")
        bin_path = os.path.join(output_dir, bin_name)
        if os.path.isfile(bin_path):
            sz = os.path.getsize(bin_path)
            ok(f"Binary: {bin_path} ({sz:,} bytes)")

    return success


def main():
    parser = argparse.ArgumentParser(description="ESP8266/ESP32 Firmware Compiler")
    parser.add_argument("--source", "-s", help="Source .ino file")
    parser.add_argument("--board", "-b", help="Board FQBN")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--lib-dir", help="Library directory")
    parser.add_argument("--dry-run", action="store_true", help="Patch only")
    parser.add_argument("--no-patch", action="store_true", help="Skip patching")
    parser.add_argument("--no-libs", action="store_true", help="Skip library check")
    parser.add_argument("--non-interactive", action="store_true", help="No prompts")
    parser.add_argument("--all", "-a", action="store_true", help="All steps (default)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    banner()
    cfg = load_config()
    interactive = not args.non_interactive

    # Apply CLI overrides
    if args.board:
        cfg.setdefault("board", {})["fqbn"] = args.board
    if args.output:
        cfg.setdefault("output", {})["dir"] = args.output
    if args.lib_dir:
        cfg.setdefault("libraries", {})["dir"] = args.lib_dir

    # Check arduino-cli
    cli_path = get_arduino_cli(cfg)
    if not cli_path:
        fail("arduino-cli not found. Run setup.py first.")
        sys.exit(1)

    # --- Source file ---
    source_file = args.source or cfg.get("source", {}).get("file", "")
    if interactive and not source_file:
        source_file = prompt_source(allow_empty=False)
        if not source_file:
            fail("No source file. Exiting.")
            sys.exit(1)
    elif source_file:
        source_file = resolve_path(source_file)
        if not os.path.isfile(source_file):
            fail(f"File not found: {source_file}")
            if interactive:
                source_file = prompt_source(allow_empty=False)
                if not source_file:
                    sys.exit(1)
            else:
                sys.exit(1)

    ok(f"Source: {source_file}")

    # --- Platform detection ---
    detected, confidence = detect_platform(source_file)
    if detected != "unknown":
        info(f"Detected: {C.BOLD}{detected.upper()}{C.RST} ({confidence}%)")

    # --- Board selection ---
    fqbn = cfg.get("board", {}).get("fqbn", "")
    if not fqbn and interactive:
        fqbn = prompt_board()
        cfg.setdefault("board", {})["fqbn"] = fqbn
    if not fqbn:
        fail("No board FQBN. Use --board or run setup.py.")
        sys.exit(1)
    ok(f"Board: {fqbn}")

    # --- Compatibility ---
    if detected != "unknown":
        compatible, msg = check_compatibility(source_file, fqbn)
        if compatible:
            ok(f"Compat: {msg}")
        else:
            fail(f"Compat: {msg}")
            if interactive:
                if not prompt_yn("Continue anyway?", default=False):
                    sys.exit(1)
            else:
                sys.exit(1)

    # --- Steps: default is --all ---
    do_patch = not args.no_patch and not args.dry_run
    do_libs = not args.no_libs
    do_compile = not args.dry_run

    if not (args.no_patch or args.no_libs or args.dry_run):
        do_patch = do_libs = do_compile = True

    if args.all:
        do_patch = do_libs = do_compile = True

    # Interactive step selection only if user explicitly excluded something
    if interactive and not (args.all or args.dry_run or args.no_patch or args.no_libs):
        section("Select steps")
        print(f"        {C.CYN}1{C.RST}. Patch source code")
        print(f"        {C.CYN}2{C.RST}. Check/install libraries")
        print(f"        {C.CYN}3{C.RST}. Compile")
        print(f"        {C.CYN}4{C.RST}. All (patch + libs + compile)")
        choice = prompt("Choice", "4")
        if choice == "1":
            do_patch, do_libs, do_compile = True, False, False
        elif choice == "2":
            do_patch, do_libs, do_compile = False, True, False
        elif choice == "3":
            do_patch, do_libs, do_compile = False, False, True
        else:
            do_patch = do_libs = do_compile = True

    # --- Execute ---
    results = {}
    if do_patch:
        results["patch"] = run_patching(source_file, cfg, dry_run=args.dry_run)
    if do_libs:
        results["libs"] = run_library_check(cli_path, source_file, cfg)
    if do_compile:
        results["compile"] = run_compile(cli_path, source_file, cfg)

    save_config(cfg)

    # --- Summary ---
    divider()
    if all(results.values()):
        print(f"  {C.GRN}{C.BOLD}  BUILD SUCCESSFUL{C.RST}")
    else:
        print(f"  {C.RED}{C.BOLD}  BUILD FAILED{C.RST}")
        for name, ok_flag in results.items():
            sym = f"{C.GRN}[+]{C.RST}" if ok_flag else f"{C.RED}[-]{C.RST}"
            print(f"      {sym} {name}")
    divider()
    print()


if __name__ == "__main__":
    main()
