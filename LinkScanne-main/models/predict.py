import joblib
import os
import json
import math
import re
import numpy as np
from urllib.parse import urlparse
from collections import Counter

def calculate_entropy(text):
    if len(text) == 0:
        return 0
    probs = [count / len(text) for count in Counter(text).values()]
    return -sum(p * math.log2(p) for p in probs)


SHORTENING_SERVICES = [
    "bit.ly", "tinyurl.com", "t.co",
    "goo.gl", "is.gd", "ow.ly"
]


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
    except Exception:
        features['domain_length'] = 0
        features['path_depth'] = 0

    features['entropy'] = calculate_entropy(url)
    features['is_shortened'] = 1 if any(
        s in url.lower() for s in SHORTENING_SERVICES
    ) else 0
    features['redirect_like'] = url.count("//") - 1
    features['has_redirect_param'] = 1 if "redirect=" in url.lower() else 0
    features['iframe_keyword'] = 1 if "iframe" in url.lower() else 0
    features['mouseover_keyword'] = 1 if "mouseover" in url.lower() else 0

    return features


def _get_model_path():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_path = os.path.join(project_root, "models", "model.joblib")
    data_path = os.path.join(project_root, "data", "model.joblib")
    if os.path.exists(models_path):
        return models_path
    if os.path.exists(data_path):
        return data_path
    return models_path  # المسار الافتراضي


def _patch_legacy_tree_monotonic_cst(estimator):
    """
    نماذج joblib من sklearn < 1.4 قد لا تحتوي على monotonic_cst؛
    الإصدارات الحديثة (مثل 1.5) تتوقعها عند predict_proba فيرفع AttributeError.
    """
    try:
        import numpy as np
        from sklearn.tree import BaseDecisionTree

        if not isinstance(estimator, BaseDecisionTree):
            return
        if getattr(estimator, "monotonic_cst", None) is not None:
            return
        n_feat = getattr(estimator, "n_features_in_", None)
        if n_feat is None and hasattr(estimator, "tree_"):
            n_feat = estimator.tree_.n_features
        if n_feat is not None and int(n_feat) > 0:
            # -1 = لا قيود أحادية النسبة (سلوك افتراضي كالنماذج القديمة)
            estimator.monotonic_cst = np.full(int(n_feat), -1, dtype=np.int8)
        else:
            estimator.monotonic_cst = None
    except Exception:
        try:
            estimator.monotonic_cst = None
        except Exception:
            pass


def _patch_sklearn_model(model):
    """يطبّق الترقيع على RandomForest أو شجرة واحدة."""
    try:
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
        from sklearn.tree import BaseDecisionTree

        if isinstance(model, (RandomForestClassifier, ExtraTreesClassifier)):
            for est in getattr(model, "estimators_", []) or []:
                _patch_legacy_tree_monotonic_cst(est)
        elif isinstance(model, BaseDecisionTree):
            _patch_legacy_tree_monotonic_cst(model)
    except Exception:
        pass


def load_model():
    model_path = _get_model_path()
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"النموذج غير موجود. قم بتشغيل Model Trining2.py أولاً لتدريب النموذج وحفظه في: {model_path}"
        )
    model = joblib.load(model_path)
    _patch_sklearn_model(model)
    return model


def load_model_info():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for base in ["models", "data"]:
        info_path = os.path.join(project_root, base, "model_info.json")
        if os.path.exists(info_path):
            with open(info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None


_model_cache = None
_model_info_cache = None


def _get_cached_model_and_info():
    global _model_cache, _model_info_cache
    if _model_cache is None:
        _model_cache = load_model()
    if _model_info_cache is None:
        _model_info_cache = load_model_info()
    return _model_cache, _model_info_cache


def predict_url(url):
    try:
        if not url or not isinstance(url, str):
            raise ValueError("الرابط غير صحيح")

        model, model_info = _get_cached_model_and_info()
        print(type(model))
        features = extract_features(url)

        feature_names = model_info.get('feature_names') if model_info else None
        if feature_names:
            feature_vector = np.array([features.get(name, 0) for name in feature_names]).reshape(1, -1)
        else:
            feature_vector = np.array(list(features.values())).reshape(1, -1)

        prediction = model.predict(feature_vector)[0]
        probabilities = model.predict_proba(feature_vector)[0]

        label_map = {0: 'safe', 1: 'suspicious', 2: 'malicious'}
        label = label_map.get(prediction, 'unknown')

        confidence = float(max(probabilities))

        result = {
            'label': label,
            'confidence': confidence,
            'features': features,
            'probabilities': {
                'safe': float(probabilities[0]) if len(probabilities) > 0 else 0.0,
                'suspicious': float(probabilities[1]) if len(probabilities) > 1 else 0.0,
                'malicious': float(probabilities[2]) if len(probabilities) > 2 else 0.0
            },
            'model_info': model_info
        }

        return result

    except FileNotFoundError as e:
        return {
            'label': 'error',
            'confidence': 0.0,
            'error': f'النموذج غير موجود: {str(e)}',
            'features': {},
            'probabilities': {'safe': 0.0, 'suspicious': 0.0, 'malicious': 0.0}
        }
    except Exception as e:
        import traceback
        return {
            'label': 'error',
            'confidence': 0.0,
            'error': f'خطأ في تحليل ML: {str(e)}',
            'features': {},
            'probabilities': {'safe': 0.0, 'suspicious': 0.0, 'malicious': 0.0},
            'traceback': traceback.format_exc()
        }


def get_feature_importance():
    model_info = load_model_info()
    if not model_info:
        return {}
    feature_names = model_info.get('feature_names', [])
    feature_importance = model_info.get('feature_importance', [])
    importance_dict = dict(zip(feature_names, feature_importance))
    return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))
    
if __name__ == "__main__":
    test_urls = [
        "https://www.google.com",
        "http://malicious-site.com/download.exe",
        "https://fake-bank.com/login"
    ]
        
    for url in test_urls:
        result = predict_url(url)
        print(f"URL: {url}")
        print(f"التصنيف: {result['label']}")
        print(f"الثقة: {result['confidence']:.4f}")
        print(f"الاحتمالات: {result['probabilities']}")
        print("-" * 50)
        