import sys
import time
import threading
import re
import subprocess
import os


def clear_line():
    """Clear current terminal line."""
    sys.stdout.write("\r\033[2K")
    sys.stdout.flush()


class Spinner:
    """Spinner with message."""

    FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, msg="Working", color="\033[1;36m"):
        self.msg = msg
        self.color = color
        self.rst = "\033[0m"
        self.running = False
        self.thread = None
        self.frame = 0

    def _animate(self):
        while self.running:
            f = self.FRAMES[self.frame % len(self.FRAMES)]
            clear_line()
            sys.stdout.write(f"      {self.color}{f}{self.rst} {self.msg}")
            sys.stdout.flush()
            self.frame += 1
            time.sleep(0.1)

    def start(self, msg=None):
        if msg:
            self.msg = msg
        self.running = True
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def update_msg(self, msg):
        self.msg = msg

    def stop(self, final_msg=None):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        clear_line()
        if final_msg:
            print(f"      \033[1;32m[*]{self.rst} {final_msg}")
        else:
            print()


class ProgressBar:
    """Progress bar with percentage and detail."""

    def __init__(self, total=100, label="Progress", width=35):
        self.total = total
        self.current = 0
        self.label = label
        self.width = width
        self.rst = "\033[0m"
        self.grn = "\033[1;32m"
        self.cyn = "\033[1;36m"
        self.gry = "\033[90m"
        self.bld = "\033[1m"

    def update(self, current, detail=""):
        self.current = min(current, self.total)
        pct = int((self.current / self.total) * 100) if self.total > 0 else 0
        filled = int(self.width * self.current / self.total) if self.total > 0 else 0
        empty = self.width - filled
        bar = f"{self.grn}{'█' * filled}{self.gry}{'░' * empty}{self.rst}"
        detail_str = f" {self.gry}{detail}{self.rst}" if detail else ""
        clear_line()
        sys.stdout.write(
            f"      {self.cyn}{self.bld}{pct:3d}%{self.rst} "
            f"[{bar}] {self.label}{detail_str}"
        )
        sys.stdout.flush()

    def increment(self, step=1, detail=""):
        self.update(self.current + step, detail)

    def finish(self, msg="Done"):
        self.update(self.total)
        clear_line()
        print(f"      \033[1;32m[*]{self.rst} {msg}")


class DownloadProgress:
    """Track download progress with speed calculation."""

    def __init__(self, label="Downloading"):
        self.label = label
        self.start_time = None
        self.last_time = None
        self.last_bytes = 0
        self.total_bytes = 0
        self.current_bytes = 0
        self.rst = "\033[0m"
        self.grn = "\033[1;32m"
        self.cyn = "\033[1;36m"
        self.gry = "\033[90m"
        self.bld = "\033[1m"
        self.bar = ProgressBar(total=100, label=label, width=30)

    def start(self, total_bytes=0):
        self.start_time = time.time()
        self.last_time = self.start_time
        self.total_bytes = total_bytes
        self.current_bytes = 0
        self.bar.update(0, "starting")

    def update(self, current_bytes, total_bytes=0):
        now = time.time()
        self.current_bytes = current_bytes
        if total_bytes > 0:
            self.total_bytes = total_bytes

        elapsed = now - self.last_time
        if elapsed >= 0.3:
            speed = (current_bytes - self.last_bytes) / elapsed if elapsed > 0 else 0
            self.last_bytes = current_bytes
            self.last_time = now

            speed_str = self._format_speed(speed)
            total_str = self._format_size(self.total_bytes) if self.total_bytes > 0 else "?"
            current_str = self._format_size(current_bytes)

            if self.total_bytes > 0:
                pct = int((current_bytes / self.total_bytes) * 100)
                self.bar.update(pct, f"{current_str}/{total_str} {speed_str}")
            else:
                self.bar.current = 0
                clear_line()
                sys.stdout.write(
                    f"      {self.cyn}{self.bld}---{self.rst} "
                    f"[{self.gry}???{self.rst}] {self.label} "
                    f"{self.gry}{current_str} {speed_str}{self.rst}"
                )
                sys.stdout.flush()

    def finish(self, msg=None):
        total_elapsed = time.time() - self.start_time if self.start_time else 0
        avg_speed = self.current_bytes / total_elapsed if total_elapsed > 0 else 0
        if not msg:
            msg = f"{self._format_size(self.current_bytes)} in {total_elapsed:.1f}s ({self._format_speed(avg_speed)})"
        self.bar.finish(msg)

    @staticmethod
    def _format_size(b):
        if b < 1024:
            return f"{b}B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f}KB"
        else:
            return f"{b / (1024 * 1024):.1f}MB"

    @staticmethod
    def _format_speed(bps):
        if bps < 1024:
            return f"{bps:.0f}B/s"
        elif bps < 1024 * 1024:
            return f"{bps / 1024:.1f}KB/s"
        else:
            return f"{bps / (1024 * 1024):.1f}MB/s"


