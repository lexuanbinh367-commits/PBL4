import ctypes
from ctypes import wintypes
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import csv
from datetime import datetime
import os

# =============================
# Backend: API Windows Network (giữ nguyên)
# =============================
iphlpapi = ctypes.WinDLL("Iphlpapi.dll")

MIB_IF_TYPE_WIFI = 71
IF_OPER_STATUS_UP = 1

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

class MIB_IF_ROW2(ctypes.Structure):
    _fields_ = [
        ("InterfaceLuid", ctypes.c_ulonglong),
        ("InterfaceIndex", wintypes.DWORD),
        ("GUID", GUID),
        ("Alias", wintypes.WCHAR * 257),
        ("Description", wintypes.WCHAR * 257),
        ("PhysicalAddressLength", wintypes.UINT),
        ("PhysicalAddress", wintypes.BYTE * 32),
        ("PermanentPhysicalAddress", wintypes.BYTE * 32),
        ("Mtu", wintypes.ULONG),
        ("Type", wintypes.ULONG),
        ("TunnelType", wintypes.ULONG),
        ("MediaType", wintypes.ULONG),
        ("PhysicalMediumType", wintypes.ULONG),
        ("AccessType", wintypes.ULONG),
        ("DirectionType", wintypes.ULONG),
        ("InterfaceAndOperStatusFlags", wintypes.BYTE * 1),
        ("OperStatus", wintypes.ULONG),
        ("AdminStatus", wintypes.ULONG),
        ("MediaConnectState", wintypes.ULONG),
        ("NetworkGuid", GUID),
        ("ConnectionType", wintypes.ULONG),
        ("TransmitLinkSpeed", ctypes.c_uint64),
        ("ReceiveLinkSpeed", ctypes.c_uint64),
        ("InOctets", ctypes.c_uint64),
        ("InUcastPkts", ctypes.c_uint64),
        ("InNUcastPkts", ctypes.c_uint64),
        ("InDiscards", ctypes.c_uint64),
        ("InErrors", ctypes.c_uint64),
        ("InUnknownProtos", ctypes.c_uint64),
        ("InUcastOctets", ctypes.c_uint64),
        ("InMulticastOctets", ctypes.c_uint64),
        ("InBroadcastOctets", ctypes.c_uint64),
        ("OutOctets", ctypes.c_uint64),
        ("OutUcastPkts", ctypes.c_uint64),
        ("OutNUcastPkts", ctypes.c_uint64),
        ("OutDiscards", ctypes.c_uint64),
        ("OutErrors", ctypes.c_uint64),
        ("OutUcastOctets", ctypes.c_uint64),
        ("OutMulticastOctets", ctypes.c_uint64),
        ("OutBroadcastOctets", ctypes.c_uint64),
        ("OutQLen", ctypes.c_uint64),
    ]

class MIB_IF_TABLE2(ctypes.Structure):
    _fields_ = [
        ("NumEntries", wintypes.ULONG),
        ("Table", MIB_IF_ROW2 * 1),
    ]

GetIfTable2 = iphlpapi.GetIfTable2
GetIfTable2.restype = wintypes.ULONG
GetIfTable2.argtypes = [ctypes.POINTER(ctypes.POINTER(MIB_IF_TABLE2))]

FreeMibTable = iphlpapi.FreeMibTable
FreeMibTable.argtypes = [ctypes.c_void_p]


def get_wifi_interfaces():
    """Return list of tuples: (InterfaceIndex, Description, row_struct) for Type == WIFI"""
    table_ptr = ctypes.POINTER(MIB_IF_TABLE2)()
    res = GetIfTable2(ctypes.byref(table_ptr))
    if res != 0:
        return []

    table = table_ptr.contents
    entries = ctypes.cast(
        ctypes.addressof(table.Table),
        ctypes.POINTER(MIB_IF_ROW2 * table.NumEntries),
    ).contents

    wifi_list = []
    for row in entries:
        if row.Type == MIB_IF_TYPE_WIFI:
            desc = row.Description.strip()
            wifi_list.append((row.InterfaceIndex, desc, row))
    FreeMibTable(table_ptr)
    return wifi_list

