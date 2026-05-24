import os, re, pandas as pd, json, logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Q, Count, Avg, StdDev
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from .models import University, Program, Student, Application, Choice
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib import messages
from django.db import transaction
from reportlab.lib.pagesizes import A4
from reportlab.lib  import colors
from django.shortcuts import get_object_or_404
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.utils import timezone
from django.http import HttpResponse
from io import BytesIO

try:
    from .utils import AdmissionDistributionSystem
except ImportError:
    class AdmissionDistributionSystem:
        def distribute_students(self): return {"error": "System not implemented"}
        def match_all_choices(self): return {"matched": 0}
        def reset_distribution(self): return 0

logger = logging.getLogger(__name__)

# --- 1. إعدادات المسارات ودوال التنظيف المتقدمة ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'ml_models')
CSV_PATH = os.path.join(MODELS_DIR, 'DATA_SET.csv')

GLOBAL_DF = None

def clean_arabic(text):
    if not isinstance(text, str): return ""
    text = text.strip().lower()
    text = re.sub(r"[إأآ]", "ا", text)
    text = re.sub(r"[ة]", "ه", text)
    text = re.sub(r"^ال", "", text)
    text = re.sub(r"[\s-]+", " ", text)
    return text.strip()

def clean_for_match(text):
    if not text: return ""
    text = str(text).strip()
    text = re.sub(r"[-–—_()،,]", " ", text)
    text = re.sub(r"[إأآ]", "ا", text)
    text = re.sub(r"[ة]", "ه", text)
    text = re.sub(r"\b(كليه|جامعه|مركز|معهد)\b", "", text)
    return " ".join(text.split()).strip()

