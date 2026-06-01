#!/bin/bash
# ============================================================
#  ESP32 / ESP8266 Firmware Compiler - Uninstaller
#  curl -fsSL https://raw.githubusercontent.com/XbibzOfficial/esp-compiler/main/uninstall.sh | bash
# ============================================================
set -e

# --- Config ---
INSTALL_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
BIN_DIR="${HOME}/.local/bin"

# --- Colors ---
_c() {
    local c="$1"; shift
    case "$c" in
        r) printf '\033[1;31m';;  g) printf '\033[1;32m';;  y) printf '\033[1;33m';;
        b) printf '\033[1;34m';;  c) printf '\033[1;36m';;  w) printf '\033[1;37m';;
        d) printf '\033[90m';;    x) printf '\033[0m';;
    esac
}

_banner() {
    local x c; x=$(_c x); c=$(_c c)
    printf '\n'
    printf '  %s============================================================%s\n' "$c" "$x"
    printf '  %s  ESP-Compiler - Uninstaller                              %s\n' "$c" "$x"
    printf '  %s============================================================%s\n' "$c" "$x"
    printf '\n'
}

_log()  { printf '  %s[>]%s %s\n' "$(_c y)" "$(_c x)" "$1"; }
_ok()   { printf '      %s[+]%s %s\n' "$(_c g)" "$(_c x)" "$1"; }
_fail() { printf '      %s[-]%s %s\n' "$(_c r)" "$(_c x)" "$1"; }
_info() { printf '      %s[~]%s %s\n' "$(_c d)" "$(_c x)" "$1"; }
_div()  { printf '  %s%s%s\n' "$(_c d)" "$(printf '─%.0s' {1..60})" "$(_c x)"; }

prompt_yn() {
    local msg="$1" default="${2:-y}"
    local suffix
    if [ "$default" = "y" ]; then
        suffix="$(_c g)Y$(_c x)/$(_c r)n$(_c x)"
    else
        suffix="$(_c g)y$(_c x)/$(_c r)N$(_c x)"
    fi
    printf '      %s[?]%s %s [%s]: ' "$(_c c)" "$(_c x)" "$msg" "$suffix"
    read -r val
    val="${val:-$default}"
    [[ "$val" =~ ^[Yy] ]]
}

safe_rm() {
    local target="$1" label="${2:-$1}"
    if [ -e "$target" ] || [ -L "$target" ]; then
        rm -rf "$target"
        _ok "Removed: ${label}"
    else
        _info "Not found: ${label}"
    fi
}

# --- Detect and clean shell config ---
clean_shell() {
    _log "Cleaning shell config"

    local marker="# ESP-Compiler (XbibzOfficial)"
    local found_any=false

    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
        if [ -f "$rc" ] && grep -q "$marker" "$rc" 2>/dev/null; then
            local tmp="${rc}.esp-uninstall.tmp"
            sed "/${marker//\#/\\#}/,/# End ESP-Compiler/d" "$rc" > "$tmp"
            mv "$tmp" "$rc"
            _ok "Cleaned: ${rc}"
            found_any=true
        fi
    done

    # Remove cesp binary
    safe_rm "${BIN_DIR}/cesp" "cesp binary"

    if [ "$found_any" = false ]; then
        _info "No shell config entries found"
    fi
}

# --- Main ---
main() {
    _banner

    _log "Removing compiler files"
    safe_rm "${INSTALL_DIR}" "Compiler directory"

    _log "Removing build output"
    if [ -d "./build" ]; then
        safe_rm "./build" "Build directory"
    fi
    if [ -d "./bibz" ]; then
        if prompt_yn "Remove bibz/ source directory?" "n"; then
            safe_rm "./bibz" "bibz directory"
        else
            _info "Kept: bibz/"
        fi
    fi

    clean_shell

    _log "Removing arduino-cli (optional)"
    if command -v arduino-cli &>/dev/null; then
        if prompt_yn "Remove arduino-cli binary and data?" "n"; then
            safe_rm "$(which arduino-cli)" "arduino-cli binary"
            safe_rm "$HOME/.arduino15" "Arduino config"
            safe_rm "$HOME/.data/data/com.termux/files/home/.arduino15" "Termux Arduino config"
            safe_rm "$HOME/Arduino" "Arduino libraries"
        else
            _info "Kept: arduino-cli"
        fi
    else
        _info "arduino-cli not found"
    fi

    _div
    printf '  %s%s  UNINSTALL COMPLETE%s\n' "$(_c g)" "$(_c w)" "$(_c x)"
    _div
    printf '\n'
    printf '  %sRestart your shell:%s\n' "$(_c w)" "$(_c x)"
    printf '    %ssource %s/.%src%s\n' "$(_c c)" "$HOME" "$([ "$SHELL" = */zsh ] && echo "zsh" || echo "bash")" "$(_c x)"
    printf '\n'
    _div
    printf '  %sSource Code By : %sXbibz Official%s\n' "$(_c d)" "$(_c w)" "$(_c x)"
    _div
    printf '\n'
}

main "$@"
