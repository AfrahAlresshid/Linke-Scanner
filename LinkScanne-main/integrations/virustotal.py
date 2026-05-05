import requests
import json
import hashlib
import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

class VirusTotalAPI:
    def __init__(self, api_key=None, cache_hours=24):
        self.api_key = api_key
        self.cache_hours = cache_hours
        self.base_url = "https://www.virustotal.com/vtapi/v2"
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vt_cache')
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _get_cache_path(self, url):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")
    
    def _is_cache_valid(self, cache_path):
        if not os.path.exists(cache_path):
            return False
        
        try:
            if not os.path.exists(cache_path):
                return False
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            cached_at = cache_data.get('cached_at', '')
            if not cached_at:
                return False
                
            cache_time = datetime.fromisoformat(cached_at)
            expiry_time = cache_time + timedelta(hours=self.cache_hours)
            
            return datetime.now() < expiry_time
        except (ValueError, KeyError, json.JSONDecodeError, OSError) as e:
            return False
        except Exception as e:
            return False
    
    def _load_from_cache(self, cache_path):
        try:
            if not os.path.exists(cache_path):
                return None
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, IOError) as e:
            return None
        except Exception as e:
            return None
    
    def _save_to_cache(self, cache_path, data):
        try:
            if not isinstance(data, dict):
                return False
            data['cached_at'] = datetime.now().isoformat()
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except (OSError, IOError, TypeError, ValueError) as e:
            return False
        except Exception as e:
            return False
    
    def _submit_url_for_analysis(self, url):
        if not self.api_key or not url:
            return None
        
        try:
            params = {
                'apikey': self.api_key,
                'url': str(url)
            }
            
            response = requests.post(
                f"{self.base_url}/url/scan",
                data=params,
                timeout=30,
                headers={'User-Agent': 'LinkScanne/1.0'}
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        return data
                    return None
                except ValueError:
                    return None
            elif response.status_code == 204:
                return None
            elif response.status_code == 403:
                return {'response_code': -1, 'error': 'API key invalid or rate limited'}
            else:
                return None
                
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.ConnectionError:
            return None
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
    
    def _get_url_report(self, url):
        if not self.api_key or not url:
            return None
        
        try:
            import hashlib
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            
            params = {
                'apikey': self.api_key,
                'resource': str(url)
            }
            
            response = requests.get(
                f"{self.base_url}/url/report",
                params=params,
                timeout=30,
                headers={'User-Agent': 'LinkScanne/1.0'}
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        return data
                    return None
                except ValueError:
                    return None
            elif response.status_code == 204:
                return None
            elif response.status_code == 403:
                return {'response_code': -1, 'error': 'API key invalid or rate limited'}
            else:
                return None
                
        except requests.exceptions.Timeout as e:
            return None
        except requests.exceptions.ConnectionError as e:
            return None
        except requests.exceptions.RequestException as e:
            return None
        except Exception as e:
            return None
    
    def analyze_url(self, url):
        try:
            if not url or not isinstance(url, str):
                raise ValueError("الرابط غير صحيح")
            
            if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
                return {
                    'vt_score': 0.0,
                    'malicious_count': 0,
                    'total_engines': 0,
                    'cached': False,
                    'report_link': '',
                    'status': 'disabled',
                    'message': 'VirusTotal API غير مفعل'
                }
            
            cache_path = self._get_cache_path(url)
            
            if self._is_cache_valid(cache_path):
                cached_data = self._load_from_cache(cache_path)
                if cached_data and isinstance(cached_data, dict):
                    cached_data['cached'] = True
                    return cached_data
            
            report = self._get_url_report(url)
            
            if report and isinstance(report, dict):
                if report.get('response_code') == 1:
                    result = self._process_report(report, url)
                    if result and isinstance(result, dict):
                        result['cached'] = False
                        self._save_to_cache(cache_path, result)
                        return result
                elif report.get('response_code') == 0:
                    scan_result = self._submit_url_for_analysis(url)
                    if scan_result and isinstance(scan_result, dict) and scan_result.get('response_code') == 1:
                        return {
                            'vt_score': 0.0,
                            'malicious_count': 0,
                            'total_engines': 0,
                            'cached': False,
                            'report_link': scan_result.get('permalink', ''),
                            'status': 'submitted',
                            'message': 'تم إرسال الرابط للتحليل، يرجى المحاولة لاحقاً',
                            'scan_id': scan_result.get('scan_id', '')
                        }
                elif report.get('response_code') == -1:
                    return {
                        'vt_score': 0.0,
                        'malicious_count': 0,
                        'total_engines': 0,
                        'cached': False,
                        'report_link': '',
                        'status': 'api_error',
                        'message': report.get('error', 'خطأ في API key أو تجاوز الحد المسموح')
                    }
            
            scan_result = self._submit_url_for_analysis(url)
            
            if scan_result and isinstance(scan_result, dict) and scan_result.get('response_code') == 1:
                return {
                    'vt_score': 0.0,
                    'malicious_count': 0,
                    'total_engines': 0,
                    'cached': False,
                    'report_link': scan_result.get('permalink', ''),
                    'status': 'submitted',
                    'message': 'تم إرسال الرابط للتحليل، يرجى المحاولة لاحقاً',
                    'scan_id': scan_result.get('scan_id', '')
                }
            
            return {
                'vt_score': 0.0,
                'malicious_count': 0,
                'total_engines': 0,
                'cached': False,
                'report_link': '',
                'status': 'error',
                'message': 'فشل في تحليل الرابط - الرابط جديد أو API غير متاح'
            }
        except Exception as e:
            return {
                'vt_score': 0.0,
                'malicious_count': 0,
                'total_engines': 0,
                'cached': False,
                'report_link': '',
                'status': 'error',
                'message': f'خطأ في تحليل الرابط: {str(e)[:100]}'
            }
    
    def _process_report(self, report, url):
        try:
            if not isinstance(report, dict):
                raise ValueError("تقرير غير صحيح")
            
            scans = report.get('scans', {})
            
            if not scans or not isinstance(scans, dict):
                return {
                    'vt_score': 0.0,
                    'malicious_count': 0,
                    'total_engines': 0,
                    'cached': False,
                    'report_link': report.get('permalink', ''),
                    'status': 'no_scans',
                    'message': 'لا توجد نتائج تحليل'
                }
            
            total_engines = len(scans)
            malicious_count = 0
            
            for engine, result in scans.items():
                if isinstance(result, dict) and result.get('detected') and result.get('result'):
                    malicious_count += 1
            
            vt_score = float(malicious_count) / float(total_engines) if total_engines > 0 else 0.0
            
            if vt_score >= 0.5:
                status = 'malicious'
                message = f'تم اكتشاف الرابط كخبيث من قبل {malicious_count} محرك'
            elif vt_score >= 0.1:
                status = 'suspicious'
                message = f'الرابط مشبوه من قبل {malicious_count} محرك'
            else:
                status = 'clean'
                message = 'الرابط آمن'
            
            return {
                'vt_score': vt_score,
                'malicious_count': malicious_count,
                'total_engines': total_engines,
                'cached': False,
                'report_link': report.get('permalink', ''),
                'status': status,
                'message': message,
                'scan_date': report.get('scan_date', '')
            }
        except Exception as e:
            return {
                'vt_score': 0.0,
                'malicious_count': 0,
                'total_engines': 0,
                'cached': False,
                'report_link': '',
                'status': 'error',
                'message': f'خطأ في معالجة التقرير: {str(e)[:100]}'
            }

def load_from_cache_or_query(url, api_key=None, cache_hours=24):
    try:
        if not url:
            return {
                'vt_score': 0.0,
                'malicious_count': 0,
                'total_engines': 0,
                'cached': False,
                'report_link': '',
                'status': 'error',
                'message': 'الرابط غير موجود'
            }
        vt = VirusTotalAPI(api_key=api_key, cache_hours=cache_hours)
        result = vt.analyze_url(url)
        if not isinstance(result, dict):
            raise ValueError("نتيجة غير صحيحة")
        return result
    except Exception as e:
        return {
            'vt_score': 0.0,
            'malicious_count': 0,
            'total_engines': 0,
            'cached': False,
            'report_link': '',
            'status': 'error',
            'message': f'خطأ في تحليل VirusTotal: {str(e)[:100]}'
        }

if __name__ == "__main__":
    test_urls = [
        "https://www.google.com",
        "http://malicious-site.com",
        "https://www.github.com"
    ]
    
    for url in test_urls:
        print(f"تحليل الرابط: {url}")
        result = load_from_cache_or_query(url)
        print(f"النتيجة: {result['vt_score']:.4f}")
        print(f"المحركات الخبيثة: {result['malicious_engines']}/{result['total_engines']}")
        print(f"الحالة: {result['status']}")
        print(f"الرسالة: {result['message']}")
        print("-" * 50)
