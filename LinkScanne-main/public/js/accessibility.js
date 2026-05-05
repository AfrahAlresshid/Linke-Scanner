/**
 * LinkScanne - إمكانية الوصول ودعم ضعاف البصر (WCAG 2.2)
 * قراءة صوتية عبر Web Speech API
 */
(function () {
    'use strict';

    var speechSynth = window.speechSynthesis;
    var voiceEnabled = localStorage.getItem('linkScanne_voiceEnabled') !== 'false';

    function getPreferredVoice(lang) {
        if (!speechSynth) return null;

        // محاولة الحصول على الأصوات - قد تحتاج إلى إعادة المحاولة
        var voices = speechSynth.getVoices();

        // إذا لم تكن الأصوات جاهزة، انتظر قليلاً
        if (voices.length === 0) {
            // إعادة المحاولة بعد تحميل الأصوات
            if (speechSynth.onvoiceschanged !== undefined) {
                speechSynth.onvoiceschanged = function () {
                    voices = speechSynth.getVoices();
                };
            }
            voices = speechSynth.getVoices();
        }

        // تحديد اللغة المطلوبة
        var targetLang = lang || 'ar';
        var isArabic = targetLang.indexOf('ar') === 0 || targetLang === 'ar';

        if (isArabic) {
            // البحث عن صوت عربي - أولوية للأصوات العربية السعودية
            var arSAVoices = voices.filter(function (v) {
                return v.lang === 'ar-SA' || v.lang === 'ar';
            });
            if (arSAVoices.length > 0) return arSAVoices[0];

            var arVoices = voices.filter(function (v) {
                return v.lang.indexOf('ar') === 0 || v.lang.toLowerCase().indexOf('arabic') !== -1;
            });
            if (arVoices.length > 0) return arVoices[0];
        } else {
            // البحث عن صوت إنجليزي - أولوية للأصوات الأمريكية
            var enUSVoices = voices.filter(function (v) {
                return v.lang === 'en-US' || v.lang === 'en';
            });
            if (enUSVoices.length > 0) return enUSVoices[0];

            var enVoices = voices.filter(function (v) {
                return v.lang.indexOf('en') === 0 || v.lang.toLowerCase().indexOf('english') !== -1;
            });
            if (enVoices.length > 0) return enVoices[0];
        }

        // Fallback: البحث عن أي صوت يطابق اللغة
        var langPrefix = targetLang.substring(0, 2);
        var langMatch = voices.filter(function (v) {
            return v.lang.indexOf(langPrefix) === 0;
        });
        if (langMatch.length > 0) return langMatch[0];

        // Fallback: أي صوت متاح
        return voices[0] || null;
    }

    function speak(text, lang) {
        if (!speechSynth || !text) return;

        // الحصول على اللغة الحالية من الزر المختار - 100% دقة
        var currentLanguage = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                currentLanguage = currentLang() || 'ar';
            } else {
                currentLanguage = currentLang || 'ar';
            }
        }

        // التأكد من أن اللغة صحيحة
        if (currentLanguage !== 'ar' && currentLanguage !== 'en') {
            currentLanguage = 'ar'; // افتراضي عربي
        }

        // تحديد لغة الكلام حسب اللغة المختارة من الزر
        // إذا تم تمرير lang، استخدمه، وإلا استخدم اللغة الحالية من الزر
        var speechLang = lang;
        if (!speechLang) {
            speechLang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        } else {
            // التأكد من أن اللغة الممررة صحيحة
            if (speechLang.indexOf('ar') === 0) {
                currentLanguage = 'ar';
            } else if (speechLang.indexOf('en') === 0) {
                currentLanguage = 'en';
            }
        }

        speechSynth.cancel();
        var u = new SpeechSynthesisUtterance(text);
        u.lang = speechLang;
        u.rate = 0.9;
        u.pitch = 1;

        // اختيار الصوت المناسب حسب اللغة المختارة
        var voice = getPreferredVoice(speechLang);
        if (voice) {
            u.voice = voice;
        }

        speechSynth.speak(u);
    }

    function stopSpeak() {
        if (speechSynth) speechSynth.cancel();
    }

    function isVoiceEnabled() {
        return voiceEnabled;
    }

    function setVoiceEnabled(enabled) {
        voiceEnabled = !!enabled;
        localStorage.setItem('linkScanne_voiceEnabled', enabled ? 'true' : 'false');
    }

    function speakAnalysisResult(label, score, url) {
        // الحصول على اللغة الحالية من الزر المختار - 100% دقة
        var lang = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                lang = currentLang() || 'ar';
            } else {
                lang = currentLang || 'ar';
            }
        }

        // التأكد من أن اللغة صحيحة
        if (lang !== 'ar' && lang !== 'en') {
            lang = 'ar'; // افتراضي عربي
        }

        var labelText = label === 'safe' ? (lang === 'ar' ? 'آمن' : 'Safe') :
            label === 'suspicious' ? (lang === 'ar' ? 'مشبوه' : 'Suspicious') :
                label === 'malicious' ? (lang === 'ar' ? 'خبيث' : 'Malicious') :
                    (lang === 'ar' ? 'خطأ' : 'Error');
        var msg = '';
        if (lang === 'ar') {
            msg = 'النتيجة: الرابط ' + labelText + '. النسبة ' + (score ? Math.round(score) + ' بالمئة.' : '');
            if (url && url.length < 80) msg += ' الرابط المُحلّل: ' + url;
        } else {
            msg = 'Result: Link is ' + labelText + '. ' + (score ? Math.round(score) + ' percent.' : '');
            if (url && url.length < 80) msg += ' Analyzed link: ' + url;
        }
        // استخدام اللغة المختارة بالضبط - 100% دقة
        speak(msg, lang === 'ar' ? 'ar-SA' : 'en-US');
    }

    function speakDetailedResults(data) {
        if (!voiceEnabled || !data) return;

        // الحصول على اللغة الحالية من الزر المختار - 100% دقة
        var lang = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                lang = currentLang() || 'ar';
            } else {
                lang = currentLang || 'ar';
            }
        }

        // التأكد من أن اللغة صحيحة
        if (lang !== 'ar' && lang !== 'en') {
            lang = 'ar'; // افتراضي عربي
        }

        var fullText = '';
        var t = typeof translate !== 'undefined' ? translate : function (k) { return k; };

        if (lang === 'ar') {
            fullText = 'نتائج التحليل التفصيلية. ';

            var label = data.final_label || 'error';
            var labelText = label === 'safe' ? 'آمن' : label === 'suspicious' ? 'مشبوه' : label === 'malicious' ? 'خبيث' : 'خطأ';
            var score = parseFloat(((data.final_score || 0) * 100).toFixed(1));

            fullText += 'التصنيف النهائي: ' + labelText + '. النتيجة النهائية: ' + score + ' بالمئة. ';

            if (data.ml_result && data.ml_result.label) {
                var mlLabel = data.ml_result.label === 'safe' ? 'آمن' : data.ml_result.label === 'suspicious' ? 'مشبوه' : data.ml_result.label === 'malicious' ? 'خبيث' : 'خطأ';
                var mlConf = ((data.ml_result.confidence || 0) * 100).toFixed(1);
                fullText += 'تحليل التعلم الآلي: التصنيف ' + mlLabel + '. الثقة ' + mlConf + ' بالمئة. ';

                var probs = data.ml_result.probabilities || {};
                if (probs.safe !== undefined) fullText += 'احتمالية آمن: ' + (probs.safe * 100).toFixed(1) + ' بالمئة. ';
                if (probs.suspicious !== undefined) fullText += 'احتمالية مشبوه: ' + (probs.suspicious * 100).toFixed(1) + ' بالمئة. ';
                if (probs.malicious !== undefined) fullText += 'احتمالية خبيث: ' + (probs.malicious * 100).toFixed(1) + ' بالمئة. ';
            }

            if (data.dynamic_result) {
                var dynScore = ((data.dynamic_result.dynamic_score || 0) * 100).toFixed(1);
                var dynSuspicious = data.dynamic_result.suspicious_indicators || 0;
                var dynTotal = data.dynamic_result.total_indicators || 0;
                fullText += 'التحليل الديناميكي: النتيجة ' + dynScore + ' بالمئة. المؤشرات المشبوهة: ' + dynSuspicious + ' من إجمالي ' + dynTotal + ' مؤشر. ';

                var events = data.dynamic_result.events || {};
                var downloads = Array.isArray(events.downloads) ? events.downloads.length : 0;
                var forms = Array.isArray(events.form_submissions) ? events.form_submissions.length : 0;
                var redirects = Array.isArray(events.redirects) ? events.redirects.length : 0;
                var js = Array.isArray(events.suspicious_js) ? events.suspicious_js.length : 0;
                var cookies = Array.isArray(events.cookies) ? events.cookies.length : 0;

                fullText += 'الأحداث المكتشفة: التحميلات ' + downloads + '. النماذج ' + forms + '. إعادة التوجيه ' + redirects + '. JavaScript مشبوه ' + js + '. الكوكيز ' + cookies + '. ';
            }

            if (data.vt_result) {
                var vtScore = ((data.vt_result.vt_score || 0) * 100).toFixed(1);
                var vtMalicious = data.vt_result.malicious_count || 0;
                var vtTotal = data.vt_result.total_engines || 98;
                var vtStatus = data.vt_result.status || 'clean';
                var statusText = vtStatus === 'clean' ? 'نظيف' : vtStatus === 'malicious' ? 'خبيث' : vtStatus === 'suspicious' ? 'مشبوه' : 'غير معروف';
                fullText += 'تحليل VirusTotal: النتيجة ' + vtScore + ' بالمئة. المحركات الخبيثة: ' + vtMalicious + ' من ' + vtTotal + '. الحالة: ' + statusText + '. ';
            }

            if (data.heuristic_score !== undefined) {
                var heuristicValue = ((data.heuristic_score || 0) * 100).toFixed(1);
                fullText += 'التحليل الاستدلالي: النتيجة ' + heuristicValue + ' بالمئة. ';
            }
        } else {
            fullText = 'Detailed analysis results. ';

            var label = data.final_label || 'error';
            var labelText = label === 'safe' ? 'Safe' : label === 'suspicious' ? 'Suspicious' : label === 'malicious' ? 'Malicious' : 'Error';
            var score = parseFloat(((data.final_score || 0) * 100).toFixed(1));

            fullText += 'Final classification: ' + labelText + '. Final result: ' + score + ' percent. ';

            if (data.ml_result && data.ml_result.label) {
                var mlLabel = data.ml_result.label === 'safe' ? 'Safe' : data.ml_result.label === 'suspicious' ? 'Suspicious' : data.ml_result.label === 'malicious' ? 'Malicious' : 'Error';
                var mlConf = ((data.ml_result.confidence || 0) * 100).toFixed(1);
                fullText += 'Machine Learning analysis: Classification ' + mlLabel + '. Confidence ' + mlConf + ' percent. ';

                var probs = data.ml_result.probabilities || {};
                if (probs.safe !== undefined) fullText += 'Safe probability: ' + (probs.safe * 100).toFixed(1) + ' percent. ';
                if (probs.suspicious !== undefined) fullText += 'Suspicious probability: ' + (probs.suspicious * 100).toFixed(1) + ' percent. ';
                if (probs.malicious !== undefined) fullText += 'Malicious probability: ' + (probs.malicious * 100).toFixed(1) + ' percent. ';
            }

            if (data.dynamic_result) {
                var dynScore = ((data.dynamic_result.dynamic_score || 0) * 100).toFixed(1);
                var dynSuspicious = data.dynamic_result.suspicious_indicators || 0;
                var dynTotal = data.dynamic_result.total_indicators || 0;
                fullText += 'Dynamic analysis: Result ' + dynScore + ' percent. Suspicious indicators: ' + dynSuspicious + ' out of total ' + dynTotal + ' indicators. ';

                var events = data.dynamic_result.events || {};
                var downloads = Array.isArray(events.downloads) ? events.downloads.length : 0;
                var forms = Array.isArray(events.form_submissions) ? events.form_submissions.length : 0;
                var redirects = Array.isArray(events.redirects) ? events.redirects.length : 0;
                var js = Array.isArray(events.suspicious_js) ? events.suspicious_js.length : 0;
                var cookies = Array.isArray(events.cookies) ? events.cookies.length : 0;

                fullText += 'Detected events: Downloads ' + downloads + '. Forms ' + forms + '. Redirects ' + redirects + '. Suspicious JavaScript ' + js + '. Cookies ' + cookies + '. ';
            }

            if (data.vt_result) {
                var vtScore = ((data.vt_result.vt_score || 0) * 100).toFixed(1);
                var vtMalicious = data.vt_result.malicious_count || 0;
                var vtTotal = data.vt_result.total_engines || 98;
                var vtStatus = data.vt_result.status || 'clean';
                var statusText = vtStatus === 'clean' ? 'clean' : vtStatus === 'malicious' ? 'malicious' : vtStatus === 'suspicious' ? 'suspicious' : 'unknown';
                fullText += 'VirusTotal analysis: Result ' + vtScore + ' percent. Malicious engines: ' + vtMalicious + ' out of ' + vtTotal + '. Status: ' + statusText + '. ';
            }

            if (data.heuristic_score !== undefined) {
                var heuristicValue = ((data.heuristic_score || 0) * 100).toFixed(1);
                fullText += 'Heuristic analysis: Result ' + heuristicValue + ' percent. ';
            }
        }

        // استخدام اللغة المختارة بالضبط - 100% دقة
        var speechLang = lang === 'ar' ? 'ar-SA' : 'en-US';
        speak(fullText, speechLang);
    }

    function announceResult(label, score, autoSpeak) {
        // الحصول على اللغة الحالية من الزر المختار - 100% دقة
        var lang = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                lang = currentLang() || 'ar';
            } else {
                lang = currentLang || 'ar';
            }
        }

        // التأكد من أن اللغة صحيحة
        if (lang !== 'ar' && lang !== 'en') {
            lang = 'ar'; // افتراضي عربي
        }

        var el = document.getElementById('result-announce');
        if (el) {
            var labelText = label === 'safe' ? (lang === 'ar' ? 'آمن' : 'Safe') :
                label === 'suspicious' ? (lang === 'ar' ? 'مشبوه' : 'Suspicious') :
                    label === 'malicious' ? (lang === 'ar' ? 'خبيث' : 'Malicious') :
                        (lang === 'ar' ? 'خطأ' : 'Error');
            if (lang === 'ar') {
                el.textContent = 'نتيجة التحليل: الرابط ' + labelText + '. النسبة ' + (score ? Math.round(score) + ' بالمئة.' : '');
            } else {
                el.textContent = 'Analysis result: Link is ' + labelText + '. ' + (score ? Math.round(score) + ' percent.' : '');
            }
        }
        if (autoSpeak !== false && voiceEnabled) {
            setTimeout(function () { speakAnalysisResult(label, score); }, 300);
        }
    }

    window.A11y = {
        speak: speak,
        stop: stopSpeak,
        isVoiceEnabled: isVoiceEnabled,
        setVoiceEnabled: setVoiceEnabled,
        speakAnalysisResult: speakAnalysisResult,
        speakDetailedResults: speakDetailedResults,
        announceResult: announceResult
    };
})();
