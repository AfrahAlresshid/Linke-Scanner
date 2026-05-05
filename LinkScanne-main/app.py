from flask import Flask, request, jsonify, session, send_from_directory, abort
from flask_cors import CORS
import json
import os
import uuid
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
import hashlib

from db.database import (
    init_db,
    get_user_by_id,
    update_user_premium,
    set_user_premium_expired,
    update_user_last_login,
    create_session,
    delete_sessions_by_user,
    get_user_by_email,
    email_exists,
    create_user,
    save_analysis,
    get_analysis_by_id,
    get_saved_analyses_by_user,
    delete_analysis as db_delete_analysis,
    get_user_profile_row,
    update_user_name_email,
    update_user_password_hash_by_id,
)
from models.predict import predict_url
from integrations.virustotal import load_from_cache_or_query
from sandbox.worker import analyze_url_dynamic
from alerts.monitor import record_analysis, get_active_alerts, acknowledge_alert, get_stats

app = Flask(__name__)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(_BASE_DIR, 'public')

_DEFAULT_CONFIG = {
    'app': {'debug': True, 'host': '127.0.0.1', 'port': 5000, 'secret_key': 'default_key'},
    'virustotal': {'enabled': False, 'api_key': '', 'cache_hours': 24},
    'weights': {'ml': 0.5, 'dynamic': 0.25, 'virustotal': 0.1, 'heuristic': 0.15},
    'thresholds': {'malicious': 0.75, 'suspicious': 0.45},
    'sandbox': {'timeout': 8},
    'alerts': {'threshold_count': 5, 'window_seconds': 300},
}


def _load_config():
    base = os.path.dirname(__file__)
    for name in ('config.json', 'config.example.json'):
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError('ملف التكوين ليس كائناً (dict)')
            if name == 'config.example.json':
                logging.getLogger().info('تم تحميل التكوين من %s (للإنتاج: SECRET_KEY وVIRUSTOTAL_API_KEY من البيئة)', name)
            return cfg
        except Exception as e:
            logging.getLogger().error('خطأ في قراءة %s: %s', path, e)
    logging.getLogger().warning('لم يُعثر على config — استخدام تكوين افتراضي.')
    return dict(_DEFAULT_CONFIG)


config = _load_config()

# متغيرات بيئة للإنتاج (Render): لا تخزن الأسرار في الريبو
if os.environ.get('SECRET_KEY'):
    config.setdefault('app', {})['secret_key'] = os.environ['SECRET_KEY']
if os.environ.get('VIRUSTOTAL_API_KEY'):
    config.setdefault('virustotal', {})['api_key'] = os.environ['VIRUSTOTAL_API_KEY']
    config.setdefault('virustotal', {})['enabled'] = True
if os.environ.get('RENDER', '').lower() == 'true':
    config.setdefault('app', {})['debug'] = False

_cors_base = [
    'http://127.0.0.1:5500', 'http://localhost:5500',
    'http://127.0.0.1:5000', 'http://localhost:5000',
]
_cors_extra = [x.strip() for x in os.environ.get('CORS_ORIGINS', '').split(',') if x.strip()]
# إعدادات CORS لدعم الجلسات - يجب استخدام origins محددة مع credentials
CORS(app, resources={
    r"/api/*": {
        "origins": _cors_base + _cors_extra,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True,  # True للسماح بإرسال الكوكيز
        "expose_headers": ["Content-Type", "Set-Cookie"]
    }
}, supports_credentials=True)
_executor = ThreadPoolExecutor(max_workers=4)

app.config['SECRET_KEY'] = config.get('app', {}).get('secret_key', 'default_secret_key_change_in_production_12345')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Lax للسماح بالكوكيز في نفس الموقع
# True على Render/HTTPS
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RENDER', '').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_NAME'] = 'linkScanne_session'
app.config['SESSION_COOKIE_DOMAIN'] = None  # None للسماح بأي domain
app.config['SESSION_COOKIE_PATH'] = '/'
# إعدادات إضافية للجلسة
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # تحديث الجلسة في كل طلب
# إعدادات مهمة لحفظ الجلسة
app.config['SESSION_COOKIE_MAX_SIZE'] = 4093  # الحد الأقصى لحجم الكوكي (4KB)

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def get_user_from_session():
    try:
        logger.debug(
            "get_user_from_session: keys=%s, cookies=%s",
            list(session.keys()),
            dict(request.cookies),
        )

        # محاولة الحصول من Flask session أولاً
        user_id = session.get('user_id')
        
        if not user_id:
            logger.debug("No user_id found in session or database")
            return None
        
        logger.debug("Resolving user id=%s", user_id)
        user = get_user_by_id(user_id)

        if user:
            # التحقق من انتهاء الاشتراك المميز
            is_premium = user[3] == 1
            if is_premium and user[4]:
                expires_at = datetime.fromisoformat(user[4])
                if expires_at < datetime.now():
                    is_premium = False
                    set_user_premium_expired(user[0])
            
            logger.debug(f"User found: {user[1]} (ID: {user[0]})")
            return {
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'is_premium': is_premium
            }
    except Exception as e:
        logger.error(f"خطأ في الحصول على المستخدم: {e}", exc_info=True)
    
    return None

def is_premium_user():
    user = get_user_from_session()
    return user and user.get('is_premium', False)