# =============================
# UI App (improved)
# =============================
class NetworkMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wi-Fi Network Monitor")
        self.root.geometry("1100x660")
        self.root.minsize(900, 520)

        # Grid base
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        # Header
        header = tk.Frame(self.root, bg="#1f2d3d", height=64)
        header.grid(row=0, column=0, columnspan=2, sticky="nsew")
        header.grid_propagate(False)
        tk.Label(header, text="📶 Wi-Fi Network Monitor", bg="#1f2d3d", fg="white",
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=16)

        # Left control panel
        control = ttk.Frame(self.root, padding=12)
        control.grid(row=1, column=0, sticky="nsew", padx=(12,6), pady=12)
        control.columnconfigure(0, weight=1)

        # Right chart panel
        chart_panel = ttk.Frame(self.root, padding=6)
        chart_panel.grid(row=1, column=1, sticky="nsew", padx=(6,12), pady=12)
        chart_panel.rowconfigure(0, weight=1)
        chart_panel.columnconfigure(0, weight=1)

        # ----- Left: controls -----
        ttk.Label(control, text="Adapter Wi-Fi:", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(control, state="readonly")
        self.combo.grid(row=1, column=0, sticky="ew", pady=(6,8))

        btn_frame = ttk.Frame(control)
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0,8))
        btn_frame.columnconfigure((0,1,2), weight=1)

        self.refresh_btn = ttk.Button(btn_frame, text="🔄 Refresh", command=self.reload_adapters)
        self.refresh_btn.grid(row=0, column=0, padx=4, sticky="ew")
        self.start_btn = ttk.Button(btn_frame, text="▶ Start", command=self.start_monitor)
        self.start_btn.grid(row=0, column=1, padx=4, sticky="ew")
        self.stop_btn = ttk.Button(btn_frame, text="⏹ Stop", command=self.stop_monitor, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=4, sticky="ew")

        # status/info box
        info_frame = ttk.LabelFrame(control, text="Thông tin (Realtime)", padding=8)
        info_frame.grid(row=3, column=0, sticky="nsew", pady=(8,8))
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="Status:").grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(info_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

        ttk.Label(info_frame, text="Download:").grid(row=1, column=0, sticky="w", pady=(6,0))
        self.dl_var = tk.StringVar(value="0.00 Mbps")
        ttk.Label(info_frame, textvariable=self.dl_var, font=("Segoe UI", 10, "bold")).grid(row=1, column=1, sticky="w", pady=(6,0))

        ttk.Label(info_frame, text="Upload:").grid(row=2, column=0, sticky="w", pady=(6,0))
        self.ul_var = tk.StringVar(value="0.00 Mbps")
        ttk.Label(info_frame, textvariable=self.ul_var, font=("Segoe UI", 10, "bold")).grid(row=2, column=1, sticky="w", pady=(6,0))

        ttk.Label(info_frame, text="Link speed:").grid(row=3, column=0, sticky="w", pady=(6,0))
        self.link_var = tk.StringVar(value="-- Mbps")
        ttk.Label(info_frame, textvariable=self.link_var).grid(row=3, column=1, sticky="w", pady=(6,0))

        # Export / clear
        util_frame = ttk.Frame(control)
        util_frame.grid(row=4, column=0, sticky="ew", pady=(8,0))
        util_frame.columnconfigure((0,1), weight=1)
        self.export_btn = ttk.Button(util_frame, text="💾 Export CSV", command=self.export_csv, state="disabled")
        self.export_btn.grid(row=0, column=0, padx=4, sticky="ew")
        self.clear_btn = ttk.Button(util_frame, text="🧹 Clear Data", command=self.clear_data)
        self.clear_btn.grid(row=0, column=1, padx=4, sticky="ew")

        # Footer note
        ttk.Label(control, text="Ghi chú: Đo bằng API Win32 (GetIfTable2)", foreground="gray").grid(row=5, column=0, sticky="w", pady=(12,0))

        # ----- Right: chart -----
        self.fig = Figure(figsize=(6,4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Network Throughput (Mbps)")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Mbps")
        self.ax.grid(True, alpha=0.3)
        self.line_down, = self.ax.plot([], [], label="Download", linewidth=2, color="#1f77b4")
        self.line_up, = self.ax.plot([], [], label="Upload", linewidth=2, color="#ff7f0e")
        self.ax.legend(loc="upper right")

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_panel)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # small status under chart
        bottom_info = ttk.Frame(chart_panel)
        bottom_info.grid(row=1, column=0, sticky="ew", pady=(8,0))
        bottom_info.columnconfigure(0, weight=1)
        self.chart_status = ttk.Label(bottom_info, text="No data", anchor="w")
        self.chart_status.grid(row=0, column=0, sticky="w")

        # Data containers
        self.max_points = 60
        self.times = deque(maxlen=self.max_points)
        self.downloads = deque(maxlen=self.max_points)
        self.uploads = deque(maxlen=self.max_points)

        # Monitoring control
        self.monitoring = False
        self.monitor_thread = None
        self.csv_file = None
        self.csv_writer = None

        # Init adapters
        self.reload_adapters()

    # ---------- UI helpers ----------
    def reload_adapters(self):
        try:
            wifis = get_wifi_interfaces()
            if not wifis:
                self.combo["values"] = []
                self.combo.set('')
                messagebox.showinfo("No Wi-Fi", "Không tìm thấy adapter Wi-Fi trên hệ thống.")
                return
            # map desc to entry
            self.if_map = {f"{desc} (idx={idx})": (idx, desc) for idx, desc, _ in wifis}
            names = list(self.if_map.keys())
            self.combo["values"] = names
            self.combo.current(0)
            self.status_var.set(f"{len(names)} Wi-Fi adapter(s) found")
        except Exception as e:
            messagebox.showerror("Error", f"Lỗi khi load adapter: {e}")

    def set_status(self, text):
        self.status_var.set(text)

    # ---------- Monitor logic (keeps original backend usage) ----------
    def start_monitor(self):
        if not getattr(self, "if_map", None):
            messagebox.showwarning("Chưa chọn", "Vui lòng refresh và chọn adapter Wi-Fi.")
            return
        sel = self.combo.get()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn adapter Wi-Fi.")
            return
        self.iface_index, self.iface_desc = self.if_map[sel]

        # get initial counters & link speed
        iface_row = self._get_iface_row(self.iface_index)
        if not iface_row:
            messagebox.showerror("Lỗi", "Không thể đọc thông tin adapter đã chọn.")
            return

        self.in_old, self.out_old = iface_row.InOctets, iface_row.OutOctets
        try:
            link_mbps = iface_row.ReceiveLinkSpeed / 1e6
            self.link_var.set(f"{link_mbps:.1f} Mbps")
        except Exception:
            self.link_var.set("-- Mbps")

        # enable CSV export
        self.export_btn.config(state="normal")

        self.monitoring = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="enabled")
        self.set_status("Monitoring...")
        # start thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self):
        self.monitoring = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.set_status("Stopped")

        # close csv if open
        if self.csv_file:
            try:
                self.csv_file.close()
            except:
                pass
            self.csv_file = None
            self.csv_writer = None
            self.export_btn.config(state="normal")

    def _get_iface_row(self, index):
        table_ptr = ctypes.POINTER(MIB_IF_TABLE2)()
        res = GetIfTable2(ctypes.byref(table_ptr))
        if res != 0:
            return None
        table = table_ptr.contents
        entries = ctypes.cast(
            ctypes.addressof(table.Table),
            ctypes.POINTER(MIB_IF_ROW2 * table.NumEntries),
        ).contents
        iface = None
        for row in entries:
            if row.InterfaceIndex == index:
                iface = row
                break
        FreeMibTable(table_ptr)
        return iface

    def _monitor_loop(self):
        start_time = time.time()
        while self.monitoring:
            time.sleep(1)
            # read fresh table and find selected interface
            iface_row = self._get_iface_row(self.iface_index)
            if not iface_row:
                self.set_status("Adapter lost")
                break

            in_new, out_new = iface_row.InOctets, iface_row.OutOctets
            # compute Mbps (bits/sec) over 1s interval
            down_mbps = (in_new - self.in_old) * 8 / 1e6
            up_mbps = (out_new - self.out_old) * 8 / 1e6
            self.in_old, self.out_old = in_new, out_new

            elapsed = int(time.time() - start_time)
            self.times.append(elapsed)
            self.downloads.append(down_mbps)
            self.uploads.append(up_mbps)

            # update numeric labels
            self.root.after(0, lambda: self.dl_var.set(f"{down_mbps:.2f} Mbps"))
            self.root.after(0, lambda: self.ul_var.set(f"{up_mbps:.2f} Mbps"))
            try:
                link_mbps = iface_row.ReceiveLinkSpeed / 1e6
                self.root.after(0, lambda: self.link_var.set(f"{link_mbps:.1f} Mbps"))
            except Exception:
                pass

            # write CSV if active
            if self.csv_writer:
                try:
                    self.csv_writer.writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        elapsed,
                        round(down_mbps, 4),
                        round(up_mbps, 4)
                    ])
                    self.csv_file.flush()
                except Exception:
                    pass

            # update chart
            self.root.after(0, self.update_plot)

        # thread exit
        self.set_status("Idle")

    # ---------- plotting ----------
    def update_plot(self):
        if not self.times:
            return
        xs = list(self.times)
        ys_d = list(self.downloads)
        ys_u = list(self.uploads)
        self.line_down.set_data(xs, ys_d)
        self.line_up.set_data(xs, ys_u)
        self.ax.set_xlim(xs[0], xs[-1])
        ymax = max(5, max(ys_d + ys_u, default=0) * 1.2)
        self.ax.set_ylim(0, ymax)
        self.canvas.draw_idle()
        self.chart_status.config(text=f"Showing last {len(xs)} samples")

    # ---------- CSV export ----------
    def export_csv(self):
        if not self.times:
            messagebox.showwarning("No Data", "Không có dữ liệu để xuất.")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Save monitoring data"
        )
        if not filename:
            return
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Time(s)", "Download(Mbps)", "Upload(Mbps)"])
                # We don't keep timestamps per-row in memory, only elapsed seconds; approximate by back-calculating
                # Better: use csv_writer live during monitoring (we support both). For now write from buffers.
                start = int(time.time()) - (self.times[-1] if self.times else 0)
                for t, d, u in zip(self.times, self.downloads, self.uploads):
                    ts = datetime.fromtimestamp(start + t).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([ts, t, f"{d:.4f}", f"{u:.4f}"])
            messagebox.showinfo("Exported", f"Data exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export CSV: {e}")

    def clear_data(self):
        self.times.clear()
        self.downloads.clear()
        self.uploads.clear()
        # reset labels
        self.dl_var.set("0.00 Mbps")
        self.ul_var.set("0.00 Mbps")
        self.link_var.set("-- Mbps")
        self.ax.clear()
        self.ax.set_title("Network Throughput (Mbps)")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Mbps")
        self.ax.grid(True, alpha=0.3)
        self.line_down, = self.ax.plot([], [], label="Download", linewidth=2, color="#1f77b4")
        self.line_up, = self.ax.plot([], [], label="Upload", linewidth=2, color="#ff7f0e")
        self.ax.legend(loc="upper right")
        self.canvas.draw_idle()
        self.chart_status.config(text="Cleared")

# =============================
# Run App
# =============================
if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except:
        pass
    app = NetworkMonitorApp(root)
    root.mainloop()
