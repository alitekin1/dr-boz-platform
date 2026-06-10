import os
import signal
import subprocess

def kill_processes():
    # Find all python processes
    cmd = ["ps", "aux"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "python" in line and ("bot_watcher.py" in line or "uvicorn_watcher.py" in line or "app.bot" in line or "uvicorn" in line):
            parts = line.split()
            pid = int(parts[1])
            if pid != os.getpid():
                print(f"Killing PID {pid}: {line[:100]}")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

if __name__ == "__main__":
    kill_processes()
