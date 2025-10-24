# capture_shapes.py
import os
import sys
import csv
import time
import uuid
import threading
import queue
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

# --- Try to import Myo. App still works (x,y only) if not found. ---
myo_available = True
try:
    import myo  # pip install myo-python
except Exception as e:
    myo_available = False
    print("[WARN] myo-python not available; EMG will be disabled:", e)

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# NEW: recognizer hookup
from recognizer import on_emg_sample, register_app

# ------------------------ Config ------------------------
DEFAULT_SHAPES = [
    "circle", "triangle", "square", "rectangle", "star",
    "arrow-left", "arrow-right", "heart", "cloud", "house",
    "stick-figure", "sun", "diamond", "plus", "asterisk"
]
EMG_SAMPLE_RATE_HZ = 200  # ~200 Hz expected
CALIBRATION_SECONDS = 3.0

# ------------------------ Data Models ------------------------
@dataclass
class EmgSample:
    t_ns: int
    emg: List[int]  # raw 8-ch

@dataclass
class XYEvent:
    t_ns: int
    x: int
    y: int
    pen_state: int  # 1 = drawing (button down), 0 = up

@dataclass
class TrialBuffer:
    trial_id: str
    label: str
    emg: List[EmgSample] = field(default_factory=list)
    xy: List[XYEvent] = field(default_factory=list)

# ------------------------ Myo Listener ------------------------
class MyoListener:
    """Myo wrapper that pushes EMG into a queue from background hub thread."""
    def __init__(self, emg_queue: queue.Queue):
        self.emg_queue = emg_queue
        self._device = None
        self._emg_count = 0

        # Defer SDK init + Hub creation to start(), so UI can come up first
        self.hub = None
        self.listener = None
        self.thread = None
        self.running = False

    def _build_listener(self):
        class _Listener(myo.DeviceListener):
            def __init__(self, outer):
                super().__init__()
                self.outer = outer

            def on_connect(self, event):
                try:
                    print("[INFO] on_connect: enabling EMG…")
                    event.device.stream_emg(myo.StreamEmg.enabled)
                    self.outer._device = event.device
                    print("[INFO] EMG enabled; move your forearm to see samples.")
                except Exception as e:
                    print("[ERROR] Failed to enable EMG in on_connect:", e)

            def on_connected(self, event):
                try:
                    print("[INFO] on_connected: enabling EMG…")
                    event.device.stream_emg(myo.StreamEmg.enabled)
                    self.outer._device = event.device
                    print("[INFO] EMG enabled; move your forearm to see samples.")
                except Exception as e:
                    print("[ERROR] Failed to enable EMG in on_connected:", e)

            def on_arm_synced(self, event):
                print("[INFO] on_arm_synced (band is worn & synced)")

            def on_emg(self, event):
                t_ns = time.time_ns()
                self.outer.emg_queue.put(EmgSample(t_ns=t_ns, emg=list(event.emg)))
                self.outer._emg_count += 1
                if self.outer._emg_count % 200 == 0:
                    print(f"[DEBUG] EMG frames: {self.outer._emg_count}  sample={event.emg}")
                return False  # keep running
        return _Listener(self)

    def start(self):
        global myo_available
        if not myo_available:
            print("[WARN] Myo not available (import failed earlier); skipping EMG start.")
            return
        if self.running:
            return

        # Try initializing SDK + Hub here (after the UI exists)
        try:
            import myo  # ensure module is importable
        except Exception as e:
            myo_available = False
            print("[WARN] myo-python not available; EMG will be disabled:", e)
            return

        try:
            # IMPORTANT: pass the SDK **ROOT** folder (NOT the bin subfolder)
            print("[Myo] Initializing SDK…")
            myo.init(sdk_path=r"C:\Users\anisa\Downloads\myo-sdk-win-0.9.0\myo-sdk-win-0.9.0")
            self.hub = myo.Hub()
            try:
                self.hub.set_locking_policy(myo.LockingPolicy.none)
            except Exception:
                pass
            self.listener = self._build_listener()
            print("[Myo] SDK + Hub ready.")
        except Exception as e:
            print("[ERROR] Myo SDK init/Hub creation failed; running without EMG:", e)
            myo_available = False
            return

        def _run():
            try:
                while self.running:
                    self.hub.run(self.listener, 1000)  # process callbacks in 1s slices
            except Exception as e:
                print("[ERROR] Hub thread crashed:", e)

        self.running = True
        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        print("[Myo] Hub thread started.")

