import os
import sys
import subprocess
import logging

def install_playwright_browsers():
    try:
        logging.info("تثبيت متصفحات Playwright...")
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install", "chromium"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logging.info("تم تثبيت متصفحات Playwright بنجاح")
            return True
        else:
            logging.error(f"فشل في تثبيت متصفحات Playwright: {result.stderr}")
            return False
            
    except Exception as e:
        logging.error(f"خطأ في تثبيت متصفحات Playwright: {e}")
        return False

def setup_project():
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # إنشاء المجلدات المطلوبة
    directories = [
        'logs',
        'db',
        'vt_cache',
        'sandbox/jobs',
        'data'
    ]
    
    for directory in directories:
        dir_path = os.path.join(project_root, directory)
        os.makedirs(dir_path, exist_ok=True)
        logging.info(f"تم إنشاء المجلد: {directory}")
    
    # تثبيت متصفحات Playwright
    install_playwright_browsers()
    
    logging.info("تم إعداد المشروع بنجاح")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_project()