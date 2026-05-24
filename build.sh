#!/usr/bin/env bash
# exit on error
set -o errexit

# تثبيت المكتبات
pip install -r requirements.txt

# تجميع ملفات الستاتيك والـ CSS
python manage.py collectstatic --no-input

# تشغيل الـ Migrate لربط جداول دجانغو بسيرفر Aiven
python manage.py migrate

# إنشاء حساب المدير تلقائياً دون الحاجة لكتابة بيانات في الـ Shell
if [ "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --no-input || true
fi