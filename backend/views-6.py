import json
import re
import logging
from io import BytesIO

from django.shortcuts              import render, redirect, get_object_or_404
from django.http                   import JsonResponse, HttpResponse
from django.views.decorators.http  import require_GET
from django.core.exceptions        import ValidationError
from django.core.validators        import validate_email
from django.contrib                import messages
from django.db                     import transaction
from django.utils                  import timezone

from reportlab.lib.pagesizes       import A4
from reportlab.lib                 import colors
from reportlab.lib.units           import cm
from reportlab.platypus            import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles          import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase             import pdfmetrics
from reportlab.pdfbase.ttfonts     import TTFont
from reportlab.lib.enums           import TA_CENTER, TA_RIGHT, TA_LEFT

from .models import University, Program, Student, StudentChoice

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  Helper validators
# ═══════════════════════════════════════════════════════════════

def _validate_phone(phone: str) -> bool:
    return bool(re.fullmatch(r'\+?[0-9]{9,15}', phone.strip()))


def _validate_percentage(value) -> float:
    pct = float(value)
    if not (0 <= pct <= 100):
        raise ValueError("النسبة يجب أن تكون بين 0 و 100")
    return pct


# ═══════════════════════════════════════════════════════════════
#  Main admission view
# ═══════════════════════════════════════════════════════════════

def addmission(request):
    """
    GET  -> blank form.
    POST -> validate -> save -> redirect to receipt page.
    """
    universities = University.objects.all().order_by('university_type', 'name')
    context = {'universities': universities}

    if request.method != 'POST':
        return render(request, 'admission.html', context)

    raw = {
        'studentName':  request.POST.get('studentName',  '').strip(),
        'seatNumber':   request.POST.get('seatNumber',   '').strip(),
        'percentage':   request.POST.get('percentage',   '').strip(),
        'phoneNumber':  request.POST.get('phoneNumber',  '').strip(),
        'emailAddress': request.POST.get('emailAddress', '').strip(),
        'fieldOfStudy': request.POST.get('fieldOfStudy', '').strip(),
        'choices_data': request.POST.get('choices_data', '').strip(),
    }
    context['form_data'] = raw

    errors = []

    for field, label in [
        ('studentName',  'الاسم الرباعي'),
        ('seatNumber',   'رقم الجلوس'),
        ('fieldOfStudy', 'المسار الدراسي'),
    ]:
        if not raw[field]:
            errors.append(f'{label} مطلوب.')

    percentage = None
    try:
        percentage = _validate_percentage(raw['percentage'])
    except (ValueError, TypeError):
        errors.append('الرجاء إدخال نسبة مئوية صحيحة بين 0 و 100.')

    if not raw['phoneNumber']:
        errors.append('رقم الهاتف مطلوب.')
    elif not _validate_phone(raw['phoneNumber']):
        errors.append('رقم الهاتف غير صحيح (9-15 رقماً).')

    if not raw['emailAddress']:
        errors.append('البريد الإلكتروني مطلوب.')
    else:
        try:
            validate_email(raw['emailAddress'])
        except ValidationError:
            errors.append('صيغة البريد الإلكتروني غير صحيحة.')

    choices = []
    if not raw['choices_data']:
        errors.append('الرجاء إضافة رغبة واحدة على الأقل.')
    else:
        try:
            choices = json.loads(raw['choices_data'])
            if not isinstance(choices, list) or len(choices) == 0:
                errors.append('الرجاء إضافة رغبة واحدة على الأقل.')
            elif len(choices) > 20:
                errors.append('الحد الأقصى للرغبات هو 20.')
        except (json.JSONDecodeError, ValueError):
            errors.append('بيانات الرغبات غير صحيحة.')

    if raw['seatNumber'] and Student.objects.filter(seat_number=raw['seatNumber']).exists():
        errors.append('رقم الجلوس مسجل مسبقاً.')

    if errors:
        for err in errors:
            messages.error(request, err)
        return render(request, 'admission.html', context)

    try:
        with transaction.atomic():
            student = Student.objects.create(
                student_name   = raw['studentName'],
                seat_number    = raw['seatNumber'],
                percentage     = percentage,
                phone_number   = raw['phoneNumber'],
                email_address  = raw['emailAddress'],
                field_of_study = raw['fieldOfStudy'],
            )
            for rank, choice in enumerate(choices, start=1):
                program_id   = choice.get('program_id')
                program_name = choice.get('pName', '').strip()
                uni_name     = choice.get('uName', '').strip()
                program_obj  = None
                if program_id:
                    try:
                        program_obj = Program.objects.get(pk=int(program_id))
                    except (Program.DoesNotExist, ValueError):
                        pass
                StudentChoice.objects.create(
                    student         = student,
                    program         = program_obj,
                    program_name    = program_name,
                    university_name = uni_name,
                    rank            = rank,
                )
    except Exception as exc:
        logger.exception("Error saving admission form: %s", exc)
        messages.error(request, 'حدث خطأ أثناء حفظ البيانات. حاول مجدداً.')
        return render(request, 'admission.html', context)

    # Redirect to receipt
    return redirect('admission_receipt', pk=student.pk)


