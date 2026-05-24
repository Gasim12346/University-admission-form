from django.contrib import admin
from django import forms
from .models import Student, Application, University, Program, Choice

# 1. واجهة عرض الرغبات (Inline) - محسنة بالأداء
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    # نستخدم raw_id_fields لمنع تحميل قائمة منسدلة ضخمة داخل الـ Inline
    raw_id_fields = ('program',) 
    readonly_fields = ('priority',) 
    can_delete = False
    verbose_name = "رغبة الطالب"
    verbose_name_plural = "رغبات الطالب المختارة"

# 2. تخصيص نموذج تعديل الطلب
class ApplicationAdminForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # تم تعديل هذا الجزء لإصلاح FieldError
            # بدلاً من استخدام 'choice__application' التي تسبب الخطأ، نستخدم IDs مباشرة
            allowed_program_ids = Choice.objects.filter(
                application=self.instance
            ).values_list('program_id', flat=True)
            
            self.fields['accepted_program'].queryset = Program.objects.filter(
                id__in=allowed_program_ids
            ).distinct()

# 3. إدارة طلبات التقديم (الجزء الذي تم إصلاحه)
@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    form = ApplicationAdminForm
    
    # تحسين الأداء: جلب البيانات المرتبطة في استعلام واحد لمنع التعليق
    list_select_related = ('student', 'accepted_program', 'accepted_program__university')
    
    list_display = ('get_student_name', 'get_form_number', 'get_percentage', 'status', 'accepted_program', 'created_at')
    
    # تحذير: تم إزالة 'accepted_program' من list_editable لأنها تسبب تعليق المتصفح 
    # بسبب حجم القوائم المنسدلة. تركنا 'status' فقط لسرعة التعديل.
    list_editable = ('status',) 
    
    list_filter = ('status', 'accepted_program__university', 'created_at')
    
    # إضافة خاصية البحث (ضرورية جداً للتعامل مع أعداد كبيرة)
    search_fields = ('student__name', 'student__form_number', 'student__seat_number')
    
    inlines = [ChoiceInline]
    
    # تحسين اختيار الطالب والبرنامج داخل صفحة التعديل لمنع الثقل
    raw_id_fields = ('student',) 
    autocomplete_fields = ('accepted_program',) # تتطلب تفعيل search_fields في ProgramAdmin

    fieldsets = (
        ('بيانات الطالب', {
            'fields': ('student', 'status')
        }),
        ('قرار اللجنة والقبول النهائي', {
            'fields': ('accepted_program',),
            'description': 'سيظهر هنا فقط التخصصات التي اختارها الطالب في رغباته.'
        }),
    )

    def get_student_name(self, obj):
        return obj.student.name if obj.student else "-"
    get_student_name.short_description = 'اسم الطالب'

    def get_form_number(self, obj):
        return obj.student.form_number if obj.student else "-"
    get_form_number.short_description = 'رقم الاستمارة'

    def get_percentage(self, obj):
        return f"{obj.student.percentage}%" if obj.student else "-"
    get_percentage.short_description = 'النسبة'

# 4. إدارة الجامعات
@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'university_type')
    search_fields = ('name',)

# 5. إدارة التخصصات (تمت إضافة البحث لتفعيل autocomplete)
@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'university')
    list_filter = ('university',)
    search_fields = ('name', 'university__name') # ضروري لعمل autocomplete_fields

# 6. إدارة الطلاب
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'seat_number', 'form_number', 'percentage')
    search_fields = ('name', 'seat_number', 'form_number')
    readonly_fields = ('form_number',)