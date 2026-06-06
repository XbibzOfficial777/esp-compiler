#!/bin/bash
# ============================================================
#  ESP-Compiler - Patch cesp shell function
#  Fixes: zsh "shift count must be <= $#" when running `cesp` with no args
#  Run: bash ~/.esp-compiler/patch-cesp.sh
#    or: curl -fsSL https://raw.githubusercontent.com/XbibzOfficial777/esp-compiler/debug/bug-fixes/patch-cesp.sh | bash
# ============================================================

INSTALL_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
BIN_DIR="$HOME/.local/bin"
marker="# ESP-Compiler (XbibzOfficial)"
end_marker="# End ESP-Compiler"

_c() { case "$1" in r) printf '\033[1;31m';; g) printf '\033[1;32m';; y) printf '\033[1;33m';; c) printf '\033[1;36m';; d) printf '\033[90m';; x) printf '\033[0m';; esac; }
_ok()   { printf '  %s[+]%s %s\n' "$(_c g)" "$(_c x)" "$1"; }
_info() { printf '  %s[~]%s %s\n' "$(_c d)" "$(_c x)" "$1"; }
_log()  { printf '  %s[>]%s %s\n' "$(_c y)" "$(_c x)" "$1"; }

printf '\n  %s== ESP-Compiler: Patch cesp ==%s\n\n' "$(_c c)" "$(_c x)"

# 1. Update ~/.local/bin/cesp binary
_log "Updating cesp binary"
mkdir -p "${BIN_DIR}"
cat > "${BIN_DIR}/cesp" << 'BIN'
#!/bin/bash
COMPILER_DIR="${ESP_COMPILER_DIR:-$HOME/.esp-compiler}"
if [ $# -eq 0 ]; then
    python3 "${COMPILER_DIR}/compiler.py"
    exit $?
fi
cmd="$1"; shift
case "$cmd" in
    setup|s)    python3 "${COMPILER_DIR}/setup.py" "$@";;
    compile|c)
        if [ $# -eq 0 ]; then
            python3 "${COMPILER_DIR}/compiler.py"
        else
            src="$1"; shift
            python3 "${COMPILER_DIR}/compiler.py" --source "$src" "$@"
        fi;;
    clean)      python3 "${COMPILER_DIR}/cleanup.py" "$@";;
    help|h)     echo "Usage: cesp [setup|compile|clean|uninstall] [flags]";;
    uninstall)  bash "${COMPILER_DIR}/uninstall.sh";;
    *)          python3 "${COMPILER_DIR}/compiler.py" --source "$cmd" "$@";;
esac
BIN
chmod +x "${BIN_DIR}/cesp"
_ok "Binary updated: ${BIN_DIR}/cesp"

# 2. Remove old shell function from .bashrc / .zshrc and rewrite it
_log "Updating shell function"
patched_any=false

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$rc" ] || continue
    if grep -q "$marker" "$rc" 2>/dev/null; then
        tmp="${rc}.cesp-patch.tmp"
        sed "/${marker//\#/\\#}/,/${end_marker//\#/\\#}/d" "$rc" > "$tmp" && mv "$tmp" "$rc"
        _info "Removed old definition from ${rc}"
    fi
    cat >> "$rc" << EOF

${marker}
export PATH="${BIN_DIR}:\$PATH"
cesp() {
    if [ \$# -eq 0 ]; then
        python3 "${INSTALL_DIR}/compiler.py"
        return \$?
    fi
    local cmd="\$1"; shift
    case "\$cmd" in
        setup|s)    python3 "${INSTALL_DIR}/setup.py" "\$@";;
        compile|c)
            if [ \$# -eq 0 ]; then
                python3 "${INSTALL_DIR}/compiler.py"
            else
                local src="\$1"; shift
                python3 "${INSTALL_DIR}/compiler.py" --source "\$src" "\$@"
            fi;;
        clean)      python3 "${INSTALL_DIR}/cleanup.py" "\$@";;
        help|h)     echo "Usage: cesp [setup|compile|clean|uninstall] [flags]";;
        uninstall)  bash "${INSTALL_DIR}/uninstall.sh";;
        *)          python3 "${INSTALL_DIR}/compiler.py" --source "\$cmd" "\$@";;
    esac
}
${end_marker}
EOF
    _ok "Updated: ${rc}"
    patched_any=true
done

if [ "$patched_any" = false ]; then
    _info "No shell RC files updated (run: source ~/.zshrc or ~/.bashrc after this)"
fi

printf '\n  %sDone! Now run:%s\n' "$(_c g)" "$(_c x)"
printf '    %ssource ~/.zshrc%s   (or ~/.bashrc)\n\n' "$(_c c)" "$(_c x)"
