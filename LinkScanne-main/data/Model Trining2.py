import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import math
from collections import Counter

from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    classification_report,
    accuracy_score,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
    auc
)
from sklearn.preprocessing import label_binarize

import joblib
import os
import re
from urllib.parse import urlparse
import json


# =====================================================
# Extra Feature Utilities
# =====================================================

def calculate_entropy(text):
    """حساب Entropy (عشوائية النص)"""
    if len(text) == 0:
        return 0
    probs = [count / len(text) for count in Counter(text).values()]
    return -sum(p * math.log2(p) for p in probs)

SHORTENING_SERVICES = [
    "bit.ly", "tinyurl.com", "t.co",
    "goo.gl", "is.gd", "ow.ly"
]

# =====================================================
# 1) Feature Extraction
# =====================================================
def extract_features(url):
    features = {}

    features['url_length'] = len(url)
    features['dot_count'] = url.count('.')
    features['dash_count'] = url.count('-')
    features['underscore_count'] = url.count('_')
    features['slash_count'] = url.count('/')
    features['question_count'] = url.count('?')
    features['equal_count'] = url.count('=')
    features['ampersand_count'] = url.count('&')

    features['digit_count'] = sum(c.isdigit() for c in url)
    features['upper_count'] = sum(c.isupper() for c in url)
    features['lower_count'] = sum(c.islower() for c in url)

    features['has_https'] = 1 if url.startswith('https://') else 0
    features['has_http'] = 1 if url.startswith('http://') else 0
    features['has_www'] = 1 if 'www.' in url else 0

    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    features['has_ip'] = 1 if re.search(ip_pattern, url) else 0

    suspicious_words = [
        'click', 'download', 'free', 'win', 'prize',
        'offer', 'limited', 'urgent', 'verify', 'login'
    ]

    features['suspicious_words'] = sum(
        1 for word in suspicious_words if word in url.lower()
    )

    suspicious_chars = ['@', '#', '$', '%', '^', '*', '+', '~', '`']

    features['suspicious_chars'] = sum(
        1 for char in suspicious_chars if char in url
    )

    try:
        parsed = urlparse(url)
        features['domain_length'] = len(parsed.netloc)

        path_parts = parsed.path.split('/')
        features['path_depth'] = len([p for p in path_parts if p])

    except:
        features['domain_length'] = 0
        features['path_depth'] = 0

    # =================================================
    # Advanced / Heuristic Features
    # =================================================

    features['entropy'] = calculate_entropy(url)

    features['is_shortened'] = 1 if any(
        s in url.lower() for s in SHORTENING_SERVICES
    ) else 0

    features['redirect_like'] = url.count("//") - 1
    features['has_redirect_param'] = 1 if "redirect=" in url.lower() else 0

    features['iframe_keyword'] = 1 if "iframe" in url.lower() else 0
    features['mouseover_keyword'] = 1 if "mouseover" in url.lower() else 0

    return features


# =====================================================
# 2) Load Dataset from CSV/Excel
# =====================================================

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if filepath.lower().endswith('.csv.xls'):
        return pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip')

    if ext in ['.csv']:
        return pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip')

    if ext in ['.xlsx', '.xls']:
        return pd.read_excel(filepath)

    return pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip')


