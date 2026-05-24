# urls.py — بوابة القبول الجامعي
from django.urls import path
from addmission_app import views 

urlpatterns = [
    # ── الصفحات العامة ──
    path('', views.home, name='home'),
    path('admission/', views.admission_page, name='addmission'),
    path('daleel/', views.daleel, name='daleel'),
    path('result/', views.Result, name='Result'),
    path('receipt/<int:pk>/', views.admission_receipt, name='admission_receipt'),
    path('receipt/<int:pk>/pdf/', views.admission_pdf_download, name='admission_pdf_download'),

    # ── APIs العامة ──
    path('get-programs/', views.get_programs, name='get_programs'),
    path('get-recommendations/', views.get_recommendations, name='get_recommendations'),
    path('check-result/', views.check_result_api, name='check_result_api'),
    path('get-csrf/', views.get_csrf_token, name='get_csrf_token'),
    path('api/get-cities/', views.api_get_cities, name='api_get_cities'),
    path('api/model-info/', views.api_model_info, name='api_model_info'),

    # ── لوحة التحكم ──
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),

    # ── APIs الإحصاءات ──
    path('api/statistics/', views.api_get_statistics, name='api_get_statistics'),

    # ── APIs التوزيع ──
    path('api/execute-allocation/', views.api_execute_allocation, name='api_execute_allocation'),
    path('api/reset-allocation/', views.api_reset_allocation, name='api_reset_allocation'),

    # ── APIs الطلبات ──
    path('admin-update-status/', views.admin_update_status, name='admin_update_status'),
    path('admin-delete-application/', views.admin_delete_application, name='admin_delete_application'),
    path('api/student-programs/', views.api_get_student_programs, name='api_get_student_programs'),
    path('api/set-acceptance/', views.api_set_acceptance, name='api_set_acceptance'),
    path('api/search-student/', views.api_search_student, name='api_search_student'),
    path('api/update-status/', views.api_update_status, name='api_update_status'),
    path('api/match-choices/', views.api_match_choices, name='api_match_choices'),

    # ── APIs CRUD الطلاب ──
    path('api/edit-student/', views.api_edit_student, name='api_edit_student'),
    path('api/list-students/', views.api_list_students, name='api_list_students'),

    # ── APIs CRUD الجامعات والتخصصات ──
    path('api/edit-university/', views.api_edit_university, name='api_edit_university'),
    path('api/edit-program/', views.api_edit_program, name='api_edit_program'),
    path('api/list-universities/', views.api_list_universities, name='api_list_universities'),

    # ── APIs تعديل الطلبات ──
    path('api/edit-application-status/', views.api_edit_application_status, name='api_edit_application_status'),

    # ── APIs التقارير ──
    path('api/report-data/', views.api_report_data, name='api_report_data'),

    # ── تصدير CSV ──
    path('export-students-csv/', views.export_students_csv, name='export_students_csv'),
    path('export-applications-csv/', views.export_applications_csv, name='export_applications_csv'),
    path('export-universities-csv/', views.export_universities_csv, name='export_universities_csv'),
    path('export-report-csv/', views.export_report_csv, name='export_report_csv'),
]
