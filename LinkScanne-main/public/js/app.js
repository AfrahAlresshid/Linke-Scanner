(function () {
    'use strict';

    var form = document.getElementById('analysis-form');
    var urlInput = document.getElementById('url-input');
    var analyzeBtn = document.getElementById('analyze-btn');
    var resultsOverlay = document.getElementById('results-overlay');
    var resultSummary = document.getElementById('result-summary');
    var resultDetails = document.getElementById('result-details');
    var loadingOverlay = document.getElementById('loading-overlay');
    var loadingIndicator = document.getElementById('loading-indicator');
    var errorModal = document.getElementById('error-modal');
    var errorMessage = document.getElementById('error-message');
    var errorClose = document.getElementById('error-close');
    var successModal = document.getElementById('success-modal');
    var successMessage = document.getElementById('success-message');
    var successClose = document.getElementById('success-close');
    var toastContainer = document.getElementById('toast-container');
    var closeResults = document.getElementById('close-results');

    var API = (typeof API_BASE !== 'undefined') ? API_BASE : 'http://127.0.0.1:5000';

    function showLoading() {
        if (loadingOverlay) loadingOverlay.style.display = 'flex';
        if (loadingIndicator) loadingIndicator.style.display = 'block';
    }

    function hideLoading() {
        if (loadingOverlay) loadingOverlay.style.display = 'none';
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    function showError(msg) {
        if (errorMessage) errorMessage.textContent = msg || 'حدث خطأ';
        if (errorModal) {
            errorModal.style.display = 'flex';
            var content = errorModal.querySelector('.notification-content');
            if (content) {
                content.className = 'notification-content error';
            }
        }
    }

    function hideError() {
        if (errorModal) errorModal.style.display = 'none';
    }

    function showSuccess(msg) {
        if (successMessage) successMessage.textContent = msg || 'تم بنجاح';
        if (successModal) {
            successModal.style.display = 'flex';
            var content = successModal.querySelector('.notification-content');
            if (content) {
                content.className = 'notification-content success';
            }
        }
    }

    function hideSuccess() {
        if (successModal) successModal.style.display = 'none';
    }

    function showToast(message, type) {
        type = type || 'info';
        if (typeof LinkNotify !== 'undefined' && LinkNotify.show) {
            LinkNotify.show(message, type, 5000);
            return;
        }
        if (!toastContainer) {
            return;
        }
        var icons = {
            error: 'fa-times-circle',
            success: 'fa-check-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };
        var titles = {
            error: 'خطأ',
            success: 'نجح',
            warning: 'تحذير',
            info: 'معلومة'
        };
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.innerHTML =
            '<div class="toast-icon"><i class="fa ' + icons[type] + '"></i></div>' +
            '<div class="toast-content"><h4>' + titles[type] + '</h4><p>' + message + '</p></div>' +
            '<button type="button" class="toast-close" onclick="this.parentElement.remove()"><i class="fa fa-times"></i></button>';
        toastContainer.appendChild(toast);
        setTimeout(function () {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 5000);
    }

    function getLabel(label) {
        if (typeof translate !== 'undefined') {
            if (label === 'safe') return translate('label.safe');
            if (label === 'suspicious') return translate('label.suspicious');
            if (label === 'malicious') return translate('label.malicious');
            return translate('label.error');
        }
        if (label === 'safe') return 'آمن';
        if (label === 'suspicious') return 'مشبوه';
        if (label === 'malicious') return 'خبيث';
        return label || 'خطأ';
    }

    function displayResults(data) {
        if (!resultSummary || !resultDetails || !resultsOverlay) {
            var errorMsg = typeof translate !== 'undefined' ? translate('error.analysis') : 'خطأ في عرض النتائج';
            showError(errorMsg);
            return;
        }

        var t = typeof translate !== 'undefined' ? translate : function (k) { return k; };
        var lang = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                lang = currentLang() || 'ar';
            } else {
                lang = currentLang || 'ar';
            }
        }
        var label = data.final_label || 'error';
        var score = parseFloat(((data.final_score || 0) * 100).toFixed(1));

        resultSummary.innerHTML =
            '<div class="result-item"><span class="label">' + t('results.final.classification') + '</span><span class="value ' + label + '">' + getLabel(label) + '</span></div>' +
            '<div class="result-item"><span class="label">' + t('results.final.score') + '</span><span class="value">' + score + '%</span></div>';

        resultDetails.innerHTML = '';

        if (data.ml_result) {
            var mlLabel = data.ml_result.label || 'error';
            var mlConf = ((data.ml_result.confidence || 0) * 100).toFixed(1);
            var mlProbs = data.ml_result.probabilities || {};

            resultDetails.innerHTML += '<div class="detail-section">' +
                '<h4><i class="fa fa-brain"></i> ' + t('results.ml.title') + '</h4>' +
                '<p><strong>' + t('results.ml.classification') + ':</strong> ' + getLabel(mlLabel) + '</p>' +
                '<p><strong>' + t('results.ml.confidence') + ':</strong> ' + mlConf + '%</p>' +
                (mlProbs.safe !== undefined ? '<p><strong>' + t('results.ml.safe') + ':</strong> ' + (mlProbs.safe * 100).toFixed(1) + '%</p>' : '') +
                (mlProbs.suspicious !== undefined ? '<p><strong>' + t('results.ml.suspicious') + ':</strong> ' + (mlProbs.suspicious * 100).toFixed(1) + '%</p>' : '') +
                (mlProbs.malicious !== undefined ? '<p><strong>' + t('results.ml.malicious') + ':</strong> ' + (mlProbs.malicious * 100).toFixed(1) + '%</p>' : '') +
                '</div>';
        }
        if (data.dynamic_result) {
            var dynScore = ((data.dynamic_result.dynamic_score || 0) * 100).toFixed(1);
            var dynEvents = data.dynamic_result.events || {};
            var dynError = data.dynamic_result.error;

            resultDetails.innerHTML += '<div class="detail-section">' +
                '<h4><i class="fa fa-play"></i> ' + t('results.dynamic.title') + '</h4>' +
                '<p style="font-size: 0.85rem; color: var(--warning); margin-bottom: 0.75rem; padding: 0.5rem; background: rgba(245, 158, 11, 0.1); border-radius: 4px; display: flex; align-items: flex-start; gap: 0.4rem;"><i class="fa fa-info-circle" style="font-size: 0.8em; color: var(--warning); margin-top: 0.15rem; flex-shrink: 0;"></i> <span><strong>' + (lang === 'ar' ? 'ملاحظة:' : 'Note:') + '</strong> ' + t('results.sandbox.note') + '</span></p>' +
                '<p><strong>' + t('results.dynamic.result') + ':</strong> ' + dynScore + '%</p>' +
                (dynError ? '<p><strong>' + (lang === 'ar' ? 'ملاحظة:' : 'Note:') + '</strong> ' + dynError + '</p>' : '') +
                (Object.keys(dynEvents).length > 0 ? '<p><strong>' + t('results.dynamic.events') + ':</strong> ' + Object.keys(dynEvents).length + '</p>' : '') +
                '</div>';
        }

        if (data.heuristic_score !== undefined) {
            resultDetails.innerHTML += '<div class="detail-section">' +
                '<h4><i class="fa fa-search"></i> ' + t('results.heuristic.title') + '</h4>' +
                '<p><strong>' + t('results.heuristic.result') + ':</strong> ' + ((data.heuristic_score || 0) * 100).toFixed(1) + '%</p>' +
                '</div>';
        }
        if (data.vt_result) {
            var vtStatus = data.vt_result.status || 'unknown';
            var vtMessage = data.vt_result.message || '';
            var vtMalicious = data.vt_result.malicious_count || 0;
            var vtTotal = data.vt_result.total_engines || 0;
            var vtScore = ((data.vt_result.vt_score || 0) * 100).toFixed(1);
            var statusText = vtStatus === 'clean' ? t('status.clean') : vtStatus === 'malicious' ? t('status.malicious') : vtStatus === 'suspicious' ? t('status.suspicious') : t('status.unknown');

            resultDetails.innerHTML += '<div class="detail-section">' +
                '<h4><i class="fa fa-shield-alt"></i> ' + t('results.vt.title') + '</h4>' +
                '<p><strong>' + t('results.vt.result') + ':</strong> ' + vtScore + '%</p>' +
                '<p><strong>' + t('results.vt.status') + ':</strong> ' + statusText + '</p>' +
                (vtTotal > 0 ? '<p><strong>' + t('results.vt.malicious') + ':</strong> ' + vtMalicious + ' / ' + vtTotal + '</p>' : '') +
                (vtMessage ? '<p><strong>' + t('results.vt.message') + ':</strong> ' + vtMessage + '</p>' : '') +
                '</div>';
        }

        if (data.analysis_id) {
            resultDetails.innerHTML += '<div class="detail-section" style="text-align: center; margin-top: 1.5rem;"><a href="result.html?id=' + data.analysis_id + '" class="btn btn-primary" style="padding: 0.75rem 2rem; font-size: 1rem;"><i class="fa fa-file-alt"></i> ' + t('results.details') + '</a></div>';
        }

        var speakBtnOverlay = document.getElementById('speak-results-btn-overlay');
        var stopBtnOverlay = document.getElementById('stop-speak-btn-overlay');

        if (speakBtnOverlay) {
            speakBtnOverlay.addEventListener('click', function () {
                if (window.A11y && window.A11y.speakDetailedResults) {
                    window.A11y.speakDetailedResults(data);
                }
            });
        }

        if (stopBtnOverlay) {
            stopBtnOverlay.addEventListener('click', function () {
                if (window.A11y && window.A11y.stop) {
                    window.A11y.stop();
                }
            });
        }

        resultsOverlay.style.display = 'flex';

        if (window.A11y && window.A11y.announceResult) {
            window.A11y.announceResult(label, score, true);
        }

        if (window.loadStats && typeof window.loadStats === 'function') {
            setTimeout(function () {
                window.loadStats();
            }, 500);
        }
    }

    function hideResults() {
        if (resultsOverlay) resultsOverlay.style.display = 'none';
    }

    function displaySimpleResult(data) {
        // عرض نتيجة بسيطة للمستخدمين غير المسجلين
        var label = data.final_label || 'error';
        var score = parseFloat(((data.final_score || 0) * 100).toFixed(1));
        var labelText = getLabel(label);

        var lang = 'ar';
        if (typeof currentLang !== 'undefined') {
            if (typeof currentLang === 'function') {
                lang = currentLang() || 'ar';
            } else {
                lang = currentLang || 'ar';
            }
        }

        // تحديد الألوان حسب النتيجة
        var labelColor = label === 'safe' ? '#10b981' : label === 'suspicious' ? '#f59e0b' : '#ef4444';
        var labelBg = label === 'safe' ? 'rgba(16, 185, 129, 0.1)' : label === 'suspicious' ? 'rgba(245, 158, 11, 0.1)' : 'rgba(239, 68, 68, 0.1)';
        var iconClass = label === 'safe' ? 'fa-check-circle' : label === 'suspicious' ? 'fa-exclamation-triangle' : 'fa-times-circle';

        // إنشاء بطاقة جميلة للمستخدمين غير المسجلين
        var simpleResultHTML = '<div class="simple-result-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000; animation: fadeIn 0.3s ease;">' +
            '<div class="simple-result-card" style="background: var(--surface); border-radius: 16px; padding: 0; max-width: 600px; width: 90%; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.5); overflow: hidden; animation: slideUp 0.4s ease;">' +
            
            // Header مع الأيقونة
            '<div style="background: linear-gradient(135deg, ' + labelColor + ' 0%, ' + labelColor + 'dd 100%); padding: 2rem 2rem 1.5rem; color: white;">' +
            '<div style="font-size: 4rem; margin-bottom: 1rem;"><i class="fa ' + iconClass + '"></i></div>' +
            '<h2 style="margin: 0; font-size: 1.75rem; font-weight: bold;">' + (lang === 'ar' ? 'نتيجة التحليل' : 'Analysis Result') + '</h2>' +
            '</div>' +
            
            // المحتوى
            '<div style="padding: 2rem;">' +
            '<div class="result-badge" style="margin: 1.5rem 0; padding: 1.5rem; border-radius: 12px; background: ' + labelBg + '; border: 2px solid ' + labelColor + ';">' +
            '<div class="result-label" style="font-size: 2rem; font-weight: bold; margin-bottom: 0.5rem; color: ' + labelColor + ';">' + labelText + '</div>' +
            '<div class="result-score" style="font-size: 1.5rem; color: var(--text-muted); font-weight: 600;">' + score + '%</div>' +
            '</div>' +
            
            '<div style="background: var(--surface-light); padding: 1.5rem; border-radius: 12px; margin: 1.5rem 0;">' +
            '<p style="color: var(--text); margin: 0 0 1rem; font-size: 1.1rem; font-weight: 600;">' + 
            (lang === 'ar' ? 'للحصول على تحليل تفصيلي كامل مع جميع التفاصيل:' : 'For full detailed analysis with all information:') +
            '</p>' +
            '<div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-top: 1.5rem;">' +
            '<a href="register.html" class="btn btn-primary" style="padding: 0.875rem 2rem; font-size: 1rem; text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem; border-radius: 8px; font-weight: 600; background: var(--primary); color: white;">' +
            '<i class="fa fa-user-plus"></i> ' + (lang === 'ar' ? 'إنشاء حساب' : 'Sign Up') +
            '</a>' +
            '<a href="payment.html" class="btn" style="padding: 0.875rem 2rem; font-size: 1rem; text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem; border-radius: 8px; font-weight: 600; background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); color: white; border: none;">' +
            '<i class="fa fa-crown"></i> ' + (lang === 'ar' ? 'الاشتراك المميز' : 'Premium') +
            '</a>' +
            '</div>' +
            '</div>' +
            '</div>' +
            
            // Footer مع زر الإغلاق
            '<div style="padding: 1rem 2rem 2rem; border-top: 1px solid var(--border-color);">' +
            '<button onclick="this.closest(\'.simple-result-overlay\').remove()" class="btn" style="padding: 0.75rem 2rem; font-size: 1rem; background: var(--surface-light); color: var(--text); border: 1px solid var(--border-color); border-radius: 8px; cursor: pointer;">' +
            '<i class="fa fa-times"></i> ' + (lang === 'ar' ? 'إغلاق' : 'Close') +
            '</button>' +
            '</div>' +
            '</div>' +
            '</div>' +
            '<style>' +
            '@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }' +
            '@keyframes slideUp { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }' +
            '</style>';

        document.body.insertAdjacentHTML('beforeend', simpleResultHTML);

        // إغلاق عند النقر خارج البطاقة
        setTimeout(function () {
            var overlay = document.querySelector('.simple-result-overlay');
            if (overlay) {
                overlay.addEventListener('click', function (e) {
                    if (e.target === overlay) {
                        overlay.remove();
                    }
                });
            }
        }, 100);
    }

    function handleSubmit(e) {
        e.preventDefault();
        var url = urlInput ? urlInput.value.trim() : '';

        if (!url) {
            showError('يرجى إدخال رابط صحيح');
            return;
        }

        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'https://' + url;
        }

        showLoading();
        if (analyzeBtn) {
            analyzeBtn.disabled = true;
            analyzeBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> جاري التحليل...';
        }

        var controller = new AbortController();
        var timeoutId = setTimeout(function () { controller.abort(); }, 60000);

        fetch(API + '/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ url: url }),
            signal: controller.signal
        })
            .then(function (response) {
                if (!response.ok) {
                    return response.text().then(function (text) {
                        try {
                            var err = JSON.parse(text);
                            throw new Error(err.error || 'خطأ في الخادم: ' + response.status);
                        } catch (e) {
                            throw new Error('خطأ في الخادم: ' + response.status + ' - ' + text.substring(0, 100));
                        }
                    });
                }
                return response.text().then(function (text) {
                    try {
                        return JSON.parse(text);
                    } catch (e) {
                        throw new Error('خطأ في تحليل الاستجابة: ' + text.substring(0, 100));
                    }
                });
            })
            .then(function (data) {
                if (!data) {
                    showError('لا توجد بيانات من الخادم');
                    return;
                }
                if (data.error) {
                    showError(data.error);
                    return;
                }

                // التحقق من وجود النتائج
                if (data.final_label !== undefined || data.final_score !== undefined) {
                    // للمستخدمين غير المسجلين: عرض نتيجة بسيطة فقط
                    if (data.is_guest) {
                        // عرض نتيجة بسيطة في الصفحة الرئيسية
                        displaySimpleResult(data);
                        return;
                    }

                    // للمستخدمين المسجلين: التوجيه لصفحة النتائج الكاملة
                    if (data.analysis_id) {
                        // التوجيه المباشر لصفحة النتائج
                        window.location.href = 'result.html?id=' + data.analysis_id;
                        return; // إيقاف التنفيذ بعد التوجيه
                    } else {
                        // إذا لم يكن هناك analysis_id، ننشئ واحداً مؤقتاً ونعيد التوجيه
                        var tempId = 'temp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                        // حفظ مؤقت في sessionStorage
                        sessionStorage.setItem('temp_analysis_' + tempId, JSON.stringify(data));
                        // التوجيه المباشر
                        window.location.href = 'result.html?id=' + tempId;
                        return; // إيقاف التنفيذ بعد التوجيه
                    }
                } else {
                    showError('البيانات المستلمة غير مكتملة: ' + JSON.stringify(data).substring(0, 200));
                }
            })
            .catch(function (err) {
                if (err.name === 'AbortError') {
                    showError('انتهت مهلة الاتصال (60 ثانية)');
                } else if (err.message && err.message.includes('Failed to fetch')) {
                    showError('فشل الاتصال بالخادم. تأكد من تشغيل: python app.py');
                } else {
                    showError(err.message || 'خطأ غير معروف. تأكد من تشغيل السيرفر: python app.py');
                }
            })
            .finally(function () {
                clearTimeout(timeoutId);
                hideLoading();
                if (analyzeBtn) {
                    analyzeBtn.disabled = false;
                    analyzeBtn.innerHTML = '<i class="fa fa-search"></i> تحليل';
                }
            });
    }

    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
    if (errorClose) {
        errorClose.addEventListener('click', hideError);
    }
    if (errorModal) {
        errorModal.addEventListener('click', function (e) {
            if (e.target === errorModal) hideError();
        });
    }
    if (successClose) {
        successClose.addEventListener('click', hideSuccess);
    }
    if (successModal) {
        successModal.addEventListener('click', function (e) {
            if (e.target === successModal) hideSuccess();
        });
    }
    if (closeResults) {
        closeResults.addEventListener('click', hideResults);
    }
    if (resultsOverlay) {
        resultsOverlay.addEventListener('click', function (e) {
            if (e.target === resultsOverlay) hideResults();
        });
    }

    window.hideSuccess = hideSuccess;
    window.hideError = hideError;
    window.showError = showError;
    window.showSuccess = showSuccess;
    window.showToast = showToast;
})();
