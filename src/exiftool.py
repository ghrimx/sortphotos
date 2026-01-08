import subprocess
import os
import sys
import json




class ExifTool(object):
    sentinel = "{ready}"

    def __init__(self, executable: str):
        self.executable = executable

    def __enter__(self):
        self.process = subprocess.Popen(
            ['perl', self.executable, '-stay_open', 'True', '-@', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  
            bufsize=0
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.process.stdin.write(b'-stay_open\nFalse\n')
            self.process.stdin.flush()
        except Exception:
            pass

    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write("\n".join(args).encode("utf-8"))
        self.process.stdin.flush()

        output = ""
        fd = self.process.stdout.fileno()

        while not output.rstrip().endswith(self.sentinel):
            chunk = os.read(fd, 4096)
            if self.verbose:
                sys.stdout.write(chunk.decode('utf-8'))
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