def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin:
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        logger.debug(f"CORS headers added for origin: {origin}")
    else:
        # إذا لم يكن هناك Origin، استخدم القيمة الافتراضية من CORS config
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
    response.headers.add('Access-Control-Expose-Headers', 'Set-Cookie')
    # إضافة Vary header للسماح بالكوكيز
    response.headers.add('Vary', 'Origin')
    return response

# ensure logs dir exists before FileHandler
_log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(_log_dir, 'app.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Middleware لضمان حفظ الجلسة
@app.after_request
def set_session_cookie(response):
    # التأكد من إرسال الكوكي في كل استجابة
    if session.modified:
        logger.info(f"Session modified in after_request, setting cookie. Session keys: {list(session.keys())}")
        logger.info(f"Session data in cookie: user_id={session.get('user_id')}, user_email={session.get('user_email')}")
        # التأكد من أن الجلسة دائمة
        if 'user_id' in session:
            session.permanent = True
            logger.info(f"Ensuring session is permanent for user_id: {session.get('user_id')}")
    return response

analysis_results = {}

def calculate_final_score(ml_result, dynamic_result, vt_result, heuristic_score):
    try:
        weights = config.get('weights', {'ml': 0.5, 'dynamic': 0.25, 'virustotal': 0.1, 'heuristic': 0.15})
        thresholds = config.get('thresholds', {'malicious': 0.75, 'suspicious': 0.45})
        
        ml_conf = float(ml_result.get('confidence', 0.0)) if isinstance(ml_result, dict) else 0.0
        ml_label = ml_result.get('label', 'error') if isinstance(ml_result, dict) else 'error'
        dyn_score = float(dynamic_result.get('dynamic_score', 0.0)) if isinstance(dynamic_result, dict) else 0.0
        vt_score = float(vt_result.get('vt_score', 0.0)) if isinstance(vt_result, dict) else 0.0
        heur_score = float(heuristic_score) if isinstance(heuristic_score, (int, float)) else 0.0
        
        ml_conf = max(0.0, min(1.0, ml_conf))
        dyn_score = max(0.0, min(1.0, dyn_score))
        vt_score = max(0.0, min(1.0, vt_score))
        heur_score = max(0.0, min(1.0, heur_score))
        
        w_ml = float(weights.get('ml', 0.5))
        w_dyn = float(weights.get('dynamic', 0.25))
        w_vt = float(weights.get('virustotal', 0.1))
        w_heur = float(weights.get('heuristic', 0.15))
        
        # عند فشل ML لا نضرب وزن الـ ML بصفر فقط؛ نوزّع وزن الـ ML على الباقي حتى تبقى النتيجة ذات معنى
        if ml_label == 'error':
            rest = w_dyn + w_vt + w_heur
            if rest > 1e-9:
                w_dyn = w_dyn + w_ml * (w_dyn / rest)
                w_vt = w_vt + w_ml * (w_vt / rest)
                w_heur = w_heur + w_ml * (w_heur / rest)
            w_ml = 0.0
            ml_conf = 0.0
        
        final_score = (
            ml_conf * w_ml +
            dyn_score * w_dyn +
            vt_score * w_vt +
            heur_score * w_heur
        )
        
        final_score = max(0.0, min(1.0, final_score))
        
        malicious_threshold = float(thresholds.get('malicious', 0.75))
        suspicious_threshold = float(thresholds.get('suspicious', 0.45))
        
        if final_score >= malicious_threshold:
            final_label = 'malicious'
        elif final_score >= suspicious_threshold:
            final_label = 'suspicious'
        else:
            final_label = 'safe'
        
        return final_score, final_label
    except Exception as e:
        logger.error(f"خطأ في حساب النتيجة النهائية: {e}")
        return 0.0, 'error'

def calculate_heuristic_score(url):
    try:
        if not url or not isinstance(url, str):
            return 0.0
        
        score = 0.0
        
        if url.startswith('http://'):
            score += 0.2
        elif url.startswith('https://'):
            score -= 0.1
        
        if 'www.' in url:
            score -= 0.1
        
        url_len = len(url)
        if url_len > 200:
            score += 0.3
        elif url_len > 100:
            score += 0.2
        
        suspicious_chars = ['@', '#', '$', '%', '^', '*', '+', '~', '`']
        for char in suspicious_chars:
            if char in url:
                score += 0.1
        
        suspicious_words = ['click', 'download', 'free', 'win', 'prize', 'offer', 'limited', 'urgent']
        url_lower = url.lower()
        for word in suspicious_words:
            if word in url_lower:
                score += 0.2
        
        import re
        try:
            ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
            if re.search(ip_pattern, url):
                score += 0.3
        except re.error:
            pass
        
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning(f"خطأ في التحليل الاستدلالي: {e}")
        return 0.0

def analyze_url_comprehensive(url, guest_mode=False):
    analysis_id = str(uuid.uuid4())
    ml_result = {'label': 'error', 'confidence': 0.0}
    vt_result = {'vt_score': 0.0, 'malicious_count': 0, 'total_engines': 0, 'status': 'error', 'message': 'خطأ في التحليل'}
    dynamic_result = {
        'dynamic_score': 0.0,
        'suspicious_indicators': 0,
        'total_indicators': 0,
        'events': {
            'downloads': [],
            'form_submissions': [],
            'redirects': [],
            'suspicious_js': [],
            'cookies': []
        }
    }
    heuristic_score = 0.0
    
    try:
        if not url or not isinstance(url, str):
            raise ValueError("الرابط غير صحيح")
        
        logger.info(
            "بدء تحليل الرابط: %s (guest_mode=%s)",
            url,
            guest_mode,
        )
        
        try:
            heuristic_score = calculate_heuristic_score(url)
        except Exception as e:
            logger.warning(f"خطأ في التحليل الاستدلالي: {e}")
            heuristic_score = 0.0
        
        try:
            if guest_mode:
                ml_result = predict_url(url)
            else:
                ml_future = _executor.submit(predict_url, url)
                ml_result = ml_future.result(timeout=30)
            if not isinstance(ml_result, dict):
                raise ValueError("نتيجة ML غير صحيحة")
            if ml_result.get('label') == 'error':
                logger.warning(f"تحذير في تحليل ML: {ml_result.get('error', 'خطأ غير معروف')}")
            else:
                logger.info(f"نتيجة ML: {ml_result.get('label', 'unknown')} - {ml_result.get('confidence', 0.0):.4f}")
        except Exception as e:
            logger.error(f"خطأ في تحليل ML: {e}", exc_info=True)
            ml_result = {'label': 'error', 'confidence': 0.0, 'error': str(e)}
        
        if guest_mode:
            vt_result = {
                'vt_score': 0.0,
                'malicious_count': 0,
                'total_engines': 0,
                'status': 'skipped',
                'message': 'غير مضمن في التحليل السريع للزوار — سجّل الدخول للتحليل الكامل',
            }
        else:
            try:
                vt_api_key = config.get('virustotal', {}).get('api_key', '')
                vt_enabled = config.get('virustotal', {}).get('enabled', False)
                if vt_enabled and vt_api_key and vt_api_key != "YOUR_API_KEY_HERE":
                    logger.info(f"بدء تحليل VirusTotal للرابط: {url}")
                    vt_future = _executor.submit(load_from_cache_or_query, url, vt_api_key, config.get('virustotal', {}).get('cache_hours', 24))
                    vt_result = vt_future.result(timeout=30)
                    if not isinstance(vt_result, dict):
                        raise ValueError("نتيجة VirusTotal غير صحيحة")
                    logger.info(f"نتيجة VirusTotal: {vt_result.get('vt_score', 0.0):.4f} - {vt_result.get('status', 'unknown')} - {vt_result.get('malicious_count', 0)}/{vt_result.get('total_engines', 0)}")
                else:
                    logger.warning("VirusTotal غير مفعل في الإعدادات أو API key غير موجود")
                    vt_result = {'vt_score': 0.0, 'malicious_count': 0, 'total_engines': 0, 'status': 'disabled', 'message': 'VirusTotal غير مفعل'}
            except Exception as e:
                logger.error(f"خطأ في تحليل VirusTotal: {e}", exc_info=True)
                vt_result = {'vt_score': 0.0, 'malicious_count': 0, 'total_engines': 0, 'status': 'error', 'message': f'خطأ: {str(e)[:50]}'}
        
        if not guest_mode:
            def run_dynamic_analysis():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        analyze_url_dynamic(url, analysis_id, config.get('sandbox', {}).get('timeout', 8))
                    )
                    if isinstance(result, dict):
                        dynamic_result.update(result)
                    loop.close()
                except asyncio.TimeoutError:
                    logger.warning("انتهت مهلة التحليل الديناميكي")
                    dynamic_result['error'] = 'انتهت المهلة'
                except Exception as e:
                    logger.error(f"خطأ في التحليل الديناميكي: {e}")
                    dynamic_result['error'] = str(e)[:100]
            
            try:
                dynamic_thread = threading.Thread(target=run_dynamic_analysis, daemon=True)
                dynamic_thread.start()
                dynamic_thread.join(timeout=config.get('sandbox', {}).get('timeout', 8) + 5)
                if dynamic_thread.is_alive():
                    logger.warning("التحليل الديناميكي لم يكتمل في الوقت المحدد")
            except Exception as e:
                logger.error(f"خطأ في تشغيل التحليل الديناميكي: {e}")
        
        try:
            final_score, final_label = calculate_final_score(ml_result, dynamic_result, vt_result, heuristic_score)
        except Exception as e:
            logger.error(f"خطأ في حساب النتيجة النهائية: {e}")
            final_score = 0.0
            final_label = 'error'
        
        result = {
            'analysis_id': analysis_id,
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'final_score': float(final_score),
            'final_label': str(final_label),
            'ml_result': ml_result if isinstance(ml_result, dict) else {'label': 'error', 'confidence': 0.0, 'probabilities': {'safe': 0.0, 'suspicious': 0.0, 'malicious': 0.0}},
            'dynamic_result': dynamic_result if isinstance(dynamic_result, dict) else {
                'dynamic_score': 0.0,
                'suspicious_indicators': 0,
                'total_indicators': 0,
                'events': {
                    'downloads': [],
                    'form_submissions': [],
                    'redirects': [],
                    'suspicious_js': [],
                    'cookies': []
                }
            },
            'vt_result': vt_result if isinstance(vt_result, dict) else {'vt_score': 0.0, 'malicious_count': 0, 'total_engines': 98, 'status': 'error', 'message': 'خطأ في التحليل'},
            'heuristic_score': float(heuristic_score),
            'weights': config.get('weights', {}),
            'thresholds': config.get('thresholds', {})
        }
        
        try:
            analysis_results[analysis_id] = result
            record_analysis(url, result)
        except Exception as e:
            logger.warning(f"خطأ في حفظ النتيجة: {e}")
        
        logger.info(f"تم تحليل الرابط بنجاح: {final_label} - {final_score:.4f}")
        return result
        
    except Exception as e:
        logger.error(f"خطأ في تحليل الرابط: {e}", exc_info=True)
        return {
            'analysis_id': analysis_id,
            'url': str(url) if url else '',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)[:200],
            'final_score': 0.0,
            'final_label': 'error',
            'ml_result': ml_result if isinstance(ml_result, dict) else {'label': 'error', 'confidence': 0.0, 'probabilities': {'safe': 0.0, 'suspicious': 0.0, 'malicious': 0.0}},
            'dynamic_result': dynamic_result if isinstance(dynamic_result, dict) else {
                'dynamic_score': 0.0,
                'suspicious_indicators': 0,
                'total_indicators': 0,
                'events': {
                    'downloads': [],
                    'form_submissions': [],
                    'redirects': [],
                    'suspicious_js': [],
                    'cookies': []
                }
            },
            'vt_result': vt_result if isinstance(vt_result, dict) else {'vt_score': 0.0, 'malicious_count': 0, 'total_engines': 98, 'status': 'error', 'message': 'خطأ في التحليل'},
            'heuristic_score': float(heuristic_score)
        }

