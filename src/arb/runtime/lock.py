import os
import sys
import logging

def is_pid_running(pid: int) -> bool:
    if pid <= 0: return False
    try:
        # On Windows, os.kill(pid, 0) checks for existence
        os.kill(pid, 0)
        return True
    except OSError:
        return False

class RunLock:
    def __init__(self, run_id: str, lock_dir: str = ".runlocks"):
        self.run_id = run_id
        self.lock_dir = lock_dir
        self.lock_path = os.path.join(lock_dir, f"{run_id}.lock")
        self.locked = False

    def acquire(self):
        os.makedirs(self.lock_dir, exist_ok=True)
        
        # Try to open with EXCLUSIVE creation
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            self.locked = True
            return True
        except FileExistsError:
            # Check if stale
            try:
                with open(self.lock_path, 'r') as f:
                    old_pid = int(f.read().strip())
                
                if not is_pid_running(old_pid):
                    logging.warning(f"Stale lock found for {self.run_id} (PID {old_pid} not running). Taking over.")
                    os.remove(self.lock_path)
                    return self.acquire()
                else:
                    logging.error(f"Run ID '{self.run_id}' is already active (PID {old_pid}).")
                    logging.error("If this is a mistake, use scripts/ps/kill_bot.ps1 or delete the lock file manually.")
                    return False
            except Exception as e:
                logging.error(f"Error checking existing lock: {e}")
                return False

    def release(self):
        if self.locked and os.path.exists(self.lock_path):
            try:
                os.remove(self.lock_path)
                self.locked = False
            except:
                pass