# ═══════════════════════════════════════════════════════════════
#  Receipt page  (HTML – browser print-to-PDF)
# ═══════════════════════════════════════════════════════════════

def admission_receipt(request, pk):
    student = get_object_or_404(Student, pk=pk)
    choices = student.choices.all().order_by('rank')
    return render(request, 'admission_receipt.html', {
        'student': student,
        'choices': choices,
    })


# ═══════════════════════════════════════════════════════════════
#  PDF download  (ReportLab server-side)════════════════════════════════

def admission_pdf_download(request, pk):
    """
    Generates a structured PDF using ReportLab and streams it as a
    file download.  Arabic text is stored as unicode; labels are
    bilingual (AR / EN) for maximum portability.

    To enable a proper Arabic font, place a TTF file on the server
    (e.g. Amiri-Regular.ttf) and uncomment the lines below:

        ARABIC_FONT_PATH = '/path/to/Amiri-Regular.ttf'
        pdfmetrics.registerFont(TTFont('Arabic', ARABIC_FONT_PATH))
        # Then replace 'Helvetica' / 'Helvetica-Bold' with 'Arabic'
    """
    student = get_object_or_404(Student, pk=pk)
    choices = student.choices.all().order_by('rank')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm,   bottomMargin=2*cm,
        title=f"Admission Receipt – {student.form_number}",
        author="Ministry of Higher Education",
    )

    # ── Colours ──────────────────────────────────────────────────
    NAVY   = colors.HexColor('#1a3a6b')
    BLUE   = colors.HexColor('#2e5fa3')
    LIGHT  = colors.HexColor('#eef2ff')
    SILVER = colors.HexColor('#f8f9fc')
    BORDER = colors.HexColor('#c3cefc')
    GREEN  = colors.HexColor('#d4edda')
    GDARK  = colors.HexColor('#155724')

    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    # ── Story ─────────────────────────────────────────────────────
    story = []

    # Header
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
            f'<font size="8" color="#b8d0f0">{student.application_date.strftime("%Y/%m/%d")}</font>',
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

    # Status banner
    st_data = [[Paragraph(
        'تم استلام طلبك بنجاح  ✓  Application Received Successfully',
        S('SB', fontName='Helvetica-Bold', fontSize=10,
          textColor=GDARK, alignment=TA_CENTER),
    )]]
    st = Table(st_data, colWidths=[17*cm])
    st.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), GREEN),
        ('TOPPADDING',   (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('BOX',          (0,0),(-1,-1), 1.5, colors.HexColor('#28a745')),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.4*cm))

    # Doc title
    story.append(Paragraph(
        'إيصال تقديم طلب القبول الجامعي  |  University Admission Receipt',
        S('DT', fontName='Helvetica-Bold', fontSize=13, textColor=NAVY,
          alignment=TA_CENTER, spaceBefore=4, spaceAfter=2),
    ))
    story.append(Paragraph(
        f'تاريخ التقديم / Submission Date: '
        f'{student.application_date.strftime("%A, %d %B %Y  –  %H:%M:%S")}',
        S('DS', fontName='Helvetica', fontSize=8, textColor=colors.grey,
          alignment=TA_CENTER, spaceAfter=6),
    ))
    story.append(HRFlowable(width='100%', thickness=1.5, color=NAVY, spaceAfter=8))

    # ── Info section builder ──────────────────────────────────────
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

    # ── 1. Personal Info ─────────────────────────────────────────
    story.append(sec_title('1.  البيانات الشخصية  |  Personal Information'))
    story.append(make_section([
        info_row('الاسم الرباعي',     'Full Name',    student.student_name),
        info_row('رقم الجلوس',        'Seat Number',  student.seat_number),
        info_row('رقم الهاتف',        'Phone Number', student.phone_number),
        info_row('البريد الإلكتروني', 'Email',        student.email_address),
    ]))

    # ── 2. Academic ───────────────────────────────────────────────
    story.append(sec_title('2.  البيانات الأكاديمية  |  Academic Information'))
    story.append(make_section([
        info_row('النسبة المئوية', 'Percentage',   f'{student.percentage}%'),
        info_row('المسار الدراسي', 'Study Track',  student.field_of_study),
        info_row('عدد الرغبات',    'No. of Choices', f'{choices.count()} / 20'),
    ]))

    # ── 3. Choices ────────────────────────────────────────────────
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
    for c in choices:
        ch_rows.append([
            Paragraph(str(c.rank), nc),
            Paragraph(c.university_name, nv),
            Paragraph(c.program_name,    nv),
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

    # ── 4. Application Meta ───────────────────────────────────────
    story.append(sec_title('4.  بيانات الطلب  |  Application Details'))
    status_map = {
        'pending':  'قيد المعالجة  (Pending)',
        'accepted': 'مقبول  (Accepted)',
        'rejected': 'مرفوض  (Rejected)',
    }
    story.append(make_section([
        info_row('رقم الاستمارة',  'Form Number',  student.form_number),
        info_row('تاريخ التقديم',  'Date',         student.application_date.strftime('%Y/%m/%d')),
        info_row('وقت التقديم',    'Time',         student.application_date.strftime('%H:%M:%S')),
        info_row('حالة الطلب',     'Status',       status_map.get(student.status, student.status)),
        info_row('قناة التقديم',   'Channel',      'البوابة الإلكترونية  /  Online Portal'),
    ]))

    # ── Footer ────────────────────────────────────────────────────
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

#  URL: /admission/<pk>/download-pdf/
# ═══════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  AJAX endpoints
# ═══════════════════════════════════════════════════════════════

@require_GET
def get_programs(request):
    university_id = request.GET.get('university_id', '').strip()
    if not university_id:
        return JsonResponse([], safe=False)
    try:
        programs = (
            Program.objects
            .filter(university_id=int(university_id))
            .order_by('name')
            .values('id', 'name', 'min_score')
        )
        return JsonResponse(list(programs), safe=False)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'university_id غير صحيح'}, status=400)


@require_GET
def get_universities_by_type(request):
    admission_type = request.GET.get('type', '').strip()
    qs = University.objects.order_by('name')
    if admission_type:
        qs = qs.filter(university_type=admission_type)
    return JsonResponse(list(qs.values('id', 'name', 'university_type')), safe=False)


@require_GET
def get_recommendations(request):
    try:
        pct      = float(request.GET.get('pct', 0))
        adm_type = request.GET.get('type',     '').strip()
        location = request.GET.get('location', '').strip()
        major    = request.GET.get('major',    '').strip()

        qs = Program.objects.select_related('university').filter(min_score__lte=pct)
        if adm_type:
            qs = qs.filter(university__university_type=adm_type)
        if location:
            qs = qs.filter(university__location__icontains=location)
        if major:
            qs = qs.filter(name__icontains=major)

        results = [
            {'id': p.id, 'pName': p.name, 'uName': p.university.name, 'min_score': p.min_score}
            for p in qs.order_by('-min_score')[:30]
        ]
        return JsonResponse(results, safe=False)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
