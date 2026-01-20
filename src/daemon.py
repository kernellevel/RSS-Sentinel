"""Daemon Module.

This module runs the background service (RSS Sentinel).
It monitors active processes and switches RSS profiles accordingly.
"""

import threading
import time
import sys
import ctypes
import psutil
import pystray
from PIL import Image, ImageDraw

from src.core import KernelSurgeon
from src.config import ConfigManager

class RSSAutopilot:
    """Handles the automated profile switching logic with Hysteresis and Gap Finder."""
    
    def __init__(self, surgeon: KernelSurgeon, config_mgr: ConfigManager, on_status_update=None):
        self.surgeon = surgeon
        self.config_mgr = config_mgr
        self.on_status_update = on_status_update
        self.stop_event = threading.Event()
        self.current_mode = "UNKNOWN"
        
        # Hysteresis Logic
        self.hysteresis_timer = 0
        self.HYSTERESIS_DELAY = 60 # Seconds to wait before leaving Gaming Mode
        
        topo = self.surgeon.get_topology_info()
        self.p_cores = topo["physical"]
        self.l_procs = topo["logical"]
        self._calculate_presets()

    def _calculate_presets(self):
        """Pre-calculates optimal settings based on Gap Finder Strategy."""
        # 1. GAMING PRESET
        # Uses surgeon's Gap Finder to find the best contiguous clean cores
        base_core, calculated_queues = self.surgeon.calculate_best_gap()
        
        self.gaming_base = base_core
        self.gaming_max = calculated_queues # We match max processors to queue count
        self.gaming_queues = calculated_queues
        self.gaming_im = "Enabled" if self.p_cores <= 6 else "Disabled"
        
        # 2. DESKTOP PRESET
        self.desktop_base = 0
        self.desktop_max = self.l_procs
        self.desktop_queues = 4 if self.l_procs < 12 else 8
        self.desktop_im = "Enabled" 

    def stop(self): self.stop_event.set()

    def run_loop(self):
        while not self.stop_event.is_set():
            try:
                self.config_mgr._load()
                if self.config_mgr.get("manual_mode"):
                    if self.current_mode != "MANUAL":
                        if self.on_status_update: self.on_status_update("MANUAL OVERRIDE", "#3498db")
                        self.current_mode = "MANUAL"
                else:
                    # --- AUTO PILOT ---
                    is_game_active = False
                    games_set = {g.lower() for g in self.config_mgr.get("games_list")}
                    
                    for p in psutil.process_iter(['name', 'cpu_percent']):
                        try:
                            if p.info['name'] and p.info['name'].lower() in games_set:
                                if p.cpu_percent(interval=0.1) > 5.0:
                                    is_game_active = True
                                    break
                        except: continue

                    if is_game_active:
                        self.hysteresis_timer = self.HYSTERESIS_DELAY # Reset/Refill timer
                        if self.current_mode != "GAMING":
                            # Refresh presets in case polluted cores changed (rare but possible)
                            self._calculate_presets()
                            if self.surgeon.safe_apply_mode(self.gaming_base, self.gaming_max, "NUMAStatic", self.gaming_im, self.gaming_queues, "GAMING"):
                                self.current_mode = "GAMING"
                                if self.on_status_update: self.on_status_update(f"GAMING MODE ({self.gaming_queues}Q)", "#e74c3c")
                    else:
                        if self.current_mode == "GAMING":
                            if self.hysteresis_timer > 0:
                                self.hysteresis_timer -= 2
                            else:
                                # Timer expired, switch to Desktop
                                if self.surgeon.safe_apply_mode(self.desktop_base, self.desktop_max, "Closest", self.desktop_im, self.desktop_queues, "DESKTOP"):
                                    self.current_mode = "DESKTOP"
                                    if self.on_status_update: self.on_status_update("DESKTOP MODE (Throughput)", "#2ecc71")
                        elif self.current_mode != "DESKTOP":
                            if self.surgeon.safe_apply_mode(self.desktop_base, self.desktop_max, "Closest", self.desktop_im, self.desktop_queues, "DESKTOP"):
                                self.current_mode = "DESKTOP"
                                if self.on_status_update: self.on_status_update("DESKTOP MODE (Throughput)", "#2ecc71")

            except Exception as e: print(f"[Autopilot] Error: {e}")
            time.sleep(2.0)