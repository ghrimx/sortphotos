import sys
import shutil
import threading
import time


class ProgressBar:
    def __init__(
        self,
        total,
        title="",
        bar_width=40,
        show_percent=True,
        stream=sys.stdout,
        color="\x1b[0;32m",  # green
    ):
        self.total = max(total, 1)
        self.title = title
        self.bar_width = bar_width
        self.show_percent = show_percent
        self.stream = stream
        self.color = color
        self.enabled = stream.isatty()
        self._last_step = -1

        self._blocks = ["█", "▏", "▎", "▍", "▌", "▋", "▊", "█"]

    def update(self, step):
        if not self.enabled:
            return

        step = min(step, self.total)
        if step == self._last_step:
            return

        self._last_step = step

        perc = step / self.total
        max_ticks = self.bar_width * 8
        num_ticks = int(round(perc * max_ticks))

        full = num_ticks // 8
        part = num_ticks % 8

        bar = self._blocks[0] * full
        if part:
            bar += self._blocks[part]
        bar += "▒" * (self.bar_width - len(bar))

        prefix = f"{self.title}: " if self.title else ""
        disp = f"{prefix}{self.color}{bar}\x1b[0m"

        if self.show_percent:
            disp += f" {perc * 100:6.2f} %"

        self.stream.write(f"\r\x1b[2K{disp}")
        self.stream.flush()

    def finish(self):
        if not self.enabled:
            return
        self.stream.write("\n")
        self.stream.flush()


class Spinner:
    def __init__(
        self,
        init_message="",
        message="Working",
        delay=0.1,
        stream=sys.stdout,
    ):
        self.init_message = init_message
        self._message = message
        self.delay = delay
        self.stream = stream
        self.frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.running = False
        self.enabled = stream.isatty()
        self._lock = threading.Lock()
        self._thread = None

    def __enter__(self):
        if self.enabled and self.init_message:
            self.stream.write(self.init_message + "\n")
            self.stream.flush()
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop(success=exc_type is None)

    def start(self):
        if not self.enabled:
            return
        self.running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def update(self, message):
        with self._lock:
            self._message = message

    def stop(self, success=True):
        if not self.enabled:
            return

        self.running = False
        self._thread.join()

        symbol = "✔" if success else "✖"
        self.stream.write(f"\r\x1b[2K{symbol} {self._message}\n")
        self.stream.flush()

    def _spin(self):
        i = 0
        while self.running:
            frame = self.frames[i % len(self.frames)]
            with self._lock:
                msg = self._message
            self.stream.write(f"\r\x1b[2K{frame} {msg}")
            self.stream.flush()
            time.sleep(self.delay)
            i += 1
