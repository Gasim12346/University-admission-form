# أضف هذه المسارات إلى urls.py الخاص بالتطبيق
# ─────────────────────────────────────────────
# استيراد الدوال من views.py
from django.contrib import admin
from django.urls import path
from addmission_app import views
from django.urls import path, include

urlpatterns = [
    # ── الصفحات العامة ──
    path('', views.home, name='home'),
    path('addmission/', views.admission_page, name='addmission'),
    path('daleel/', views.daleel, name='daleel'),
    path('result/', views.Result, name='Result'),
    path('receipt/<int:pk>/', views.admission_receipt, name='admission_receipt'),
    path('receipt/<int:pk>/pdf/', views.admission_pdf_download, name='admission_pdf_download'),
    # ── APIs العامة ──
    path('get-programs/', views.get_programs, name='get_programs'),
    path('get-recommendations/', views.get_recommendations, name='get_recommendations'),
    path('check-result-api/', views.check_result_api, name='check_result_api'),
    path('get-csrf/', views.get_csrf_token, name='get_csrf_token'),
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    #  API جديد: جلب قائمة المدن من الداتاسيت
    path('api/get-cities/', views.api_get_cities, name='api_get_cities'),
    # ── APIs لوحة التحكم ──
    path('api/statistics/', views.api_get_statistics, name='api_get_statistics'),
    path('api/execute-allocation/', views.api_execute_allocation, name='api_execute_allocation'),
    path('api/reset-allocation/', views.api_reset_allocation, name='api_reset_allocation'),
    path('api/match-choices/', views.api_match_choices, name='api_match_choices'),
    path('api/student-programs/', views.api_get_student_programs, name='api_get_student_programs'),
    path('api/set-acceptance/', views.api_set_acceptance, name='api_set_acceptance'),
    path('api/search-student/', views.api_search_student, name='api_search_student'),
    path('admin-update-status/', views.admin_update_status, name='admin_update_status'),
    path('admin-delete-application/', views.admin_delete_application, name='admin_delete_application'),
]