def parse_compile_line(line):
    """Parse arduino-cli verbose output line.
    Returns (event_type, detail)."""
    line = line.strip()
    if not line:
        return None, ""

    # Compiling a source file
    if re.search(r'Compiling\s+', line) and re.search(r'\.(cpp|c|ino)', line):
        m = re.search(r'[/\\]([^/\\]+\.(?:cpp|c|ino))', line)
        return "compiling", m.group(1) if m else "file"

    # Compiling library
    if line.startswith("Compiling library"):
        m = re.search(r'"(.+?)"', line)
        return "library", m.group(1) if m else "lib"

    # Compiling sketch
    if "Compiling sketch" in line:
        return "sketch", "sketch"

    # Linking / archiving
    if re.search(r'(Linking|Archiving|Generating)', line):
        return "linking", ""

    # Memory usage percentage (final summary)
    m = re.search(r'used\s+[\d,]+\s*/\s*[\d,]+\s+bytes\s*\((\d+)%\)', line)
    if m:
        return "progress", int(m.group(1))

    # Exit status error
    if line.startswith("exit status"):
        return "error", line

    # Error line
    if "error:" in line.lower():
        return "error", line

    # Warning
    if "warning:" in line.lower():
        return "warning", line

    # Cached files (count as compiled)
    if "Using cached" in line:
        return "cached", ""

    # Detecting / prototypes / other stages
    if "Detecting libraries" in line:
        return "stage", "Detecting libraries"
    if "Generating function prototypes" in line:
        return "stage", "Generating prototypes"

    return None, ""


class CompileProgress:
    """Track real compilation progress with bar."""

    def __init__(self):
        self.bar = ProgressBar(total=100, label="Compiling", width=35)
        self.compiled = 0
        self.total_size = 0
        self.mem_pct = 0
        self.current_stage = ""
        self.errors = []
        self.linked = False

    def _format_size(self, b):
        if b < 1024:
            return f"{b}B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f}KB"
        else:
            return f"{b / (1024 * 1024):.1f}MB"

    def feed_line(self, line):
        event, detail = parse_compile_line(line)
        if event is None:
            return True

        if event == "stage":
            self.current_stage = detail
            if detail == "Detecting libraries":
                self.bar.update(5, "detecting")
            elif detail == "Generating prototypes":
                self.bar.update(8, "generating")

        elif event == "sketch":
            self.bar.update(10, "sketch")

        elif event == "library":
            self.compiled += 1
            pct = min(10 + self.compiled * 2, 65)
            self.bar.update(pct, f"lib: {detail}")

        elif event == "compiling":
            self.compiled += 1
            pct = min(10 + self.compiled * 2, 65)
            size_str = f" | {self._format_size(self.total_size)}" if self.total_size > 0 else ""
            self.bar.update(pct, f"{self.compiled} files{size_str}")

        elif event == "cached":
            self.compiled += 1
            pct = min(10 + self.compiled * 2, 65)
            self.bar.update(pct, f"{self.compiled} files (cached)")

        elif event == "linking":
            self.linked = True
            self.bar.update(70, "linking")

        elif event == "progress":
            self.mem_pct = detail
            pct = 75 + int(detail * 0.25)
            self.bar.update(pct, f"memory: {detail}%")

        elif event == "error":
            self.errors.append(detail)
            return False

        return True

    def finish(self, success, elapsed=0):
        if success:
            self.bar.update(100, f"{self.compiled} files")
            size_str = f" | {self._format_size(self.total_size)}" if self.total_size > 0 else ""
            msg = f"Done in {elapsed:.1f}s | {self.compiled} files{size_str}"
            if self.mem_pct:
                msg += f" | RAM: {self.mem_pct}%"
            self.bar.finish(msg)
        else:
            self.bar.finish("Failed")


def run_compile_with_progress(cmd, timeout=300, source_dir=None):
    """Run arduino-cli compile with real progress tracking."""
    progress = CompileProgress()

    # Calculate total source size
    if source_dir and os.path.isdir(source_dir):
        total = 0
        for root, dirs, files in os.walk(source_dir):
            for f in files:
                if f.endswith(('.ino', '.cpp', '.c', '.h')):
                    total += os.path.getsize(os.path.join(root, f))
        progress.total_size = total

    progress.bar.update(0, "starting")

    start = time.time()

    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in proc.stdout:
            progress.feed_line(line.rstrip())

        proc.wait(timeout=timeout)
        elapsed = time.time() - start

        success = proc.returncode == 0
        progress.finish(success, elapsed)

        return success, "", "\n".join(progress.errors), elapsed

    except subprocess.TimeoutExpired:
        proc.kill()
        elapsed = time.time() - start
        progress.finish(False, elapsed)
        return False, "", f"Timed out after {timeout}s", elapsed
    except Exception as e:
        elapsed = time.time() - start
        progress.finish(False, elapsed)
        return False, "", str(e), elapsed


def download_with_progress(url, dest, label="Downloading"):
    """Download a file with progress display using curl."""
    progress = DownloadProgress(label)
    progress.start()

    proc = subprocess.Popen(
        ['curl', '-fsSL', '-o', dest, '-w', '%{size_download}', url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        while proc.poll() is None:
            if os.path.isfile(dest):
                size = os.path.getsize(dest)
                progress.update(size)
            time.sleep(0.3)

        proc.wait()
        if os.path.isfile(dest):
            final_size = os.path.getsize(dest)
            progress.update(final_size)

        success = proc.returncode == 0
        if success:
            progress.finish()
        else:
            progress.bar.finish("Failed")
        return success
    except Exception:
        proc.kill()
        progress.bar.finish("Failed")
        return False
    finally:
        monitor.kill()
