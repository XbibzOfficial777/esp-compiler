import re
import os


DEFAULT_PATCHES = [
    {
        "id": "eeprom_include",
        "description": "Insert #include <EEPROM.h> after first WiFi include",
        "pattern": r"(#include\s*<(?:ESP8266)?WiFi\.h>)",
        "insert_after": '\n#include <EEPROM.h>',
        "check": r"#include\s*<EEPROM\.h>",
        "auto": True
    },
    {
        "id": "web_password_scope",
        "description": "Move web_password declaration to global scope",
        "pattern": r'(String\s+web_password\s*=\s*"";)',
        "delete_match": True,
        "insert_after_pattern": r"(int\s+attack_interval\s*=\s*\d+;)",
        "insert_after_text": '\nString web_password = "";',
        "auto": True
    },
    {
        "id": "server_on_typo",
        "description": "Fix server._catchAllHandleron typo",
        "search": "server._catchAllHandleron",
        "replace": "server.on",
        "auto": True
    }
]


def read_file(path):
    """Read file content."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_file(path, content):
    """Write content to file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def apply_patches(source_file, patches=None, dry_run=False):
    """Apply patches to source file. Returns list of (patch_id, applied, detail)."""
    if patches is None:
        patches = DEFAULT_PATCHES

    try:
        content = read_file(source_file)
    except FileNotFoundError:
        return [("error", False, f"File not found: {source_file}")]

    original = content
    results = []

    for patch in patches:
        pid = patch.get("id", "unknown")
        auto = patch.get("auto", False)
        desc = patch.get("description", "")

        if not auto:
            results.append((pid, False, "Skipped (not auto)"))
            continue

        if "search" in patch and "replace" in patch:
            if patch["search"] in content:
                content = content.replace(patch["search"], patch["replace"])
                results.append((pid, True, desc))
            else:
                results.append((pid, False, "Pattern not found, already fixed"))

        elif "check" in patch and "pattern" in patch and "insert_after" in patch:
            if patch.get("check") and re.search(patch["check"], content):
                results.append((pid, False, "Already present"))
            else:
                m = re.search(patch["pattern"], content)
                if m:
                    insert_text = patch["insert_after"]
                    content = content[:m.end()] + insert_text + content[m.end():]
                    results.append((pid, True, desc))
                else:
                    results.append((pid, False, "Anchor pattern not found"))

        elif "delete_match" in patch and "insert_after_pattern" in patch:
            did_delete = False
            if re.search(patch["pattern"], content):
                content = re.sub(patch["pattern"], "", content)
                did_delete = True

            insert_after = patch.get("insert_after_pattern", "")
            insert_text = patch.get("insert_after_text", "")
            if insert_after and insert_text:
                m = re.search(insert_after, content)
                if m:
                    content = content[:m.end()] + insert_text + content[m.end():]
                    results.append((pid, True, f"{desc} (deleted old: {did_delete})"))
                else:
                    results.append((pid, False, "Insert anchor not found"))
            else:
                results.append((pid, did_delete, "Delete only"))

        else:
            results.append((pid, False, "Unknown patch format"))

    if content != original and not dry_run:
        backup_path = source_file + ".bak"
        write_file(backup_path, original)
        write_file(source_file, content)

    return results


def build_patches_from_config(config):
    """Build patch list from config.json custom rules."""
    patches = list(DEFAULT_PATCHES)
    custom = config.get("patches", {}).get("rules", [])

    for rule in custom:
        if rule.get("type") == "regex_replace" and "search" in rule and "replace" in rule:
            patches.append({
                "id": rule.get("id", "custom"),
                "description": rule.get("description", "Custom patch"),
                "search": rule["search"],
                "replace": rule["replace"],
                "auto": rule.get("auto", True)
            })
        elif rule.get("type") == "insert_after" and "pattern" in rule and "text" in rule:
            patches.append({
                "id": rule.get("id", "custom"),
                "description": rule.get("description", "Custom patch"),
                "pattern": rule["pattern"],
                "insert_after": rule["text"],
                "check": rule.get("check", ""),
                "auto": rule.get("auto", True)
            })

    return patches
