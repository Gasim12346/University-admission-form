import csv
import os
from django.core.management.base import BaseCommand
from addmission_app.models import University, Program 

class Command(BaseCommand):
    help = 'استيراد البيانات مع تصحيح نوع الجامعة بناءً على مصدر الملف'

    def handle(self, *args, **kwargs):
        # 1. تعريف الملفات والأنواع المرتبطة بها
        sources = [
            {'file': 'حكومية.csv', 'type': 'حكومية', 'uni_col': 'الجامعة', 'fac_col': 'الكلية'},
            {'file': 'اهلية.csv', 'type': 'أهلية', 'uni_col': 'un_name', 'fac_col': 'fac_name'},
        ]

        def clean(text):
            return text.strip() if text else ""

        for source in sources:
            file_path = source['file']
            uni_type = source['type']
            
            if os.path.exists(file_path):
                self.stdout.write(f"--- جاري معالجة ملف: {file_path} (تصنيف: {uni_type}) ---")
                
                with open(file_path, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        uni_name = clean(row.get(source['uni_col']))
                        prog_name = clean(row.get(source['fac_col']))
                        
                        if uni_name and prog_name:
                            # update_or_create تبحث بالاسم فقط، وإذا وجدت السجل تقوم بتحديث النوع فوراً
                            uni_obj, created = University.objects.update_or_create(
                                name=uni_name,
                                defaults={
                                    'university_type': uni_type, # هنا يتم فرض النوع بناءً على السورس
                                    'region': 'السودان' # يمكنك تغييرها لاحقاً
                                }
                            )
                            
                            # إنشاء التخصص وربطه بالجامعة
                            Program.objects.get_or_create(
                                name=prog_name,
                                university=uni_obj
                            )
                self.stdout.write(self.style.SUCCESS(f"تم الانتهاء من {file_path}"))
            else:
                self.stdout.write(self.style.WARNING(f"الملف {file_path} غير موجود."))

        self.stdout.write(self.style.SUCCESS('✅ اكتملت العملية: تم تحديث جميع الأنواع بدقة.'))