def normalize_ar(text):
    if not isinstance(text, str): return ''
    text = text.strip()
    text = re.sub(r'[إأآ]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text)
    text = re.sub(r'ـ', '', text)
    text = re.sub(r'[​-‏]', '', text)
    text = re.sub(r'–|—', '-', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def word_overlap_score(a, b):
    words_a = set(normalize_ar(a).split())
    words_b = set(normalize_ar(b).split())
    stop = {'في', 'من', 'و', 'ال', 'على', 'الى', 'عن', 'مع', 'لل'}
    words_a -= stop
    words_b -= stop
    if not words_a or not words_b: return 0.0
    common = words_a & words_b
    return len(common) / max(len(words_a), len(words_b))

def extract_fac_from_college(college_text):
    if not isinstance(college_text, str): return college_text
    m = re.search(r'(?<!\s)-(?!\s-)', college_text)
    if m:
        return college_text[:m.start()].strip()
    return college_text.split('-')[0].strip()

PROGRAM_LOOKUP = {}

def build_program_lookup():
    global PROGRAM_LOOKUP
    try:
        from .models import Program
        all_programs = Program.objects.select_related('university').all()
        lookup = {}
        for prog in all_programs:
            norm_uni = normalize_ar(prog.university.name)
            norm_fac = normalize_ar(prog.name)
            key = (norm_uni[:25], norm_fac[:25])
            lookup[key] = prog.id
        PROGRAM_LOOKUP = lookup
        print(f"✅ PROGRAM_LOOKUP: {len(PROGRAM_LOOKUP)} سجل")
    except Exception as e:
        print(f"⚠️ PROGRAM_LOOKUP build failed: {e}")

def find_best_program(ds_university, ds_college, uni_type_filter):
    try:
        from .models import Program
        fac_name = extract_fac_from_college(ds_college)
        norm_ds_uni = normalize_ar(ds_university)
        norm_ds_fac = normalize_ar(fac_name)
        best_prog = None
        best_score = 0.0
        for (norm_uni, norm_fac), prog_id in PROGRAM_LOOKUP.items():
            uni_score = word_overlap_score(norm_ds_uni, norm_uni)
            fac_score = word_overlap_score(norm_ds_fac, norm_fac)
            total_score = uni_score * 0.6 + fac_score * 0.4
            if total_score > best_score and total_score >= 0.5:
                try:
                    prog = Program.objects.select_related('university').get(id=prog_id)
                    if uni_type_filter in prog.university.university_type:
                        best_score = total_score
                        best_prog = prog
                except:
                    pass
        return best_prog
    except Exception as e:
        return None

def load_system_files():
    global GLOBAL_DF
    try:
        if os.path.exists(CSV_PATH):
            df = pd.read_csv(CSV_PATH, dtype=str)
            df['actual_score'] = pd.to_numeric(df['min_score'], errors='coerce').fillna(0.0)
            df['clean_loc']    = df['uni_location'].apply(clean_arabic)
            df['clean_major']  = df['major'].apply(clean_arabic)
            df['clean_type']   = df['uni_type'].apply(clean_arabic)
            df['clean_track']  = df['study_track'].apply(clean_arabic)
            df['ds_university'] = df['university']
            df['ds_college']    = df['college']
            df['ds_fac_name']   = df['college'].apply(extract_fac_from_college)
            df = df.sort_values('actual_score', ascending=True)
            GLOBAL_DF = df
            build_program_lookup()
            return True
    except Exception as e:
        print(f"🚨 Error loading CSV: {e}")
        return False

load_system_files()

# --- دالة جلب المدن من الداتاسيت ---
def get_cities_from_dataset():
    """تجلب قائمة المدن الفريدة من الداتاسيت مرتبةً أبجدياً"""
    global GLOBAL_DF
    try:
        if GLOBAL_DF is not None and 'uni_location' in GLOBAL_DF.columns:
            cities = sorted(GLOBAL_DF['uni_location'].dropna().unique().tolist())
            return [c for c in cities if str(c).strip()]
    except Exception as e:
        logger.error(f"get_cities_from_dataset error: {e}")
    return []

# --- 2. دوال مساعدة لوحة التحكم (Admin Helpers) ---
def get_current_statistics():
    try:
        applications = Application.objects.all()
        avg_res = Student.objects.aggregate(avg=Avg('percentage'))['avg']
        avg_val = round(float(avg_res), 2) if avg_res is not None else 0
        total_choices = Choice.objects.count()
        matched_choices = Choice.objects.filter(program__isnull=False).count()
        return {
            'total_applications': applications.count(),
            'pending': applications.filter(status='يتم المراجعة').count(),
            'accepted': applications.filter(status='تم القبول').count(),
            'rejected': applications.filter(status='مرفوض').count(),
            'avg_percentage': avg_val,
            'total_choices': total_choices,
            'matched_choices': matched_choices,
            'match_percentage': round((matched_choices / total_choices * 100), 1) if total_choices > 0 else 0
        }
    except Exception as e:
        logger.error(f"Statistics Error: {e}")
        return {'total_applications': 0, 'pending': 0, 'accepted': 0, 'rejected': 0, 'avg_percentage': 0}

# --- 3. محرك التوصية — شجرة القرار ---
def get_recommendations(request):
    """
    يستخدم نموذج شجرة القرار (public_model.pkl أو private_model.pkl)
    لتوليد التوصيات بناءً على مدخلات الطالب.

    Parameters (GET):
        pct      — النسبة المئوية
        field    — المسار الدراسي  (مثال: علمي-أحياء)
        major    — التخصص المطلوب (مثال: طب)
        location — المدينة        (مثال: الخرطوم)
        type     — نوع الجامعة    (حكومية | أهلية)
    """
    try:
        from .ml_engine import get_dt_recommendations, get_available_majors

        u_score    = float(request.GET.get('pct', 0))
        u_track    = request.GET.get('field', '').strip()
        u_major    = request.GET.get('major', '').strip()
        u_location = request.GET.get('location', '').strip()
        u_type     = request.GET.get('type', 'حكومية').strip()

        # اختيار النموذج بناءً على نوع الجامعة
        model_type = 'public' if 'حكوم' in u_type else 'private'

        results = get_dt_recommendations(
            track          = u_track,
            major          = u_major,
            location       = u_location,
            student_score  = u_score,
            model_type     = model_type,
            top_n          = 20,
            min_prob       = 0.001,
        )

        # إذا أرجع خطأ
        if isinstance(results, dict) and 'error' in results:
            logger.warning(f"get_recommendations DT error: {results['error']}")
            return JsonResponse({'error': results['error']}, status=400)

        # ربط نتائج النموذج بـ program IDs من قاعدة البيانات
        db_type_filter = "حكومية" if model_type == 'public' else "أهلية"
        for item in results:
            if item['id'] == 0:
                db_prog = find_best_program(item['uName'], item['pName'], db_type_filter)
                if db_prog:
                    item['id'] = db_prog.id

        return JsonResponse(results, safe=False)

    except Exception as e:
        logger.error(f"get_recommendations error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# --- API: معلومات النماذج ---
def api_model_info(request):
    """يُعيد معلومات النموذجين المتاحين."""
    try:
        from .ml_engine import get_model_info, get_available_tracks, get_available_majors, get_available_locations
        model_type = request.GET.get('type', 'private')
        return JsonResponse({
            'success':   True,
            'info':      get_model_info(model_type),
            'tracks':    get_available_tracks(model_type),
            'majors':    get_available_majors(model_type),
            'locations': get_available_locations(model_type),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# --- API: جلب قائمة المدن ---
def api_get_cities(request):
    """يُرجع قائمة المدن الموجودة في الداتاسيت"""
    cities = get_cities_from_dataset()
    return JsonResponse(cities, safe=False)

def _validate_phone(phone: str) -> bool:
    return bool(re.fullmatch(r'\+?[0-9]{9,15}', phone.strip()))

def _validate_percentage(value) -> float:
    pct = float(value)
    if not (0 <= pct <= 100):
        raise ValueError("النسبة يجب أن تكون بين 0 و 100")
    return pct

def admission_page(request):
    universities = University.objects.all().order_by('university_type', 'name')
    context = {'universities': universities}

    if request.method != 'POST':
        return render(request, 'Addmission.html', context)

    raw = {
        'studentName':  request.POST.get('studentName',  '').strip(),
        'seatNumber':   request.POST.get('seatNumber',   '').strip(),
        'percentage':   request.POST.get('percentage',   '').strip(),
        'phoneNumber':  request.POST.get('phoneNumber',  '').strip(),
        'emailAddress': request.POST.get('emailAddress', '').strip(),
        'fieldOfStudy': request.POST.get('fieldOfStudy', '').strip(),
        'choices_data': request.POST.get('choices_data', '').strip(),
        'modelType':    request.POST.get('modelType',    'حكومية'),
    }
    context['form_data'] = raw
    errors = []

    for field, label in [('studentName', 'الاسم'), ('seatNumber', 'رقم الجلوس'), ('fieldOfStudy', 'المسار')]:
        if not raw[field]:
            errors.append(f'{label} مطلوب.')

    percentage = 0.0
    try:
        percentage = _validate_percentage(raw['percentage'])
    except:
        errors.append('الرجاء إدخال نسبة مئوية صحيحة.')

    if not raw['phoneNumber'] or not _validate_phone(raw['phoneNumber']):
        errors.append('رقم الهاتف غير صحيح.')
    if raw['emailAddress']:
        try:
            validate_email(raw['emailAddress'])
        except ValidationError:
            errors.append('صيغة البريد الإلكتروني غير صحيحة.')

    if not raw['choices_data'] or raw['choices_data'] == '[]':
        errors.append('الرجاء إضافة رغبة واحدة على الأقل.')

    if raw['seatNumber'] and Student.objects.filter(seat_number=raw['seatNumber']).exists():
        errors.append('رقم الجلوس مسجل مسبقاً.')

    if errors:
        for err in errors:
            messages.error(request, err)
        return render(request, 'Addmission.html', context)

    try:
        with transaction.atomic():
            student = Student.objects.create(
                name           = raw['studentName'],
                seat_number    = raw['seatNumber'],
                percentage     = percentage,
                field_of_study = raw['fieldOfStudy'],
                phone_number   = raw['phoneNumber'],
                email_address  = raw['emailAddress'],
            )

            application = Application.objects.create(
                student      = student,
                choices_json = raw['choices_data'],
            )

            db_type_filter = "حكومية" if "حكوم" in raw['modelType'] else "أهلية"
            choices_list   = json.loads(raw['choices_data'])

            for index, item in enumerate(choices_list):
                program_obj = None
                # ✅ إصلاح: قراءة 'id' بدلاً من 'program_id' لأن executeAdd يحفظه كـ 'id'
                # نقبل كلا المفتاحين لضمان التوافق
                p_id   = item.get('id') or item.get('program_id')
                p_name = item.get('pName', '')
                u_name = item.get('uName', '')

                if p_id and str(p_id) != '0' and str(p_id).lstrip('-').isdigit() and int(p_id) > 0:
                    program_obj = Program.objects.filter(id=int(p_id)).first()

                if not program_obj and (p_name or u_name):
                    program_obj = find_best_program(u_name, p_name, db_type_filter)

                Choice.objects.create(
                    application = application,
                    program     = program_obj,
                    priority    = index + 1,
                )

        from django.urls import reverse
        return redirect(reverse('admission_receipt', kwargs={'pk': student.pk}))

    except Exception as e:
        logger.exception("Error in admission_page: %s", e)
        messages.error(request, f'حدث خطأ أثناء الحفظ: {str(e)}')
        return render(request, 'Addmission.html', context)

# --- 4. لوحة التحكم الكاملة ---
def admin_dashboard(request):
    """لوحة تحكم شاملة تعرض جميع الإحصاءات وإدارة الطلبات"""
    applications = Application.objects.select_related(
        'student', 'accepted_program__university'
    ).prefetch_related('choices__program__university').all().order_by('-created_at')

    stats = get_current_statistics()

    # إحصاءات الجامعات الأعلى طلباً
    top_universities = (
        Choice.objects
        .filter(program__isnull=False)
        .values('program__university__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # إحصاءات التخصصات الأعلى طلباً
    top_programs = (
        Choice.objects
        .filter(program__isnull=False)
        .values('program__name', 'program__university__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # توزيع حسب المسار الدراسي
    track_distribution = (
        Student.objects
        .values('field_of_study')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # توزيع حسب حالة الطلب
    status_chart = {
        'يتم المراجعة': stats.get('pending', 0),
        'تم القبول': stats.get('accepted', 0),
        'مرفوض': stats.get('rejected', 0),
    }

    context = {
        'applications': applications,
        'stats': stats,
        'top_universities': top_universities,
        'top_programs': top_programs,
        'track_distribution': track_distribution,
        'status_chart': json.dumps(status_chart),
        'universities': University.objects.all().order_by('name'),
        'programs': Program.objects.select_related('university').all().order_by('university__name'),
    }
    return render(request, 'admin_dashboard.html', context)

def admin_applications(request):
    """صفحة إدارة الطلبات مع فلاتر وبحث"""
    status_filter = request.GET.get('status', '')
    search_query  = request.GET.get('q', '').strip()
    track_filter  = request.GET.get('track', '')

    applications = Application.objects.select_related(
        'student', 'accepted_program__university'
    ).prefetch_related('choices__program__university').all()

    if status_filter:
        applications = applications.filter(status=status_filter)
    if track_filter:
        applications = applications.filter(student__field_of_study=track_filter)
    if search_query:
        applications = applications.filter(
            Q(student__name__icontains=search_query) |
            Q(student__seat_number__icontains=search_query) |
            Q(student__form_number__icontains=search_query)
        )

    applications = applications.order_by('-created_at')
    tracks = Student.objects.values_list('field_of_study', flat=True).distinct()

    context = {
        'applications': applications,
        'status_filter': status_filter,
        'search_query': search_query,
        'track_filter': track_filter,
        'tracks': tracks,
        'stats': get_current_statistics(),
    }
    return render(request, 'admin_applications.html', context)

def admin_students(request):
    """صفحة إدارة الطلاب"""
    search_query = request.GET.get('q', '').strip()
    students = Student.objects.all()

    if search_query:
        students = students.filter(
            Q(name__icontains=search_query) |
            Q(seat_number__icontains=search_query) |
            Q(form_number__icontains=search_query)
        )

    students = students.order_by('-id')
    context = {
        'students': students,
        'search_query': search_query,
        'stats': get_current_statistics(),
    }
    return render(request, 'admin_students.html', context)

def admin_universities(request):
    """صفحة إدارة الجامعات والتخصصات"""
    universities = University.objects.prefetch_related('programs').all().order_by('name')
    context = {
        'universities': universities,
        'stats': get_current_statistics(),
        'total_universities': universities.count(),
        'total_programs': Program.objects.count(),
        'gov_count': universities.filter(university_type='حكومية').count(),
        'private_count': universities.filter(university_type='أهلية').count(),
    }
    return render(request, 'admin_universities.html', context)

def admin_statistics(request):
    """صفحة إحصاءات تفصيلية"""
    stats = get_current_statistics()

    # توزيع النسب المئوية
    score_ranges = {
        '90-100': Student.objects.filter(percentage__gte=90).count(),
        '80-89':  Student.objects.filter(percentage__gte=80, percentage__lt=90).count(),
        '70-79':  Student.objects.filter(percentage__gte=70, percentage__lt=80).count(),
        '60-69':  Student.objects.filter(percentage__gte=60, percentage__lt=70).count(),
        'أقل من 60': Student.objects.filter(percentage__lt=60).count(),
    }

    top_universities = (
        Choice.objects.filter(program__isnull=False)
        .values('program__university__name', 'program__university__university_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    track_distribution = (
        Student.objects.values('field_of_study')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    context = {
        'stats': stats,
        'score_ranges': json.dumps(score_ranges),
        'score_ranges_raw': score_ranges,
        'top_universities': top_universities,
        'track_distribution': track_distribution,
    }
    return render(request, 'admin_statistics.html', context)

@csrf_exempt
@require_http_methods(["POST"])
def admin_update_status(request):
    """تحديث حالة الطلب"""
    try:
        data = json.loads(request.body)
        app_id = data.get('application_id')
        new_status = data.get('status')
        valid_statuses = ['يتم المراجعة', 'تم القبول', 'مرفوض']
        if not app_id or new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'بيانات غير صحيحة'}, status=400)
        application = Application.objects.select_related('student').get(id=int(app_id))
        application.status = new_status
        application.save()
        return JsonResponse({
            'success': True,
            'message': f'تم تحديث حالة طلب {application.student.name} إلى {new_status}'
        })
    except Application.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الطلب غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def admin_delete_application(request):
    """حذف طلب تقديم"""
    try:
        data = json.loads(request.body)
        app_id = data.get('application_id')
        if not app_id:
            return JsonResponse({'success': False, 'error': 'application_id مطلوب'}, status=400)
        with transaction.atomic():
            application = Application.objects.select_related('student').get(id=int(app_id))
            student_name = application.student.name
            student = application.student
            application.delete()
            student.delete()
        return JsonResponse({'success': True, 'message': f'تم حذف طلب {student_name} بنجاح'})
    except Application.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الطلب غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# --- 5. API الموجودة ---
@csrf_exempt
@require_http_methods(["POST"])
def api_execute_allocation(request):
    try:
        system = AdmissionDistributionSystem()
        stats = system.distribute_students()
        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_reset_allocation(request):
    try:
        system = AdmissionDistributionSystem()
        count = system.reset_distribution()
        return JsonResponse({'success': True, 'reset_count': count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def api_get_statistics(request):
    return JsonResponse({'success': True, **get_current_statistics()})

# --- 6. الدوال العامة ---
def home(request): return render(request, 'index.html')
def Result(request): return render(request, 'Result.html')
def daleel(request): return render(request, 'daleel.html', {'universities': University.objects.all()})

def check_result_api(request):
    form_no = request.GET.get('form_no')
    try:
        student = Student.objects.get(form_number=form_no)
        application = Application.objects.get(student=student)
        return JsonResponse({
            'status': 'success',
            'student_name': student.name,
            'percentage': student.percentage,
            'application_status': application.status,
            'accepted_program': application.accepted_program.name if application.accepted_program else None,
            'university_name': application.accepted_program.university.name if application.accepted_program else ""
        })
    except:
        return JsonResponse({'status': 'error', 'message': 'Not Found'})
    

def get_programs(request):
    application_id = request.GET.get('application_id')
    if application_id:
        choices = Choice.objects.filter(application_id=application_id).select_related('program__university').order_by('priority')
        results = []
        for choice in choices:
            if choice.program:
                results.append({
                    'id': choice.program.id,
                    'name': f"رغبة {choice.priority}: {choice.program.name} - {choice.program.university.name}"
                })
        return JsonResponse(results, safe=False)

    u_id = request.GET.get('university_id')
    if u_id:
        programs = Program.objects.filter(university_id=u_id).values('id', 'name')
        return JsonResponse(list(programs), safe=False)

    return JsonResponse([], safe=False)

@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({'success': True})

def admission_receipt(request, pk):
    student     = get_object_or_404(Student, pk=pk)
    application = Application.objects.filter(student=student).first()

    choices = []
    if application:
        for c in Choice.objects.filter(application=application)\
                               .select_related('program__university')\
                               .order_by('priority'):
            choices.append({
                'rank':            c.priority,
                'university_name': c.program.university.name if c.program else '—',
                'program_name':    c.program.name            if c.program else '—',
            })

    class StudentProxy:
        pass
    p = StudentProxy()
    p.form_number    = student.form_number
    p.seat_number    = student.seat_number
    p.percentage     = student.percentage
    p.field_of_study = student.field_of_study
    p.student_name   = student.name
    p.phone_number   = getattr(student, 'phone_number',  '—')
    p.email_address  = getattr(student, 'email_address', '—')
    p.application_date = application.created_at if application else timezone.now()
    p.status           = application.status     if application else 'يتم المراجعة'

    return render(request, 'admission_receipt.html', {'student': p, 'choices': choices})

def admission_pdf_download(request, pk):
    student = get_object_or_404(Student, pk=pk)
    application = Application.objects.filter(student=student).first()
    raw_choices = []
    if application:
        raw_choices = list(
            Choice.objects.filter(application=application)
                          .select_related('program__university')
                          .order_by('priority')
        )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm,   bottomMargin=2*cm,
        title=f"Admission Receipt – {student.form_number}",
        author="Ministry of Higher Education",
    )

    NAVY   = colors.HexColor('#1a3a6b')
    BLUE   = colors.HexColor('#2e5fa3')
    LIGHT  = colors.HexColor('#eef2ff')
    SILVER = colors.HexColor('#f8f9fc')
    BORDER = colors.HexColor('#c3cefc')
    GREEN  = colors.HexColor('#d4edda')
    GDARK  = colors.HexColor('#155724')

    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    story = []
    app_date   = application.created_at if application else timezone.now()
    app_status = application.status     if application else 'يتم المراجعة'

    hdr_data = [[
        Paragraph(
            'وزارة التعليم العالي والبحث العلمي<br/>'
            '<font size="9" color="#b8d0f0">Ministry of Higher Education and Scientific Research</font>',
            S('H', fontName='Helvetica-Bold', fontSize=13,
              textColor=colors.white, alignment=TA_CENTER),
        ),
        Paragraph(
            f'رقم الاستمارة<br/>'
            f'<font size="16"><b>{student.form_number}</b></font><br/>'
            f'<font size="8" color="#b8d0f0">{app_date.strftime("%Y/%m/%d")}</font>',
            S('FN', fontName='Helvetica', fontSize=9,
              textColor=colors.white, alignment=TA_CENTER),
        ),
    ]]
    hdr = Table(hdr_data, colWidths=[13*cm, 4*cm])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), NAVY),
        ('BACKGROUND',   (1,0),(1,0),   BLUE),
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING',   (0,0),(-1,-1), 18),
        ('BOTTOMPADDING',(0,0),(-1,-1), 18),
        ('LEFTPADDING',  (0,0),(-1,-1), 12),
        ('RIGHTPADDING', (0,0),(-1,-1), 12),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.3*cm))

    st_data = [[Paragraph(
        'تم استلام طلبك بنجاح  ✓  Application Received Successfully',
        S('SB', fontName='Helvetica-Bold', fontSize=10,
          textColor=GDARK, alignment=TA_CENTER),
    )]]
    st = Table(st_data, colWidths=[17*cm])
    st.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1)),
        ('TOPPADDING',   (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('BOX',          (0,0),(-1,-1), 1.5),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph(
        'إيصال تقديم طلب القبول الجامعي  |  University Admission Receipt',
        S('DT', fontName='Helvetica-Bold', fontSize=13, textColor=NAVY,
          alignment=TA_CENTER, spaceBefore=4, spaceAfter=2),
    ))
    story.append(Paragraph(
        f'تاريخ التقديم / Submission Date: '
        f'{app_date.strftime("%A, %d %B %Y  –  %H:%M:%S")}',
        S('DS', fontName='Helvetica', fontSize=8, textColor=colors.grey,
          alignment=TA_CENTER, spaceAfter=6),
    ))
    story.append(HRFlowable(width='100%', thickness=1.5, color=NAVY, spaceAfter=8))

    def info_row(label_ar, label_en, value):
        return [
            Paragraph(f'{label_ar}  /  {label_en}',
                      S(f'L{label_ar}', fontName='Helvetica-Bold', fontSize=8,
                        textColor=colors.HexColor('#7b8ab8'))),
            Paragraph(str(value),
                      S(f'V{label_ar}', fontName='Helvetica', fontSize=10,
                        textColor=colors.HexColor('#1a1a2e'))),
        ]

    def make_section(rows_data):
        tbl = Table(rows_data, colWidths=[5.5*cm, 11.5*cm])
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(0,-1), SILVER),
            ('ROWBACKGROUNDS',(1,0),(1,-1), [colors.white, LIGHT]),
            ('GRID',          (0,0),(-1,-1), 0.5, BORDER),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0),(-1,-1), 8),
            ('BOTTOMPADDING', (0,0),(-1,-1), 8),
            ('LEFTPADDING',   (0,0),(-1,-1), 10),
            ('RIGHTPADDING',  (0,0),(-1,-1), 10),
        ]))
        return tbl

    def sec_title(txt):
        return Paragraph(txt, S(f'ST{txt[:4]}', fontName='Helvetica-Bold',
                                fontSize=11, textColor=NAVY,
                                spaceBefore=12, spaceAfter=6))

    story.append(sec_title('1.  البيانات الشخصية  |  Personal Information'))
    story.append(make_section([
        info_row('الاسم الرباعي',     'Full Name',    getattr(student, 'name', getattr(student, 'student_name', '—'))),
        info_row('رقم الجلوس',        'Seat Number',  student.seat_number),
        info_row('رقم الهاتف',        'Phone Number', getattr(student, 'phone_number', '—')),
        info_row('البريد الإلكتروني', 'Email',        getattr(student, 'email_address', '—')),
    ]))

    story.append(sec_title('2.  البيانات الأكاديمية  |  Academic Information'))
    story.append(make_section([
        info_row('النسبة المئوية', 'Percentage',   f'{student.percentage}%'),
        info_row('المسار الدراسي', 'Study Track',  student.field_of_study),
        info_row('عدد الرغبات',    'No. of Choices', f'{len(raw_choices)} / 20'),
    ]))

    story.append(sec_title('3.  قائمة الرغبات  |  Selected Programs'))
    nc = S('NC', fontName='Helvetica', fontSize=9, alignment=TA_CENTER,
           textColor=colors.HexColor('#1a1a2e'))
    nb = S('NB', fontName='Helvetica-Bold', fontSize=9,
           textColor=colors.white, alignment=TA_CENTER)
    nv = S('NV', fontName='Helvetica', fontSize=9,
           textColor=colors.HexColor('#1a1a2e'))

    ch_rows = [[
        Paragraph('#', nb),
        Paragraph('الجامعة  /  University', nb),
        Paragraph('التخصص  /  Program',    nb),
    ]]
    for c in raw_choices:
        uni_name  = c.program.university.name if c.program else '—'
        prog_name = c.program.name            if c.program else '—'
        ch_rows.append([
            Paragraph(str(c.priority), nc),
            Paragraph(uni_name,  nv),
            Paragraph(prog_name, nv),
        ])

    ch_tbl = Table(ch_rows, colWidths=[1.2*cm, 8*cm, 7.8*cm])
    ch_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,0), NAVY),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, LIGHT]),
        ('GRID',          (0,0),(-1,-1), 0.5, BORDER),
        ('ALIGN',         (0,0),(0,-1),  'CENTER'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1), 7),
        ('BOTTOMPADDING', (0,0),(-1,-1), 7),
        ('LEFTPADDING',   (0,0),(-1,-1), 8),
        ('RIGHTPADDING',  (0,0),(-1,-1), 8),
    ]))
    story.append(ch_tbl)

    story.append(sec_title('4.  بيانات الطلب  |  Application Details'))
    status_map = {
        'يتم المراجعة': 'قيد المراجعة  (Pending)',
        'تم القبول':    'مقبول  (Accepted)',
        'مرفوض':        'مرفوض  (Rejected)',
    }
    story.append(make_section([
        info_row('رقم الاستمارة',  'Form Number',  student.form_number),
        info_row('تاريخ التقديم',  'Date',         app_date.strftime('%Y/%m/%d')),
        info_row('وقت التقديم',    'Time',         app_date.strftime('%H:%M:%S')),
        info_row('حالة الطلب',     'Status',       status_map.get(app_status, app_status)),
        info_row('قناة التقديم',   'Channel',      'البوابة الإلكترونية  /  Online Portal'),
    ]))

    story.append(Spacer(1, 0.6*cm))
    story.append(HRFlowable(width='100%', thickness=0.8, color=BORDER))
    story.append(Spacer(1, 0.2*cm))
    footer_s = S('FT', fontName='Helvetica', fontSize=8,
                 textColor=colors.grey, alignment=TA_CENTER)
    story.append(Paragraph(
        'جميع الحقوق محفوظة لوزارة التعليم العالي والبحث العلمي  '
        '|  All rights reserved © Ministry of Higher Education',
        footer_s,
    ))
    story.append(Paragraph(
        f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")}  |  {student.form_number}',
        footer_s,
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="admission_{student.form_number}.pdf"'
    )
    return response

# --- API لوحة التحكم ---
@csrf_exempt
@require_http_methods(["POST"])
def api_match_choices(request):
    try:
        unmatched = Choice.objects.filter(program__isnull=True)
        total = unmatched.count()
        matched_count = 0
        for choice in unmatched:
            try:
                choices_list = json.loads(choice.application.choices_json or '[]')
                idx = choice.priority - 1
                if idx < len(choices_list):
                    item = choices_list[idx]
                    p_name = item.get('pName', '')
                    u_name = item.get('uName', '')
                    prog = find_best_program(u_name, p_name, 'حكومية') or find_best_program(u_name, p_name, 'أهلية')
                    if prog:
                        choice.program = prog
                        choice.save()
                        matched_count += 1
            except Exception:
                continue
        return JsonResponse({'success': True, 'matched': matched_count, 'total': total,
                             'message': f'تم مطابقة {matched_count} من {total} رغبة'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_http_methods(["GET"])
def api_get_student_programs(request):
    app_id = request.GET.get('application_id')
    if not app_id:
        return JsonResponse({'success': False, 'error': 'application_id مطلوب'}, status=400)
    try:
        application = Application.objects.prefetch_related(
            'choices__program__university'
        ).get(id=int(app_id))
        programs = []
        for choice in application.choices.filter(program__isnull=False).order_by('priority'):
            programs.append({
                'id': choice.program.id,
                'name': choice.program.name,
                'university': choice.program.university.name,
                'priority': choice.priority,
            })
        return JsonResponse({'success': True, 'programs': programs,
                             'student_name': application.student.name})
    except Application.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الطلب غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_set_acceptance(request):
    try:
        data = json.loads(request.body)
        app_id     = data.get('application_id')
        program_id = data.get('program_id')
        if not app_id or not program_id:
            return JsonResponse({'success': False, 'error': 'application_id و program_id مطلوبان'}, status=400)
        with transaction.atomic():
            application = Application.objects.select_related('student').get(id=int(app_id))
            program     = Program.objects.select_related('university').get(id=int(program_id))
            if not application.choices.filter(program_id=program_id).exists():
                return JsonResponse({'success': False, 'error': 'هذا البرنامج ليس من رغبات الطالب'}, status=400)
            application.accepted_program = program
            application.status = 'تم القبول'
            application.save()
        return JsonResponse({'success': True,
                             'message': f'تم قبول {application.student.name} في {program.name} ',
                             'program_name': program.name,
                             'university_name': program.university.name})
    except Application.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الطلب غير موجود'}, status=404)
    except Program.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'البرنامج غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_http_methods(["GET"])
def api_search_student(request):
    seat = request.GET.get('seat_number', '').strip()
    form = request.GET.get('form_number', '').strip()
    if not seat and not form:
        return JsonResponse({'success': False, 'error': 'أدخل رقم الجلوس أو رقم الاستمارة'}, status=400)
    try:
        student     = Student.objects.get(seat_number=seat) if seat else Student.objects.get(form_number=form)
        application = Application.objects.select_related('accepted_program__university').get(student=student)
        return JsonResponse({'success': True, 'application': {
            'id':             application.id,
            'student_name':   student.name,
            'seat_number':    student.seat_number,
            'form_number':    student.form_number,
            'percentage':     student.percentage,
            'field_of_study': student.field_of_study,
            'status':         application.status,
            'accepted_program': {
                'name':       application.accepted_program.name,
                'university': application.accepted_program.university.name,
            } if application.accepted_program else None,
        }})
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'لم يُعثر على طالب بهذا الرقم'}, status=404)
    except Application.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'لا يوجد طلب لهذا الطالب'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_update_status(request):
    """نفس admin_update_status لكن بمسار API"""
    return admin_update_status(request)


# ═══════════════════════════════════════════════════════════════
#  📊 CSV EXPORT APIs — تصدير البيانات
# ═══════════════════════════════════════════════════════════════

import csv
from datetime import datetime

def _csv_response(filename):
    """ينشئ HttpResponse جاهز لـ CSV بترميز UTF-8 مع BOM للعربية في Excel"""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["GET"])
