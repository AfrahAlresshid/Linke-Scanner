// عنوان الـ API:
// - عند فتح الموقع من Flask على المنفذ 5000 (مُستحسن) → نفس المنشأ، كوكي الجلسة يعمل.
// - Live Server (مثلاً 5500) → طلبات من منفذ آخر = cross-origin وقد تفشل الجلسة في المتصفح.
(function () {
    var loc = window.location;
    var port = loc.port;
    var h = loc.hostname;
    // إنتاج (Render، نطاق حقيقي): نفس المنشأ — الطلبات إلى /api على نفس الخادم
    if (h !== '127.0.0.1' && h !== 'localhost') {
        window.API_BASE = loc.origin;
    } else if (port === '5000' || port === '') {
        window.API_BASE = loc.origin;
    } else {
        // Live Server (مثلاً 5500) → الـ API على Flask 5000
        window.API_BASE = loc.protocol + '//' + h + ':5000';
    }
})();
var API_BASE = window.API_BASE;
