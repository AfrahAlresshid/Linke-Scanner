# LinkScanne - نظام تحليل الروابط الذكي

## تشغيل المشروع

**1. تشغيل السيرفر (الباك اند):**
```bash
python app.py
```

**2. فتح الموقع:**
- افتح مجلد `public` بـ **Live Server** (امتداد VS Code) أو أي خادم استاتيكي
- أو انقر يمين على `public/index.html` ← Open with Live Server

السيرفر يعمل على: **http://127.0.0.1:5000** (API فقط)  
الموقع: HTML/CSS/JS في مجلد `public/` يُفتح عبر Live Server

*(أول تشغيل: `pip install -r requirements.txt` ثم `playwright install chromium` ثم `python data/Model Trining2.py`)*

---

## نظرة عامة

LinkScanne هو نظام ويب متكامل لتحليل الروابط واكتشاف الروابط الخبيثة باستخدام تقنيات متقدمة تشمل:

- **التحليل الإحصائي بالذكاء الاصطناعي**: استخدام نماذج التعلم الآلي لتصنيف الروابط
- **التحليل الديناميكي**: فحص الروابط داخل بيئة Sandbox آمنة
- **التحليل الاستدلالي**: استخدام القواعد والأنماط المعروفة
- **التكامل مع VirusTotal**: الاستفادة من قاعدة البيانات العالمية للروابط الخبيثة
- **نظام التنبيهات**: مراقبة فورية للروابط المشبوهة

## الميزات الرئيسية

### 1. تحليل متعدد المستويات
- **التعلم الآلي**: تصنيف الروابط بناءً على الميزات اللغوية والإحصائية
- **التحليل الديناميكي**: فحص سلوك الرابط في بيئة معزولة
- **VirusTotal**: مقارنة مع قاعدة البيانات العالمية
- **التحليل الاستدلالي**: فحص الأنماط المشبوهة

### 2. واجهة مستخدم متقدمة
- تصميم دارك مود احترافي
- واجهة متجاوبة تعمل على جميع الأجهزة
- عرض النتائج بشكل تفصيلي وواضح
- تحديث فوري للإحصائيات والتنبيهات

### 3. نظام التنبيهات الذكي
- مراقبة تلقائية للروابط المشبوهة
- تنبيهات فورية عند اكتشاف أنماط خطيرة
- إدارة شاملة للتنبيهات

## متطلبات النظام

- Python 3.10.6 أو أحدث
- نظام تشغيل Windows/Linux/macOS
- ذاكرة وصول عشوائي: 4 GB على الأقل
- مساحة تخزين: 2 GB متاحة

## التثبيت والتشغيل

### 1. تثبيت المتطلبات

```bash
pip install -r requirements.txt
```

### 2. تثبيت متصفحات Playwright

```bash
playwright install chromium
```

### 3. تدريب النموذج

```bash
python data/Model Trining2.py
```

### 4. إعداد VirusTotal API (اختياري)

