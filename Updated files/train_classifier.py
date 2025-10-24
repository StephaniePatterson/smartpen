# train_classifier.py
import pandas as pd
import numpy as np, pickle
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix

ds = np.load("data/training/myo_ds_30l_10ol.npz")
X, y = ds["X"], ds["y"]

print("First window shape:", X[0].shape)  # (30, 8)
print("First reading in first window:", X[0][0])  # array of 8 EMG values
print("First window (all 30 readings):\n", X[0])
# Xf = X.reshape(X.shape[0], -1)

#Undersampling for neutral

neutral_idx = np.where(y == 0)[0]
other_idx = np.where(y != 0)[0]

n_other = len(other_idx)
sample_size = min(len(neutral_idx), len(other_idx))
neutral_idx_sampled = np.random.choice(neutral_idx, size=sample_size, replace=False)
other_idx_sampled = np.random.choice(other_idx, size=sample_size, replace=False)
balanced_idx = np.concatenate([neutral_idx_sampled, other_idx_sampled])
np.random.shuffle(balanced_idx)

balanced_idx = np.concatenate([neutral_idx_sampled, other_idx])
np.random.shuffle(balanced_idx)

X_balanced = X[balanced_idx]
y_balanced = y[balanced_idx]
Xf_balanced = X_balanced.reshape(X_balanced.shape[0], -1)

# look at the first sample (30 rows × 8 columns)
sample_index = 0
df = pd.DataFrame(X_balanced[sample_index], columns=[f"Channel_{i+1}" for i in range(8)])
print(df.head(10))   # show first 10 rows


X_train, X_test, y_train, y_test = train_test_split(Xf_balanced, y_balanced, test_size=0.2, stratify=y, random_state=42)
clf = make_pipeline(StandardScaler(), SVC(kernel="rbf", C=10, gamma="scale"))
clf.fit(X_train, y_train)
print(classification_report(y_test, clf.predict(X_test)))
pickle.dump(clf, open("svm.pkl", "wb"))
