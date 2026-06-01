#!/bin/bash
# ============================================================
#  ESP8266 / ESP32 Firmware Compiler - Installer
#  curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/main/install.sh | bash
# ============================================================

REPO="${GITHUB_REPO:-XbibzOfficial777/esp-compiler}"
BRANCH="${GIT_BRANCH:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
INSTALL_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
BIN_DIR="${HOME}/.local/bin"

_c() {
    case "$1" in
        r) printf '\033[1;31m';;  g) printf '\033[1;32m';;  y) printf '\033[1;33m';;
        c) printf '\033[1;36m';;  w) printf '\033[1;37m';;  d) printf '\033[90m';;
        x) printf '\033[0m';;
    esac
}

_banner() {
    local C W D X
    C=$(_c c); W=$(_c w); D=$(_c d); X=$(_c x)
    printf '\n'
    printf '  %s  ______                      _ __         %s\n' "$C" "$X"
    printf '  %s / ____/___  ____ ___  ____  (_) /__  _____%s\n' "$C" "$X"
    printf '  %s/ /   / __ \\/ __ `__ \\/ __ \\/ / / _ \\/ ___/%s\n' "$C" "$X"
    printf '  %s/ /___/ /_/ / / / / / /_/ / / /  __/ /    %s\n' "$C" "$X"
    printf '  %s\\____/\\____/_/ /_/ /_/ .___/_/_/\\___/_/     %s\n' "$C" "$X"
    printf '  %s                    /_/  %sXbibz Official%s%s\n' "$C" "$W" "$C" "$X"
    printf '\n'
    printf '  %sESP8266 / ESP32 Firmware Compiler v2.0%s\n' "$D" "$X"
    printf '  %s============================================================%s\n\n' "$C" "$X"
}

_log()  { printf '  %s[>]%s %s\n' "$(_c y)" "$(_c x)" "$1"; }
_ok()   { printf '      %s[+]%s %s\n' "$(_c g)" "$(_c x)" "$1"; }
_fail() { printf '      %s[-]%s %s\n' "$(_c r)" "$(_c x)" "$1"; }
_info() { printf '      %s[~]%s %s\n' "$(_c d)" "$(_c x)" "$1"; }
_div()  { printf '  %s%s%s\n' "$(_c d)" "$(printf '─%.0s' {1..60})" "$(_c x)"; }

detect_shell() {
    local name
    name=$(basename "${SHELL:-/bin/bash}")
    if [ "$name" = "zsh" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"; SHELL_NAME="zsh"
    else
        SHELL_RC="$HOME/.bashrc"; SHELL_NAME="bash"
    fi
    _info "Shell: ${SHELL_NAME} (${SHELL_RC})"
}

check_python() {
    _log "Checking Python"
    for p in python3 python; do
        if command -v "$p" &>/dev/null; then
            local v
            v=$("$p" --version 2>&1 | grep -oP '\d+\.\d+')
            local major minor
            major=$(echo "$v" | cut -d. -f1)
            minor=$(echo "$v" | cut -d. -f2)
            # Python 3.8+ or Python 4+
            if [ "$major" -ge 4 ] || { [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; }; then
                PYTHON="$p"
                _ok "Python ${v}"
                return 0
            fi
        fi
    done
    _fail "Python 3.8+ required"
    return 1
}

download_files() {
    _log "Downloading compiler"
    mkdir -p "${INSTALL_DIR}/lib"

    local files=(
        "config.json" "lib/__init__.py" "lib/installer.py"
        "lib/patcher.py" "lib/progress.py" "setup.py"
        "compiler.py" "cleanup.py" "install.sh" "uninstall.sh"
    )

    local ok=0
    for f in "${files[@]}"; do
        local target="${INSTALL_DIR}/${f}"
        mkdir -p "$(dirname "$target")"
        if curl -fsSL "${RAW}/${f}" -o "$target" 2>/dev/null; then
            ok=$((ok + 1))
        else
            _fail "Failed: ${f}"
        fi
    done

    chmod +x "${INSTALL_DIR}/install.sh" "${INSTALL_DIR}/uninstall.sh" 2>/dev/null || true
    _ok "Downloaded ${ok} files"
}

install_arduino_cli() {
    _log "Checking arduino-cli"
    if command -v arduino-cli &>/dev/null; then
        _ok "arduino-cli: $(which arduino-cli)"
        return 0
    fi

    _log "Installing arduino-cli"
    mkdir -p "${BIN_DIR}"

    local tmpsh
    tmpsh=$(mktemp)
    if ! curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh -o "$tmpsh" 2>/dev/null; then
        _fail "Failed to download arduino-cli installer"
        rm -f "$tmpsh"
        return 1
    fi

    # Validate downloaded file is not empty
    if [ ! -s "$tmpsh" ]; then
        _fail "Downloaded installer is empty"
        rm -f "$tmpsh"
        return 1
    fi

    # Run install silently
    BINDIR="${BIN_DIR}" bash "$tmpsh" >/dev/null 2>&1 &
    local pid=$!

    # Spinner while waiting
    local sp='|/-\'
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r      %s%s%s Installing arduino-cli..." "$(_c c)" "${sp:i++%${#sp}:1}" "$(_c x)"
        sleep 0.1
    done
    wait "$pid" 2>/dev/null
    printf "\r\033[2K"
    rm -f "$tmpsh"

    if [ -f "${BIN_DIR}/arduino-cli" ]; then
        _ok "arduino-cli installed"
    else
        _fail "arduino-cli install failed"
        return 1
    fi
}

setup_shell() {
    _log "Setting up ${SHELL_NAME}"

    local marker="# ESP-Compiler (XbibzOfficial)"
    if [ -f "$SHELL_RC" ] && grep -q "$marker" "$SHELL_RC" 2>/dev/null; then
        _ok "Shell already configured"
    else
        cat >> "$SHELL_RC" << EOF

${marker}
export PATH="${BIN_DIR}:\$PATH"
cesp() {
    local cmd="\$1"; shift
    case "\$cmd" in
        setup|s)    python3 "${INSTALL_DIR}/setup.py" "\$@";;
        compile|c)  python3 "${INSTALL_DIR}/compiler.py" "\$@";;
        clean)      python3 "${INSTALL_DIR}/cleanup.py" "\$@";;
        help|h)     echo "Usage: cesp [setup|compile|clean|uninstall] [flags]";;
        uninstall)  bash "${INSTALL_DIR}/uninstall.sh";;
        *)          python3 "${INSTALL_DIR}/compiler.py" --source "\$cmd" "\$@";;
    esac
}
# End ESP-Compiler
EOF
        _ok "Added cesp command"
    fi

    mkdir -p "${BIN_DIR}"
    cat > "${BIN_DIR}/cesp" << 'BIN'
