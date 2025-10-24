# Myo Shape Capture (EMG + X/Y) — README

This guide lets you replicate a Python capture app that records **Myo armband EMG** (8 channels) together with **handwriting/drawing X–Y** from a mouse/trackpad (no touchscreen required). It saves a **single CSV** with timestamps, EMG, X, Y, and pen state.

---

## 1) Requirements

* **Windows 10/11 (64-bit)**
* **Bluetooth LE USB dongle** (Myo dongle or compatible BLE);
  driver must install cleanly in Device Manager.
* **Myo armband**, powered on, worn, and synced (vibration after sync).
* **Python 3.10 (64-bit)** recommended
* **Myo SDK for Windows 0.9.x** (unzipped locally)

---

## 2) Folder layout (example)

```
C:\Users\<you>\Desktop\Myo\
  capture_shapes.py
C:\Users\<you>\Downloads\myo-sdk-win-0.9.0\myo-sdk-win-0.9.0\
  bin\myo64.dll
  ...
C:\MyoEnv\  (virtual environment)
```

---

## 3) Create a Python virtual environment

Open **PowerShell** (Run as admin not required):

```powershell
# Create and activate a clean venv
python -m venv C:\MyoEnv
& C:\MyoEnv\Scripts\Activate.ps1

# Sanity
python --version
where.exe python
```

You should see `C:\MyoEnv\Scripts\python.exe`.

---

## 4) Install Python packages

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install myo-python cffi
```

> The package name is **myo-python** but you import it as `import myo`.

---

## 5) Myo SDK (DLL) setup

1. Download/unzip **Myo SDK 0.9.x** access here: https://github.com/NiklasRosenstein/myo-python/releases. Move the myo64 folder to your original myo folder. 
2. In code, call:

```python
myo.init(sdk_path=r"C:\Users\<you>\Downloads\myo-sdk-win-0.9.0\myo-sdk-win-0.9.0")
```

> Use the **SDK root folder** (not `\bin`). The wrapper appends `\bin\myo64.dll`.

---

## 6) Bluetooth dongle driver

* Plug in the dongle, open **Device Manager**.
* If you see a yellow warning / “requires further installation”:

  * Right-click → **Update driver** → **Browse my computer** → select the SDK `drivers` folder (Bluegiga/Thalmic INF) → **Next**.
  * If Windows blocks the driver, temporarily disable driver signature enforcement (Advanced Startup) and install again.
* After installation, no warning icons should be present.

---

## 7) App code: key pieces to verify

In `capture_shapes.py`:

1. **Import & SDK path**

```python
import myo
myo.init(sdk_path=r"C:\Users\<you>\Downloads\myo-sdk-win-0.9.0\myo-sdk-win-0.9.0")
```

2. **Hub & unlock**

```python
self.hub = myo.Hub()
self.hub.set_locking_policy(myo.LockingPolicy.none)
```

3. **Enable EMG (enum, not True/False)**
   In both `on_connect` and/or `on_connected`:

```python
event.device.stream_emg(myo.StreamEmg.enabled)
```

4. **Run the hub continuously**
   Inside `MyoListener.start()`:

```python
def start(self):
    if self.running: return
    def _run():
        try:
            while self.running:
                self.hub.run(self.listener, 1000)  # (listener, duration_ms)
        except Exception as e:
            print("[ERROR] Hub thread crashed:", e)
    self.running = True
    self.thread = threading.Thread(target=_run, daemon=True)
    self.thread.start()
```

`stop()`:

```python
def stop(self):
    if not self.running: return
    try:
        self.running = False
        self.hub.stop()  # no args
    except Exception as e:
        print("[ERROR] Stopping hub:", e)
