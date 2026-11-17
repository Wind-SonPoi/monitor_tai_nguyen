"""Giám sát CPU, RAM, Disk Active Time và I/O bằng Tkinter + psutil."""
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import psutil


class ResourceMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Giám sát tài nguyên máy tính")
        self.root.geometry("700x535")
        self.root.resizable(False, False)
        drive = os.environ.get("SystemDrive", "C:")
        self.disk_path = drive + "\\" if os.name == "nt" else "/"
        self.thresholds = {"CPU": 85.0, "RAM": 85.0, "DiskActive": 85.0}
        self.previous_over = set()
        self.value_labels, self.bars, self.threshold_inputs = {}, {}, {}
        self.previous_io = psutil.disk_io_counters()
        self.previous_io_time = time.monotonic()
        self.disk_active_value = None
        self.stop_event = threading.Event()

        ttk.Label(root, text="GIÁM SÁT TÀI NGUYÊN HỆ THỐNG",
                  font=("Segoe UI", 14, "bold")).pack(pady=(12, 5))
        panel = ttk.LabelFrame(root, text="Mức sử dụng hiện tại", padding=10)
        panel.pack(fill="x", padx=18, pady=5)
        rows = (
            ("CPU", "CPU Usage", True),
            ("RAM", "Memory / RAM", True),
            ("DiskActive", "Disk Active Time", True),
            ("DiskCapacity", f"Dung lượng ổ đĩa ({self.disk_path})", True),
            ("DiskRead", "Disk Read", False),
            ("DiskWrite", "Disk Write", False),
        )
        for name, title, has_bar in rows:
            row = ttk.Frame(panel)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=title, width=31).pack(side="left")
            if has_bar:
                bar = ttk.Progressbar(row, maximum=100, length=300, mode="determinate")
                bar.pack(side="left", padx=(0, 10))
                self.bars[name] = bar
            label = ttk.Label(row, text="Đang đọc...", width=13)
            label.pack(side="left")
            self.value_labels[name] = label

        setting = ttk.LabelFrame(root, text="Ngưỡng cảnh báo (%)", padding=10)
        setting.pack(fill="x", padx=18, pady=6)
        for name, title in (("CPU", "CPU"), ("RAM", "Memory"),
                            ("DiskActive", "Disk Active Time")):
            item = ttk.Frame(setting)
            item.pack(side="left", expand=True, padx=8)
            ttk.Label(item, text=title).pack(side="left", padx=(0, 5))
            entry = ttk.Entry(item, width=6, justify="center")
            entry.insert(0, str(int(self.thresholds[name])))
            entry.pack(side="left")
            self.threshold_inputs[name] = entry

        actions = ttk.Frame(root)
        actions.pack(pady=4)
        ttk.Button(actions, text="Áp dụng ngưỡng", command=self.apply_thresholds).pack(
            side="left", padx=5)
        ttk.Button(actions, text="Thoát", command=self.close).pack(side="left", padx=5)
        self.status = ttk.Label(root, text="Đang khởi tạo...", foreground="#285b2a")
        self.status.pack(pady=5)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if os.name == "nt":
            threading.Thread(target=self.read_disk_active_loop, daemon=True).start()
        self.root.after(1000, self.update_metrics)

    def close(self):
        self.stop_event.set()
        self.root.destroy()

    def read_disk_active_loop(self):
        """Đọc Disk Active Time qua bộ đếm hiệu năng Windows ở luồng nền."""
        script = ("$ErrorActionPreference='Stop'; "
                  "$d=Get-CimInstance -ClassName Win32_PerfFormattedData_PerfDisk_PhysicalDisk "
                  "-Filter \"Name='_Total'\"; "
                  "if ($null -eq $d) { throw 'Disk counter unavailable' }; "
                  "[Console]::WriteLine([string]::Format(" 
                  "[Globalization.CultureInfo]::InvariantCulture, '{0:F2}', "
                  "[double]$d.PercentDiskTime))")
        while not self.stop_event.is_set():
            try:
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True, text=True, timeout=4,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
                value = float(result.stdout.strip().splitlines()[-1].replace(",", "."))
                self.disk_active_value = min(100.0, max(0.0, value))
            except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                self.disk_active_value = None
            self.stop_event.wait(2.0)

    def apply_thresholds(self):
        new_values = {}
        try:
            for name, entry in self.threshold_inputs.items():
                value = float(entry.get().strip())
                if not 1 <= value <= 100:
                    raise ValueError("Mỗi ngưỡng phải nằm trong khoảng 1–100.")
                new_values[name] = value
        except ValueError as exc:
            message = str(exc) if str(exc).startswith("Mỗi ngưỡng") else (
                "Vui lòng nhập số từ 1 đến 100 cho cả ba ngưỡng.")
            messagebox.showerror("Ngưỡng không hợp lệ", message)
            return
        self.thresholds = new_values
        self.previous_over.clear()
        self.status.config(text="Đã cập nhật ngưỡng cảnh báo.", foreground="#285b2a")

    def read_metrics(self):
        now = time.monotonic()
        io = psutil.disk_io_counters()
        elapsed = max(now - self.previous_io_time, 0.001)
        read_rate = write_rate = 0.0
        if io is not None and self.previous_io is not None:
            read_rate = max(0, io.read_bytes - self.previous_io.read_bytes) / 1048576 / elapsed
            write_rate = max(0, io.write_bytes - self.previous_io.write_bytes) / 1048576 / elapsed
        if io is not None:
            self.previous_io = io
            self.previous_io_time = now
        return {
            "CPU": psutil.cpu_percent(interval=None),
            "RAM": psutil.virtual_memory().percent,
            "DiskActive": self.disk_active_value,
            "DiskCapacity": psutil.disk_usage(self.disk_path).percent,
            "DiskRead": read_rate,
            "DiskWrite": write_rate,
        }

    def update_metrics(self):
        try:
            metrics = self.read_metrics()
            currently_over = set()
            for name, value in metrics.items():
                if value is None:
                    self.value_labels[name].config(text="Không khả dụng")
                    if name in self.bars:
                        self.bars[name]["value"] = 0
                    continue
                unit = " MB/s" if name in ("DiskRead", "DiskWrite") else "%"
                self.value_labels[name].config(text=f"{value:.1f}{unit}")
                if name in self.bars:
                    self.bars[name]["value"] = value
                if name in self.thresholds and value >= self.thresholds[name]:
                    currently_over.add(name)

            newly_over = currently_over - self.previous_over
            self.previous_over = currently_over
            if currently_over:
                names = {"CPU": "CPU", "RAM": "RAM", "DiskActive": "Disk Active Time"}
                text = "Đang vượt ngưỡng: " + ", ".join(names[n] for n in sorted(currently_over))
                self.status.config(text=text, foreground="#b00020")
            elif metrics["DiskActive"] is None:
                self.status.config(text="Không đọc được Disk Active Time từ bộ đếm Windows.",
                                   foreground="#9a6700")
            else:
                self.status.config(text="Các chỉ số đang trong ngưỡng an toàn.",
                                   foreground="#285b2a")
            if newly_over:
                names = {"CPU": "CPU", "RAM": "RAM", "DiskActive": "Disk Active Time"}
                details = "\n".join(
                    f"{names[n]}: {metrics[n]:.1f}% (ngưỡng {self.thresholds[n]:.1f}%)"
                    for n in sorted(newly_over))
                messagebox.showwarning("Cảnh báo tài nguyên", details)
        except (OSError, psutil.Error) as exc:
            self.status.config(text=f"Không đọc được dữ liệu: {exc}", foreground="#b00020")
        self.root.after(1000, self.update_metrics)


def main():
    root = tk.Tk()
    ResourceMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
