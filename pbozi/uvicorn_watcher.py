import subprocess
import time
import sys
import os

def run_server():
    print("Starting uvicorn watcher...")
    while True:
        print("Launching uvicorn...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        activate_script = os.path.join(base_dir, "backend/venv/bin/activate")
        command = f"source {activate_script} && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload"
        
        try:
            # Run uvicorn via bash
            process = subprocess.Popen(
                ["/usr/bin/bash", "-c", command],
                cwd=os.path.join(base_dir, "backend"),
                stdout=open("backend_persistent.log", "a"),
                stderr=subprocess.STDOUT,
            )
            process.wait()
            print(f"Uvicorn exited with code {process.returncode}. Restarting in 5 seconds...")
        except Exception as e:
            print(f"Error launching uvicorn: {e}. Restarting in 10 seconds...")
            time.sleep(5)
        
        time.sleep(5)

if __name__ == "__main__":
    run_server()
