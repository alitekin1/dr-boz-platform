import subprocess
import time
import sys
import os

def run_bot():
    print("Starting transactions bot watcher...")
    while True:
        print("Launching transactions bot...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        activate_script = os.path.join(base_dir, "backend/venv/bin/activate")
        command = f"export PYTHONPATH=./backend:$PYTHONPATH && source {activate_script} && python3 -u -m app.transactions_bot"
        
        try:
            process = subprocess.Popen(
                ["/usr/bin/bash", "-c", command],
                cwd=os.path.join(base_dir, "backend"),
                stdout=open("transactions_bot.log", "a"),
                stderr=subprocess.STDOUT,
            )
            process.wait()
            print(f"Transactions bot exited with code {process.returncode}. Restarting in 5 seconds...")
        except Exception as e:
            print(f"Error launching transactions bot: {e}. Restarting in 10 seconds...")
            time.sleep(5)
        
        time.sleep(5)

if __name__ == "__main__":
    run_bot()
