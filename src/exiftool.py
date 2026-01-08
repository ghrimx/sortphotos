import subprocess
import os
import json
from pathlib import Path


class ExifTool(object):
    sentinel = "{ready}"

    def __init__(self, executable: str|Path):
        self.executable = executable

    def __enter__(self):
        try:
            self.process = subprocess.Popen(
                ["perl", self.executable, "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start ExifTool: {e}")

        if self.process.poll() is not None:
            raise RuntimeError(
                f"ExifTool exited immediately with code {self.process.returncode}"
            )

        if not self.process.stdin or not self.process.stdout:
            raise RuntimeError("ExifTool pipes not initialized")
        
        if not self._health_check():
            raise RuntimeError("ExifTool failed health check")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.process.stdin.write(b'-stay_open\nFalse\n')
            self.process.stdin.flush()
        except Exception:
            pass

    def _health_check(self) -> bool:
        try:
            self.process.stdin.write(b"-ver\n-execute\n")
            self.process.stdin.flush()

            output = ""
            while self.sentinel not in output:
                chunk = self.process.stdout.read(1024)
                if not chunk:
                    break
                output += chunk.decode("utf-8", errors="replace")

            return self.sentinel in output
        except Exception:
            return False

    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write("\n".join(args).encode("utf-8"))
        self.process.stdin.flush()

        output = ""
        fd = self.process.stdout.fileno()

        while not output.rstrip().endswith(self.sentinel):
            chunk = os.read(fd, 4096)

            if not chunk:
                break
            output += chunk.decode("utf-8", errors="replace")

        return output.replace(self.sentinel, "").strip()

    def get_metadata(self, *args):
        raw = self.execute(*args)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid ExifTool output")