def _find_data_file(basename):
    candidates = [
        os.path.join(DATA_DIR, basename),
        os.path.join(DATA_DIR, f"{basename}.csv"),
        os.path.join(DATA_DIR, f"{basename}.csv.xls"),
        os.path.join(DATA_DIR, f"{basename}.xlsx"),
        os.path.join(DATA_DIR, f"{basename}.xls"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def load_dataset_from_csv():

    print("تحميل البيانات من ملفات CSV/Excel...")

    path_safe = _find_data_file("benign_urls")

    if not path_safe:
        raise FileNotFoundError(
            f"لم يتم العثور على ملف benign_urls في: {DATA_DIR}"
        )

    df_safe = _load_file(path_safe)

    url_col = 'url' if 'url' in df_safe.columns else df_safe.columns[0]

    df_safe = df_safe[[url_col]].rename(columns={url_col: 'url'})
    df_safe['label'] = 0

    path_susp = _find_data_file("suspicious_urls")

    if not path_susp:
        raise FileNotFoundError(
            f"لم يتم العثور على ملف suspicious_urls في: {DATA_DIR}"
        )

    df_suspicious = _load_file(path_susp)

    url_col = 'url' if 'url' in df_suspicious.columns else df_suspicious.columns[0]

    df_suspicious = df_suspicious[[url_col]].rename(columns={url_col: 'url'})
    df_suspicious['label'] = 1

    path_mal = _find_data_file("malicious_phish")

    if not path_mal:
        raise FileNotFoundError(
            f"لم يتم العثور على ملف malicious_phish في: {DATA_DIR}"
        )

    df_malicious = _load_file(path_mal)

    url_col = 'url' if 'url' in df_malicious.columns else df_malicious.columns[0]

    if 'type' in df_malicious.columns:
        df_malicious = df_malicious[
            df_malicious['type'].str.lower().isin(
                ['phishing', 'defacement']
            )
        ].copy()

    df_malicious = df_malicious[[url_col]].rename(
        columns={url_col: 'url'}
    )

    df_malicious['label'] = 2

    for d in [df_safe, df_suspicious, df_malicious]:

        d.dropna(subset=['url'], inplace=True)

        d['url'] = d['url'].astype(str).str.strip()

        d.drop(
            d[d['url'] == ''].index,
            inplace=True
        )

    SAMPLE_SIZE = 5000

    df_safe = df_safe.sample(
        n=min(SAMPLE_SIZE, len(df_safe)),
        random_state=42
    )

    df_suspicious = df_suspicious.sample(
        n=min(SAMPLE_SIZE, len(df_suspicious)),
        random_state=42
    )

    df_malicious = df_malicious.sample(
        n=min(SAMPLE_SIZE, len(df_malicious)),
        random_state=42
    )

    df = pd.concat(
        [
            df_safe,
            df_suspicious,
            df_malicious
        ],
        ignore_index=True
    )

    print("عدد العينات بعد التوازن:")
    print(df['label'].value_counts())

    return df


# =====================================================
# 3) EDA
# =====================================================

def run_eda(df, X):

    print("بدء التحليل الاستكشافي EDA...")

    plt.figure(figsize=(6,4))

    sns.countplot(
        x=df['label'],
        palette="Set2"
    )

    plt.xticks(
        [0,1,2],
        ['Safe', 'Suspicious', 'Malicious']
    )

    plt.title("Class Distribution")
    plt.xlabel("Class")
    plt.ylabel("Count")
    plt.show()

    df_plot = X.copy()
    df_plot['label'] = df['label']

    plt.figure(figsize=(8,5))

    sns.boxplot(
        x='label',
        y='url_length',
        data=df_plot,
        palette="Set3"
    )

    plt.xticks(
        [0,1,2],
        ['Safe', 'Suspicious', 'Malicious']
    )

    plt.title("URL Length Distribution by Class")
    plt.show()

    plt.figure(figsize=(14,10))

    sns.heatmap(
        X.corr(),
        cmap="coolwarm",
        linewidths=0.5
    )

    plt.title("Feature Correlation Heatmap")
    plt.show()


# =====================================================
# 4) Train Model + Evaluation
# =====================================================

def train_model():

    print("بدء تدريب النموذج...")

    df = load_dataset_from_csv()

    X_features = df['url'].apply(extract_features)

    X_full = pd.DataFrame(list(X_features))
    X = pd.DataFrame(list(X_features))

    TOP_FEATURES = X.columns.tolist()

    X = X[TOP_FEATURES]

    y = df['label']

    run_eda(df, X_full)

    # =================================================
    # Logistic Regression (أول مرة لحساب الأهمية)
    # =================================================
    lr_temp = LogisticRegression(
    max_iter=3000,
    random_state=42,
    class_weight='balanced',
    multi_class='auto'
)

    # تقسيم البيانات (قبل حساب الأهمية)
    X_train_full, X_test_full, y_train_full, y_test_full = train_test_split(
     X,
     y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

    # تدريب مؤقت فقط لحساب الأهمية
    lr_temp.fit(X_train_full, y_train_full)

    coef_values_full = np.mean(
    np.abs(lr_temp.coef_),
    axis=0
)

    lr_importance_df = pd.DataFrame({
    'Feature': X.columns,
    'Importance': coef_values_full
})

    lr_importance_df = lr_importance_df.sort_values(
    by='Importance',
    ascending=False
)

# اختيار أفضل 15 فيتشر
    TOP_15_FEATURES = lr_importance_df['Feature'].head(15).tolist()

    print("\nأفضل 15 فيتشر:")
    print(TOP_15_FEATURES)

# استخدام أفضل 15 فقط للتدريب
    X_selected = X[TOP_15_FEATURES]

    X_train, X_test, y_train, y_test = train_test_split(
      X_selected,
      y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

    # =================================================
    # SVM
    # =================================================

    svm_model = SVC(
        kernel='rbf',
        C=1.0,
        gamma='scale',
        probability=True
    )

    svm_model.fit(X_train, y_train)

    svm_cv = cross_val_score(
        svm_model,
        X_selected,
        y,
        cv=5,
        scoring='accuracy'
    )

    print("SVM CV Mean:", svm_cv.mean())

    y_pred_svm = svm_model.predict(X_test)

    svm_accuracy = accuracy_score(
        y_test,
        y_pred_svm
    )

    print(f"\nدقة النموذج (SVM): {svm_accuracy:.4f}\n")

    print("تقرير SVM:")

    print(
        classification_report(
            y_test,
            y_pred_svm,
            target_names=[
                'Safe',
                'Suspicious',
                'Malicious'
            ]
        )
    )

    cm_svm = confusion_matrix(
        y_test,
        y_pred_svm
    )

    plt.figure(figsize=(6,5))

    sns.heatmap(
        cm_svm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=[
            'Safe',
            'Suspicious',
            'Malicious'
        ],
        yticklabels=[
            'Safe',
            'Suspicious',
            'Malicious'
        ]
    )

    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title("Confusion Matrix (SVM)")
    plt.show()

    svm_probs = svm_model.predict_proba(X_test)

    svm_auc = roc_auc_score(
        y_test_bin,
        svm_probs,
        multi_class='ovr',
        average='macro'
    )

    print(f"SVM AUC: {svm_auc:.4f}")

    # =================================================
    # Logistic Regression
    # =================================================
    lr_model = LogisticRegression(
        max_iter=3000,
        random_state=42,
        class_weight='balanced',
        multi_class='auto'
    )

    lr_model.fit(X_train, y_train)

    lr_cv = cross_val_score(
        lr_model,
        X_selected,
        y,
        cv=5,
        scoring='accuracy'
    )

    print("Logistic Regression CV Mean:", lr_cv.mean())

    y_pred_lr = lr_model.predict(X_test)

    lr_accuracy = accuracy_score(
        y_test,
        y_pred_lr
    )
    y_test_bin = label_binarize(
    y_test,
    classes=[0,1,2]
)
    print(f"\nدقة النموذج (Logistic Regression): {lr_accuracy:.4f}\n")

    print("تقرير Logistic Regression:")

    print(
        classification_report(
            y_test,
            y_pred_lr,
            target_names=[
                'Safe',
                'Suspicious',
                'Malicious'
            ]
        )
    )

    cm_lr = confusion_matrix(
        y_test,
        y_pred_lr
    )

    plt.figure(figsize=(6,5))

    sns.heatmap(
        cm_lr,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=[
            'Safe',
            'Suspicious',
            'Malicious'
        ],
        yticklabels=[
            'Safe',
            'Suspicious',
            'Malicious'
        ]
    )

    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title("Confusion Matrix (Logistic Regression)")
    plt.show()

    # Feature importance (كل الفيتشرز)
    lr_importance_df = pd.DataFrame({
        'Feature': X_full.columns,
        'Importance': 0.0
    })

    coef_values = np.mean(
        np.abs(lr_temp.coef_),
        axis=0
    )

    for i, f in enumerate(TOP_FEATURES):

        lr_importance_df.loc[
            lr_importance_df['Feature'] == f,
            'Importance'
        ] = coef_values[i]

    lr_importance_df = lr_importance_df.sort_values(
        by='Importance',
        ascending=False
    )

    plt.figure(figsize=(10,6))

    sns.barplot(
        x='Importance',
        y='Feature',
        data=lr_importance_df,
        palette="magma"
    )

    plt.title("Feature Importance (Logistic Regression)")
    plt.show()

    lr_probs = lr_model.predict_proba(X_test)

    lr_auc = roc_auc_score(
        y_test_bin,
        lr_probs,
        multi_class='ovr',
        average='macro'
    )

    print(f"Logistic Regression AUC: {lr_auc:.4f}")

    # حفظ مودل Logistic Regression
    os.makedirs("models", exist_ok=True)

    joblib.dump(lr_model, "models/model.joblib")

    model_info = {
    "model_name": "Logistic Regression",
    "feature_names": TOP_15_FEATURES,
    "feature_importance": coef_values.tolist()
}

    with open(
    "models/model_info.json",
    "w",
    encoding="utf-8"
) as f:

     json.dump(
        model_info,
        f,
        ensure_ascii=False,
        indent=4
    )

    print("تم حفظ مودل Logistic Regression بنجاح")

    # =========================
    # AUC Comparison Plot
    # =================================================

    plt.figure(figsize=(8,6))


    fpr_svm, tpr_svm, _ = roc_curve(
        y_test_bin.ravel(),
        svm_probs.ravel()
    )

    plt.plot(
        fpr_svm,
        tpr_svm,
        label=f'SVM (AUC={svm_auc:.3f})'
    )

    fpr_lr, tpr_lr, _ = roc_curve(
     y_test_bin.ravel(),
        lr_probs.ravel()
    )

    plt.plot(
        fpr_lr,
        tpr_lr,
        label=f'Logistic Regression (AUC={lr_auc:.3f})'
    )

    plt.plot(
        [0,1],
        [0,1],
        linestyle='--'
    )

    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("AUC Comparison")
    plt.legend()
    plt.show()

# =====================================================
# 5) Run
# =====================================================

if __name__ == "__main__":

    train_model()