# ------------------------ Normalizer (Calibration) ------------------------
class EmgNormalizer:
    """Collects a few seconds of rest EMG and converts to z-scores."""
    def __init__(self):
        self.mean = None
        self.std = None
        self.lock = threading.Lock()

    def fit(self, samples: List[List[int]]):
        import math
        if not samples:
            return
        ch = list(zip(*samples))  # 8 tuples
        mean = [sum(c)/len(c) for c in ch]
        std = []
        for i, c in enumerate(ch):
            mu = mean[i]
            var = sum((v - mu) ** 2 for v in c) / max(1, (len(c) - 1))
            std.append((math.sqrt(var) or 1.0))
        with self.lock:
            self.mean = mean
            self.std = std

    def transform(self, emg: List[int]) -> List[float]:
        with self.lock:
            if self.mean is None or self.std is None:
                return list(map(float, emg))
            return [(emg[i] - self.mean[i]) / (self.std[i] if self.std[i] else 1.0) for i in range(len(emg))]

# ------------------------ Capture App ------------------------
class CaptureApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Myo Shape Capture (EMG + (x,y))")

        # state
        self.current_label = tk.StringVar(value=DEFAULT_SHAPES[0])
        self.trial_id = tk.StringVar(value=self._new_trial_id())
        self.capturing = False
        self.pen_down = 0
        self.trial = None

        # NEW: brush size (live gesture-controlled)
        self.brush_size = tk.IntVar(value=3)

        # queues & threads
        self.emg_queue = queue.Queue()
        self.listener = MyoListener(self.emg_queue)
        self.normalizer = EmgNormalizer()
        self.calibrating = False
        self.calibration_raw: List[List[int]] = []

        # UI
        self._build_ui()

        # Start EMG listener (non-blocking)
        self.root.after(100, self.listener.start)
        self.root.after(5, self._pump_emg_queue)

        # Start EMG pump into app + recognizer
        self.root.after(5, self._pump_emg_queue)
    
    def increase_brush(self):
        current = self.brush_size.get()
        self.brush_size.set(min(current + 1, 20))  # max 20

    def decrease_brush(self):
        current = self.brush_size.get()
        self.brush_size.set(max(current - 1, 1))  # min 1

    # ---------- UI ----------
    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="Shape label:").pack(side="left")
        self.shape_combo = ttk.Combobox(row1, values=DEFAULT_SHAPES, textvariable=self.current_label, width=20, state="readonly")
        self.shape_combo.pack(side="left", padx=6)

        ttk.Label(row1, text="Trial ID:").pack(side="left", padx=(12, 2))
        self.trial_entry = ttk.Entry(row1, textvariable=self.trial_id, width=16)
        self.trial_entry.pack(side="left")

        # Brush indicator
        ttk.Label(row1, text="Brush:").pack(side="left", padx=(12, 4))
        self.brush_label = ttk.Label(row1, textvariable=self.brush_size)
        self.brush_label.pack(side="left")

        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=6)
        self.btn_cal = ttk.Button(row2, text="Calibrate (rest 3s)", command=self._do_calibrate)
        self.btn_start = ttk.Button(row2, text="Start", command=self._do_start)
        self.btn_stop = ttk.Button(row2, text="Stop", command=self._do_stop, state="disabled")
        self.btn_save = ttk.Button(row2, text="Save CSV", command=self._do_save, state="disabled")
        self.btn_cancel = ttk.Button(row2, text="Cancel Trial", command=self._do_cancel, state="disabled")
        self.btn_cal.pack(side="left")
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop.pack(side="left", padx=6)
        self.btn_save.pack(side="left", padx=6)
        self.btn_cancel.pack(side="left", padx=6)

        # Canvas for drawing
        self.canvas = tk.Canvas(frm, bg="white", width=900, height=600, highlightthickness=1, highlightbackground="#aaa")
        self.canvas.pack(fill="both", expand=True, pady=8)

        # Bind stylus/mouse events
        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)

        # Status
        self.status = tk.StringVar(value="Ready. Connect Myo and (optionally) run Calibrate.")
        ttk.Label(frm, textvariable=self.status).pack(anchor="w")

    # ---------- Trial control ----------
    def _new_trial_id(self):
        return uuid.uuid4().hex[:8]

    def _do_calibrate(self):
        if not myo_available:
            messagebox.showwarning("Calibration", "Myo EMG not available; cannot calibrate.")
            return
        if self.capturing:
            messagebox.showinfo("Busy", "Stop current capture before calibration.")
            return
        self.status.set("Calibrating... keep arm relaxed.")
        self.calibrating = True
        self.calibration_raw = []
        t_end = time.time() + CALIBRATION_SECONDS

        def _collect():
            while time.time() < t_end:
                try:
                    s: EmgSample = self.emg_queue.get(timeout=0.1)
                    self.calibration_raw.append(s.emg)
                except queue.Empty:
                    pass
            self.normalizer.fit(self.calibration_raw)
            self.calibrating = False
            self.status.set(f"Calibration done on {len(self.calibration_raw)} EMG frames.")

        threading.Thread(target=_collect, daemon=True).start()

    def _do_start(self):
        if self.capturing:
            return
        label = self.current_label.get().strip()
        if not label:
            messagebox.showwarning("Label required", "Select or type a shape label.")
            return
        self.trial = TrialBuffer(trial_id=self.trial_id.get().strip() or self._new_trial_id(), label=label)
        self.capturing = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_cancel.configure(state="normal")
        self.btn_save.configure(state="disabled")
        self.canvas.delete("all")
        self.status.set(f"Capturing… Draw your {label}. Press Stop when finished.")

    def _do_stop(self):
        if not self.capturing:
            return
        self.capturing = False
        self.btn_stop.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.btn_save.configure(state="normal")
        self.btn_start.configure(state="normal")
        self.status.set(f"Stopped. {len(self.trial.emg)} EMG frames, {len(self.trial.xy)} XY points. Click Save.")

    def _do_save(self):
        if not self.trial:
            return

        print(f"[SAVE] EMG frames: {len(self.trial.emg)}, XY points: {len(self.trial.xy)}")

        default_name = f"{self.trial.label}_{self.trial.trial_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return

        # Merge by timestamp: EMG rows copy last-seen XY; XY rows have blank EMG
        merged = []
        for e in self.trial.emg:
            merged.append(("emg", e.t_ns, e.emg, None))
        for p in self.trial.xy:
            merged.append(("xy", p.t_ns, None, p))
        merged.sort(key=lambda z: z[1])

        rows = []
        last_x = None
        last_y = None
        last_pen = 0

        for kind, t_ns, e, p in merged:
            if kind == "emg":
                vals = self.normalizer.transform(e)
                rx = "" if last_x is None else int(last_x)
                ry = "" if last_y is None else int(last_y)
                rp = last_pen
                row = [self.trial.trial_id, self.trial.label, int(t_ns)] \
                      + [f"{v:.4f}" for v in vals] + [rx, ry, rp]
                rows.append(row)
            else:
                last_x, last_y, last_pen = int(p.x), int(p.y), int(p.pen_state)
                row = [self.trial.trial_id, self.trial.label, int(t_ns)] \
                      + [""] * 8 + [last_x, last_y, last_pen]
                rows.append(row)

        headers = ["trial_id", "label", "timestamp_ns"] \
                  + [f"emg{i+1}" for i in range(8)] + ["x", "y", "pen_state"]

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(rows)

            messagebox.showinfo("Saved", f"Saved {len(rows)} merged rows (EMG + X,Y) to:\n{path}")
            self.status.set("Saved CSV. Ready for next trial.")
            self.trial_id.set(self._new_trial_id())
            self.btn_save.configure(state="disabled")

        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            print("[ERROR] Save failed:", e)

    def _do_cancel(self):
        if not self.capturing:
            return
        self.capturing = False
        self.trial = None
        self.canvas.delete("all")
        self.btn_stop.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self.btn_start.configure(state="normal")
        self.status.set("Trial canceled.")

    # ---------- Canvas events ----------
    def _on_down(self, event):
        if not self.capturing:
            return
        self.pen_down = 1
        self._record_xy(event.x, event.y, 1)
        self.last_pt = (event.x, event.y)

    def _on_move(self, event):
        if not self.capturing or self.pen_down == 0:
            return
        lx, ly = getattr(self, "last_pt", (event.x, event.y))
        # Use current brush size here
        self.canvas.create_line(lx, ly, event.x, event.y, width=self.brush_size.get())
        self.last_pt = (event.x, event.y)
        self._record_xy(event.x, event.y, 1)

    def _on_up(self, event):
        if not self.capturing:
            return
        self.pen_down = 0
        self._record_xy(event.x, event.y, 0)

    def _record_xy(self, x, y, pen_state):
        if not self.trial:
            return
        self.trial.xy.append(XYEvent(t_ns=time.time_ns(), x=int(x), y=int(y), pen_state=int(pen_state)))
        if len(self.trial.xy) <= 5 or len(self.trial.xy) % 100 == 0:
            print(f"[XY] x={x}, y={y}, pen={pen_state}, total_xy={len(self.trial.xy)}")

    # ---------- EMG pump ----------
    def _pump_emg_queue(self):
        try:
            while True:
                s: EmgSample = self.emg_queue.get_nowait()
                if getattr(self, "_dbg_emg_ct", None) is None:
                    self._dbg_emg_ct = 0
                self._dbg_emg_ct += 1
                if self._dbg_emg_ct % 100 == 0:
                    print(f"[app] EMG frames seen by app: {self._dbg_emg_ct}")
                if self.capturing and self.trial is not None:
                    self.trial.emg.append(s)

                # NEW: stream raw EMG to recognizer for live brush control
                on_emg_sample(s.emg)

        except queue.Empty:
            pass
        # re-arm
        self.root.after(5, self._pump_emg_queue)

# ------------------------ main ------------------------
def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = CaptureApp(root)

    # Let recognizer call back into the GUI for brush changes
    register_app(app)

    root.protocol("WM_DELETE_WINDOW", lambda: on_close(app, root))
    root.mainloop()

def on_close(app: CaptureApp, root):
    try:
        app.listener.stop()
    except Exception:
        pass
    root.destroy()

if __name__ == "__main__":
    main()
