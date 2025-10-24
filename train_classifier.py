# train_classifier.py
import pandas as pd
import numpy as np, pickle
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix

ds = np.load("myo_ds_30l_10ol.npz")
X, y = ds["X"], ds["y"]
Xf = X.reshape(X.shape[0], -1)

# look at the first sample (30 rows × 8 columns)
sample_index = 0
df = pd.DataFrame(X[sample_index], columns=[f"Channel_{i+1}" for i in range(8)])
print(df.head(10))   # show first 10 rows


X_train, X_test, y_train, y_test = train_test_split(Xf, y, test_size=0.2, stratify=y, random_state=42)
clf = make_pipeline(StandardScaler(), SVC(kernel="rbf", C=10, gamma="scale"))
clf.fit(X_train, y_train)
print(classification_report(y_test, clf.predict(X_test)))
pickle.dump(clf, open("svm.pkl", "wb"))