def export_students_csv(request):
    """تصدير جدول الطلاب كاملاً بصيغة CSV"""
    response = _csv_response(f'students_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
    writer = csv.writer(response)
    writer.writerow(['رقم الاستمارة', 'الاسم', 'رقم الجلوس', 'النسبة المئوية',
                     'المسار الدراسي', 'رقم الهاتف', 'البريد الإلكتروني',
                     'حالة الطلب', 'البرنامج المقبول', 'الجامعة المقبولة', 'تاريخ التسجيل'])
    students = Student.objects.prefetch_related(
        'application_set__accepted_program__university'
    ).all().order_by('id')
    for s in students:
        app = s.application_set.first()
        writer.writerow([
            s.form_number,
            s.name,
            s.seat_number,
            s.percentage,
            s.field_of_study,
            getattr(s, 'phone_number', ''),
            getattr(s, 'email_address', ''),
            app.status if app else '',
            app.accepted_program.name if app and app.accepted_program else '',
            app.accepted_program.university.name if app and app.accepted_program else '',
            s.id,
        ])
    return response


@require_http_methods(["GET"])
def export_applications_csv(request):
    """تصدير جدول الطلبات مع الرغبات"""
    status_filter = request.GET.get('status', '')
    track_filter  = request.GET.get('track', '')
    response = _csv_response(f'applications_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
    writer = csv.writer(response)
    writer.writerow(['رقم الطلب', 'رقم الاستمارة', 'اسم الطالب', 'رقم الجلوس',
                     'النسبة', 'المسار', 'الحالة', 'البرنامج المقبول',
                     'الجامعة المقبولة', 'عدد الرغبات', 'تاريخ التقديم'])
    apps = Application.objects.select_related(
        'student', 'accepted_program__university'
    ).prefetch_related('choices').all().order_by('-created_at')
    if status_filter:
        apps = apps.filter(status=status_filter)
    if track_filter:
        apps = apps.filter(student__field_of_study=track_filter)
    for app in apps:
        s = app.student
        writer.writerow([
            app.id,
            s.form_number,
            s.name,
            s.seat_number,
            s.percentage,
            s.field_of_study,
            app.status,
            app.accepted_program.name if app.accepted_program else '',
            app.accepted_program.university.name if app.accepted_program else '',
            app.choices.count(),
            app.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


@require_http_methods(["GET"])
def export_universities_csv(request):
    """تصدير جدول الجامعات والتخصصات"""
    response = _csv_response(f'universities_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
    writer = csv.writer(response)
    writer.writerow(['رقم الجامعة', 'اسم الجامعة', 'نوع الجامعة',
                     'رقم التخصص', 'اسم التخصص', 'عدد الطلاب المقبولين'])
    universities = University.objects.prefetch_related('programs').all().order_by('name')
    for uni in universities:
        programs = uni.programs.all()
        if programs.exists():
            for prog in programs:
                accepted_count = Application.objects.filter(
                    accepted_program=prog, status='تم القبول'
                ).count()
                writer.writerow([
                    uni.id, uni.name, uni.university_type,
                    prog.id, prog.name, accepted_count,
                ])
        else:
            writer.writerow([uni.id, uni.name, uni.university_type, '', '', ''])
    return response


@require_http_methods(["GET"])
def export_report_csv(request):
    """
    تصدير تقرير إحصائي شامل — يشمل:
    ملخص + توزيع النسب + توزيع المسارات + أعلى الجامعات
    """
    report_type = request.GET.get('type', 'summary')
    response = _csv_response(f'report_{report_type}_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
    writer = csv.writer(response)

    if report_type == 'summary':
        stats = get_current_statistics()
        writer.writerow(['📊 تقرير ملخص النظام', '', datetime.now().strftime('%Y-%m-%d %H:%M')])
        writer.writerow([])
        writer.writerow(['البيان', 'القيمة'])
        writer.writerow(['إجمالي الطلبات',    stats['total_applications']])
        writer.writerow(['قيد المراجعة',       stats['pending']])
        writer.writerow(['تم القبول',          stats['accepted']])
        writer.writerow(['مرفوض',              stats['rejected']])
        writer.writerow(['متوسط النسبة',       stats['avg_percentage']])
        writer.writerow(['إجمالي الرغبات',     stats['total_choices']])
        writer.writerow(['رغبات مرتبطة',       stats['matched_choices']])
        writer.writerow(['نسبة الارتباط %',    stats['match_percentage']])
        writer.writerow([])
        writer.writerow(['توزيع النسب المئوية', ''])
        writer.writerow(['النطاق', 'عدد الطلاب'])
        ranges = [
            ('90 - 100', Student.objects.filter(percentage__gte=90).count()),
            ('80 - 89',  Student.objects.filter(percentage__gte=80, percentage__lt=90).count()),
            ('70 - 79',  Student.objects.filter(percentage__gte=70, percentage__lt=80).count()),
            ('60 - 69',  Student.objects.filter(percentage__gte=60, percentage__lt=70).count()),
            ('أقل من 60',Student.objects.filter(percentage__lt=60).count()),
        ]
        for label, count in ranges:
            writer.writerow([label, count])

    elif report_type == 'tracks':
        writer.writerow(['📚 تقرير توزيع المسارات الدراسية', '', datetime.now().strftime('%Y-%m-%d %H:%M')])
        writer.writerow([])
        writer.writerow(['المسار الدراسي', 'عدد الطلاب', 'عدد المقبولين', 'نسبة القبول %'])
        tracks = Student.objects.values('field_of_study').annotate(count=Count('id')).order_by('-count')
        for t in tracks:
            track_name = t['field_of_study']
            total = t['count']
            accepted = Application.objects.filter(
                student__field_of_study=track_name, status='تم القبول'
            ).count()
            pct = round(accepted / total * 100, 1) if total > 0 else 0
            writer.writerow([track_name, total, accepted, pct])

    elif report_type == 'universities':
        writer.writerow(['🏛️ تقرير الجامعات الأعلى طلباً', '', datetime.now().strftime('%Y-%m-%d %H:%M')])
        writer.writerow([])
        writer.writerow(['الجامعة', 'نوع الجامعة', 'عدد الرغبات', 'عدد المقبولين'])
        unis = (
            Choice.objects.filter(program__isnull=False)
            .values('program__university__name', 'program__university__university_type')
            .annotate(choices_count=Count('id'))
            .order_by('-choices_count')
        )
        for u in unis:
            name = u['program__university__name']
            uni_type = u['program__university__university_type']
            accepted = Application.objects.filter(
                accepted_program__university__name=name, status='تم القبول'
            ).count()
            writer.writerow([name, uni_type, u['choices_count'], accepted])

    elif report_type == 'accepted':
        writer.writerow(['✅ تقرير الطلاب المقبولين', '', datetime.now().strftime('%Y-%m-%d %H:%M')])
        writer.writerow([])
        writer.writerow(['الاسم', 'رقم الجلوس', 'النسبة', 'المسار',
                         'البرنامج المقبول', 'الجامعة', 'تاريخ القبول'])
        accepted_apps = Application.objects.filter(status='تم القبول').select_related(
            'student', 'accepted_program__university'
        ).order_by('-created_at')
        for app in accepted_apps:
            s = app.student
            writer.writerow([
                s.name, s.seat_number, s.percentage, s.field_of_study,
                app.accepted_program.name if app.accepted_program else '',
                app.accepted_program.university.name if app.accepted_program else '',
                app.created_at.strftime('%Y-%m-%d'),
            ])

    return response


# ═══════════════════════════════════════════════════════════════
#  ✏️ EDIT APIs — تعديل البيانات
# ═══════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(["POST"])
def api_edit_student(request):
    """تعديل بيانات طالب"""
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        if not student_id:
            return JsonResponse({'success': False, 'error': 'student_id مطلوب'}, status=400)

        student = get_object_or_404(Student, id=int(student_id))
        errors = []

        # تحديث الحقول المرسلة فقط
        if 'name' in data:
            val = str(data['name']).strip()
            if not val:
                errors.append('الاسم لا يمكن أن يكون فارغاً')
            else:
                student.name = val

        if 'seat_number' in data:
            val = str(data['seat_number']).strip()
            if not val:
                errors.append('رقم الجلوس لا يمكن أن يكون فارغاً')
            elif Student.objects.filter(seat_number=val).exclude(id=student.id).exists():
                errors.append('رقم الجلوس مستخدم من طالب آخر')
            else:
                student.seat_number = val

        if 'percentage' in data:
            try:
                pct = float(data['percentage'])
                if not (0 <= pct <= 100):
                    errors.append('النسبة يجب أن تكون بين 0 و 100')
                else:
                    student.percentage = pct
            except (ValueError, TypeError):
                errors.append('النسبة يجب أن تكون رقماً')

        if 'field_of_study' in data:
            val = str(data['field_of_study']).strip()
            if val:
                student.field_of_study = val

        if 'phone_number' in data:
            val = str(data['phone_number']).strip()
            if val and not _validate_phone(val):
                errors.append('رقم الهاتف غير صحيح')
            elif val:
                student.phone_number = val

        if 'email_address' in data:
            val = str(data['email_address']).strip()
            if val:
                try:
                    validate_email(val)
                    student.email_address = val
                except ValidationError:
                    errors.append('صيغة البريد الإلكتروني غير صحيحة')

        if errors:
            return JsonResponse({'success': False, 'errors': errors}, status=400)

        student.save()
        return JsonResponse({
            'success': True,
            'message': f'تم تحديث بيانات الطالب {student.name} بنجاح',
            'student': {
                'id': student.id,
                'name': student.name,
                'seat_number': student.seat_number,
                'percentage': float(student.percentage),
                'field_of_study': student.field_of_study,
            }
        })
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الطالب غير موجود'}, status=404)
    except Exception as e:
        logger.exception("api_edit_student error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_edit_university(request):
    """تعديل بيانات جامعة أو إضافة جديدة"""
    try:
        data = json.loads(request.body)
        action = data.get('action', 'edit')   # edit | add | delete

        if action == 'add':
            name = str(data.get('name', '')).strip()
            uni_type = str(data.get('university_type', '')).strip()
            if not name:
                return JsonResponse({'success': False, 'error': 'اسم الجامعة مطلوب'}, status=400)
            if University.objects.filter(name=name).exists():
                return JsonResponse({'success': False, 'error': 'الجامعة موجودة مسبقاً'}, status=400)
            uni = University.objects.create(name=name, university_type=uni_type)
            build_program_lookup()
            return JsonResponse({
                'success': True,
                'message': f'تمت إضافة جامعة {uni.name} بنجاح',
                'university': {'id': uni.id, 'name': uni.name, 'university_type': uni.university_type}
            })

        elif action == 'edit':
            uni_id = data.get('university_id')
            if not uni_id:
                return JsonResponse({'success': False, 'error': 'university_id مطلوب'}, status=400)
            uni = get_object_or_404(University, id=int(uni_id))
            if 'name' in data:
                new_name = str(data['name']).strip()
                if not new_name:
                    return JsonResponse({'success': False, 'error': 'الاسم لا يمكن أن يكون فارغاً'}, status=400)
                if University.objects.filter(name=new_name).exclude(id=uni.id).exists():
                    return JsonResponse({'success': False, 'error': 'هذا الاسم مستخدم لجامعة أخرى'}, status=400)
                uni.name = new_name
            if 'university_type' in data:
                uni.university_type = str(data['university_type']).strip()
            uni.save()
            build_program_lookup()
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث بيانات {uni.name} بنجاح',
                'university': {'id': uni.id, 'name': uni.name, 'university_type': uni.university_type}
            })

        elif action == 'delete':
            uni_id = data.get('university_id')
            if not uni_id:
                return JsonResponse({'success': False, 'error': 'university_id مطلوب'}, status=400)
            uni = get_object_or_404(University, id=int(uni_id))
            program_count = uni.programs.count()
            accepted_count = Application.objects.filter(
                accepted_program__university=uni, status='تم القبول'
            ).count()
            if accepted_count > 0:
                return JsonResponse({
                    'success': False,
                    'error': f'لا يمكن حذف الجامعة — لديها {accepted_count} طالب مقبول فيها'
                }, status=400)
            uni_name = uni.name
            uni.delete()
            build_program_lookup()
            return JsonResponse({
                'success': True,
                'message': f'تم حذف جامعة {uni_name} و{program_count} تخصص تابع لها'
            })

        return JsonResponse({'success': False, 'error': 'action غير معروف'}, status=400)

    except Exception as e:
        logger.exception("api_edit_university error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_edit_program(request):
    """تعديل بيانات تخصص أو إضافة / حذف"""
    try:
        data = json.loads(request.body)
        action = data.get('action', 'edit')

        if action == 'add':
            name   = str(data.get('name', '')).strip()
            uni_id = data.get('university_id')
            if not name or not uni_id:
                return JsonResponse({'success': False, 'error': 'name وuniversity_id مطلوبان'}, status=400)
            uni = get_object_or_404(University, id=int(uni_id))
            if Program.objects.filter(name=name, university=uni).exists():
                return JsonResponse({'success': False, 'error': 'التخصص موجود مسبقاً في هذه الجامعة'}, status=400)
            prog = Program.objects.create(name=name, university=uni)
            build_program_lookup()
            return JsonResponse({
                'success': True,
                'message': f'تمت إضافة تخصص {prog.name} في {uni.name}',
                'program': {'id': prog.id, 'name': prog.name, 'university': uni.name}
            })

        elif action == 'edit':
            prog_id = data.get('program_id')
            if not prog_id:
                return JsonResponse({'success': False, 'error': 'program_id مطلوب'}, status=400)
            prog = get_object_or_404(Program, id=int(prog_id))
            if 'name' in data:
                new_name = str(data['name']).strip()
                if not new_name:
                    return JsonResponse({'success': False, 'error': 'الاسم لا يمكن أن يكون فارغاً'}, status=400)
                prog.name = new_name
            if 'university_id' in data:
                prog.university = get_object_or_404(University, id=int(data['university_id']))
            prog.save()
            build_program_lookup()
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث التخصص {prog.name} بنجاح',
                'program': {'id': prog.id, 'name': prog.name, 'university': prog.university.name}
            })

        elif action == 'delete':
            prog_id = data.get('program_id')
            if not prog_id:
                return JsonResponse({'success': False, 'error': 'program_id مطلوب'}, status=400)
            prog = get_object_or_404(Program, id=int(prog_id))
            accepted_count = Application.objects.filter(
                accepted_program=prog, status='تم القبول'
            ).count()
            if accepted_count > 0:
                return JsonResponse({
                    'success': False,
                    'error': f'لا يمكن حذف التخصص — لديه {accepted_count} طالب مقبول فيه'
                }, status=400)
            prog_name = prog.name
            prog.delete()
            build_program_lookup()
            return JsonResponse({'success': True, 'message': f'تم حذف تخصص {prog_name} بنجاح'})

        return JsonResponse({'success': False, 'error': 'action غير معروف'}, status=400)

    except Exception as e:
        logger.exception("api_edit_program error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_edit_application_status(request):
    """تعديل حالة طلب وتغيير البرنامج المقبول"""
    try:
        data   = json.loads(request.body)
        app_id = data.get('application_id')
        if not app_id:
            return JsonResponse({'success': False, 'error': 'application_id مطلوب'}, status=400)

        application = get_object_or_404(Application, id=int(app_id))

        if 'status' in data:
            valid = ['يتم المراجعة', 'تم القبول', 'مرفوض']
            if data['status'] not in valid:
                return JsonResponse({'success': False, 'error': 'حالة غير صحيحة'}, status=400)
            application.status = data['status']

        if 'accepted_program_id' in data:
            prog_id = data['accepted_program_id']
            if prog_id:
                application.accepted_program = get_object_or_404(Program, id=int(prog_id))
            else:
                application.accepted_program = None

        application.save()
        return JsonResponse({
            'success': True,
            'message': f'تم تحديث الطلب بنجاح — الحالة: {application.status}'
        })
    except Exception as e:
        logger.exception("api_edit_application_status error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════
#  📋 REPORT APIs — بيانات التقارير للعرض في الواجهة
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET"])
def api_report_data(request):
    """
    يُعيد بيانات تقرير كـ JSON للعرض في الواجهة قبل التصدير.
    report_type: summary | tracks | universities | accepted | score_dist
    """
    report_type = request.GET.get('type', 'summary')

    try:
        if report_type == 'summary':
            stats = get_current_statistics()
            avg_pct_res = Student.objects.aggregate(
                avg=Avg('percentage'), std=StdDev('percentage')
            )
            data = {
                **stats,
                'std_percentage': round(float(avg_pct_res['std'] or 0), 2),
                'total_universities': University.objects.count(),
                'total_programs': Program.objects.count(),
                'gov_universities': University.objects.filter(university_type='حكومية').count(),
                'private_universities': University.objects.filter(university_type='أهلية').count(),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

        elif report_type == 'score_dist':
            ranges = [
                {'range': '90-100', 'min': 90,  'max': 100, 'count': Student.objects.filter(percentage__gte=90).count()},
                {'range': '80-89',  'min': 80,  'max': 89,  'count': Student.objects.filter(percentage__gte=80, percentage__lt=90).count()},
                {'range': '70-79',  'min': 70,  'max': 79,  'count': Student.objects.filter(percentage__gte=70, percentage__lt=80).count()},
                {'range': '60-69',  'min': 60,  'max': 69,  'count': Student.objects.filter(percentage__gte=60, percentage__lt=70).count()},
                {'range': 'أقل 60', 'min': 0,   'max': 59,  'count': Student.objects.filter(percentage__lt=60).count()},
            ]
            data = {'ranges': ranges}

        elif report_type == 'tracks':
            tracks = []
            for t in Student.objects.values('field_of_study').annotate(
                total=Count('id')
            ).order_by('-total'):
                name = t['field_of_study']
                accepted = Application.objects.filter(
                    student__field_of_study=name, status='تم القبول'
                ).count()
                rejected = Application.objects.filter(
                    student__field_of_study=name, status='مرفوض'
                ).count()
                tracks.append({
                    'name': name,
                    'total': t['total'],
                    'accepted': accepted,
                    'rejected': rejected,
                    'pending': t['total'] - accepted - rejected,
                    'acceptance_rate': round(accepted / t['total'] * 100, 1) if t['total'] > 0 else 0,
                })
            data = {'tracks': tracks}

        elif report_type == 'universities':
            unis = []
            for u in (
                Choice.objects.filter(program__isnull=False)
                .values('program__university__id', 'program__university__name',
                        'program__university__university_type')
                .annotate(choices_count=Count('id'))
                .order_by('-choices_count')[:20]
            ):
                uni_name = u['program__university__name']
                accepted = Application.objects.filter(
                    accepted_program__university__name=uni_name, status='تم القبول'
                ).count()
                unis.append({
                    'id':           u['program__university__id'],
                    'name':         uni_name,
                    'type':         u['program__university__university_type'],
                    'choices':      u['choices_count'],
                    'accepted':     accepted,
                    'programs_count': Program.objects.filter(
                        university__name=uni_name
                    ).count(),
                })
            data = {'universities': unis}

        elif report_type == 'accepted':
            accepted_apps = Application.objects.filter(status='تم القبول').select_related(
                'student', 'accepted_program__university'
            ).order_by('accepted_program__university__name')
            rows = []
            for app in accepted_apps:
                s = app.student
                rows.append({
                    'name':       s.name,
                    'seat':       s.seat_number,
                    'percentage': float(s.percentage),
                    'track':      s.field_of_study,
                    'program':    app.accepted_program.name if app.accepted_program else '',
                    'university': app.accepted_program.university.name if app.accepted_program else '',
                    'date':       app.created_at.strftime('%Y-%m-%d'),
                })
            data = {'accepted': rows, 'total': len(rows)}

        else:
            return JsonResponse({'success': False, 'error': 'نوع التقرير غير معروف'}, status=400)

        return JsonResponse({'success': True, 'data': data})

    except Exception as e:
        logger.exception("api_report_data error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_list_students(request):
    """قائمة الطلاب للتعديل — مع بحث وصفحات"""
    search = request.GET.get('q', '').strip()
    page   = int(request.GET.get('page', 1))
    limit  = int(request.GET.get('limit', 50))

    students = Student.objects.prefetch_related('application_set').all()
    if search:
        students = students.filter(
            Q(name__icontains=search) |
            Q(seat_number__icontains=search) |
            Q(form_number__icontains=search)
        )
    students = students.order_by('id')
    total = students.count()
    start = (page - 1) * limit
    students_page = students[start:start + limit]

    rows = []
    for s in students_page:
        app = s.application_set.first()
        rows.append({
            'id':            s.id,
            'form_number':   s.form_number,
            'name':          s.name,
            'seat_number':   s.seat_number,
            'percentage':    float(s.percentage),
            'field_of_study':s.field_of_study,
            'phone_number':  getattr(s, 'phone_number', ''),
            'email_address': getattr(s, 'email_address', ''),
            'status':        app.status if app else '',
            'application_id':app.id if app else None,
        })
    return JsonResponse({
        'success': True,
        'students': rows,
        'total': total,
        'page': page,
        'pages': (total + limit - 1) // limit,
    })


@require_http_methods(["GET"])
def api_list_universities(request):
    """قائمة الجامعات والتخصصات للتعديل"""
    unis = University.objects.prefetch_related('programs').all().order_by('name')
    result = []
    for u in unis:
        result.append({
            'id':             u.id,
            'name':           u.name,
            'university_type':u.university_type,
            'programs_count': u.programs.count(),
            'programs': [
                {
                    'id':   p.id,
                    'name': p.name,
                    'accepted_count': Application.objects.filter(
                        accepted_program=p, status='تم القبول'
                    ).count(),
                }
                for p in u.programs.all().order_by('name')
            ],
        })
    return JsonResponse({'success': True, 'universities': result})
