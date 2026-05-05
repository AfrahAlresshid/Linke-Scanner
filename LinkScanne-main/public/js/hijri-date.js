// تحويل الأرقام من إنجليزية إلى عربية
function toArabicNumerals(str) {
    if (!str) return str;
    var arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
    return String(str).replace(/\d/g, function(digit) {
        return arabicNumerals[parseInt(digit)];
    });
}

// تحويل الأرقام من عربية إلى إنجليزية
function toEnglishNumerals(str) {
    if (!str) return str;
    var arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
    var englishNumerals = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
    var result = String(str);
    for (var i = 0; i < arabicNumerals.length; i++) {
        result = result.replace(new RegExp(arabicNumerals[i], 'g'), englishNumerals[i]);
    }
    return result;
}

// تحويل التاريخ من ميلادي إلى هجري
function gregorianToHijri(dateStr) {
    if (!dateStr) return '';
    
    try {
        var date = new Date(dateStr);
        if (isNaN(date.getTime())) {
            // محاولة تحليل صيغ أخرى
            date = new Date(dateStr.replace(' ', 'T'));
        }
        
        if (isNaN(date.getTime())) return '';
        
        var year = date.getFullYear();
        var month = date.getMonth() + 1;
        var day = date.getDate();
        
        // استخدام API لتحويل دقيق
        return convertToHijriAPI(year, month, day);
    } catch (e) {
        return convertToHijriSimple(dateStr);
    }
}

function convertToHijriAPI(year, month, day) {
    // استخدام خوارزمية تقريبية (يمكن استبدالها بـ API)
    var jd = gregorianToJD(year, month, day);
    var hijri = jdToHijri(jd);
    return hijri.year + '-' + String(hijri.month).padStart(2, '0') + '-' + String(hijri.day).padStart(2, '0');
}

function gregorianToJD(year, month, day) {
    if (month <= 2) {
        year -= 1;
        month += 12;
    }
    var a = Math.floor(year / 100);
    var b = 2 - a + Math.floor(a / 4);
    return Math.floor(365.25 * (year + 4716)) + Math.floor(30.6001 * (month + 1)) + day + b - 1524.5;
}

function jdToHijri(jd) {
    jd = Math.floor(jd) + 0.5;
    var year = Math.floor((30 * (jd - 1948440) + 10646) / 10631);
    var yearStart = 1948440 + Math.floor((year - 1) * 10631 / 30);
    var month = Math.floor((jd - yearStart) / 29.5) + 1;
    if (month > 12) month = 12;
    var day = jd - yearStart - Math.floor((month - 1) * 29.5) + 1;
    return { year: year, month: month, day: Math.floor(day) };
}

function convertToHijriSimple(dateStr) {
    if (!dateStr) return '';
    try {
        var date = new Date(dateStr);
        if (isNaN(date.getTime())) return '';
        
        var year = date.getFullYear();
        var month = date.getMonth() + 1;
        var day = date.getDate();
        
        // تحويل تقريبي
        var hijriYear = year - 579;
        var hijriMonth = month;
        var hijriDay = day;
        
        // تعديل بسيط
        if (month >= 9) {
            hijriYear += 1;
        }
        
        return hijriYear + '-' + String(hijriMonth).padStart(2, '0') + '-' + String(hijriDay).padStart(2, '0');
    } catch (e) {
        return '';
    }
}

function formatDate(dateStr, lang) {
    if (!dateStr) return '';
    
    try {
        var date = new Date(dateStr);
        if (isNaN(date.getTime())) {
            // محاولة تحليل صيغ أخرى
            date = new Date(dateStr.replace(' ', 'T'));
        }
        
        if (isNaN(date.getTime())) return dateStr;
        
        var hijri = gregorianToHijri(dateStr);
        
        // التاريخ الميلادي - دائماً بالأرقام الإنجليزية
        // استخدام en-US لضمان الأرقام الإنجليزية
        var gregorian = date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
        
        // التأكد من أن جميع الأرقام إنجليزية (تحويل أي أرقام عربية إلى إنجليزية)
        gregorian = toEnglishNumerals(gregorian);
        
        // إذا كانت اللغة عربية، نترجم أسماء الأشهر و AM/PM
        if (lang === 'ar') {
            var englishMonths = ['January', 'February', 'March', 'April', 'May', 'June', 
                                'July', 'August', 'September', 'October', 'November', 'December'];
            var arabicMonths = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                               'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
            for (var i = 0; i < englishMonths.length; i++) {
                gregorian = gregorian.replace(englishMonths[i], arabicMonths[i]);
            }
            
            // استبدال AM/PM بالعربية
            gregorian = gregorian.replace(/\bAM\b/gi, 'ص');
            gregorian = gregorian.replace(/\bPM\b/gi, 'م');
        }
        
        // التاريخ الهجري - دائماً بالأرقام العربية
        var hijriFormatted = '';
        if (hijri) {
            var hijriParts = hijri.split('-');
            if (hijriParts.length === 3) {
                var hijriMonths = lang === 'ar' ? 
                    ['محرم', 'صفر', 'ربيع الأول', 'ربيع الثاني', 'جمادى الأولى', 'جمادى الثانية', 
                     'رجب', 'شعبان', 'رمضان', 'شوال', 'ذو القعدة', 'ذو الحجة'] :
                    ['Muharram', 'Safar', 'Rabi\' al-awwal', 'Rabi\' al-thani', 'Jumada al-awwal', 'Jumada al-thani',
                     'Rajab', 'Sha\'ban', 'Ramadan', 'Shawwal', 'Dhu al-Qi\'dah', 'Dhu al-Hijjah'];
                var monthIndex = parseInt(hijriParts[1]) - 1;
                var hijriDay = toArabicNumerals(hijriParts[2]);
                var hijriYear = toArabicNumerals(hijriParts[0]);
                hijriFormatted = hijriDay + ' ' + hijriMonths[monthIndex] + ' ' + hijriYear + ' هـ';
            }
        }
        
        return {
            gregorian: gregorian,
            hijri: hijriFormatted || hijri,
            raw: {
                gregorian: dateStr,
                hijri: hijri
            }
        };
    } catch (e) {
        return {
            gregorian: dateStr,
            hijri: '',
            raw: {
                gregorian: dateStr,
                hijri: ''
            }
        };
    }
}

if (typeof window !== 'undefined') {
    window.gregorianToHijri = gregorianToHijri;
    window.formatDate = formatDate;
    window.toArabicNumerals = toArabicNumerals;
    window.toEnglishNumerals = toEnglishNumerals;
}
