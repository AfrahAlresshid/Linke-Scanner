import asyncio
import json
import os
import time
import shutil
from datetime import datetime
from playwright.async_api import async_playwright
from urllib.parse import urlparse
import re

class SandboxWorker:
    def __init__(self, analysis_id, timeout=15):
        self.analysis_id = analysis_id
        self.timeout = timeout
        self.job_dir = os.path.join(os.path.dirname(__file__), 'jobs', analysis_id)
        self.summary_file = os.path.join(self.job_dir, 'dynamic_summary.json')
        os.makedirs(self.job_dir, exist_ok=True)
        # أثناء `playwright install` (مثلاً على Render) المتصفحات تُنزَّل لمسار الافتراضي
        # (~/.cache/ms-playwright). نستخدم المجلد المحلي فقط إن وُجدت نسخة مثبتة داخله.
        _local_browsers = os.path.join(os.path.dirname(__file__), 'browsers')
        if os.path.isdir(_local_browsers) and os.listdir(_local_browsers):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = _local_browsers
        self.events = {
            'downloads': [],
            'form_submissions': [],
            'redirects': [],
            'suspicious_js': [],
            'cookies': [],
            'xhr_requests': [],
            'errors': [],
            'console_logs': []
        }
        
        self.dynamic_score = 0.0
        self.suspicious_indicators = 0
        self.total_indicators = 0
    
    async def analyze_url(self, url):
        try:
            async with async_playwright() as p:
                # إعداد المتصفح
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--no-first-run',
                        '--disable-default-apps',
                        '--disable-extensions',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                )
                
                page = await context.new_page()
                
                # إعداد مراقب الأحداث
                await self._setup_event_listeners(page)
                
                # تحليل الرابط مع timeout
                try:
                    await asyncio.wait_for(
                        self._navigate_and_analyze(page, url),
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    self.events['errors'].append({
                        'type': 'timeout',
                        'message': f'انتهت مهلة التحليل ({self.timeout} ثانية)',
                        'timestamp': datetime.now().isoformat()
                    })
                
                await browser.close()
                
                # حساب النتيجة الديناميكية
                self._calculate_dynamic_score()
                
                # حفظ الملخص
                await self._save_summary(url)
                
                return {
                    'dynamic_score': self.dynamic_score,
                    'suspicious_indicators': self.suspicious_indicators,
                    'total_indicators': self.total_indicators,
                    'events': self.events,
                    'summary_file': self.summary_file
                }
                
        except Exception as e:
            self.events['errors'].append({
                'type': 'exception',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'dynamic_score': 0.0,
                'suspicious_indicators': 0,
                'total_indicators': 0,
                'events': self.events,
                'error': str(e)
            }
    
    async def _setup_event_listeners(self, page):
        async def handle_download(download):
            self.events['downloads'].append({
                'url': download.url,
                'suggested_filename': download.suggested_filename,
                'timestamp': datetime.now().isoformat()
            })
            self.suspicious_indicators += 1
        
        page.on('download', handle_download)
        async def handle_request(request):
            if request.method == 'POST':
                self.events['form_submissions'].append({
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'timestamp': datetime.now().isoformat()
                })
                self.suspicious_indicators += 1
        
        page.on('request', handle_request)
        async def handle_response(response):
            if response.status >= 300 and response.status < 400:
                self.events['redirects'].append({
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'timestamp': datetime.now().isoformat()
                })
                self.suspicious_indicators += 1
        
        page.on('response', handle_response)
        async def handle_error(error):
            self.events['errors'].append({
                'type': 'page_error',
                'message': str(error),
                'timestamp': datetime.now().isoformat()
            })
        
        page.on('pageerror', handle_error)
        async def handle_console(msg):
            self.events['console_logs'].append({
                'type': msg.type,
                'text': msg.text,
                'timestamp': datetime.now().isoformat()
            })
            
            # فحص JavaScript مشبوه
            if self._is_suspicious_js(msg.text):
                self.events['suspicious_js'].append({
                    'text': msg.text,
                    'timestamp': datetime.now().isoformat()
                })
                self.suspicious_indicators += 1
        
        page.on('console', handle_console)
        async def handle_xhr(request):
            if request.resource_type in ['xhr', 'fetch']:
                self.events['xhr_requests'].append({
                    'url': request.url,
                    'method': request.method,
                    'timestamp': datetime.now().isoformat()
                })
                self.total_indicators += 1
        
        page.on('request', handle_xhr)
    
    async def _navigate_and_analyze(self, page, url):
        try:
            response = await page.goto(url, wait_until='networkidle', timeout=10000)
            
            if response:
                self.total_indicators += 1
                
                # فحص الاستجابة
                if response.status >= 400:
                    self.suspicious_indicators += 1
                title = await page.title()
                if self._is_suspicious_title(title):
                    self.suspicious_indicators += 1
                content = await page.content()
                if self._is_suspicious_content(content):
                    self.suspicious_indicators += 1
                links = await page.query_selector_all('a')
                for link in links:
                    href = await link.get_attribute('href')
                    if href and self._is_suspicious_link(href):
                        self.suspicious_indicators += 1
                forms = await page.query_selector_all('form')
                for form in forms:
                    self.total_indicators += 1
                    action = await form.get_attribute('action')
                    if action and self._is_suspicious_form(action):
                        self.suspicious_indicators += 1
                        self.events['form_submissions'].append({
                            'action': action,
                            'timestamp': datetime.now().isoformat()
                        })
                
                # فحص الكوكيز
                cookies = await page.context.cookies()
                for cookie in cookies:
                    self.total_indicators += 1
                    self.events['cookies'].append({
                        'name': cookie['name'],
                        'domain': cookie['domain'],
                        'timestamp': datetime.now().isoformat()
                    })
                    if self._is_suspicious_cookie(cookie):
                        self.suspicious_indicators += 1
                
                # إضافة مؤشرات إضافية
                scripts = await page.query_selector_all('script')
                self.total_indicators += len(scripts)
                for script in scripts:
                    content = await script.inner_text()
                    if content and self._is_suspicious_js(content):
                        self.suspicious_indicators += 1
                        self.events['suspicious_js'].append({
                            'content': content[:200],
                            'timestamp': datetime.now().isoformat()
                        })
                
                # انتظار لالتقاط المزيد من الأحداث
                await asyncio.sleep(2)
                
        except Exception as e:
            self.events['errors'].append({
                'type': 'navigation_error',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def _is_suspicious_js(self, text):
        suspicious_patterns = [
            r'eval\s*\(',
            r'Function\s*\(',
            r'document\.write',
            r'innerHTML\s*=',
            r'outerHTML\s*=',
            r'location\.href\s*=',
            r'window\.open',
            r'atob\s*\(',
            r'btoa\s*\(',
            r'unescape\s*\(',
            r'escape\s*\(',
            r'String\.fromCharCode',
            r'charCodeAt',
            r'fromCharCode'
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _is_suspicious_title(self, title):
        suspicious_titles = [
            'click here',
            'download now',
            'free download',
            'win prize',
            'urgent',
            'limited time',
            'verify account',
            'update now'
        ]
        
        title_lower = title.lower()
        for suspicious in suspicious_titles:
            if suspicious in title_lower:
                return True
        
        return False
    
    def _is_suspicious_content(self, content):
        suspicious_patterns = [
            r'click\s+here',
            r'download\s+now',
            r'free\s+download',
            r'win\s+prize',
            r'urgent\s+action',
            r'limited\s+time',
            r'verify\s+account',
            r'update\s+now',
            r'congratulations',
            r'you\s+won',
            r'claim\s+now'
        ]
        
        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, content_lower):
                return True
        
        return False
    
    def _is_suspicious_link(self, href):
        suspicious_domains = [
            'bit.ly',
            'tinyurl.com',
            'short.link',
            'goo.gl',
            't.co',
            'ow.ly'
        ]
        
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower()
            
            for suspicious in suspicious_domains:
                if suspicious in domain:
                    return True
            if re.search(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', href):
                return True
            
        except:
            pass
        
        return False
    
    def _is_suspicious_form(self, action):
        suspicious_actions = [
            'login',
            'signin',
            'verify',
            'update',
            'confirm',
            'submit'
        ]
        
        action_lower = action.lower()
        for suspicious in suspicious_actions:
            if suspicious in action_lower:
                return True
        
        return False
    
    def _is_suspicious_cookie(self, cookie):
        suspicious_names = [
            'tracking',
            'analytics',
            'session',
            'token',
            'auth'
        ]
        
        name_lower = cookie['name'].lower()
        for suspicious in suspicious_names:
            if suspicious in name_lower:
                return True
        
        return False
    
    def _calculate_dynamic_score(self):
        if self.total_indicators == 0:
            self.dynamic_score = 0.0
            return
        
        base_ratio = self.suspicious_indicators / max(self.total_indicators, 1)
        
        downloads_count = len(self.events['downloads'])
        forms_count = len(self.events['form_submissions'])
        redirects_count = len(self.events['redirects'])
        suspicious_js_count = len(self.events['suspicious_js'])
        cookies_count = len(self.events['cookies'])
        errors_count = len(self.events['errors'])
        
        score = base_ratio
        
        if downloads_count > 0:
            score += min(downloads_count * 0.1, 0.3)
        if forms_count > 0:
            score += min(forms_count * 0.05, 0.2)
        if redirects_count > 2:
            score += min((redirects_count - 2) * 0.05, 0.2)
        if suspicious_js_count > 0:
            score += min(suspicious_js_count * 0.15, 0.4)
        if cookies_count > 10:
            score += min((cookies_count - 10) * 0.01, 0.1)
        if errors_count > 0:
            score += min(errors_count * 0.05, 0.2)
        
        self.dynamic_score = min(score, 1.0)
    
    async def _save_summary(self, url):
        summary = {
            'url': url,
            'analysis_id': self.analysis_id,
            'timestamp': datetime.now().isoformat(),
            'dynamic_score': self.dynamic_score,
            'suspicious_indicators': self.suspicious_indicators,
            'total_indicators': self.total_indicators,
            'events': self.events,
            'summary': {
                'downloads_count': len(self.events['downloads']),
                'form_submissions_count': len(self.events['form_submissions']),
                'redirects_count': len(self.events['redirects']),
                'suspicious_js_count': len(self.events['suspicious_js']),
                'cookies_count': len(self.events['cookies']),
                'xhr_requests_count': len(self.events['xhr_requests']),
                'errors_count': len(self.events['errors']),
                'console_logs_count': len(self.events['console_logs'])
            }
        }
        
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
    
    def cleanup(self):
        try:
            if os.path.exists(self.job_dir):
                shutil.rmtree(self.job_dir)
        except Exception as e:
            print(f"خطأ في تنظيف الملفات: {e}")

async def analyze_url_dynamic(url, analysis_id, timeout=15):
    worker = SandboxWorker(analysis_id, timeout)
    result = await worker.analyze_url(url)
    worker.cleanup()
    return result

if __name__ == "__main__":
    async def test_sandbox():
        test_urls = [
            "https://www.google.com",
            "https://www.github.com",
            "http://malicious-site.com"
        ]
        
        for i, url in enumerate(test_urls):
            print(f"تحليل الرابط: {url}")
            result = await analyze_url_dynamic(url, f"test_{i}", timeout=10)
            print(f"النتيجة الديناميكية: {result['dynamic_score']:.4f}")
            print(f"المؤشرات المشبوهة: {result['suspicious_indicators']}")
            print(f"إجمالي المؤشرات: {result['total_indicators']}")
            print("-" * 50)
    
    asyncio.run(test_sandbox())
