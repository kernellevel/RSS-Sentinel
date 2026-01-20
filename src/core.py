import subprocess
import winreg
import json
import time
import os
from typing import Dict, List, Optional, Union, Tuple

class KernelSurgeon:
    """The interface for system-level modifications."""
    
    def __init__(self):
        """Initializes the surgeon and scans for hardware context."""
        self.topology: Dict[str, int] = self._analyze_topology()
        self.polluted_cores: List[int] = self.scan_polluted_cores()
        self.target_adapters: List[str] = []
        self._scan_adapters_cache()
        self.gateway_ip = self._get_default_gateway()

    def _get_default_gateway(self) -> str:
        try:
            ps_cmd = "Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty NextHop"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            ip = res.stdout.strip()
            return ip if ip else "8.8.8.8"
        except: return "8.8.8.8"

    def scan_polluted_cores(self) -> List[int]:
        def run_registry_scan() -> int:
            ps_script = r"""
            $total_mask = [long]0
            $basePath = "HKLM:\SYSTEM\CurrentControlSet\Enum"
            $keys = Get-ChildItem -Path $basePath -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*Affinity Policy*' }
            foreach ($key in $keys) {
                $path = $key.Name.Replace('HKEY_LOCAL_MACHINE', 'HKLM:')
                $val = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
                if ($val -and $val.AssignmentSetOverride) {
                    $item_mask = [long]0
                    $data = $val.AssignmentSetOverride
                    if ($data -is [byte[]]) {
                        for ($i=0; $i -lt $data.Length; $i++) {
                            $multiplier = [long][math]::Pow(256, $i)
                            $item_mask += [long]$data[$i] * $multiplier
                        }
                    } elseif ($data -is [long] -or $data -is [int]) {
                        $item_mask = [long]$data
                    }
                    $total_mask = $total_mask -bor $item_mask
                }
            }
            Write-Output $total_mask
            """
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, startupinfo=si)
                out = res.stdout.strip()
                return int(out) if out else 0
            except: return 0

        print("[Core] Scanning Registry for IRQ-polluted cores...")
        polluted_mask = 1 
        polluted_mask |= run_registry_scan()
        indices = []
        for i in range(64):
            if (polluted_mask & (1 << i)): indices.append(i)
        return indices if indices else [0]

    def calculate_best_gap(self) -> Tuple[int, int]:
        l_procs = self.topology.get("logical", 8)
        polluted = set(self.polluted_cores)
        clean_set = set(i for i in range(l_procs) if i not in polluted)
        
        if not clean_set:
            return (1, 1)

        search_range = range(l_procs - 1, -1, -1)

        # Priority 1: 4 cores, even start
        for n in search_range:
            if n % 2 == 0 and n + 3 < l_procs:
                if all(i in clean_set for i in range(n, n + 4)):
                    print(f"[Core] Safety-Fit: Priority 1 (4 Cores, Even Base {n})")
                    return (n, 4)

        # Priority 2: 4 cores, any start
        for n in search_range:
            if n + 3 < l_procs:
                if all(i in clean_set for i in range(n, n + 4)):
                    print(f"[Core] Safety-Fit: Priority 2 (4 Cores, Base {n})")
                    return (n, 4)

        # Priority 3: 2 cores, even start
        for n in search_range:
            if n % 2 == 0 and n + 1 < l_procs:
                if all(i in clean_set for i in range(n, n + 2)):
                    print(f"[Core] Safety-Fit: Priority 3 (2 Cores, Even Base {n})")
                    return (n, 2)

        # Priority 4: 2 cores, any start
        for n in search_range:
            if n + 1 < l_procs:
                if all(i in clean_set for i in range(n, n + 2)):
                    print(f"[Core] Safety-Fit: Priority 4 (2 Cores, Base {n})")
                    return (n, 2)

        sorted_clean = sorted(list(clean_set), reverse=True)
        print(f"[Core] Safety-Fit: Fallback (1 Core, Base {sorted_clean[0]})")
        return (sorted_clean[0], 1)

    def _analyze_topology(self) -> Dict[str, int]:
        try:
            import psutil
            p_cores = psutil.cpu_count(logical=False)
            l_procs = psutil.cpu_count(logical=True)
            return {"physical": p_cores or 4, "logical": l_procs or 8, "ht": (l_procs or 8) > (p_cores or 4)}
        except: return {"physical": 4, "logical": 8, "ht": True}

    def _scan_adapters_cache(self) -> None: 
        ps_script = "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false } | Select-Object -ExpandProperty Name"
        try:
            res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.target_adapters = [name.strip() for name in res.stdout.split('\n') if name.strip()]
        except: pass

    def apply_rss_settings(self, base_proc: int, max_procs: int, queues: int, profile: str = "Closest") -> bool:
        if not self.target_adapters: return False
        
        # [DEBUG] Ensuring parameters reach PowerShell as intended
        print(f"[DEBUG] Applying Base: {base_proc}, Queues: {queues}, MaxProcs: {max_procs}, Profile: {profile}")
        
        commands = []
        for nic in self.target_adapters:
            # RSS Affinity & Max Processors
            commands.append(f"Set-NetAdapterRss -Name '{nic}' -BaseProcessorNumber {base_proc} -MaxProcessors {max_procs} -Profile {profile} -ErrorAction SilentlyContinue")
            # Number of Receive Queues
            commands.append(f"Set-NetAdapterRss -Name '{nic}' -NumberOfReceiveQueues {queues} -ErrorAction SilentlyContinue")
        
        try:
            subprocess.run(["powershell", "-Command", "; ".join(commands)], creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            print(f"[Core] RSS Settings Error: {e}")
            return False

    def apply_advanced_properties(self, interrupt_mod: Union[int, str]) -> bool:
        if not self.target_adapters: return False
        val_im = str(interrupt_mod) if not isinstance(interrupt_mod, int) else ("Enabled" if interrupt_mod == 1 else "Disabled")
        commands = [f"Set-NetAdapterAdvancedProperty -Name '{nic}' -DisplayName 'Interrupt Moderation' -DisplayValue '{val_im}' -ErrorAction SilentlyContinue" for nic in self.target_adapters]
        try:
            subprocess.run(["powershell", "-Command", "; ".join(commands)], creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except: return False

    def apply_registry_tweaks(self, mode: str, queues: int) -> bool:
        try:
            key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "ReceiveSideScaling", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "EnableTCPA", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "MaxNumRSSQueues", 0, winreg.REG_DWORD, queues)
            return True
        except: return False
            
    def backup_network_config(self) -> Optional[dict]:
        backup = {}
        try:
            key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ) as key:
                for name in ["ReceiveSideScaling", "EnableTCPA", "MaxNumRSSQueues"]:
                    try:
                        val, _ = winreg.QueryValueEx(key, name)
                        backup[name] = val
                    except: pass
            
            from src.config import PROJECT_ROOT
            backup_path = os.path.join(PROJECT_ROOT, "network_backup.json")
            with open(backup_path, "w") as f: json.dump(backup, f)
            return backup
        except: return None

    def restore_network_config(self, backup_data: Optional[dict] = None) -> bool:
        from src.config import PROJECT_ROOT
        backup_path = os.path.join(PROJECT_ROOT, "network_backup.json")
        if not backup_data and os.path.exists(backup_path):
            try:
                with open(backup_path, "r") as f: backup_data = json.load(f)
            except: pass
        if not backup_data: return False
        try:
            key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_WRITE) as key:
                for name, val in backup_data.items(): winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, val)
            return True
        except: return False

    def check_connectivity(self) -> bool:
        try:
            res = subprocess.run(["ping", self.gateway_ip, "-n", "1", "-w", "1000"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return res.returncode == 0
        except: return False

    def safe_apply_mode(self, base, max_p, profile, im_mode, queues, mode_name) -> bool:
        print(f"[Core] Applying SAFE Mode: {mode_name} (Base:{base}, Queues:{queues})...")
        backup = self.backup_network_config()
        self.apply_rss_settings(base, max_p, queues, profile)
        self.apply_advanced_properties(im_mode)
        self.apply_registry_tweaks(mode_name, queues)
        time.sleep(2)
        if not self.check_connectivity():
            print("[Core] Connectivity Lost! Rolling back...")
            self.restore_network_config(backup)
            self.apply_advanced_properties("Enabled")
            return False
        return True

    def manage_autostart(self, enable: bool) -> bool:
        import sys
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "RSS_Sentinel"
        
        if getattr(sys, 'frozen', False):
             cmd = f'"{sys.executable}" --tray'
        else:
            # Use pythonw.exe to avoid console window on startup
            py_exe = sys.executable
            if py_exe.lower().endswith("python.exe"):
                pyw_exe = py_exe[:-4] + "w.exe"
                if os.path.exists(pyw_exe):
                    py_exe = pyw_exe
            
            # Ensure we point to the main script correctly
            script_path = os.path.abspath(sys.argv[0])
            cmd = f'"{py_exe}" "{script_path}" --tray'

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE) as key:
                if enable: winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                else: 
                    try: winreg.DeleteValue(key, app_name)
                    except: pass
            return True
        except: return False

    def get_topology_info(self) -> Dict[str, int]: return self.topology