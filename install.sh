#!/bin/bash
# ============================================================
#  ESP32 / ESP8266 Firmware Compiler - Installer
#  curl -fsSL https://raw.githubusercontent.com/XbibzOfficial/esp-compiler/main/install.sh | bash
# ============================================================
set -e

# --- Config ---
REPO="${GITHUB_REPO:-XbibzOfficial777/esp-compiler}"
BRANCH="${GIT_BRANCH:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
INSTALL_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
BIN_DIR="${HOME}/.local/bin"

# --- Colors ---
_c() {
    local c="$1"; shift
    case "$c" in
        r) printf '\033[1;31m';;  # red
        g) printf '\033[1;32m';;  # green
        y) printf '\033[1;33m';;  # yellow
        b) printf '\033[1;34m';;  # blue
        c) printf '\033[1;36m';;  # cyan
        w) printf '\033[1;37m';;  # white
        d) printf '\033[90m';;    # dim
        x) printf '\033[0m';;     # reset
    esac
}

_banner() {
    local R G B W D X
    R=$(_c r); G=$(_c g); C=$(_c c); W=$(_c w); D=$(_c d); X=$(_c x)
    cat << 'BANNER'

                           (                             )\           )          (   )\   (   (    
                        (((_)   (     (     `  )  )\ ((_) ))\  )(   
                        )\___   )\    )\   /(/( ((_) _  /((_)(()\  
                       ((/ __| ((_) _((_)) ((_)\_ (_)| |(_))   ((_) 
                        | (__ / _ \| '  \()| '_ \)| || |/ -_) | '_| 
                         \___|\___/|_|_|_| | .__/ |_||_|\___| |_|   
                                           |_|         Xbibz Official

BANNER
    printf '  %s  ESP8266 / ESP32  Firmware Compiler  v2.0%s\n' "$D" "$X"
    printf '  %s============================================================%s\n\n' "$C" "$X"
}

_log()  { printf '  %s[>]%s %s\n' "$(_c y)" "$(_c x)" "$1"; }
_ok()   { printf '      %s[+]%s %s\n' "$(_c g)" "$(_c x)" "$1"; }
_fail() { printf '      %s[-]%s %s\n' "$(_c r)" "$(_c x)" "$1"; }
_info() { printf '      %s[~]%s %s\n' "$(_c d)" "$(_c x)" "$1"; }
_div()  { printf '  %s%s%s\n' "$(_c d)" "$(printf '─%.0s' {1..60})" "$(_c x)"; }

# --- Detect shell ---
detect_shell() {
    local shell_name
    shell_name=$(basename "${SHELL:-/bin/bash}")

    if [ "$shell_name" = "zsh" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
        SHELL_NAME="zsh"
    elif [ "$shell_name" = "bash" ] || [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
        SHELL_NAME="bash"
    else
        SHELL_RC="$HOME/.bashrc"
        SHELL_NAME="bash"
    fi
    _info "Detected shell: ${SHELL_NAME} (${SHELL_RC})"
}

# --- Check python ---
check_python() {
    _log "Checking Python"
    local py=""
    for p in python3 python; do
        if command -v "$p" &>/dev/null; then
            local ver
            ver=$("$p" --version 2>&1 | grep -oP '\d+\.\d+')
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
                py="$p"
                _ok "Python ${ver} (${p})"
                break
            fi
        fi
    done
    if [ -z "$py" ]; then
        _fail "Python 3.8+ required"
        return 1
    fi
    PYTHON="$py"
}

# --- Download files ---
download_files() {
    _log "Downloading compiler to ${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}/lib"

    local files=(
        "config.json"
        "lib/__init__.py"
        "lib/installer.py"
        "lib/patcher.py"
        "lib/progress.py"
        "setup.py"
        "compiler.py"
        "cleanup.py"
        "install.sh"
        "uninstall.sh"
    )

    for f in "${files[@]}"; do
        local target="${INSTALL_DIR}/${f}"
        mkdir -p "$(dirname "$target")"
        if curl -fsSL "${RAW}/${f}" -o "$target" 2>/dev/null; then
            _ok "${f}"
        else
            _fail "Failed: ${f}"
        fi
    done

    chmod +x "${INSTALL_DIR}/install.sh" "${INSTALL_DIR}/uninstall.sh" 2>/dev/null || true
}

# --- Install arduino-cli ---
install_arduino_cli() {
    _log "Checking arduino-cli"
    if command -v arduino-cli &>/dev/null; then
        _ok "arduino-cli: $(which arduino-cli)"
        return 0
    fi

    _log "Installing arduino-cli"
    mkdir -p "${BIN_DIR}"
    if curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="${BIN_DIR}" sh 2>/dev/null; then
        _ok "arduino-cli installed"
    else
        _fail "arduino-cli install failed"
        return 1
    fi
}

# --- Setup PATH and cesp command ---
setup_shell() {
    _log "Setting up ${SHELL_NAME} config"

    local marker="# ESP-Compiler (XbibzOfficial)"
    local already_done=false

    # Check if already configured
    if [ -f "$SHELL_RC" ] && grep -q "$marker" "$SHELL_RC" 2>/dev/null; then
        already_done=true
    fi

    if [ "$already_done" = false ]; then
        {
            echo ""
            echo "${marker}"
            export PATH="${BIN_DIR}:\$PATH"
            echo "export PATH=\"${BIN_DIR}:\$PATH\""
            echo ""
            echo "# ESP Compiler shortcut command"
            echo "cesp() {"
            echo "    local cmd=\"\$1\"; shift"
            echo "    case \"\$cmd\" in"
            echo "        setup|s)    \"${INSTALL_DIR}/setup.py\" \"\$@\";;"
            echo "        compile|c)  \"${INSTALL_DIR}/compiler.py\" \"\$@\";;"
            echo "        clean)      \"${INSTALL_DIR}/cleanup.py\" \"\$@\";;"
            echo "        help|h)     echo 'Usage: cesp [setup|compile|clean|uninstall] [flags]';;"
            echo "        uninstall)  bash \"${INSTALL_DIR}/uninstall.sh\";;"
            echo "        *)          \"${INSTALL_DIR}/compiler.py\" --source \"\$cmd\" \"\$@\";;"
            echo "    esac"
            echo "}"
            echo "# End ESP-Compiler"
            echo ""
        } >> "$SHELL_RC"
        _ok "Added cesp command to ${SHELL_RC}"
    else
        _ok "Shell config already set up"
    fi

    # Also create symlink in BIN_DIR for direct access
    mkdir -p "${BIN_DIR}"
    cat > "${BIN_DIR}/cesp" << 'SYMLINK'
#!/bin/bash
# ESP Compiler shortcut - XbibzOfficial
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
SYMLINK
    chmod +x "${BIN_DIR}/cesp"
    _ok "Binary: ${BIN_DIR}/cesp"
}

# --- Main ---
main() {
    _banner
    detect_shell
    check_python || exit 1
    download_files
    install_arduino_cli || exit 1
    setup_shell

    _div
    printf '  %s%s  INSTALLATION COMPLETE%s\n' "$(_c g)" "$(_c w)" "$(_c x)"
    _div
    printf '\n'
    printf '  %sQuick Start:%s\n' "$(_c w)" "$(_c x)"
    printf '    %scesp setup%s              # Interactive setup\n' "$(_c c)" "$(_c x)"
    printf '    %scesp compile file.ino%s   # Compile firmware\n' "$(_c c)" "$(_c x)"
    printf '    %scesp help%s               # Show all commands\n' "$(_c c)" "$(_c x)"
    printf '\n'
    printf '  %sRestart your shell:%s\n' "$(_c w)" "$(_c x)"
    printf '    %ssource %s%s\n' "$(_c c)" "$SHELL_RC" "$(_c x)"
    printf '\n'
    _div
    printf '  %sSource Code By : %sXbibz Official%s\n' "$(_c d)" "$(_c w)" "$(_c x)"
    _div
    printf '\n'
}

main "$@"
