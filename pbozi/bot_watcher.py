import subprocess
import time
import sys
import os

def run_bot():
    print("Starting bot watcher...")
    while True:
        print("Launching bot...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        activate_script = os.path.join(base_dir, "backend/venv/bin/activate")
        # Use relative paths for logs to be safer
        command = f"export PYTHONPATH=./backend:$PYTHONPATH && source {activate_script} && python3 -u -m app.bot"
        
        try:
            process = subprocess.Popen(
                ["/usr/bin/bash", "-c", command],
                cwd=os.path.join(base_dir, "backend"),
                stdout=open("bot_persistent_new.log", "a"),
                stderr=subprocess.STDOUT,
            )
            process.wait()
            print(f"Bot exited with code {process.returncode}. Restarting in 5 seconds...")
        except Exception as e:
            print(f"Error launching bot: {e}. Restarting in 10 seconds...")
            time.sleep(5)
        
        time.sleep(5)

if __name__ == "__main__":
    run_bot()
