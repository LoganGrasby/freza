#!/bin/sh
set -e

# Freza installer
# Usage: curl -fsSL https://freza.ai/install.sh | sh

REPO="https://github.com/LoganGrasby/freza.git"
MIN_PYTHON="3.10"

info()  { printf '  \033[1;34m→\033[0m %s\n' "$*"; }
ok()    { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
err()   { printf '  \033[1;31m✗\033[0m %s\n' "$*" >&2; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

# ── OS check ────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macOS" ;;
  Linux)  PLATFORM="Linux" ;;
  *)
    err "Unsupported platform: $OS"
    err "Freza supports macOS and Linux."
    exit 1
    ;;
esac
info "Detected $PLATFORM"

# ── Python check ────────────────────────────────────────────────────
check_python_version() {
  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi
  py_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  py_major="${py_version%%.*}"
  py_minor="${py_version#*.}"
  min_major="${MIN_PYTHON%%.*}"
  min_minor="${MIN_PYTHON#*.}"
  [ "$py_major" -gt "$min_major" ] && return 0
  [ "$py_major" -eq "$min_major" ] && [ "$py_minor" -ge "$min_minor" ] && return 0
  return 1
}

if ! check_python_version; then
  err "Python $MIN_PYTHON or later is required."
  case "$PLATFORM" in
    macOS)
      err "Install it with:  brew install python@3.12"
      err "Or download from: https://www.python.org/downloads/"
      ;;
    Linux)
      err "Install it with your package manager, e.g.:"
      err "  sudo apt install python3   (Debian/Ubuntu)"
      err "  sudo dnf install python3   (Fedora)"
      ;;
  esac
  exit 1
fi
ok "Python $(python3 --version | awk '{print $2}') found"

# ── pipx check / install ───────────────────────────────────────────
ensure_pipx() {
  if command -v pipx >/dev/null 2>&1; then
    return 0
  fi

  info "pipx not found — installing it now"
  case "$PLATFORM" in
    macOS)
      if command -v brew >/dev/null 2>&1; then
        brew install pipx
        pipx ensurepath
      else
        python3 -m pip install --user pipx
        python3 -m pipx ensurepath
      fi
      ;;
    Linux)
      python3 -m pip install --user pipx
      python3 -m pipx ensurepath
      ;;
  esac

  # Re-source PATH so pipx is available in this session
  export PATH="$HOME/.local/bin:$PATH"

  if ! command -v pipx >/dev/null 2>&1; then
    err "Failed to install pipx. Install it manually:"
    err "  https://pipx.pypa.io/stable/installation/"
    exit 1
  fi
}

ensure_pipx
ok "pipx is available"

# ── Install freza ───────────────────────────────────────────────────
bold ""
bold "Installing freza…"
pipx install "git+${REPO}" || pipx upgrade "git+${REPO}"
ok "freza installed"

# ── Ensure ~/.local/bin is on PATH (persist to shell profile) ───────
pipx ensurepath >/dev/null 2>&1 || true
export PATH="$HOME/.local/bin:$PATH"

if ! command -v freza >/dev/null 2>&1; then
  err "freza was installed but is not on your PATH."
  err "Add this to your shell profile and restart your terminal:"
  err '  export PATH="$HOME/.local/bin:$PATH"'
  exit 1
fi
ok "freza is on PATH"

# ── Bootstrap workspace ─────────────────────────────────────────────
bold ""
bold "Bootstrapping workspace…"
freza init
ok "Workspace initialized"

# ── Done ────────────────────────────────────────────────────────────
bold ""
bold "🎉 Freza is ready!"
echo ""
info "Talk to your agent:  freza invoke default \"hello\""
info "Open the web UI:     freza webui"
info "Check status:        freza status"
echo ""
bold "NOTE: If 'freza' is not found, restart your terminal or run:"
echo '  source ~/.bashrc   # (or ~/.zshrc on macOS)'
echo ""
