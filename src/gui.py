from src.config import TRACE_FILE, ERROR_FILE
import flet as ft
try:
    from flet import icons
except ImportError:
    from flet import Icons as icons
import time
import psutil
import math
import threading
import sys
import os
import pystray
from PIL import Image, ImageDraw

from src.config import ConfigManager
from src.core import KernelSurgeon
from src.daemon import RSSAutopilot 

# --- RELEASE CONSTANTS ---
COLOR_BG = "#0f0f0f"
COLOR_PANEL = "#1a1a1a"
COLOR_ACCENT = "#00ff41"  
COLOR_GAMING = "#ff3333"  
COLOR_DESKTOP = "#00aaff" 
COLOR_TEXT_DIM = "#666666"
FONT_MONO = "Consolas"

def create_tray_image(width: int, color: str = "#00ff41") -> Image.Image:
    image = Image.new('RGB', (width, width), (0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([width//4, width//4, 3*width//4, 3*width//4], outline=color, width=4)
    return image

class CpuCoreGrid(ft.Container):
    def __init__(self, physical_cores, logical_procs, base, max_p, polluted_indices=None):
        super().__init__()
        self.p_cores = physical_cores
        self.l_procs = logical_procs
        self.base = base
        self.max_p = max_p
        self.polluted_indices = set(polluted_indices) if polluted_indices else set()
        cols = math.ceil(math.sqrt(self.l_procs))
        self.grid = ft.GridView(runs_count=cols, spacing=8, run_spacing=8, padding=10, expand=True)
        self.content = self.grid
        self.bgcolor = "#111111"
        self.border_radius = 12
        self.border = ft.border.all(1, "#333333")
        self.expand = True 
        self.build_grid()

    def update_config(self, base, max_p):
        self.base = int(base)
        self.max_p = int(max_p)
        self.build_grid()
        self.update()

    def build_grid(self):
        self.grid.controls.clear()
        end = self.base + self.max_p
        for i in range(self.l_procs):
            is_active = self.base <= i < end
            is_polluted = i in self.polluted_indices
            bg_color = "#222222"
            border_color = "transparent"
            if is_active:
                bg_color = COLOR_ACCENT if i < self.p_cores else "#008f24"
            if is_polluted:
                border_color = "#ff0000"
                if not is_active: bg_color = "#331111"
            self.grid.controls.append(ft.Container(content=ft.Text(f"{i}", size=12, weight="bold", color="white" if is_active else "#555555"), bgcolor=bg_color, border=ft.border.all(2, border_color) if border_color != "transparent" else None, border_radius=6, alignment=ft.alignment.center))

class ConsoleLog(ft.Container):
    def __init__(self):
        super().__init__()
        self.log_view = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        self.content = self.log_view
        self.bgcolor = "#050505"
        self.border = ft.border.all(1, "#222222")
        self.border_radius = 8
        self.padding = 10
        self.height = 180
    
    def log(self, message, color="white"):
        ts = time.strftime("%H:%M:%S")
        self.log_view.controls.append(ft.Text(f"[{ts}] {message}", font_family=FONT_MONO, size=11, color=color))
        if len(self.log_view.controls) > 100: self.log_view.controls.pop(0)
        try: self.update()
        except: pass

def main_gui(page: ft.Page, start_minimized=False):
    config = ConfigManager()
    surgeon = KernelSurgeon()
    topo = surgeon.get_topology_info()

    def update_ui_from_state(base, max_p, manual_active):
        """Syncs all UI elements with current settings."""
        sl_base.value = base
        sl_max.value = max_p
        lbl_base.value = f"Base Core: {base}"
        lbl_max.value = f"Core Range (Queues): {max_p}"
        c_controls.disabled = not manual_active
        c_controls.opacity = 1.0 if manual_active else 0.6
        cpu_grid.update_config(base, max_p)
        page.update()

    def on_autopilot_status(msg, color):
        console.log(f"Sentinel: {msg}", color)
        # If autopilot changed settings, reflect it on the grid (even if sliders are locked)
        if not sw_manual.value:
            # We don't have direct access to autopilot's current target here easily, 
            # but we can refresh the grid based on what the surgeon just applied.
            # In a real scenario, we might want to pass (base, max) in the callback.
            pass
        if tray_icon:
            tray_icon.title = f"RSS Sentinel: {msg}"
            tray_icon.icon = create_tray_image(64, color)

    def on_tray_exit(icon, item):
        autopilot.stop()
        icon.stop()
        page.window_destroy()
        sys.exit(0)
            
    def run_tray():
        nonlocal tray_icon
        menu = pystray.Menu(pystray.MenuItem("Restore Dashboard", lambda: (setattr(page, 'window_visible', True), page.update())), 
                            pystray.MenuItem("Exit Fully", on_tray_exit))
        tray_icon = pystray.Icon("RSS-Sentinel", create_tray_image(64), "RSS Sentinel Active", menu)
        tray_icon.run()

    try:
        page.title = "RSS SENTINEL PRO"
        page.window_width = 1000 
        page.window_height = 750
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = COLOR_BG
        page.padding = 25
        page.window_prevent_close = True
        page.window_visible = not start_minimized

        console = ConsoleLog()
        cpu_grid = CpuCoreGrid(topo["physical"], topo["logical"], config.get("manual_base"), config.get("manual_max"), polluted_indices=surgeon.polluted_cores)

        autopilot = RSSAutopilot(surgeon, config, on_autopilot_status)
        threading.Thread(target=autopilot.run_loop, daemon=True).start()

        tray_icon = None
        threading.Thread(target=run_tray, daemon=True).start()

        page.on_window_event = lambda e: (setattr(page, 'window_visible', False) or page.update()) if e.data == "close" else None

        def on_save(e):
            config.set("manual_mode", sw_manual.value)
            if sw_manual.value:
                config.set("manual_base", int(sl_base.value))
                config.set("manual_max", int(sl_max.value))
                config.set("manual_profile", dd_profile.value)
            
            config.set("autostart", sw_autostart.value)
            surgeon.manage_autostart(sw_autostart.value)
            
            # Update visual state
            update_ui_from_state(int(sl_base.value), int(sl_max.value), sw_manual.value)
            console.log("Configuration updated.", COLOR_ACCENT)

        def on_slider_change(e):
            lbl_base.value = f"Base Core: {int(sl_base.value)}"
            lbl_max.value = f"Core Range (Queues): {int(sl_max.value)}"
            cpu_grid.update_config(sl_base.value, sl_max.value)
            page.update()

        def force_mode(mode_type):
            sw_manual.value = True
            if mode_type == "GAMING":
                base, queues = surgeon.calculate_best_gap()
                sl_base.value = base
                sl_max.value = queues
                dd_profile.value = "NUMAStatic"
                console.log(f"Manual Override: GAMING (Base {base}, Q {queues})", COLOR_GAMING)
            else:
                sl_base.value = 0
                sl_max.value = topo['logical']
                dd_profile.value = "Closest"
                console.log("Manual Override: DESKTOP (Max)", COLOR_DESKTOP)
            on_save(None)

        # UI Elements
        sw_manual = ft.Switch(label="MANUAL OVERRIDE", value=config.get("manual_mode"), on_change=on_save, active_color=COLOR_ACCENT)
        sw_autostart = ft.Switch(label="SYSTEM AUTOSTART", value=config.get("autostart"), on_change=on_save, active_color=COLOR_ACCENT)
        
        lbl_base = ft.Text(f"Base Core: {config.get('manual_base')}", size=13, weight="bold")
        sl_base = ft.Slider(min=0, max=topo['logical']-1, divisions=topo['logical'], value=config.get("manual_base"), on_change=on_slider_change, active_color=COLOR_ACCENT)
        
        lbl_max = ft.Text(f"Core Range (Queues): {config.get('manual_max')}", size=13, weight="bold")
        sl_max = ft.Slider(min=1, max=topo['logical'], divisions=topo['logical'], value=config.get("manual_max"), on_change=on_slider_change, active_color=COLOR_ACCENT)
        
        dd_profile = ft.Dropdown(label="RSS Policy", options=[ft.dropdown.Option("Closest"), ft.dropdown.Option("ClosestStatic"), ft.dropdown.Option("NUMA"), ft.dropdown.Option("NUMAStatic")], value=config.get("manual_profile"), border_color="#444444")

        c_controls = ft.Column([
            ft.Row([
                ft.ElevatedButton("FORCE GAMING", icon=icons.GAMES, on_click=lambda e: force_mode("GAMING"), color="white", bgcolor=COLOR_GAMING, expand=True, height=45),
                ft.ElevatedButton("FORCE DESKTOP", icon=icons.COMPUTER, on_click=lambda e: force_mode("DESKTOP"), color="white", bgcolor=COLOR_DESKTOP, expand=True, height=45)
            ]),
            ft.Divider(height=30, color="#333333"),
            lbl_base, sl_base,
            lbl_max, sl_max,
            ft.Container(height=10),
            dd_profile,
            ft.Container(height=10),
            ft.ElevatedButton("APPLY SETTINGS", on_click=on_save, color="black", bgcolor=COLOR_ACCENT, height=50, width=500)
        ], spacing=10)

        # Set initial lock state
        c_controls.disabled = not sw_manual.value
        c_controls.opacity = 1.0 if sw_manual.value else 0.6

        # Build Main UI
        page.add(
            ft.Row([
                ft.Icon(icons.SECURITY, size=35, color=COLOR_ACCENT), 
                ft.Column([
                    ft.Text("RSS SENTINEL PRO", size=22, weight="bold"), 
                    ft.Text(f"ACTIVE: {topo['physical']}P / {topo['logical']}L CORES", size=10, color=COLOR_TEXT_DIM)
                ], spacing=0)
            ]),
            ft.Divider(height=20, color="#222222"),
            ft.Tabs(tabs=[
                ft.Tab(text="COMMAND CENTER", content=ft.Container(padding=20, content=ft.Row([
                    ft.Container(width=400, bgcolor=COLOR_PANEL, padding=25, border_radius=15, content=ft.Column([sw_manual, sw_autostart, ft.Divider(height=20, color="#333333"), c_controls])),
                    ft.Container(expand=True, content=ft.Column([
                        ft.Text("LIVE TOPOLOGY MAP", size=12, color=COLOR_TEXT_DIM, weight="bold"), 
                        cpu_grid, 
                        ft.Text("EVENT LOG", size=12, color=COLOR_TEXT_DIM, weight="bold"), 
                        console
                    ], expand=True))
                ], spacing=30, expand=True))),
                ft.Tab(text="GAMES DATABASE", content=ft.Container(padding=20, content=ft.Column([
                    ft.Text("Manage Automated Triggers", size=18, weight="bold"),
                    ft.Text("Modes will shift based on process activity.", size=12, color=COLOR_TEXT_DIM)
                ])))
            ], expand=1)
        )
        console.log("Sentinel Pro Online.", COLOR_ACCENT)
        console.log(f"Isolated: {surgeon.polluted_cores}", "#ffaa00")

    except Exception as e:
        with open(ERROR_FILE, "a") as f: f.write(f"GUI Error: {e}\n")
        page.add(ft.Text(f"CRITICAL UI ERROR: {e}", color="red"))

def run_gui(start_minimized=False):
    ft.app(target=lambda p: main_gui(p, start_minimized))