#!/bin/bash
COMPILER_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
cmd="$1"; shift
case "$cmd" in
    setup|s)    python3 "${COMPILER_DIR}/setup.py" "$@";;
    compile|c)  python3 "${COMPILER_DIR}/compiler.py" "$@";;
    clean)      python3 "${COMPILER_DIR}/cleanup.py" "$@";;
    help|h)     echo "Usage: cesp [setup|compile|clean|uninstall] [flags]";;
    uninstall)  bash "${COMPILER_DIR}/uninstall.sh";;
    *)          python3 "${COMPILER_DIR}/compiler.py" --source "$cmd" "$@";;
esac
BIN
    chmod +x "${BIN_DIR}/cesp"
    _ok "Binary: ${BIN_DIR}/cesp"
}

main() {
    _banner
    detect_shell
    check_python || exit 1
    download_files
    install_arduino_cli || true
    setup_shell

    echo
    _div
    printf '  %s%s  INSTALLATION COMPLETE%s\n\n' "$(_c g)" "$(_c w)" "$(_c x)"

    printf '  %sUsage:%s\n' "$(_c w)" "$(_c x)"
    printf '    %scesp setup%s                  # First-time setup\n' "$(_c c)" "$(_c x)"
    printf '    %scesp compile firmware.ino%s   # Compile firmware\n' "$(_c c)" "$(_c x)"
    printf '    %scesp compile firmware.ino --board esp32:esp32:esp32%s\n' "$(_c c)" "$(_c x)"
    printf '    %scesp clean%s                  # Cleanup build files\n' "$(_c c)" "$(_c x)"
    printf '    %scesp help%s                   # Show all commands\n' "$(_c c)" "$(_c x)"
    printf '    %scesp uninstall%s              # Remove compiler\n' "$(_c c)" "$(_c x)"

    printf '\n  %sNext steps:%s\n' "$(_c w)" "$(_c x)"
    printf '    1. %ssource %s%s\n' "$(_c c)" "$SHELL_RC" "$(_c x)"
    printf '    2. %scesp setup%s\n' "$(_c c)" "$(_c x)"
    printf '    3. %scesp compile your_firmware.ino%s\n\n' "$(_c c)" "$(_c x)"

    _div
    printf '  %sSource Code By : %sXbibz Official%s\n' "$(_c d)" "$(_c w)" "$(_c x)"
    _div
    echo
}

main "$@"
