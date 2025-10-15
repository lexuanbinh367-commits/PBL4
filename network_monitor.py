import ctypes
from ctypes import wintypes
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# =============================
# Backend: API Windows Network
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
    """Lấy danh sách các Wi-Fi interface khả dụng"""
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
            wifi_list.append((row.InterfaceIndex, row.Description.strip(), row))

    FreeMibTable(table_ptr)
    return wifi_list


# =============================
# App UI
# =============================
class NetworkMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📶 Wi-Fi Network Monitor")
        self.root.geometry("1000x600")
        self.root.minsize(900, 500)

        # Layout chính
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1, minsize=280)  # panel trái
        self.root.grid_columnconfigure(1, weight=3)               # panel phải

        # Panel cấu hình
        self.config_frame = ttk.LabelFrame(self.root, text="⚙️ Cấu hình")
        self.config_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Panel biểu đồ
        self.chart_frame = ttk.LabelFrame(self.root, text="📊 Biểu đồ tốc độ")
        self.chart_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # --- Config panel ---
        ttk.Label(self.config_frame, text="Chọn Wi-Fi:").pack(pady=10)
        self.combo = ttk.Combobox(self.config_frame, state="readonly", width=28)
        self.combo.pack(pady=5, padx=10, fill="x")

        self.start_btn = tk.Button(self.config_frame, text="▶ Start Monitor", bg="green", fg="white",
                                   command=self.start_monitor)
        self.start_btn.pack(pady=10, ipadx=10, ipady=5)

        self.stop_btn = tk.Button(self.config_frame, text="■ Stop", bg="red", fg="white",
                                  command=self.stop_monitor, state="disabled")
        self.stop_btn.pack(pady=5, ipadx=10, ipady=5)

        self.status_label = ttk.Label(self.config_frame, text="Chưa theo dõi adapter nào", wraplength=250)
        self.status_label.pack(pady=15)

        # --- Chart panel ---
        self.chart_frame.rowconfigure(0, weight=1)
        self.chart_frame.columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Wi-Fi Speed (Mbps)")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Mbps")
        self.ax.grid(True)
        self.line1, = self.ax.plot([], [], label="Download", color="blue")
        self.line2, = self.ax.plot([], [], label="Upload", color="red")
        self.ax.legend()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.draw()

        # Data
        self.times = deque(maxlen=60)
        self.downloads = deque(maxlen=60)
        self.uploads = deque(maxlen=60)

        self.monitoring = False
        self.thread = None

        # Load Wi-Fi list
        self.load_wifi_list()

    def load_wifi_list(self):
        wifi_list = get_wifi_interfaces()
        if not wifi_list:
            self.combo["values"] = []
        else:
            self.combo["values"] = [w[1] for w in wifi_list]
            self.if_map = {w[1]: w for w in wifi_list}
            self.combo.current(0)

    def start_monitor(self):
        if not self.combo.get():
            messagebox.showwarning("Cảnh báo", "Chưa chọn Wi-Fi adapter!")
            return

        desc = self.combo.get()
        self.iface_index, self.iface_name, iface = self.if_map[desc]

        self.status_label.config(text=f"Đang theo dõi: {self.iface_name}")

        self.monitoring = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        self.times.clear()
        self.downloads.clear()
        self.uploads.clear()
        self.start_time = time.time()
        self.in_old, self.out_old = iface.InOctets, iface.OutOctets

        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

    def stop_monitor(self):
        self.monitoring = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def update_loop(self):
        while self.monitoring:
            time.sleep(1)
            iface = None
            for idx, name, row in get_wifi_interfaces():
                if idx == self.iface_index:
                    iface = row
                    break
            if not iface:
                break

            in_new, out_new = iface.InOctets, iface.OutOctets
            down = (in_new - self.in_old) * 8 / 1e6
            up = (out_new - self.out_old) * 8 / 1e6
            self.in_old, self.out_old = in_new, out_new

            t = int(time.time() - self.start_time)
            self.times.append(t)
            self.downloads.append(down)
            self.uploads.append(up)

            self.root.after(0, self.update_plot)

    def update_plot(self):
        self.line1.set_data(self.times, self.downloads)
        self.line2.set_data(self.times, self.uploads)
        self.ax.set_xlim(max(0, self.times[0] if self.times else 0),
                         (self.times[-1] if self.times else 60))
        ymax = max(5, max(self.downloads + self.uploads, default=0) * 1.2)
        self.ax.set_ylim(0, ymax)
        self.canvas.draw_idle()


if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use("clam")
    app = NetworkMonitorApp(root)
    root.mainloop()