@app.route('/api/health', methods=['GET', 'OPTIONS', 'HEAD'])
def health():
    try:
        logger.debug("Health check request: %s %s", request.method, request.path)
        
        if request.method == 'OPTIONS':
            response = jsonify({})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS, HEAD')
            response.headers.add('Access-Control-Max-Age', '3600')
            return response
        
        if request.method == 'HEAD':
            response = jsonify({})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.status_code = 200
            return response
        
        response_data = {
            'ok': True, 
            'status': 'running', 
            'message': 'LinkScanne API is running',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        }
        
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS, HEAD')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.status_code = 200
        
        logger.debug("Health check OK")
        return response
        
    except Exception as e:
        logger.error(f"Error in health endpoint: {e}", exc_info=True)
        error_response = jsonify({
            'ok': False,
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        })
        error_response.headers.add('Access-Control-Allow-Origin', '*')
        error_response.status_code = 500
        return error_response

@app.route('/')
def index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

@app.route('/api/test', methods=['GET', 'POST'])
def test():
    return jsonify({'message': 'API is working', 'method': request.method})

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type يجب أن يكون application/json'}), 400
        
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({'error': 'بيانات غير صحيحة'}), 400
        
        url = (data.get('url') or '').strip()
        
        if not url:
            return jsonify({'error': 'الرابط مطلوب'}), 400
        
        if len(url) > 2048:
            return jsonify({'error': 'الرابط طويل جداً'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # التحقق من حالة المستخدم
        user = get_user_from_session()
        is_premium = user and user.get('is_premium', False)
        is_logged_in = user is not None
        
        logger.info(f"استلام طلب تحليل: {url} - مستخدم: {'مميز' if is_premium else 'عادي' if is_logged_in else 'زائر'}")
        
        # للمستخدمين غير المسجلين: تحليل بسيط فقط
        if not is_logged_in:
            # تحليل سريع للزوار — بدون VT ولا sandbox (كان يسبب انتظاراً طويلاً)
            result = analyze_url_comprehensive(url, guest_mode=True)
            
            if not isinstance(result, dict):
                raise ValueError("النتيجة غير صحيحة")
            
            # إرجاع نتيجة بسيطة فقط
            response = jsonify({
                'final_label': result.get('final_label', 'error'),
                'final_score': float(result.get('final_score', 0.0)),
                'is_guest': True,
                'message': 'للحصول على تحليل تفصيلي، يرجى تسجيل الدخول أو الاشتراك'
            })
            return add_cors_headers(response), 200
        
        # للمستخدمين المسجلين: تحليل كامل
        result = analyze_url_comprehensive(url)
        
        if not isinstance(result, dict):
            raise ValueError("النتيجة غير صحيحة")
        
        logger.info(f"إرسال النتيجة: {result.get('final_label', 'unknown')}")
        
        if result.get('error'):
            return jsonify({
                'error': result['error'][:200],
                'final_label': result.get('final_label', 'error'),
                'final_score': float(result.get('final_score', 0.0)),
                'ml_result': result.get('ml_result', {}),
                'dynamic_result': result.get('dynamic_result', {}),
                'vt_result': result.get('vt_result', {})
            }), 200
        
        if is_logged_in and result.get('analysis_id'):
            try:
                save_analysis(
                    result['analysis_id'],
                    user['id'],
                    url,
                    json.dumps(result),
                    datetime.now().isoformat()
                )
            except Exception as e:
                logger.error(f"خطأ في حفظ التحليل: {e}")
        
        response = jsonify(result)
        return add_cors_headers(response), 200
        
    except ValueError as e:
        logger.error(f"خطأ في القيم: {e}")
        return jsonify({'error': str(e)[:200]}), 400
    except KeyError as e:
        logger.error(f"مفتاح مفقود: {e}")
        return jsonify({'error': f'مفتاح مفقود: {str(e)}'}), 400
    except Exception as e:
        logger.error(f"خطأ في API التحليل: {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/analysis/<analysis_id>')
def get_analysis(analysis_id):
    try:
        if not analysis_id:
            return jsonify({'error': 'معرف التحليل مطلوب'}), 400

        result = None

        if analysis_id in analysis_results:
            result = analysis_results[analysis_id]
        else:
            analysis_data = get_analysis_by_id(analysis_id)
            if analysis_data:
                try:
                    result = json.loads(analysis_data)
                except Exception as e:
                    logger.warning(f"خطأ في تحليل بيانات التحليل المحفوظة: {e}")

        if result and isinstance(result, dict):
            return jsonify(result)
        else:
            return jsonify({'error': 'التحليل غير موجود'}), 404

    except Exception as e:
        logger.error(f"خطأ في الحصول على التحليل: {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/stats')
def get_stats_api():
    try:
        stats = get_stats()
        if not isinstance(stats, dict):
            stats = {
                'urls': {'total': 0, 'malicious': 0, 'suspicious': 0, 'safe': 0}, 
                'alerts': {'total': 0, 'active': 0},
                'analyses': {'total': 0, 'today': 0}
            }
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على الإحصائيات: {e}", exc_info=True)
        return jsonify({
            'urls': {'total': 0, 'malicious': 0, 'suspicious': 0, 'safe': 0},
            'alerts': {'total': 0, 'active': 0},
            'analyses': {'total': 0, 'today': 0},
            'error': str(e)[:100]
        }), 200

@app.route('/api/alerts')
def get_alerts():
    try:
        alerts = get_active_alerts()
        if not isinstance(alerts, list):
            alerts = []
        return jsonify(alerts)
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على التنبيهات: {e}", exc_info=True)
        return jsonify([]), 200

@app.route('/api/alerts/ack', methods=['POST'])
def acknowledge_alert_api():
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type يجب أن يكون application/json'}), 400
        
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'بيانات غير صحيحة'}), 400
        
        alert_id = data.get('alert_id')
        acknowledged_by = data.get('acknowledged_by', 'user')
        
        if not alert_id:
            return jsonify({'error': 'معرف التنبيه مطلوب'}), 400
        
        success = acknowledge_alert(str(alert_id), str(acknowledged_by))
        
        if success:
            return jsonify({'message': 'تم تأكيد التنبيه بنجاح'})
        else:
            return jsonify({'error': 'فشل في تأكيد التنبيه'}), 400
            
    except Exception as e:
        logger.error(f"خطأ في تأكيد التنبيه: {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/auth/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        user_id = session.get('user_id')
        logger.info(f"Logout request - user_id: {user_id}, session keys: {list(session.keys())}")
        
        # حذف الجلسة من Flask session
        session.clear()
        
        if user_id:
            try:
                delete_sessions_by_user(user_id)
                logger.info(f"Session deleted from database for user {user_id}")
            except Exception as e:
                logger.error(f"Error deleting session from database: {e}")
        
        response = jsonify({'message': 'تم تسجيل الخروج بنجاح', 'logged_out': True})
        response = add_cors_headers(response)
        logger.info("Logout successful")
        return response, 200
    except Exception as e:
        logger.error(f"خطأ في تسجيل الخروج: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500

@app.route('/api/auth/me', methods=['GET', 'OPTIONS'])
def get_current_user():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        logger.debug(
            "GET /api/auth/me keys=%s user_id=%s",
            list(session.keys()),
            session.get('user_id'),
        )
        user = get_user_from_session()
        
        if not user:
            logger.debug("auth/me: no logged-in user")
            response = jsonify({
                'user': None, 
                'is_logged_in': False, 
                'session_id': session.get('user_id'),
                'session_keys': list(session.keys()),
                'cookies': dict(request.cookies)
            })
            return add_cors_headers(response), 200
        
        response = jsonify({
            'user': user,
            'is_logged_in': True,
            'session_id': session.get('user_id'),
            'session_keys': list(session.keys())
        })
        return add_cors_headers(response), 200
    except Exception as e:
        logger.error(f"خطأ في الحصول على المستخدم: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500


@app.route('/api/user/profile', methods=['GET', 'PUT', 'OPTIONS'])
def user_profile():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)

    user = get_user_from_session()
    if not user:
        response = jsonify({'error': 'يجب تسجيل الدخول أولاً'})
        return add_cors_headers(response), 401

    if request.method == 'GET':
        row = get_user_profile_row(user['id'])
        if not row:
            response = jsonify({'error': 'المستخدم غير موجود'})
            return add_cors_headers(response), 404
        is_premium = row[3] == 1
        expires = row[4]
        if is_premium and expires:
            try:
                if datetime.fromisoformat(expires) < datetime.now():
                    is_premium = False
            except ValueError:
                pass
        payload = {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'is_premium': is_premium,
            'premium_expires_at': row[4],
            'created_at': row[5],
            'last_login': row[6],
        }
        return add_cors_headers(jsonify({'user': payload})), 200

    if request.method == 'PUT':
        if not request.is_json:
            response = jsonify({'error': 'Content-Type يجب أن يكون application/json'})
            return add_cors_headers(response), 400
        data = request.get_json(silent=True) or {}
        name = str(data.get('name', '')).strip()
        email = str(data.get('email', '')).strip()
        if not name or len(name) < 2:
            response = jsonify({'error': 'الاسم يجب أن يكون على الأقل حرفين'})
            return add_cors_headers(response), 400
        if not email or '@' not in email:
            response = jsonify({'error': 'البريد الإلكتروني غير صحيح'})
            return add_cors_headers(response), 400
        ok, err = update_user_name_email(user['id'], name, email)
        if not ok:
            msg = 'البريد مستخدم من حساب آخر' if err == 'email_taken' else 'تعذر التحديث'
            response = jsonify({'error': msg})
            return add_cors_headers(response), 400
        session['user_email'] = email
        session.modified = True
        row = get_user_profile_row(user['id'])
        payload = {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'is_premium': row[3] == 1,
            'premium_expires_at': row[4],
            'created_at': row[5],
            'last_login': row[6],
        }
        response = jsonify({'message': 'تم حفظ التغييرات', 'user': payload})
        return add_cors_headers(response), 200

    response = jsonify({'error': 'طريقة غير مسموحة'})
    return add_cors_headers(response), 405


@app.route('/api/user/password', methods=['PUT', 'OPTIONS'])
def user_password():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)

    user = get_user_from_session()
    if not user:
        response = jsonify({'error': 'يجب تسجيل الدخول أولاً'})
        return add_cors_headers(response), 401

    if not request.is_json:
        response = jsonify({'error': 'Content-Type يجب أن يكون application/json'})
        return add_cors_headers(response), 400

    data = request.get_json(silent=True) or {}
    current_pw = str(data.get('current_password', ''))
    new_pw = str(data.get('new_password', ''))
    if not current_pw or not new_pw:
        response = jsonify({'error': 'كلمة المرور الحالية والجديدة مطلوبة'})
        return add_cors_headers(response), 400
    if len(new_pw) < 6:
        response = jsonify({'error': 'كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل'})
        return add_cors_headers(response), 400

    row = get_user_by_email(user['email'])
    if not row or not verify_password(current_pw, row[3]):
        response = jsonify({'error': 'كلمة المرور الحالية غير صحيحة'})
        return add_cors_headers(response), 401

    update_user_password_hash_by_id(user['id'], hash_password(new_pw))
    response = jsonify({'message': 'تم تغيير كلمة المرور'})
    return add_cors_headers(response), 200


@app.route('/api/payment/subscribe', methods=['POST', 'OPTIONS'])
def subscribe():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        user = get_user_from_session()
        if not user:
            response = jsonify({'error': 'يجب تسجيل الدخول أولاً'})
            return add_cors_headers(response), 401
        
        if not request.is_json:
            response = jsonify({'error': 'Content-Type يجب أن يكون application/json'})
            return add_cors_headers(response), 400
        
        data = request.get_json(silent=True) or {}
        payment_method = data.get('payment_method', 'manual')  # manual, card, etc.
        
        # في الإنتاج، يجب التحقق من الدفع الفعلي
        # هنا نعتبر أن الدفع نجح
        expires_at = datetime.now() + timedelta(days=30)
        update_user_premium(user['id'], True, expires_at.isoformat())
        logger.info(f"تم تفعيل الاشتراك المميز للمستخدم: {user['email']}")
        
        response = jsonify({
            'message': 'تم تفعيل الاشتراك المميز بنجاح',
            'premium_expires_at': expires_at.isoformat()
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        logger.error(f"خطأ في الاشتراك: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500

@app.route('/api/config')
def get_config():
    try:
        public_config = {
            'weights': config.get('weights', {}),
            'thresholds': config.get('thresholds', {}),
            'virustotal_enabled': config.get('virustotal', {}).get('enabled', False)
        }
        return jsonify(public_config)
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على التكوين: {e}", exc_info=True)
        return jsonify({
            'weights': {'ml': 0.5, 'dynamic': 0.25, 'virustotal': 0.1, 'heuristic': 0.15},
            'thresholds': {'malicious': 0.75, 'suspicious': 0.45},
            'virustotal_enabled': False,
            'error': str(e)[:100]
        }), 200

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        if not request.is_json:
            response = jsonify({'error': 'Content-Type يجب أن يكون application/json'})
            return add_cors_headers(response), 400
        
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            response = jsonify({'error': 'بيانات غير صحيحة'})
            return add_cors_headers(response), 400
        
        name = str(data.get('name', '')).strip()
        email = str(data.get('email', '')).strip()
        password = str(data.get('password', '')).strip()
        
        if not name or len(name) < 2:
            response = jsonify({'error': 'الاسم يجب أن يكون على الأقل حرفين'})
            return add_cors_headers(response), 400
        if not email or '@' not in email:
            response = jsonify({'error': 'البريد الإلكتروني غير صحيح'})
            return add_cors_headers(response), 400
        if not password or len(password) < 6:
            response = jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'})
            return add_cors_headers(response), 400
        
        if email_exists(email):
            response = jsonify({'error': 'البريد الإلكتروني مستخدم بالفعل'})
            return add_cors_headers(response), 400

        password_hash = hash_password(password)
        created_at = datetime.now().isoformat()
        user_id = create_user(name, email, password_hash, created_at)
        
        # إنشاء جلسة وحفظها في قاعدة البيانات أيضاً
        # حفظ في Flask session
        session.permanent = True
        session['user_id'] = int(user_id)
        session['user_email'] = str(email[:100])
        session['logged_in_at'] = str(datetime.now().isoformat())
        session.modified = True
        
        try:
            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(days=30)
            create_session(session_id, user_id, expires_at)
            logger.info(f"Session saved to database: {session_id} for new user {user_id}")
            session['session_id'] = session_id
        except Exception as e:
            logger.error(f"Error saving session to database: {e}")
        
        user = {
            'id': user_id,
            'name': name[:100],
            'email': email[:100],
            'is_premium': False,
            'created_at': created_at
        }
        
        logger.info(f"تم إنشاء حساب جديد: {email}")
        
        response = jsonify({
            'message': 'تم إنشاء الحساب بنجاح',
            'user': user,
            'session_saved': True,
            'session_id': session.get('user_id')
        })
        # التأكد من إرسال الكوكي
        response = add_cors_headers(response)
        logger.info(f"Register response sent, session keys: {list(session.keys())}")
        return response, 200
        
    except Exception as e:
        logger.error(f"خطأ في إنشاء الحساب: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        response = jsonify({})
        return add_cors_headers(response)
    
    try:
        if not request.is_json:
            response = jsonify({'error': 'Content-Type يجب أن يكون application/json'})
            return add_cors_headers(response), 400
        
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            response = jsonify({'error': 'بيانات غير صحيحة'})
            return add_cors_headers(response), 400
        
        email = str(data.get('email', '')).strip()
        password = str(data.get('password', '')).strip()
        
        if not email or '@' not in email:
            response = jsonify({'error': 'البريد الإلكتروني غير صحيح'})
            return add_cors_headers(response), 400
        if not password:
            response = jsonify({'error': 'كلمة المرور مطلوبة'})
            return add_cors_headers(response), 400
        
        user_data = get_user_by_email(email)
        if not user_data:
            response = jsonify({'error': 'البريد الإلكتروني أو كلمة المرور غير صحيحة'})
            return add_cors_headers(response), 401

        if not verify_password(password, user_data[3]):
            response = jsonify({'error': 'البريد الإلكتروني أو كلمة المرور غير صحيحة'})
            return add_cors_headers(response), 401

        is_premium = user_data[4] == 1
        if is_premium and user_data[5]:
            expires_at = datetime.fromisoformat(user_data[5])
            if expires_at < datetime.now():
                is_premium = False
                set_user_premium_expired(user_data[0])

        update_user_last_login(user_data[0])
        
        # إنشاء جلسة وحفظها في قاعدة البيانات أيضاً
        user_id = int(user_data[0])
        
        # حفظ في Flask session
        session.permanent = True
        session['user_id'] = user_id
        session['user_email'] = str(user_data[2])
        session['logged_in_at'] = str(datetime.now().isoformat())
        session.modified = True
        
        try:
            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(days=30)
            create_session(session_id, user_id, expires_at)
            logger.info(f"Session saved to database: {session_id} for user {user_id}")
            session['session_id'] = session_id
        except Exception as e:
            logger.error(f"Error saving session to database: {e}")

        logger.info(f"Session created for user {user_data[0]}, session keys: {list(session.keys())}")
        logger.info(f"Session permanent: {session.permanent}, Session modified: {session.modified}")
        logger.info(f"Session data: user_id={session.get('user_id')}, user_email={session.get('user_email')}")
        
        user = {
            'id': user_data[0],
            'name': user_data[1],
            'email': user_data[2],
            'is_premium': is_premium,
            'last_login': datetime.now().isoformat()
        }
        
        logger.info(f"تم تسجيل الدخول: {email} - {'مميز' if is_premium else 'عادي'}")
        
        # التأكد من أن الجلسة محفوظة قبل إرسال الرد
        # Flask يحفظ الجلسة تلقائياً في after_request إذا كانت modified=True
        # لكن نحتاج للتأكد من أن البيانات موجودة
        logger.info(f"Before response - Session keys: {list(session.keys())}, user_id: {session.get('user_id')}")
        
        response = jsonify({
            'message': 'تم تسجيل الدخول بنجاح',
            'user': user,
            'session_saved': True,
            'session_id': session.get('user_id'),
            'session_keys': list(session.keys())
        })
        # التأكد من إرسال الكوكي
        response = add_cors_headers(response)
        # إضافة معلومات الكوكي في الرد
        logger.info(f"Login response sent, session keys: {list(session.keys())}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Session cookie will be set: {app.config.get('SESSION_COOKIE_NAME')}")
        
        return response, 200
        
    except Exception as e:
        logger.error(f"خطأ في تسجيل الدخول: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type يجب أن يكون application/json'}), 400
        
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'بيانات غير صحيحة'}), 400
        
        email = str(data.get('email', '')).strip()
        
        if not email or '@' not in email:
            return jsonify({'error': 'البريد الإلكتروني غير صحيح'}), 400
        
        logger.info(f"طلب استعادة كلمة المرور: {email}")
        
        return jsonify({
            'message': 'تم إرسال رابط استعادة كلمة المرور إلى بريدك الإلكتروني'
        })
        
    except Exception as e:
        logger.error(f"خطأ في استعادة كلمة المرور: {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/save-result', methods=['POST'])
def save_result():
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type يجب أن يكون application/json'}), 400
        
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'بيانات غير صحيحة'}), 400
        
        url = str(data.get('url', '')).strip()
        result = data.get('result', {})
        user_id = data.get('user_id')
        
        if not url:
            return jsonify({'error': 'الرابط مطلوب'}), 400
        if not isinstance(result, dict):
            return jsonify({'error': 'النتيجة يجب أن تكون كائن'}), 400
        if not user_id:
            return jsonify({'error': 'معرف المستخدم مطلوب'}), 400
        
        saved_result = {
            'id': len(analysis_results) + 1,
            'url': url[:500],
            'result': result,
            'user_id': str(user_id),
            'saved_at': datetime.now().isoformat()
        }
        
        logger.info(f"تم حفظ نتيجة التحليل: {url} للمستخدم {user_id}")
        
        return jsonify({
            'message': 'تم حفظ النتيجة بنجاح',
            'saved_result': saved_result
        })
        
    except Exception as e:
        logger.error(f"خطأ في حفظ النتيجة: {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/saved-results', methods=['GET', 'OPTIONS'])
def get_saved_results():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    
    try:
        # التحقق من تسجيل الدخول - إرجاع فقط تحليلات المستخدم الحالي
        user = get_user_from_session()
        user_id = user['id'] if user else None
        
        saved_results = []
        
        if user_id:
            try:
                rows = get_saved_analyses_by_user(user_id)
                for row in rows:
                    analysis_data = {}
                    try:
                        if row[2]:
                            analysis_data = json.loads(row[2])
                    except Exception:
                        pass
                    final_label = analysis_data.get('final_label', 'error')
                    final_score = analysis_data.get('final_score', 0.0)
                    saved_results.append({
                        'id': row[0],
                        'url': row[1],
                        'analysis_data': analysis_data,
                        'final_label': final_label,
                        'final_score': final_score,
                        'created_at': row[3],
                        'updated_at': row[3]
                    })
            except Exception as e:
                logger.warning(f"خطأ في جلب التحليلات من قاعدة بيانات المستخدمين: {e}")
        
        # التحليلات المحفوظة من linkScanne.db فقط (جدول saved_analyses)
        logger.info(f"تم طلب النتائج المحفوظة: {len(saved_results)} نتيجة للمستخدم: {user_id if user_id else 'غير مسجل'}")
        
        response = jsonify({
            'saved_results': saved_results,
            'count': len(saved_results)
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على النتائج المحفوظة: {e}", exc_info=True)
        response = jsonify({
            'saved_results': [],
            'count': 0,
            'error': str(e)[:100]
        })
        return add_cors_headers(response), 200

@app.route('/api/analysis/<analysis_id>', methods=['DELETE', 'OPTIONS'])
def delete_analysis(analysis_id):
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    
    try:
        # التحقق من تسجيل الدخول
        user = get_user_from_session()
        if not user:
            response = jsonify({'error': 'يجب تسجيل الدخول أولاً'})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Credentials', 'true')
            return response, 401
        
        if not analysis_id:
            response = jsonify({'error': 'معرف التحليل مطلوب'})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Credentials', 'true')
            return response, 400
        
        deleted = False
        
        try:
            if db_delete_analysis(analysis_id, user['id']):
                deleted = True
        except Exception as e:
            logger.warning(f"خطأ في حذف من قاعدة بيانات المستخدمين: {e}")
        
        # حذف من الذاكرة إذا كان موجوداً
        if analysis_id in analysis_results:
            del analysis_results[analysis_id]
            deleted = True
        
        if deleted:
            logger.info(f"تم حذف التحليل: {analysis_id} للمستخدم: {user['email']}")
            response = jsonify({'message': 'تم حذف التحليل بنجاح'})
            return add_cors_headers(response), 200
        else:
            response = jsonify({'error': 'التحليل غير موجود أو ليس لديك صلاحية لحذفه'})
            return add_cors_headers(response), 404
        
    except Exception as e:
        logger.error(f"خطأ في حذف التحليل: {e}", exc_info=True)
        response = jsonify({'error': str(e)[:200]})
        return add_cors_headers(response), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/<path:path>')
def serve_public(path):
    if path.startswith('api'):
        abort(404)
    safe = path.replace('\\', '/').strip()
    if not safe or '..' in safe:
        abort(404)
    full = os.path.normpath(os.path.join(PUBLIC_DIR, safe))
    pub_norm = os.path.normpath(PUBLIC_DIR)
    if not full.startswith(pub_norm):
        abort(404)
    if os.path.isfile(full):
        return send_from_directory(PUBLIC_DIR, safe)
    abort(404)


@app.errorhandler(404)
def not_found(error):
    path = request.path if hasattr(request, 'path') else 'unknown'
    logger.warning(f"404 - {request.method} {path}")
    if path.startswith('/api/'):
        response = jsonify({'error': 'API endpoint not found', 'path': path})
    else:
        response = jsonify({'error': 'الصفحة غير موجودة', 'path': path})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 - {str(error)}", exc_info=True)
    return jsonify({'error': 'خطأ داخلي في الخادم'}), 500

@app.errorhandler(400)
def bad_request(error):
    logger.warning(f"400 - {str(error)}")
    return jsonify({'error': 'طلب غير صحيح'}), 400

@app.errorhandler(405)
def method_not_allowed(error):
    logger.warning(f"405 - {request.method} {request.path}")
    return jsonify({'error': 'الطريقة غير مسموحة'}), 405

if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(__file__), 'logs'), exist_ok=True)
    app_cfg = config.get('app', {})
    debug = app_cfg.get('debug', True)
    run_kwargs = {
        'host': app_cfg.get('host', '127.0.0.1'),
        'port': app_cfg.get('port', 5000),
        'debug': debug,
        'threaded': True,
    }
    if debug:
        # إيقاف إعادة التشغيل المستمرة عند لمس أدوات أخرى لملفات داخل site-packages (pytest، إلخ)
        run_kwargs['exclude_patterns'] = ['*site-packages*']
        run_kwargs['reloader_type'] = 'stat'
    app.run(**run_kwargs)
