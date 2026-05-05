#!/usr/bin/env bash
# سكربت البناء لـ Render — نفّذه كما هو (لا تضف --with-deps؛ يتطلب root ويفشل على Render).
set -euo pipefail
pip install -r requirements.txt
# تثبيت ثنائيات المتصفح فقط (تحميل إلى ~/.cache/ms-playwright). بدون تثبيت حزم apt.
export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1
python -m playwright install chromium