1. احصل على مفتاح API من [VirusTotal](https://www.virustotal.com/gui/my-apikey)
2. افتح ملف `config.json`
3. استبدل `YOUR_API_KEY_HERE` بمفتاح API الخاص بك:

```json
{
  "virustotal": {
    "enabled": true,
    "api_key": "مفتاح_API_الخاص_بك",
    "cache_hours": 24
  }
}
```

### 5. تشغيل الخادم
```bash
python app.py
```

### 6. الوصول للتطبيق

افتح المتصفح وانتقل إلى: `http://127.0.0.1:5000`

## استخدام API

### تحليل رابط

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### الحصول على الإحصائيات

```bash
curl http://127.0.0.1:5000/api/stats
```

### الحصول على التنبيهات النشطة

```bash
curl http://127.0.0.1:5000/api/alerts
```

### تأكيد تنبيه

```bash
curl -X POST http://127.0.0.1:5000/api/alerts/ack \
  -H "Content-Type: application/json" \
  -d '{"alert_id": 1}'
```

## هيكل المشروع

```
LinkScanne/
├── app.py                 # تطبيق Flask الرئيسي
├── requirements.txt       # المتطلبات
├── config.json           # التكوين
├── README.md             # هذا الملف
├── models/               # نماذج التعلم الآلي
│   ├── predict.py        # توقع النتائج
│   └── model.joblib      # النموذج المدرب
├── data/                 # بيانات التدريب
│   └── Model Trining2.py # تدريب النموذج
├── public/               # الملفات الأمامية
│   ├── index.html        # الصفحة الرئيسية
│   ├── css/
│   │   └── style.css     # التصميم
│   ├── js/
│   │   └── app.js        # JavaScript
│   └── *.html            # صفحات HTML الأخرى
├── sandbox/              # نظام Sandbox
│   ├── worker.py         # عامل التحليل الديناميكي
│   ├── config.json       # تكوين Sandbox
│   └── jobs/             # ملفات العمل المؤقتة
├── integrations/         # التكاملات الخارجية
│   └── virustotal.py     # تكامل VirusTotal
├── alerts/               # نظام التنبيهات
│   ├── monitor.py        # مراقب التنبيهات
│   └── rules.json        # قواعد التنبيهات
├── vt_cache/             # كاش VirusTotal
├── logs/                 # ملفات السجل
└── db/                   # قاعدة البيانات
    └── alerts.db         # قاعدة بيانات التنبيهات
```

## التكوين

### ملف config.json

```json
{
  "app": {
    "debug": true,
    "host": "127.0.0.1",
    "port": 5000,
    "secret_key": "linkScanne_secret_key_2024"
  },
  "virustotal": {
    "enabled": true,
    "api_key": "YOUR_API_KEY_HERE",
    "cache_hours": 24
  },
  "weights": {
    "ml": 0.5,
    "dynamic": 0.25,
    "heuristic": 0.15,
    "virustotal": 0.10
  },
  "thresholds": {
    "malicious": 0.75,
    "suspicious": 0.45
  },
  "sandbox": {
    "timeout": 15,
    "playwright_browsers_path": "./sandbox/browsers"
  },
  "alerts": {
    "threshold_count": 5,
    "window_seconds": 300
  }
}
```

## ملاحظات مهمة

### نظام Sandbox

- يستخدم Playwright لتحليل الروابط ديناميكياً
- يعمل في بيئة معزولة مع timeout قابل للتكوين
- يراقب الأحداث المشبوهة مثل التحميلات والنماذج
- لا يحفظ أي ملفات خارج مجلد المشروع

### الأمان

- جميع العمليات تتم محلياً
- لا يتم إرسال بيانات خارجية إلا لـ VirusTotal (اختياري)
- قاعدة البيانات محلية
- السجلات محفوظة محلياً

### الأداء

- استخدام الكاش لتقليل استعلامات VirusTotal
- معالجة متوازية للتحليل الديناميكي
- قاعدة بيانات SQLite محلية سريعة

## استكشاف الأخطاء

### مشاكل شائعة

1. **خطأ في تحميل النموذج**: تأكد من تشغيل `python data/Model Trining2.py`
2. **خطأ في VirusTotal**: تحقق من صحة مفتاح API
3. **خطأ في Sandbox**: تأكد من تثبيت Playwright بشكل صحيح
4. **خطأ في قاعدة البيانات**: تحقق من صلاحيات الكتابة في مجلد `db/`

### ملفات السجل

- `logs/app.log`: سجل التطبيق الرئيسي
- `logs/run.log`: سجل عملية التشغيل

## التطوير

### إضافة ميزات جديدة

1. **إضافة محرك تحليل جديد**: أنشئ ملف في مجلد `integrations/`
2. **تعديل الأوزان**: حدث ملف `config.json`
3. **إضافة قواعد تنبيهات**: حدث ملف `alerts/rules.json`

### الاختبار

```bash
# اختبار النموذج
python models/predict.py

# اختبار VirusTotal
python integrations/virustotal.py

# اختبار Sandbox
python sandbox/worker.py

# اختبار التنبيهات
python alerts/monitor.py
```

## الدعم

للحصول على المساعدة أو الإبلاغ عن مشاكل، يرجى مراجعة ملفات السجل في مجلد `logs/`.