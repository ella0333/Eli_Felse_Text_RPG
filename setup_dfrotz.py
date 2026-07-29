"""Cross-platform dfrotz installer.

Detects the OS and ensures dfrotz is available:
- Windows: verifies the bundled bin/windows/dfrotz.exe exists
- macOS: installs via Homebrew or compiles from source
- Linux: installs via package manager (apt/dnf/pacman) or compiles from source
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
BIN_DIR = MODULE_ROOT / "bin"
VENDOR_DIR = MODULE_ROOT / "vendor"
FROTZ_REPO = "https://gitlab.com/DavidGriffith/frotz.git"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def _ask_yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} ({hint}): ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def _verify_dfrotz(path: str) -> bool:
    """Check that dfrotz runs."""
    try:
        result = subprocess.run(
            [path, "-v"],
            capture_output=True, text=True, timeout=5,
        )
        # dfrotz -v may exit 0 or 1 depending on version, just check it ran
        return result.returncode in (0, 1)
    except Exception:
        return False


def _compile_from_source() -> str | None:
    """Clone frotz and compile dfrotz. Returns path to binary or None."""
    if not shutil.which("git"):
        print("  git is not installed. Cannot compile from source.")
        return None
    if not shutil.which("make"):
        print("  make is not installed. Cannot compile from source.")
        return None

    src_dir = VENDOR_DIR / "frotz-src"
    if src_dir.exists():
        print(f"  Removing old source directory: {src_dir}")
        shutil.rmtree(src_dir)

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    print("\n  Cloning frotz source...")
    result = _run(["git", "clone", "--depth", "1", FROTZ_REPO, str(src_dir)])
    if result.returncode != 0:
        print("  Clone failed.")
        return None

    print("  Compiling dfrotz...")
    result = _run(["make", "dfrotz"], cwd=str(src_dir))
    if result.returncode != 0:
        print("  Compilation failed.")
        return None

    built = src_dir / "dfrotz"
    if not built.exists():
        print("  dfrotz binary not found after compilation.")
        return None

    dest = BIN_DIR / "dfrotz"
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(built), str(dest))
    os.chmod(str(dest), 0o755)
    print(f"  Copied dfrotz to {dest}")
    return str(dest)


def setup_windows() -> str | None:
    """Windows: check for bundled binary."""
    exe = BIN_DIR / "windows" / "dfrotz.exe"
    if exe.exists():
        print(f"  Found bundled dfrotz at {exe}")
        return str(exe)

    # Check module root (legacy location)
    legacy = MODULE_ROOT / "dfrotz.exe"
    if legacy.exists():
        print(f"  Found dfrotz at legacy location {legacy}")
        return str(legacy)

    # Check PATH
    found = shutil.which("dfrotz")
    if found:
        print(f"  Found dfrotz on PATH: {found}")
        return found

    print("  ERROR: bin/windows/dfrotz.exe is missing.")
    print("  This file should have been included with the repository.")
    print("  Re-clone the repo or download dfrotz.exe from:")
    print("    https://davidgriffith.gitlab.io/frotz/")
    print(f"  and place it at: {exe}")
    return None


def setup_macos() -> str | None:
    """macOS: try brew, then compile from source."""
    # Check if already available
    found = shutil.which("dfrotz")
    if found:
        print(f"  dfrotz already available: {found}")
        return found

    local = BIN_DIR / "dfrotz"
    if local.exists():
        print(f"  Found dfrotz at {local}")
        return str(local)

    # Try Homebrew
    if shutil.which("brew"):
        print("\n  Homebrew detected. Installing frotz...")
        if _ask_yn("  Install frotz via Homebrew?"):
            result = _run(["brew", "install", "frotz"])
            if result.returncode == 0:
                found = shutil.which("dfrotz")
                if found:
                    return found
                # brew frotz may install as 'frotz' not 'dfrotz'
                found = shutil.which("frotz")
                if found:
                    print(f"  Note: installed as 'frotz' (not 'dfrotz'): {found}")
                    return found
            print("  Homebrew install failed, trying compile from source...")
    else:
        print("  Homebrew not found, trying compile from source...")

    # Compile from source
    if _ask_yn("  Compile dfrotz from source?"):
        return _compile_from_source()

    return None


def setup_linux() -> str | None:
    """Linux: try package manager, then compile from source."""
    # Check if already available
    found = shutil.which("dfrotz")
    if found:
        print(f"  dfrotz already available: {found}")
        return found

    local = BIN_DIR / "dfrotz"
    if local.exists():
        print(f"  Found dfrotz at {local}")
        return str(local)

    installed = False

    # Try apt
    if shutil.which("apt-get"):
        if _ask_yn("  Install frotz via apt? (requires sudo)"):
            result = _run(["sudo", "apt-get", "install", "-y", "frotz"])
            installed = result.returncode == 0

    # Try dnf
    elif shutil.which("dnf"):
        if _ask_yn("  Install frotz via dnf? (requires sudo)"):
            result = _run(["sudo", "dnf", "install", "-y", "frotz"])
            installed = result.returncode == 0

    # Try pacman
    elif shutil.which("pacman"):
        if _ask_yn("  Install frotz via pacman? (requires sudo)"):
            result = _run(["sudo", "pacman", "-S", "--noconfirm", "frotz"])
            installed = result.returncode == 0

    if installed:
        found = shutil.which("dfrotz") or shutil.which("frotz")
        if found:
            return found

    # Compile from source
    if not installed:
        print("  No supported package manager found or install skipped.")
    if _ask_yn("  Compile dfrotz from source?"):
        return _compile_from_source()

    return None


def main():
    print("\n========================================")
    print("  dfrotz Setup")
    print("========================================\n")

    system = platform.system()
    print(f"  Platform: {system}\n")

    if system == "Windows":
        path = setup_windows()
    elif system == "Darwin":
        path = setup_macos()
    elif system == "Linux":
        path = setup_linux()
    else:
        print(f"  Unsupported platform: {system}")
        print("  You'll need to install dfrotz manually.")
        print("  See: https://davidgriffith.gitlab.io/frotz/")
        sys.exit(1)

    if not path:
        print("\n  dfrotz setup failed.")
        print("  See https://davidgriffith.gitlab.io/frotz/ for manual install.\n")
        sys.exit(1)

    if _verify_dfrotz(path):
        print(f"\n  dfrotz is ready: {path}")
    else:
        print(f"\n  Warning: dfrotz was found at {path} but could not be verified.")
        print("  It may still work. Try running a game to test.")

    print("  Setup complete.\n")


if __name__ == "__main__":
    main()
