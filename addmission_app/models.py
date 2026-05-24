from django.db import models
import random

# دالة لتوليد رقم استمارة مكون من 8 أرقام فقط وغير مكرر
def generate_numeric_form_number():
    while True:
        number = str(random.randint(10000000, 99999999))
        if not Student.objects.filter(form_number=number).exists():
            return number

class University(models.Model):
    UNIVERSITY_TYPES = [('حكومية', 'حكومية'), ('أهلية', 'خاصة')]
    name = models.CharField(max_length=200, unique=True, verbose_name="اسم الجامعة")
    region = models.CharField(max_length=100, verbose_name="المنطقة/الولاية")
    university_type = models.CharField(max_length=20, choices=UNIVERSITY_TYPES, default='حكومية', verbose_name="نوع الجامعة")
    def __str__(self): return f"{self.name} ({self.university_type})"
    class Meta:
        verbose_name = "جامعة"
        verbose_name_plural = "الجامعات"

class Program(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='programs', verbose_name="الجامعة")
    name = models.CharField(max_length=200, verbose_name="اسم التخصص/الكلية")
    def __str__(self): return f"{self.name} - {self.university.name}"
    class Meta:
        verbose_name = "تخصص"
        verbose_name_plural = "التخصصات"

class Student(models.Model):
    form_number    = models.CharField(max_length=8, unique=True, editable=False, verbose_name="رقم الاستمارة")
    name           = models.CharField(max_length=200, verbose_name="اسم الطالب رباعي")
    seat_number    = models.CharField(max_length=20, verbose_name="رقم الجلوس")
    percentage     = models.FloatField(verbose_name="النسبة المئوية")
    field_of_study = models.CharField(max_length=50, verbose_name="المسار")
    phone_number   = models.CharField(max_length=20, blank=True, default='', verbose_name="رقم الهاتف")
    email_address  = models.EmailField(max_length=254, blank=True, default='', verbose_name="البريد الإلكتروني")
    def save(self, *args, **kwargs):
        if not self.form_number: self.form_number = generate_numeric_form_number()
        super().save(*args, **kwargs)
    def __str__(self): return self.name
    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"

class Application(models.Model):
    STATUS_CHOICES = [('يتم المراجعة', 'يتم المراجعة'), ('تم القبول', 'تم القبول'), ('مرفوض', 'مرفوض')]
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='application', verbose_name="الطالب")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='يتم المراجعة', verbose_name="حالة الطلب")
    accepted_program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الرغبة المقبول بها")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التقديم")
    choices_json = models.TextField(default="[]", verbose_name="الرغبات المسجلة")
    def __str__(self): return f"طلب {self.student.name}"
    class Meta:
        verbose_name = "طلب تقديم"
        verbose_name_plural = "طلبات التقديم"
# ابحث عن كلاس Choice في ملف models.py وحدثه كالتالي:
class Choice(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='choices', verbose_name="الطلب")
    # أضفنا related_name='program_choices' هنا
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, related_name='program_choices', verbose_name="البرنامج")
    priority = models.IntegerField(verbose_name="الأولوية")
    is_matched = models.BooleanField(default=False)
    class Meta:
        verbose_name = "رغبة"
        verbose_name_plural = "الرغبات"