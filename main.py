"""RSS Sentinel - Network Latency Controller.

This is the main entry point for the application.
It routes execution to either the GUI (Dashboard) or the Daemon (System Tray).
"""

import sys
import os
import traceback
import argparse

# Use the same logic as src.config for paths
def get_app_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_app_path()
os.chdir(BASE_DIR)
DEBUG_FILE = os.path.join(BASE_DIR, "debug_start.txt")
ERROR_FILE = os.path.join(BASE_DIR, "error.log")
TRACE_FILE = os.path.join(BASE_DIR, "debug_trace.txt")

try:
    with open(DEBUG_FILE, "w") as f:
        f.write(f"Startup... (Frozen: {getattr(sys, 'frozen', False)})\n")
        f.write(f"Executable: {sys.executable}\n")
        f.write(f"Base Dir: {BASE_DIR}\n")
        if hasattr(sys, '_MEIPASS'):
            f.write(f"MEIPASS: {sys._MEIPASS}\n")
except PermissionError:
    pass

# --- LOGGING SETUP ---
# Redirect stderr to error.log to capture crashes
try:
    sys.stderr = open(ERROR_FILE, "a", encoding="utf-8")
except PermissionError:
    pass

def log_crash(msg):
    """Writes a crash message to the log file."""
    try:
        with open(ERROR_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[CRASH] {msg}\n")
    except Exception:
        pass

def main():
    try:
        with open(TRACE_FILE, "a") as f:
            f.write("Main: Start\n")
            
        parser = argparse.ArgumentParser(description="RSS Sentinel Controller")
        parser.add_argument('--tray', action='store_true', help='Run in background (System Tray)')
        parser.add_argument('--gui', action='store_true', help='Run the Configuration Dashboard')
        
        args = parser.parse_args()

        # In v3.0 Unified Architecture, we always launch the GUI entry point.
        # The GUI module handles the tray thread and autopilot internally.
        # Ideally, we would pass 'start_minimized=True' if args.tray is set,
        # but Flet's current architecture makes starting purely hidden tricky.
        # The user will see the window pop up and can close it to tray.
        with open(TRACE_FILE, "a") as f:
            f.write("Main: Importing GUI\n")
            
        from src.gui import run_gui
        
        with open(TRACE_FILE, "a") as f:
            f.write("Main: Imported GUI. Calling run_gui\n")
            
        run_gui(start_minimized=args.tray)
        
        with open(TRACE_FILE, "a") as f:
            f.write("Main: run_gui returned (Unexpected)\n")
            
    except ImportError as e:
        log_crash(f"Dependency Error: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        log_crash(f"Runtime Error: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
