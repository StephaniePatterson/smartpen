import pickle
import numpy as np
from collections import deque
#import requests

with open("svm.pkl", "rb") as f:
    clf = pickle.load(f)

WINDOW_SIZE = 30
NUM_CHANNELS = 8
STRIDE = 1
current = deque(maxlen=WINDOW_SIZE)

ds = np.load("data/training/myo_ds_30l_10ol.npz")
print(np.unique(ds['y'], return_counts=True))

label_map = {
    0: "neutral",
    1: "flexion",
    2: "extension",
    7: "fist"
}
def on_emg_sample(emg_sample):
    """
    emg_sample: iterable of length 8 (EMG_1..EMG_8)
    """
    #print(emg_sample)

    processed = [abs(float(v)) * 10 for v in emg_sample]
    # append frame (ensure floats)
    current.append(processed)

    # when the buffer is full, make prediction(s)
    if len(current) == WINDOW_SIZE:
        # convert to numpy array shape (WINDOW_SIZE, NUM_CHANNELS)
        window = np.array(current, dtype=np.float32)
        #print(window)
        # flatten (1, 240)
        X = window.reshape(1, -1)
        # predict
        pred = clf.predict(X)   
        label = int(pred[0])
        gesture = label_map.get(label, f"label_{label}")

        # score = clf.decision_function(X) 
        if gesture != "neutral":
            print("something else detected!!!\n\n")
        handle_prediction(gesture, label)

def handle_prediction(gesture_name, label):
    # No-op placeholder: route this to UI, LSL marker stream, print, etc.
    if gesture_name != "neutral":
        print(f"Predicted: {gesture_name} (label {label})")