```

5. **XY capture** (mouse/trackpad)

* The canvas binds `<ButtonPress-1>`, `<B1-Motion>`, `<ButtonRelease-1>`.
* You must **click-and-hold left button** and **drag** to draw.

6. **Single merged CSV**
   The save routine merges EMG and XY by timestamp; EMG rows carry the **last-seen X,Y**. Header:

```
trial_id, label, timestamp_ns, emg1..emg8, x, y, pen_state
```

---

## 8) Run the app

```powershell
& C:\MyoEnv\Scripts\Activate.ps1
cd C:\Users\<you>\Desktop\Myo
python capture_shapes.py
```

**Workflow in the GUI**

1. Pick a **Shape label** (e.g., `circle`).
2. Click **Start**.
3. Wear the Myo, move your forearm (to produce EMG).
4. **Draw** on the white canvas (click-drag with mouse/trackpad).
5. Click **Stop** → **Save CSV**.
6. The status line shows counts like:
   `Stopped. 842 EMG frames, 1034 XY points. Click Save.`

---

## 9) CSV format details

* **Rows are time-sorted** across EMG and XY events.
* **EMG rows:** `emg1..emg8` are filled; `x,y,pen_state` carry the most recent XY (blank until first XY event occurs).
* **XY rows:** EMG columns are blank; `x,y,pen_state` are filled.
* Timestamps are **nanoseconds** (`time.time_ns()`).

Open in Excel by importing with **comma** delimiter or open in a text editor to verify columns.

---

## 10) Non-touch laptops

No touchscreen is needed:

* Use **left-click and hold** on the canvas, then drag to draw.
* Releasing the button sets `pen_state=0`.

Optional “keyboard draw” mode can be added (e.g., hold **D** to draw), but the default mouse bindings are sufficient.

---

## 11) Common errors & fixes

### `No module named 'myo'`

* You’re not in the venv or didn’t install the package there.
  Run:

  ```powershell
  & C:\MyoEnv\Scripts\Activate.ps1
  python -m pip install myo-python cffi
  python -c "import myo; print('OK')"
  ```

### `OSError: cannot load myo64.dll`

* Pass the **SDK root** to `myo.init(...)`.
* Ensure 64-bit Python + 64-bit DLL.
* Install VC++ 2015–2022 x64 redistributable if MSVCP/VCRUNTIME errors appear.

### `expected callable or DeviceListener`

* Wrong `Hub.run` signature. Use `hub.run(self.listener, 1000)`.

### `Hub.stop() takes 1 positional argument but 2 were given`

* Newer API is `hub.stop()` (no args).

### No EMG in CSV (but XY present)

* Ensure `event.device.stream_emg(myo.StreamEmg.enabled)` in connect callback(s).
* **Close Myo Connect**.
* Wear/sync the band (vibration).
* Confirm the hub thread **loops** (see code in §7.4).
* Dongle driver installed without warning icons.

### Indentation / TabError

* Convert indentation to **spaces** in your editor.
  In VS Code: bottom-right → **Spaces** → *Convert Indentation to Spaces*.
  Validate:

  ```powershell
  python -m tabnanny C:\Users\<you>\Desktop\Myo\capture_shapes.py
  ```

---

## 12) Quick diagnostics (optional)

* Print EMG heartbeat every ~1s:

  ```python
  self._emg_count += 1
  if self._emg_count % 200 == 0:
      print(f"[DEBUG] EMG frames: {self._emg_count}")
  ```
* Print a few XY:

  ```python
  if len(self.trial.xy) <= 5 or len(self.trial.xy) % 100 == 0:
      print(f"[XY] x={x}, y={y}, pen={pen_state}, n={len(self.trial.xy)}")
  ```
* On save:

  ```python
  print(f"[SAVE] EMG={len(self.trial.emg)} XY={len(self.trial.xy)}")
  ```

---

## 13) What “good” looks like

Console:

```
[INFO] on_connected: enabling EMG…
[INFO] EMG enabled; move your forearm to see samples.
[INFO] on_arm_synced (band is worn & synced)
[DEBUG] EMG frames: 200
[XY] x=432, y=281, pen=1, n=12
```

Status line after Stop:

```
Stopped. 842 EMG frames, 1034 XY points. Click Save.
```

CSV (first data rows):

```
trial_id,label,timestamp_ns,emg1,emg2,emg3,emg4,emg5,emg6,emg7,emg8,x,y,pen_state
a1b2c3d4,circle, ... ,  0.1240, -0.0135, ... , 512, 290, 1
a1b2c3d4,circle, ... ,  "" , "" , "" , "" , "" , "" , "" ,  514, 293, 1
```

---

## 14) Reuse / next steps

* Change the **shape list** (dropdown) in the config.
* Adjust sample rate logic or add on-the-fly filtering.
* Use the CSV as input to your classifier/training pipeline.

---