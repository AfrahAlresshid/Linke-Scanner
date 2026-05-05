import sqlite3
import json
import os
from datetime import datetime


class AlertMonitor:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', 'db', 'alerts.db'
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_database()

    def _init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'"
            )
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(alerts)")
                cols = [row[1] for row in cursor.fetchall()]
                if 'final_label' not in cols:
                    cursor.execute("DROP TABLE alerts")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    final_label TEXT NOT NULL,
                    final_score REAL NOT NULL,
                    analysis_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0,
                    acknowledged_by TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"خطأ في إعداد قاعدة البيانات: {e}")

    def record_analysis(self, url, result):
        try:
            final_label = result.get('final_label', 'safe')
            final_score = float(result.get('final_score', 0.0))

            # حفظ التنبيه فقط للروابط الخطيرة أو المشبوهة
            if final_label not in ('malicious', 'suspicious'):
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            analysis_data = json.dumps(result, ensure_ascii=False)
            created_at = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO alerts (url, final_label, final_score, analysis_data, created_at, acknowledged)
                VALUES (?, ?, ?, ?, ?, 0)
            ''', (url[:500], final_label, final_score, analysis_data, created_at))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"خطأ في تسجيل التحليل: {e}")

    def acknowledge_alert(self, alert_id, acknowledged_by="user"):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE alerts
                SET acknowledged = 1, acknowledged_by = ?
                WHERE id = ? AND acknowledged = 0
            ''', (acknowledged_by, alert_id))
            updated = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return updated
        except Exception as e:
            print(f"خطأ في تأكيد التنبيه: {e}")
            return False

    def get_active_alerts(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, url, final_label, final_score, analysis_data, created_at, acknowledged, acknowledged_by
                FROM alerts
                WHERE acknowledged = 0
                ORDER BY created_at DESC
            ''')
            alerts = []
            for row in cursor.fetchall():
                alerts.append({
                    'id': row[0],
                    'url': row[1],
                    'final_label': row[2],
                    'final_score': row[3],
                    'analysis_data': json.loads(row[4]) if row[4] else {},
                    'created_at': row[5],
                    'acknowledged': bool(row[6]),
                    'acknowledged_by': row[7]
                })
            conn.close()
            return alerts
        except Exception as e:
            print(f"خطأ في الحصول على التنبيهات: {e}")
            return []

    def get_stats(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM alerts')
            total_alerts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM alerts WHERE acknowledged = 0')
            active_alerts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM alerts WHERE acknowledged = 1')
            acknowledged_alerts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(DISTINCT url) FROM alerts')
            total_urls = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(CASE WHEN final_label = "malicious" THEN 1 ELSE 0 END) FROM alerts')
            malicious_count = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(CASE WHEN final_label = "suspicious" THEN 1 ELSE 0 END) FROM alerts')
            suspicious_count = cursor.fetchone()[0] or 0

            conn.close()

            # إحصائيات التحليلات من linkScanne.db
            analyses_total = 0
            analyses_today = 0
            safe_count = 0
            main_db = os.path.join(os.path.dirname(self.db_path), '..', 'linkScanne.db')
            if os.path.exists(main_db):
                try:
                    conn_main = sqlite3.connect(main_db)
                    cur = conn_main.cursor()
                    cur.execute('SELECT COUNT(*) FROM saved_analyses')
                    analyses_total = cur.fetchone()[0] or 0
                    cur.execute(
                        'SELECT COUNT(*) FROM saved_analyses WHERE date(created_at) = date("now")'
                    )
                    analyses_today = cur.fetchone()[0] or 0
                    conn_main.close()
                except Exception:
                    pass

            return {
                'urls': {
                    'total': total_urls,
                    'malicious': malicious_count,
                    'suspicious': suspicious_count,
                    'safe': safe_count
                },
                'alerts': {
                    'total': total_alerts,
                    'active': active_alerts,
                    'acknowledged': acknowledged_alerts
                },
                'analyses': {
                    'total': analyses_total,
                    'today': analyses_today
                }
            }

        except Exception as e:
            print(f"خطأ في الحصول على الإحصائيات: {e}")
            return {
                'urls': {'total': 0, 'malicious': 0, 'suspicious': 0, 'safe': 0},
                'alerts': {'total': 0, 'active': 0, 'acknowledged': 0},
                'analyses': {'total': 0, 'today': 0}
            }


alert_monitor = AlertMonitor()


def record_analysis(url, result):
    alert_monitor.record_analysis(url, result)


def get_active_alerts():
    return alert_monitor.get_active_alerts()


def acknowledge_alert(alert_id, acknowledged_by="system"):
    return alert_monitor.acknowledge_alert(alert_id, acknowledged_by)


def get_stats():
    return alert_monitor.get_stats()
