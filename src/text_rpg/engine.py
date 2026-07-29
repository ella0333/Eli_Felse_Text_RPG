"""Z-machine game engine - wraps dfrotz in a subprocess.

All interaction with the game happens through this class. The LLM never touches
the process directly; it only receives text output and its commands are validated
before being forwarded.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


def _find_dfrotz(module_root: Path, config_path: Optional[str] = None) -> str:
    """Locate dfrotz binary.

    Priority: config > bin/ directory > module root (legacy) > system PATH.
    """
    if config_path and Path(config_path).exists():
        return config_path

    # Check bin/ directory (new standard location)
    if platform.system() == "Windows":
        bundled = module_root / "bin" / "windows" / "dfrotz.exe"
    else:
        bundled = module_root / "bin" / "dfrotz"
    if bundled.exists():
        return str(bundled)

    # Check module root (legacy compatibility)
    if platform.system() == "Windows":
        local = module_root / "dfrotz.exe"
    else:
        local = module_root / "dfrotz"
    if local.exists():
        return str(local)

    # Check system PATH
    found = shutil.which("dfrotz")
    if found:
        return found

    raise FileNotFoundError(
        "dfrotz not found. Run 'python setup_dfrotz.py' to install it, "
        "or set dfrotz_path in your config. See README for details."
    )


class TextRPGEngine:
    """Manages a single dfrotz subprocess for one game session."""

    def __init__(self, game_path: str, save_dir: Path, dfrotz_path: str):
        self.game_path = game_path
        self.save_dir = save_dir
        self.dfrotz_path = dfrotz_path
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.process: Optional[subprocess.Popen] = None
        self.last_score: Optional[int] = None
        self.last_moves: Optional[int] = None

    # ── Save file management ──────────────────────────────────────────────

    def get_save_files(self) -> List[Dict]:
        """Get all save files with metadata, newest first."""
        saves = []
        for file in sorted(self.save_dir.glob("*.sav"), reverse=True):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            meta_file = file.with_suffix(".meta")
            meta = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            if not meta:
                meta = {
                    "date": mtime.strftime("%m/%d/%Y"),
                    "time": mtime.strftime("%I:%M %p"),
                    "score": None,
                    "moves": None,
                }
            saves.append({
                "filename": file.name,
                "filepath": file,
                "date": meta.get("date", "Unknown"),
                "time": meta.get("time", "Unknown"),
                "score": meta.get("score"),
                "moves": meta.get("moves"),
                "mtime": mtime,
            })
        return saves

    def has_save_files(self) -> bool:
        return any(self.save_dir.glob("*.sav"))

    def _save_metadata(self, save_filename: str, score: int = None, moves: int = None):
        now = datetime.now()
        meta = {
            "date": now.strftime("%m/%d/%Y"),
            "time": now.strftime("%I:%M %p"),
            "score": score,
            "moves": moves,
        }
        meta_file = self.save_dir / save_filename.replace(".sav", ".meta")
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _generate_save_filename(self, game_key: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{game_key}_{timestamp}.sav"

    # ── Process lifecycle ─────────────────────────────────────────────────

    async def start(self, restore_filename: Optional[str] = None) -> str:
        """Start dfrotz and return initial output. Optionally restore a save."""
        cmd = [self.dfrotz_path, "-p", "-m", self.game_path]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            cwd=str(self.save_dir),
        )
        await asyncio.sleep(0.5)

        if self.process.poll() is not None:
            stderr = ""
            try:
                stderr = self.process.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return f"[ERROR: dfrotz exited immediately]\n{stderr}"

        output = await self._read_output(timeout=3.0)

        if restore_filename:
            restore_out = await self._do_restore(restore_filename)
            if "ok" in restore_out.lower() or "restored" in restore_out.lower():
                look_out = await self.send_command("look")
                return look_out + f"\n[Restored from save: {restore_filename}]"
            return output + f"\n[Starting new game - restore of {restore_filename} failed]"

        return output

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    async def send_command(self, command: str) -> str:
        """Send a parser command and return game response."""
        if not self.is_running():
            return "[Game not running]"
        try:
            self.process.stdin.write((command + "\n").encode("utf-8"))
            self.process.stdin.flush()
            await asyncio.sleep(0.2)
            output = await self._read_output(timeout=3.0)
            return output if output else "[No response from game]"
        except Exception as e:
            return f"[Error sending command: {e}]"

    async def save_game(self, game_key: str) -> str:
        """Save the current game state."""
        if not self.is_running():
            return "[Game not running - cannot save]"
        try:
            await asyncio.sleep(0.2)
            _ = await self._read_output(timeout=0.5)

            self.process.stdin.write(b"\n")
            self.process.stdin.flush()
            await asyncio.sleep(0.3)
            _ = await self._read_output(timeout=1.0)

            score, moves = await self._get_score_and_moves()

            await asyncio.sleep(0.3)
            _ = await self._read_output(timeout=0.5)

            save_filename = self._generate_save_filename(game_key)

            self.process.stdin.write(b"SAVE\n")
            self.process.stdin.flush()
            await asyncio.sleep(0.5)
            _ = await self._read_output(timeout=2.0)

            self.process.stdin.write((save_filename + "\n").encode("utf-8"))
            self.process.stdin.flush()
            await asyncio.sleep(0.5)

            save_output = await self._read_output(timeout=2.0)
            save_lower = save_output.lower()

            if "ok" in save_lower or "saved" in save_lower:
                self._save_metadata(save_filename, score, moves)
                return f"[Game saved: {save_filename}]"

            # Check if file was created anyway
            if (self.save_dir / save_filename).exists():
                self._save_metadata(save_filename, score, moves)
                return f"[Game saved: {save_filename}]"

            return f"[Save may have failed: {save_output}]"
        except Exception as e:
            return f"[Error saving game: {e}]"

    async def save_and_quit(self, game_key: str) -> None:
        """Save and terminate the game process."""
        if self.is_running():
            await self.save_game(game_key)
            try:
                self.process.stdin.write(b"quit\n")
                self.process.stdin.flush()
                await asyncio.sleep(0.3)
                quit_output = await self._read_output(timeout=1.0)
                if "?" in quit_output or "sure" in quit_output.lower():
                    self.process.stdin.write(b"y\n")
                    self.process.stdin.flush()
                    await asyncio.sleep(0.3)
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except Exception:
                    self.process.kill()
            except Exception:
                if self.process:
                    try:
                        self.process.terminate()
                    except Exception:
                        pass
            finally:
                self.process = None

    async def quit_no_save(self) -> None:
        """Terminate without saving."""
        if self.is_running():
            try:
                self.process.stdin.write(b"quit\n")
                self.process.stdin.flush()
                await asyncio.sleep(0.3)
                quit_output = await self._read_output(timeout=1.0)
                if "?" in quit_output or "sure" in quit_output.lower():
                    self.process.stdin.write(b"y\n")
                    self.process.stdin.flush()
                    await asyncio.sleep(0.3)
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except Exception:
                    self.process.kill()
            except Exception:
                if self.process:
                    try:
                        self.process.terminate()
                    except Exception:
                        pass
            finally:
                self.process = None

    # ── Restore ───────────────────────────────────────────────────────────

    async def _do_restore(self, save_filename: str) -> str:
        if not self.is_running():
            return "[Game not running]"
        try:
            self.process.stdin.write(b"restore\n")
            self.process.stdin.flush()
            await asyncio.sleep(0.3)
            _ = await self._read_output(timeout=2.0)
            self.process.stdin.write((save_filename + "\n").encode("utf-8"))
            self.process.stdin.flush()
            await asyncio.sleep(0.3)
            return await self._read_output(timeout=2.0)
        except Exception as e:
            return f"[Restore error: {e}]"

    async def restore_game(self, save_filename: str) -> str:
        """Restore a save mid-session."""
        if not self.is_running():
            return "[Game not running - cannot restore]"
        result = await self._do_restore(save_filename)
        if "ok" in result.lower() or "restored" in result.lower():
            look_out = await self.send_command("look")
            return f"[Restored: {save_filename}]\n\n{look_out}"
        return f"[Restore may have failed: {result}]"

    # ── Score extraction ──────────────────────────────────────────────────

    def parse_score_from_output(self, text: str):
        """Extract score/moves from game output and store as last known."""
        score_match = re.search(r"score[^\d]*(\d+)", text.lower())
        moves_match = re.search(r"(\d+)\s*(?:move|turn)", text.lower())
        if score_match:
            self.last_score = int(score_match.group(1))
        if moves_match:
            self.last_moves = int(moves_match.group(1))

    async def _get_score_and_moves(self) -> tuple:
        score, moves = None, None
        try:
            score_output = await self.send_command("score")
            score_match = re.search(r"score[^\d]*(\d+)", score_output.lower())
            moves_match = re.search(r"(\d+)\s*(?:move|turn)", score_output.lower())
            if score_match:
                score = int(score_match.group(1))
            if moves_match:
                moves = int(moves_match.group(1))
        except Exception:
            pass
        if score is not None:
            self.last_score = score
        if moves is not None:
            self.last_moves = moves
        return score or self.last_score, moves or self.last_moves

    # ── Non-blocking pipe reading ─────────────────────────────────────────

    async def _read_output(self, timeout: float = 3.0) -> str:
        if not self.process:
            return ""
        output_chunks = []
        start = asyncio.get_event_loop().time()
        last_read = start
        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed > timeout:
                    break
                if self.process.poll() is not None:
                    try:
                        remaining = self.process.stdout.read()
                        if remaining:
                            output_chunks.append(remaining.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                    break
                available = self._peek_pipe()
                if available > 0:
                    try:
                        data = self.process.stdout.read(available)
                        if data:
                            output_chunks.append(data.decode("utf-8", errors="replace"))
                            last_read = asyncio.get_event_loop().time()
                            if "".join(output_chunks).rstrip().endswith(">"):
                                break
                    except Exception:
                        break
                else:
                    if output_chunks and (asyncio.get_event_loop().time() - last_read) > 0.5:
                        break
                    await asyncio.sleep(0.05)
        except Exception as e:
            output_chunks.append(f"[Read error: {e}]")
        return "".join(output_chunks).strip()

    def _peek_pipe(self) -> int:
        """Check bytes available on stdout without blocking."""
        if platform.system() == "Windows":
            try:
                import ctypes
                import msvcrt
                handle = msvcrt.get_osfhandle(self.process.stdout.fileno())
                available = ctypes.c_ulong()
                ctypes.windll.kernel32.PeekNamedPipe(
                    handle, None, 0, None, ctypes.byref(available), None
                )
                return available.value
            except Exception:
                return 0
        else:
            # Unix: use select
            import select
            readable, _, _ = select.select([self.process.stdout], [], [], 0)
            if readable:
                return 4096  # read up to 4k
            return 0
