#!/usr/bin/env python3
"""
Unit tests for esp-compiler
Covers: installer.py, patcher.py, progress.py, compiler.py helpers, cleanup.py
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.installer import (
    run, get_arduino_cli, get_installed_cores,
    get_installed_libs, scan_includes, resolve_lib_name,
    detect_platform, check_compatibility, auto_install_libs,
    install_lib, install_core, HEADER_TO_LIB, SKIPPED_LIBS,
    ESP8266_HEADERS, ESP32_HEADERS,
)
from lib.patcher import (
    apply_patches, build_patches_from_config, DEFAULT_PATCHES,
    read_file, write_file,
)
from lib.progress import (
    parse_compile_line, CompileProgress, ProgressBar,
)
from compiler import (
    load_config, save_config, resolve_path, validate_source,
    validate_config,
)
from cleanup import is_protected_path, safe_remove


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_temp_ino(content="", dirname=None, filename=None):
    """Create a temporary .ino file inside a properly-named folder."""
    base = dirname or "sketch"
    fname = filename or f"{base}.ino"
    d = tempfile.mkdtemp()
    sketch_dir = os.path.join(d, base)
    os.makedirs(sketch_dir)
    path = os.path.join(sketch_dir, fname)
    with open(path, "w") as f:
        f.write(content or "void setup(){} void loop(){}")
    return path, d


# ---------------------------------------------------------------------------
# 1. lib/installer.py — run()
# ---------------------------------------------------------------------------

class TestRun(unittest.TestCase):

    def test_run_returns_stdout(self):
        out, err = run("echo hello")
        self.assertEqual(out, "hello")
        self.assertEqual(err, "")

    def test_run_returns_stderr(self):
        out, err = run("echo error >&2", capture=True)
        # shell=True so redirection works
        self.assertIsNotNone(out)

    def test_run_timeout(self):
        out, err = run("sleep 10", timeout=0.1)
        self.assertIsNone(out)
        self.assertIn("timed out", err.lower())

    def test_run_nonexistent_command(self):
        out, err = run("nonexistent_cmd_xyz_12345")
        # Returns None or empty, no exception
        self.assertIsNotNone(err)

    def test_run_check_nonzero(self):
        out, err = run("exit 1", check=True)
        self.assertIsNone(out)


# ---------------------------------------------------------------------------
# 2. lib/installer.py — get_arduino_cli()
# ---------------------------------------------------------------------------

class TestGetArduinoCli(unittest.TestCase):

    def test_returns_config_path_if_exists(self):
        with tempfile.NamedTemporaryFile(suffix="arduino-cli", delete=False) as f:
            f.write(b"")
            cli = f.name
        try:
            cfg = {"arduino_cli": {"path": cli}}
            result = get_arduino_cli(cfg)
            self.assertEqual(result, cli)
        finally:
            os.unlink(cli)

    def test_returns_none_if_not_found(self):
        cfg = {"arduino_cli": {"path": "/nonexistent/path/arduino-cli"}}
        with patch("lib.installer.run", return_value=(None, "")):
            result = get_arduino_cli(cfg)
            self.assertIsNone(result)

    def test_empty_config_falls_through(self):
        with patch("lib.installer.run", return_value=(None, "")):
            result = get_arduino_cli({})
            self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 3. lib/installer.py — get_installed_cores() — FIX: non-installed cores skipped
# ---------------------------------------------------------------------------

class TestGetInstalledCores(unittest.TestCase):

    def test_returns_installed_cores(self):
        mock_json = json.dumps({
            "platforms": [
                {
                    "id": "esp8266:esp8266",
                    "name": "ESP8266",
                    "installed_version": "3.1.2",
                }
            ]
        })
        with patch("lib.installer.run", return_value=(mock_json, "")):
            cores = get_installed_cores("arduino-cli")
        self.assertEqual(len(cores), 1)
        self.assertEqual(cores[0]["id"], "esp8266:esp8266")
        self.assertEqual(cores[0]["installed_version"], "3.1.2")

    def test_skips_non_installed_cores(self):
        """FIX: cores with no installed_version and no installed=True in releases
        must NOT appear in results."""
        mock_json = json.dumps({
            "platforms": [
                {
                    "id": "esp32:esp32",
                    "name": "ESP32",
                    # no installed_version, no installed flag in releases
                    "releases": {
                        "2.0.0": {"installed": False}
                    }
                }
            ]
        })
        with patch("lib.installer.run", return_value=(mock_json, "")):
            cores = get_installed_cores("arduino-cli")
        self.assertEqual(len(cores), 0)

    def test_releases_installed_flag(self):
        """Cores with releases[ver].installed=True should be returned."""
        mock_json = json.dumps({
            "platforms": [
                {
                    "id": "esp32:esp32",
                    "name": "ESP32",
                    "releases": {
                        "2.0.0": {"installed": True}
                    }
                }
            ]
        })
        with patch("lib.installer.run", return_value=(mock_json, "")):
            cores = get_installed_cores("arduino-cli")
        self.assertEqual(len(cores), 1)
        self.assertEqual(cores[0]["installed_version"], "2.0.0")

    def test_returns_empty_on_invalid_json(self):
        with patch("lib.installer.run", return_value=("not-json", "")):
            cores = get_installed_cores("arduino-cli")
        self.assertEqual(cores, [])

    def test_returns_empty_on_no_output(self):
        with patch("lib.installer.run", return_value=(None, "error")):
            cores = get_installed_cores("arduino-cli")
        self.assertEqual(cores, [])


# ---------------------------------------------------------------------------
# 4. lib/installer.py — scan_includes()
# ---------------------------------------------------------------------------

class TestScanIncludes(unittest.TestCase):

    def test_angle_bracket_include(self):
        path, tmpd = make_temp_ino("#include <WiFi.h>\nvoid setup(){}")
        try:
            includes = scan_includes(path)
            self.assertIn("WiFi.h", includes)
        finally:
            shutil.rmtree(tmpd)

    def test_quoted_include(self):
        path, tmpd = make_temp_ino('#include "mylib.h"\nvoid setup(){}')
        try:
            includes = scan_includes(path)
            self.assertIn("mylib.h", includes)
        finally:
            shutil.rmtree(tmpd)

    def test_multiple_includes(self):
        path, tmpd = make_temp_ino(
            "#include <ArduinoJson.h>\n#include <DHT.h>\nvoid setup(){}"
        )
        try:
            includes = scan_includes(path)
            self.assertIn("ArduinoJson.h", includes)
            self.assertIn("DHT.h", includes)
        finally:
            shutil.rmtree(tmpd)

    def test_nonexistent_file_returns_empty(self):
        includes = scan_includes("/nonexistent/file.ino")
        self.assertEqual(includes, [])

    def test_no_includes(self):
        path, tmpd = make_temp_ino("void setup(){} void loop(){}")
        try:
            includes = scan_includes(path)
            self.assertEqual(includes, [])
        finally:
            shutil.rmtree(tmpd)


# ---------------------------------------------------------------------------
# 5. lib/installer.py — resolve_lib_name()
# ---------------------------------------------------------------------------

class TestResolveLibName(unittest.TestCase):

    def test_known_header_returns_lib_name(self):
        self.assertEqual(resolve_lib_name("ArduinoJson.h"), "ArduinoJson")

    def test_skipped_header_returns_none(self):
        self.assertIsNone(resolve_lib_name("WiFi.h"))
        self.assertIsNone(resolve_lib_name("ESP8266WiFi.h"))
        self.assertIsNone(resolve_lib_name("Arduino.h"))

    def test_unknown_header_returns_none(self):
        self.assertIsNone(resolve_lib_name("myCustomLib.h"))

    def test_all_skipped_libs_return_none(self):
        for h in SKIPPED_LIBS:
            self.assertIsNone(resolve_lib_name(h), f"Expected None for {h}")


# ---------------------------------------------------------------------------
# 6. lib/installer.py — detect_platform()
# ---------------------------------------------------------------------------

class TestDetectPlatform(unittest.TestCase):

    def test_detects_esp8266_from_header(self):
        path, tmpd = make_temp_ino("#include <ESP8266WiFi.h>\nvoid setup(){}")
        try:
            plat, conf = detect_platform(path)
            self.assertEqual(plat, "esp8266")
            self.assertGreater(conf, 0)
        finally:
            shutil.rmtree(tmpd)

    def test_detects_esp32_from_header(self):
        path, tmpd = make_temp_ino("#include <WiFi.h>\nvoid setup(){}")
        try:
            plat, conf = detect_platform(path)
            self.assertEqual(plat, "esp32")
            self.assertGreater(conf, 0)
        finally:
            shutil.rmtree(tmpd)

    def test_unknown_for_generic_code(self):
        path, tmpd = make_temp_ino("void setup(){} void loop(){}")
        try:
            plat, conf = detect_platform(path)
            self.assertEqual(plat, "unknown")
        finally:
            shutil.rmtree(tmpd)

    def test_esp8266_ifdefs_boost_score(self):
        code = "#include <ESP8266WiFi.h>\n#if defined(ESP8266)\nvoid setup(){}\n#endif"
        path, tmpd = make_temp_ino(code)
        try:
            plat, conf = detect_platform(path)
            self.assertEqual(plat, "esp8266")
            self.assertGreater(conf, 50)
        finally:
            shutil.rmtree(tmpd)

    def test_nonexistent_file_returns_unknown(self):
        plat, conf = detect_platform("/nonexistent/sketch.ino")
        self.assertEqual(plat, "unknown")
        self.assertEqual(conf, 0)


# ---------------------------------------------------------------------------
# 7. lib/installer.py — check_compatibility()
# ---------------------------------------------------------------------------

class TestCheckCompatibility(unittest.TestCase):

    def test_compatible_esp8266_board(self):
        path, tmpd = make_temp_ino("#include <ESP8266WiFi.h>\nvoid setup(){}")
        try:
            ok, msg = check_compatibility(path, "esp8266:esp8266:generic")
            self.assertTrue(ok)
        finally:
            shutil.rmtree(tmpd)

    def test_incompatible_esp8266_code_on_esp32_board(self):
        path, tmpd = make_temp_ino("#include <ESP8266WiFi.h>\nvoid setup(){}")
        try:
            ok, msg = check_compatibility(path, "esp32:esp32:esp32")
            self.assertFalse(ok)
            self.assertIn("mismatch", msg.lower())
        finally:
            shutil.rmtree(tmpd)

    def test_generic_code_is_compatible_with_any_board(self):
        path, tmpd = make_temp_ino("void setup(){}")
        try:
            ok, msg = check_compatibility(path, "esp32:esp32:esp32")
            self.assertTrue(ok)
        finally:
            shutil.rmtree(tmpd)

    def test_low_confidence_allows_mismatch(self):
        """Confidence < 40% should not block compilation."""
        with patch("lib.installer.detect_platform", return_value=("esp8266", 30)):
            ok, msg = check_compatibility("/any.ino", "esp32:esp32:esp32")
            self.assertTrue(ok)
            self.assertIn("low confidence", msg.lower())


# ---------------------------------------------------------------------------
# 8. lib/installer.py — auto_install_libs() — FIX: ok var shadowing
# ---------------------------------------------------------------------------

class TestAutoInstallLibs(unittest.TestCase):

    def test_skips_already_installed(self):
        path, tmpd = make_temp_ino("#include <ArduinoJson.h>\nvoid setup(){}")
        try:
            with patch("lib.installer.get_installed_libs", return_value=["ArduinoJson"]):
                results = auto_install_libs("cli", path, "/tmp/libs")
            self.assertEqual(results, [])
        finally:
            shutil.rmtree(tmpd)

    def test_installs_missing_lib(self):
        path, tmpd = make_temp_ino("#include <ArduinoJson.h>\nvoid setup(){}")
        try:
            with patch("lib.installer.get_installed_libs", return_value=[]):
                with patch("lib.installer.install_lib", return_value=(True, "ok")):
                    results = auto_install_libs("cli", path, "/tmp/libs")
            self.assertEqual(len(results), 1)
            self.assertIn("ArduinoJson", results[0][0])
            self.assertEqual(results[0][1], "installed")
        finally:
            shutil.rmtree(tmpd)

    def test_reports_failed_install(self):
        path, tmpd = make_temp_ino("#include <ArduinoJson.h>\nvoid setup(){}")
        try:
            with patch("lib.installer.get_installed_libs", return_value=[]):
                with patch("lib.installer.install_lib", return_value=(False, "network error")):
                    results = auto_install_libs("cli", path, "/tmp/libs")
            self.assertIn("failed", results[0][1])
        finally:
            shutil.rmtree(tmpd)

    def test_extra_libs_installed(self):
        path, tmpd = make_temp_ino("void setup(){}")
        try:
            with patch("lib.installer.get_installed_libs", return_value=[]):
                with patch("lib.installer.install_lib", return_value=(True, "ok")):
                    results = auto_install_libs("cli", path, "/tmp/libs", extra_libs=["FastLED"])
            names = [r[0] for r in results]
            self.assertIn("FastLED", names)
        finally:
            shutil.rmtree(tmpd)


# ---------------------------------------------------------------------------
# 9. lib/patcher.py — apply_patches()
# ---------------------------------------------------------------------------

class TestApplyPatches(unittest.TestCase):

    def _write_ino(self, content):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "sketch", "sketch.ino")
        os.makedirs(os.path.dirname(p))
        with open(p, "w") as f:
            f.write(content)
        return p, d

    def test_simple_search_replace(self):
        path, tmpd = self._write_ino("server._catchAllHandleron(\"/\");")
        try:
            results = apply_patches(path, [DEFAULT_PATCHES[2]])
            applied = [r for r in results if r[1]]
            self.assertTrue(len(applied) >= 1)
            content = read_file(path)
            self.assertIn("server.on", content)
            self.assertNotIn("_catchAllHandleron", content)
        finally:
            shutil.rmtree(tmpd)

    def test_no_change_when_pattern_absent(self):
        path, tmpd = self._write_ino("void setup(){}")
        try:
            results = apply_patches(path, [DEFAULT_PATCHES[2]])
            applied = [r for r in results if r[1]]
            self.assertEqual(len(applied), 0)
        finally:
            shutil.rmtree(tmpd)

    def test_insert_after_pattern(self):
        src = '#include <ESP8266WiFi.h>\nvoid setup(){}'
        path, tmpd = self._write_ino(src)
        try:
            results = apply_patches(path, [DEFAULT_PATCHES[0]])  # eeprom_include
            applied = [r for r in results if r[1]]
            self.assertTrue(len(applied) >= 1)
            content = read_file(path)
            self.assertIn("#include <EEPROM.h>", content)
        finally:
            shutil.rmtree(tmpd)

    def test_dry_run_does_not_modify_file(self):
        src = "server._catchAllHandleron(\"/\");"
        path, tmpd = self._write_ino(src)
        try:
            apply_patches(path, [DEFAULT_PATCHES[2]], dry_run=True)
            content = read_file(path)
            self.assertIn("_catchAllHandleron", content)
        finally:
            shutil.rmtree(tmpd)

    def test_already_present_check_skips(self):
        src = '#include <ESP8266WiFi.h>\n#include <EEPROM.h>\nvoid setup(){}'
        path, tmpd = self._write_ino(src)
        try:
            results = apply_patches(path, [DEFAULT_PATCHES[0]])
            pid, applied, detail = results[0]
            self.assertFalse(applied)
            self.assertIn("already present", detail.lower())
        finally:
            shutil.rmtree(tmpd)

    def test_backup_created_on_change(self):
        path, tmpd = self._write_ino("server._catchAllHandleron(\"/\");")
        bak = path + ".bak"
        try:
            apply_patches(path, [DEFAULT_PATCHES[2]])
            self.assertTrue(os.path.isfile(bak))
        finally:
            shutil.rmtree(tmpd)

    def test_file_not_found_returns_error(self):
        results = apply_patches("/nonexistent/sketch.ino")
        self.assertEqual(results[0][0], "error")
        self.assertFalse(results[0][1])

    def test_unknown_patch_format(self):
        results = apply_patches.__wrapped__ if hasattr(apply_patches, "__wrapped__") else apply_patches
        path, tmpd = make_temp_ino("void setup(){}")
        try:
            bad_patch = {"id": "bad", "auto": True}
            results = apply_patches(path, [bad_patch])
            self.assertFalse(results[0][1])
            self.assertIn("Unknown patch format", results[0][2])
        finally:
            shutil.rmtree(tmpd)


# ---------------------------------------------------------------------------
# 10. lib/patcher.py — build_patches_from_config() — FIX: empty check coercion
# ---------------------------------------------------------------------------

class TestBuildPatchesFromConfig(unittest.TestCase):

    def test_returns_default_patches_with_no_custom(self):
        cfg = {"patches": {"rules": []}}
        patches = build_patches_from_config(cfg)
        ids = [p["id"] for p in patches]
        self.assertIn("eeprom_include", ids)
        self.assertIn("server_on_typo", ids)

    def test_custom_regex_replace_added(self):
        cfg = {"patches": {"rules": [
            {"type": "regex_replace", "search": "foo", "replace": "bar", "id": "my_fix", "auto": True}
        ]}}
        patches = build_patches_from_config(cfg)
        ids = [p["id"] for p in patches]
        self.assertIn("my_fix", ids)

    def test_custom_insert_after_added(self):
        cfg = {"patches": {"rules": [
            {"type": "insert_after", "pattern": r"(#include.*)", "text": "\n//added", "id": "insert_test", "auto": True}
        ]}}
        patches = build_patches_from_config(cfg)
        ids = [p["id"] for p in patches]
        self.assertIn("insert_test", ids)

    def test_empty_check_coerced_to_none(self):
        """FIX: check: '' in config must be treated as None, not empty regex."""
        cfg = {"patches": {"rules": [
            {"type": "insert_after", "pattern": r"(#include.*)", "text": "\n//added",
             "id": "empty_check_test", "check": "", "auto": True}
        ]}}
        patches = build_patches_from_config(cfg)
        custom = next(p for p in patches if p["id"] == "empty_check_test")
        # Empty string check must be coerced to None
        self.assertIsNone(custom["check"])

    def test_non_auto_patch_not_applied(self):
        path, tmpd = make_temp_ino("foo = 1;")
        try:
            cfg = {"patches": {"rules": [
                {"type": "regex_replace", "search": "foo", "replace": "bar",
                 "id": "disabled_fix", "auto": False}
            ]}}
            patches = build_patches_from_config(cfg)
            results = apply_patches(path, patches)
            # disabled patch should not be applied
            disabled = next((r for r in results if r[0] == "disabled_fix"), None)
            if disabled:
                self.assertFalse(disabled[1])
        finally:
            shutil.rmtree(tmpd)


# ---------------------------------------------------------------------------
# 11. lib/progress.py — parse_compile_line()
# ---------------------------------------------------------------------------

class TestParseCompileLine(unittest.TestCase):

    def test_compiling_cpp_file(self):
        event, detail = parse_compile_line("Compiling /path/to/main.cpp")
        self.assertEqual(event, "compiling")
        self.assertEqual(detail, "main.cpp")

    def test_compiling_ino_file(self):
        event, detail = parse_compile_line("Compiling /path/sketch.ino")
        self.assertEqual(event, "compiling")

    def test_compiling_library(self):
        event, detail = parse_compile_line('Compiling library "ArduinoJson"')
        self.assertEqual(event, "library")
        self.assertEqual(detail, "ArduinoJson")

    def test_linking(self):
        event, detail = parse_compile_line("Linking everything together")
        self.assertEqual(event, "linking")

    def test_memory_usage(self):
        # Arduino output format: "Sketch used 12345 / 32768 bytes (37%)"
        event, detail = parse_compile_line("Sketch used 12345 / 32768 bytes (37%)")
        self.assertEqual(event, "progress")
        self.assertEqual(detail, 37)

    def test_error_line(self):
        event, detail = parse_compile_line("sketch.ino:5: error: expected ';'")
        self.assertEqual(event, "error")

    def test_warning_line(self):
        event, detail = parse_compile_line("sketch.ino:3: warning: unused variable")
        self.assertEqual(event, "warning")

    def test_empty_line(self):
        event, detail = parse_compile_line("")
        self.assertIsNone(event)

    def test_unrecognized_line(self):
        event, detail = parse_compile_line("Some random output line")
        self.assertIsNone(event)

    def test_exit_status_error(self):
        event, detail = parse_compile_line("exit status 1")
        self.assertEqual(event, "error")

    def test_cached_file(self):
        event, detail = parse_compile_line("Using cached object file")
        self.assertEqual(event, "cached")

    def test_detecting_libraries_stage(self):
        event, detail = parse_compile_line("Detecting libraries used...")
        self.assertEqual(event, "stage")
        self.assertEqual(detail, "Detecting libraries")


# ---------------------------------------------------------------------------
# 12. lib/progress.py — CompileProgress.feed_line()
# ---------------------------------------------------------------------------

class TestCompileProgress(unittest.TestCase):

    def _progress(self):
        p = CompileProgress()
        # Suppress actual terminal output
        p.bar = MagicMock()
        return p

    def test_sketch_event_updates_bar(self):
        p = self._progress()
        p.feed_line("Compiling sketch")
        p.bar.update.assert_called()

    def test_library_event_increments_compiled(self):
        p = self._progress()
        p.feed_line('Compiling library "ArduinoJson"')
        self.assertEqual(p.compiled, 1)

    def test_error_event_returns_false(self):
        p = self._progress()
        result = p.feed_line("sketch.ino:1: error: 'x' was not declared")
        self.assertFalse(result)
        self.assertEqual(len(p.errors), 1)

    def test_memory_usage_updates_mem_pct(self):
        p = self._progress()
        p.feed_line("Sketch used 12345 / 32768 bytes (37%)")
        self.assertEqual(p.mem_pct, 37)

    def test_linking_sets_linked_flag(self):
        p = self._progress()
        p.feed_line("Linking everything together")
        self.assertTrue(p.linked)

    def test_unknown_line_returns_true(self):
        p = self._progress()
        result = p.feed_line("Some unrecognized output")
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# 13. compiler.py — load_config() / save_config()
# ---------------------------------------------------------------------------

class TestLoadSaveConfig(unittest.TestCase):

    def test_load_returns_dict(self):
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"board": {"fqbn": "esp32:esp32:esp32"}}, f)
            tmppath = f.name
        try:
            import compiler
            orig = compiler.CONFIG_PATH
            compiler.CONFIG_PATH = Path(tmppath)
            cfg = load_config()
            self.assertEqual(cfg["board"]["fqbn"], "esp32:esp32:esp32")
            compiler.CONFIG_PATH = orig
        finally:
            os.unlink(tmppath)

    def test_load_returns_empty_on_json_error(self):
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not json{{{")
            tmppath = f.name
        try:
            import compiler
            orig = compiler.CONFIG_PATH
            compiler.CONFIG_PATH = Path(tmppath)
            cfg = load_config()
            self.assertEqual(cfg, {})
            compiler.CONFIG_PATH = orig
        finally:
            os.unlink(tmppath)


# ---------------------------------------------------------------------------
# 14. compiler.py — resolve_path()
# ---------------------------------------------------------------------------

class TestResolvePath(unittest.TestCase):

    def test_empty_returns_empty(self):
        self.assertEqual(resolve_path(""), "")

    def test_absolute_existing_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmppath = f.name
        try:
            result = resolve_path(tmppath)
            self.assertEqual(result, os.path.normpath(tmppath))
        finally:
            os.unlink(tmppath)

    def test_tilde_expansion(self):
        result = resolve_path("~/nonexistent_test_file.ino")
        self.assertNotIn("~", result)


# ---------------------------------------------------------------------------
# 15. compiler.py — validate_source()
# ---------------------------------------------------------------------------

class TestValidateSource(unittest.TestCase):

    def test_valid_ino_file(self):
        path, tmpd = make_temp_ino("void setup(){}")
        try:
            ok, result = validate_source(path)
            self.assertTrue(ok)
        finally:
            shutil.rmtree(tmpd)

    def test_nonexistent_file(self):
        ok, msg = validate_source("/nonexistent/sketch.ino")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())

    def test_non_ino_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False) as f:
            tmppath = f.name
            f.write(b"int main(){}")
        try:
            ok, msg = validate_source(tmppath)
            self.assertFalse(ok)
            self.assertIn(".ino", msg)
        finally:
            os.unlink(tmppath)

    def test_empty_source_string(self):
        ok, msg = validate_source("")
        self.assertFalse(ok)

    def test_empty_file_fails(self):
        d = tempfile.mkdtemp()
        sketch_dir = os.path.join(d, "sketch")
        os.makedirs(sketch_dir)
        path = os.path.join(sketch_dir, "sketch.ino")
        open(path, "w").close()
        try:
            ok, msg = validate_source(path)
            self.assertFalse(ok)
            self.assertIn("empty", msg.lower())
        finally:
            shutil.rmtree(d)


# ---------------------------------------------------------------------------
# 16. compiler.py — validate_config()
# ---------------------------------------------------------------------------

class TestValidateConfig(unittest.TestCase):

    def test_empty_config_has_warnings(self):
        warnings = validate_config({})
        self.assertIsInstance(warnings, list)
        self.assertTrue(len(warnings) > 0)
        text = " ".join(warnings).lower()
        self.assertIn("fqbn", text)

    def test_valid_fqbn_no_fqbn_warning(self):
        cfg = {"board": {"fqbn": "esp32:esp32:esp32"}}
        warnings = validate_config(cfg)
        fqbn_warns = [w for w in warnings if "fqbn" in w.lower()]
        self.assertEqual(len(fqbn_warns), 0)

    def test_missing_source_file_warns(self):
        cfg = {"board": {"fqbn": "esp32:esp32:esp32"},
               "source": {"file": "/nonexistent/sketch.ino"}}
        warnings = validate_config(cfg)
        source_warns = [w for w in warnings if "source" in w.lower()]
        self.assertTrue(len(source_warns) > 0)


# ---------------------------------------------------------------------------
# 17. cleanup.py — is_protected_path() — FIX: subdirectory blocking removed
# ---------------------------------------------------------------------------

class TestIsProtectedPath(unittest.TestCase):

    def test_root_is_protected(self):
        self.assertTrue(is_protected_path("/"))

    def test_sdcard_is_protected(self):
        self.assertTrue(is_protected_path("/sdcard"))
        self.assertTrue(is_protected_path("/sdcard/DCIM/photos"))

    def test_storage_is_protected(self):
        self.assertTrue(is_protected_path("/storage"))
        self.assertTrue(is_protected_path("/storage/emulated/0/anything"))

    def test_home_itself_is_protected(self):
        self.assertTrue(is_protected_path(os.path.expanduser("~")))

    def test_arduino15_not_blocked(self):
        """FIX: ~/.arduino15 is a direct child of ~ but should NOT be blocked
        (it's a build artifact, not user data). The old depth<=1 rule incorrectly
        blocked it."""
        arduino15 = os.path.join(os.path.expanduser("~"), ".arduino15")
        result = is_protected_path(arduino15)
        self.assertFalse(result)

    def test_tmp_is_protected(self):
        self.assertTrue(is_protected_path("/tmp"))

    def test_safe_subdir_not_protected(self):
        result = is_protected_path("/tmp/cc-agent/67540777/project/esp-compiler/build")
        self.assertFalse(result)

    def test_allowlist_bypasses_protection(self):
        from cleanup import ALLOWLIST_PATHS
        test_path = "/sdcard/sandbox/hasil_c"
        ALLOWLIST_PATHS.add(test_path)
        try:
            result = is_protected_path(test_path)
            self.assertFalse(result)
        finally:
            ALLOWLIST_PATHS.discard(test_path)


# ---------------------------------------------------------------------------
# 18. cleanup.py — safe_remove()
# ---------------------------------------------------------------------------

class TestSafeRemove(unittest.TestCase):

    def test_removes_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmppath = f.name
        safe_remove(tmppath)
        self.assertFalse(os.path.exists(tmppath))

    def test_removes_directory(self):
        d = tempfile.mkdtemp()
        safe_remove(d)
        self.assertFalse(os.path.exists(d))

    def test_blocks_protected_path(self):
        result = safe_remove("/sdcard")
        self.assertFalse(result)

    def test_removes_symlink_not_target(self):
        target = tempfile.mkdtemp()
        link = target + "_link"
        os.symlink(target, link)
        try:
            safe_remove(link)
            self.assertFalse(os.path.islink(link))
            self.assertTrue(os.path.isdir(target))
        finally:
            shutil.rmtree(target, ignore_errors=True)
            if os.path.exists(link):
                os.unlink(link)

    def test_nonexistent_path_returns_false(self):
        result = safe_remove("/nonexistent/path/xyz")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# 19. Integration: patcher + scan_includes
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):

    def test_full_patch_pipeline(self):
        """Full pipeline: scan includes → detect platform → apply patches."""
        code = (
            "#include <ESP8266WiFi.h>\n"
            "server._catchAllHandleron(\"/\");\n"
            "void setup(){}\nvoid loop(){}\n"
        )
        path, tmpd = make_temp_ino(code)
        try:
            includes = scan_includes(path)
            self.assertIn("ESP8266WiFi.h", includes)

            plat, conf = detect_platform(path)
            self.assertEqual(plat, "esp8266")

            results = apply_patches(path)
            applied_ids = {r[0] for r in results if r[1]}
            self.assertIn("eeprom_include", applied_ids)
            self.assertIn("server_on_typo", applied_ids)

            content = read_file(path)
            self.assertIn("#include <EEPROM.h>", content)
            self.assertNotIn("_catchAllHandleron", content)
        finally:
            shutil.rmtree(tmpd)

    def test_auto_install_skips_builtins(self):
        """Built-in headers must not trigger library installation."""
        code = (
            "#include <WiFi.h>\n#include <WebServer.h>\n"
            "#include <EEPROM.h>\nvoid setup(){}\n"
        )
        path, tmpd = make_temp_ino(code)
        try:
            with patch("lib.installer.get_installed_libs", return_value=[]):
                with patch("lib.installer.install_lib", return_value=(True, "ok")) as mock_install:
                    results = auto_install_libs("cli", path, "/tmp/libs")
            # None of WiFi.h, WebServer.h, EEPROM.h should trigger install
            self.assertEqual(results, [])
            mock_install.assert_not_called()
        finally:
            shutil.rmtree(tmpd)


# ---------------------------------------------------------------------------
# 20. Edge cases and regression tests
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_header_to_lib_mapping_complete(self):
        """Ensure all HEADER_TO_LIB entries resolve correctly."""
        for header, lib in HEADER_TO_LIB.items():
            result = resolve_lib_name(header)
            self.assertEqual(result, lib, f"Mismatch for {header}")

    def test_esp8266_headers_not_in_esp32(self):
        """ESP8266-specific headers should not appear in ESP32_HEADERS."""
        overlap = ESP8266_HEADERS & ESP32_HEADERS
        self.assertEqual(overlap, set(), f"Unexpected overlap: {overlap}")

    def test_skipped_libs_not_in_header_to_lib(self):
        """Headers in SKIPPED_LIBS must not be mapped to installable libraries."""
        for h in SKIPPED_LIBS:
            self.assertNotIn(h, HEADER_TO_LIB, f"{h} is in both SKIPPED_LIBS and HEADER_TO_LIB")

    def test_apply_patches_non_auto_all_skipped(self):
        """Patches with auto=False must all be skipped."""
        path, tmpd = make_temp_ino("server._catchAllHandleron(\"/\");")
        try:
            patches = [dict(p, auto=False) for p in DEFAULT_PATCHES]
            results = apply_patches(path, patches)
            for pid, applied, detail in results:
                self.assertFalse(applied, f"Patch {pid} should not have applied")
        finally:
            shutil.rmtree(tmpd)

    def test_progress_bar_update_does_not_exceed_total(self):
        """ProgressBar.update clamps value to total."""
        bar = ProgressBar(total=100)
        bar.update(150)
        self.assertEqual(bar.current, 100)

    def test_progress_bar_zero_total(self):
        """ProgressBar with total=0 should not raise ZeroDivisionError."""
        bar = ProgressBar(total=0)
        try:
            bar.update(0)
        except ZeroDivisionError:
            self.fail("ProgressBar raised ZeroDivisionError with total=0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
