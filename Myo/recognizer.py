import pickle
import numpy as np
from collections import deque
import time

# --- Load trained SVM pipeline (must exist as svm.pkl) ---
with open("svm.pkl", "rb") as f:
    clf = pickle.load(f)

# --- Sliding window config (matches training) ---
WINDOW_SIZE = 30
NUM_CHANNELS = 8

# Smoothing/debounce
PRED_SMOOTH = 3
ACTION_COOLDOWN_S = 0.40

_current = deque(maxlen=WINDOW_SIZE)
_pred_hist = deque(maxlen=PRED_SMOOTH)
_last_action_ts = 0.0

# Label map (adjust to your dataset)
label_map = {
    0: "neutral",
    1: "flexion",
    2: "extension",
    7: "fist"
}

# Will be set by capture_shapes.register_app(app)
_app_ref = None

def register_app(app):
    global _app_ref
    _app_ref = app

def _majority_vote(labels):
    if not labels:
        return None
    vals, counts = np.unique(labels, return_counts=True)
    return int(vals[np.argmax(counts)])

def on_emg_sample(emg_sample):
    # Simple abs scaling to mimic your earlier preprocessing
    processed = [abs(float(v)) * 10 for v in emg_sample]
    _current.append(processed)
    if len(_current) < WINDOW_SIZE:
        return
    window = np.array(_current, dtype=np.float32).reshape(1, -1)
    label = int(clf.predict(window)[0])
    _pred_hist.append(label)
    smooth_label = _majority_vote(list(_pred_hist))
    gesture = label_map.get(smooth_label, f"label_{smooth_label}")
    if gesture in ("flexion", "extension"):
        _handle_prediction(gesture)

def _handle_prediction(gesture_name):
    global _last_action_ts
    now = time.monotonic()
    if (now - _last_action_ts) < ACTION_COOLDOWN_S:
        return
    _last_action_ts = now
    if _app_ref is None:
        return
    try:
        if gesture_name == "flexion":
            _app_ref.root.after(0, _app_ref.decrease_brush)
        elif gesture_name == "extension":
            _app_ref.root.after(0, _app_ref.increase_brush)
    except Exception:
        pass
