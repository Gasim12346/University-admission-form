"""
utils.py - نظام التوزيع والقبول الجامعي
=========================================
"""

import os
import re
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
#  مسارات الملفات
# ═══════════════════════════════════════
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'ml_models')
CSV_PATH   = os.path.join(MODELS_DIR, 'DATA_SET.csv')


# ═══════════════════════════════════════
#  1. دوال التطبيع العربي
# ═══════════════════════════════════════

def normalize_ar(text):
    if not isinstance(text, str):
        return ''
    text = text.strip()
    text = re.sub(r'[إأآٱ]',  'ا', text)
    text = re.sub(r'ة',       'ه', text)
    text = re.sub(r'ى',       'ي', text)
    text = re.sub(r'ـ',       '',  text)
    text = re.sub(r'[\u0610-\u061A\u064B-\u065F]', '', text)
    text = re.sub(r'[،,\-–—_()\[\]{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def _stop_words():
    return {
        'في', 'من', 'و', 'ال', 'على', 'الى', 'عن', 'مع', 'لل',
        'كليه', 'كلية', 'جامعه', 'جامعة', 'مركز', 'معهد', 'قسم',
    }


def word_overlap_score(a, b):
    stop = _stop_words()
    wa = set(normalize_ar(a).split()) - stop
    wb = set(normalize_ar(b).split()) - stop
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def extract_faculty_name(college_text):
    if not isinstance(college_text, str):
        return str(college_text)
    return re.split(r'\s*-\s*', college_text)[0].strip()


# ═══════════════════════════════════════
#  2. فهرس البرامج
# ═══════════════════════════════════════

class _ProgramIndex:
    def __init__(self):
        self._index = {}
        self._built = False

    def build(self):
        try:
            from .models import Program
            entries = Program.objects.select_related('university').values(
                'id', 'name', 'university__name'
            )
            idx = {}
            for e in entries:
                key = (
                    normalize_ar(e['university__name'])[:30],
                    normalize_ar(e['name'])[:30],
                )
                idx[key] = e['id']
            self._index = idx
            self._built = True
            logger.info("ProgramIndex: %d سجل", len(idx))
        except Exception as exc:
            logger.warning("ProgramIndex.build failed: %s", exc)

    def find(self, uni_name, fac_name, uni_type_filter=''):
        if not self._built:
            self.build()
        try:
            from .models import Program
            best_prog  = None
            best_score = 0.45
            norm_uni = normalize_ar(uni_name)
            norm_fac = normalize_ar(fac_name)
            for (idx_uni, idx_fac), prog_id in self._index.items():
                uni_score = word_overlap_score(norm_uni, idx_uni)
                fac_score = word_overlap_score(norm_fac, idx_fac)
                total     = uni_score * 0.55 + fac_score * 0.45
                if total > best_score:
                    try:
                        prog = Program.objects.select_related('university').get(id=prog_id)
                        if uni_type_filter and uni_type_filter not in prog.university.university_type:
                            continue
                        best_score = total
                        best_prog  = prog
                    except Exception:
                        continue
            return best_prog
        except Exception as exc:
            logger.error("ProgramIndex.find error: %s", exc)
            return None

    def rebuild(self):
        self._built = False
        self.build()


PROGRAM_INDEX = _ProgramIndex()


# ═══════════════════════════════════════
#  3. خريطة السعة من الداتاسيت
# ═══════════════════════════════════════

_CAPACITY_MAP_CACHE = None

def _load_capacity_map():
    global _CAPACITY_MAP_CACHE
    if _CAPACITY_MAP_CACHE is not None:
        return _CAPACITY_MAP_CACHE

    try:
        if not os.path.exists(CSV_PATH):
            logger.warning("CSV غير موجود: %s", CSV_PATH)
            return {}

        df = pd.read_csv(CSV_PATH, dtype=str)
        df['min_score']     = pd.to_numeric(df['min_score'],     errors='coerce').fillna(0)
        df['student_score'] = pd.to_numeric(df['student_score'], errors='coerce').fillna(0)

        grouped = (
            df.groupby(['university', 'college', 'uni_type', 'uni_location', 'major', 'min_score'])
            .agg(capacity=('student_score', 'count'), avg_score=('student_score', 'mean'))
            .reset_index()
        )

        cap_map = {}
        for _, row in grouped.iterrows():
            key = (
                normalize_ar(str(row['university']))[:40],
                normalize_ar(extract_faculty_name(str(row['college'])))[:40],
            )
            if key not in cap_map or row['capacity'] > cap_map[key]['capacity']:
                cap_map[key] = {
                    'min_score': float(row['min_score']),
                    'capacity':  int(row['capacity']),
                    'avg_score': round(float(row['avg_score']), 2),
                    'uni_type':  str(row['uni_type']),
                    'location':  str(row['uni_location']),
                    'major':     str(row['major']),
                }

        logger.info("CapacityMap: %d برنامج", len(cap_map))
        _CAPACITY_MAP_CACHE = cap_map
        return cap_map

    except Exception as exc:
        logger.error("_load_capacity_map error: %s", exc)
        return {}


def _get_program_min_score(prog, cap_map):
    key = (
        normalize_ar(prog.university.name)[:40],
        normalize_ar(prog.name)[:40],
    )
    if key in cap_map:
        return cap_map[key]['min_score']

    best_val = None
    best_sim = 0.0
    norm_uni = normalize_ar(prog.university.name)
    norm_fac = normalize_ar(prog.name)
    for (ku, kf), info in cap_map.items():
        sim = word_overlap_score(norm_uni, ku) * 0.6 + word_overlap_score(norm_fac, kf) * 0.4
        if sim > best_sim and sim > 0.4:
            best_sim = sim
            best_val = info['min_score']
    return best_val if best_val is not None else 0.0


def _get_program_capacity(prog, cap_map):
    key = (
        normalize_ar(prog.university.name)[:40],
        normalize_ar(prog.name)[:40],
    )
    if key in cap_map:
        return cap_map[key]['capacity']

    best_cap = 20
    best_sim = 0.0
    norm_uni = normalize_ar(prog.university.name)
    norm_fac = normalize_ar(prog.name)
    for (ku, kf), info in cap_map.items():
        sim = word_overlap_score(norm_uni, ku) * 0.6 + word_overlap_score(norm_fac, kf) * 0.4
        if sim > best_sim and sim > 0.4:
            best_sim = sim
            best_cap = info['capacity']
    return best_cap


# ═══════════════════════════════════════
#  4. نظام التوزيع الرئيسي
# ═══════════════════════════════════════

class AdmissionDistributionSystem:
    """
    يوزّع الطلاب على البرامج:
      1. يرتّب الطلاب تنازلياً حسب النسبة
      2. لكل طالب يمر على رغباته بالترتيب
      3. يقبل في أول رغبة تحقق:
           - نسبة الطالب >= min_score للبرنامج
           - البرنامج لم يمتلئ (accepted < capacity)
    """

    def __init__(self):
        self._cap_map = {}

    # ── التوزيع الكامل ──────────────────────────────

    def distribute_students(self):
        # ننقل الـ imports هنا لتجنب مشاكل circular import
        from django.db import transaction
        from .models import Application, Choice, Program

        self._cap_map = _load_capacity_map()

        applications = (
            Application.objects
            .select_related('student')
            .prefetch_related('choices__program__university')
            .filter(status='يتم المراجعة')
            .order_by('-student__percentage')
        )

        accepted_counts = {}

        stats = {
            'total':    0,
            'accepted': 0,
            'skipped':  0,
            'errors':   0,
            'details':  [],
        }

        for app in applications:
            stats['total'] += 1
            try:
                result = self._process_application(app, accepted_counts)
                if result['accepted']:
                    stats['accepted'] += 1
                else:
                    stats['skipped'] += 1
                stats['details'].append(result)
            except Exception as exc:
                stats['errors'] += 1
                logger.error("distribute_students - خطأ في طلب %d: %s", app.id, exc)

        logger.info(
            "التوزيع اكتمل: %d مقبول / %d غير مقبول / %d خطأ",
            stats['accepted'], stats['skipped'], stats['errors']
        )
        return stats

    # ── معالجة طلب واحد ─────────────────────────────

    def _process_application(self, application, accepted_counts):
        from django.db import transaction

        student    = application.student
        percentage = float(student.percentage)
        choices    = (
            application.choices
            .select_related('program__university')
            .order_by('priority')
        )

        for choice in choices:
            prog = choice.program
            if prog is None:
                continue

            min_score = _get_program_min_score(prog, self._cap_map)
            capacity  = _get_program_capacity(prog, self._cap_map)

            try:
                db_accepted = prog.applications_accepted.count()
            except Exception:
                db_accepted = 0

            session_accepted = accepted_counts.get(prog.id, 0)
            total_accepted   = db_accepted + session_accepted

            qualifies    = percentage >= min_score
            has_capacity = total_accepted < capacity

            if qualifies and has_capacity:
                with transaction.atomic():
                    application.accepted_program = prog
                    application.status           = 'تم القبول'
                    application.save(update_fields=['accepted_program', 'status'])

                accepted_counts[prog.id] = session_accepted + 1

                return {
                    'accepted':      True,
                    'student':       student.name,
                    'percentage':    percentage,
                    'program':       prog.name,
                    'university':    prog.university.name,
                    'priority_used': choice.priority,
                    'min_score':     min_score,
                    'capacity':      capacity,
                }

        return {
            'accepted':   False,
            'student':    student.name,
            'percentage': percentage,
        }

    # ── إعادة تعيين التوزيع ─────────────────────────

    def reset_distribution(self):
        from django.db import transaction
        from .models import Application

        with transaction.atomic():
            updated = Application.objects.filter(
                status='تم القبول'
            ).update(
                accepted_program=None,
                status='يتم المراجعة',
            )

        logger.info("reset_distribution: أُعيد تعيين %d طلب", updated)
        return updated

    # ── مطابقة الرغبات اليتيمة ──────────────────────

    def match_all_choices(self):
        import json as _json
        from django.db import transaction
        from .models import Choice

        unmatched = Choice.objects.filter(program__isnull=True).select_related(
            'application__student'
        )
        total   = unmatched.count()
        matched = 0
        failed  = 0

        if not PROGRAM_INDEX._built:
            PROGRAM_INDEX.build()

        for choice in unmatched:
            try:
                choices_list = _json.loads(choice.application.choices_json or '[]')
                idx = choice.priority - 1
                if idx < 0 or idx >= len(choices_list):
                    failed += 1
                    continue

                item   = choices_list[idx]
                u_name = item.get('uName', '')
                p_name = item.get('pName', '')

                prog = (
                    PROGRAM_INDEX.find(u_name, p_name, 'حكومية') or
                    PROGRAM_INDEX.find(u_name, p_name, 'أهلية')
                )

                if prog:
                    choice.program = prog
                    choice.save(update_fields=['program'])
                    matched += 1
                else:
                    failed += 1

            except Exception as exc:
                logger.warning("match_all_choices choice %d: %s", choice.id, exc)
                failed += 1

        result = {
            'total':   total,
            'matched': matched,
            'failed':  failed,
            'message': 'تم مطابقة %d من %d رغبة (فشل %d)' % (matched, total, failed),
        }
        logger.info(result['message'])
        return result

    # ── إحصاءات السعة ────────────────────────────────

    def get_capacity_stats(self):
        from django.db.models import Count
        from .models import Program

        cap_map  = _load_capacity_map()
        programs = Program.objects.select_related('university').annotate(
            accepted_count=Count('applications_accepted')
        )

        full      = []
        available = []

        for prog in programs:
            capacity  = _get_program_capacity(prog, cap_map)
            accepted  = prog.accepted_count
            remaining = capacity - accepted

            entry = {
                'program':    prog.name,
                'university': prog.university.name,
                'capacity':   capacity,
                'accepted':   accepted,
                'remaining':  remaining,
            }
            if remaining <= 0:
                full.append(entry)
            else:
                available.append(entry)

        return {
            'full_programs':      full,
            'available_programs': available,
            'total_capacity':     sum(e['capacity']  for e in full + available),
            'total_accepted':     sum(e['accepted']  for e in full + available),
            'total_remaining':    sum(e['remaining'] for e in available),
        }


# ═══════════════════════════════════════
#  5. دوال مساعدة عامة
# ═══════════════════════════════════════

def find_best_program(uni_name, fac_name, uni_type=''):
    if not PROGRAM_INDEX._built:
        PROGRAM_INDEX.build()
    return PROGRAM_INDEX.find(uni_name, fac_name, uni_type)


def rebuild_program_index():
    PROGRAM_INDEX.rebuild()
    logger.info("تم إعادة بناء فهرس البرامج.")


def get_program_capacity_from_csv(uni_name, prog_name):
    cap_map = _load_capacity_map()
    norm_u  = normalize_ar(uni_name)[:40]
    norm_p  = normalize_ar(prog_name)[:40]

    if (norm_u, norm_p) in cap_map:
        return cap_map[(norm_u, norm_p)]

    best_info  = None
    best_score = 0.0
    for (ku, kp), info in cap_map.items():
        score = (
            word_overlap_score(norm_u, ku) * 0.6 +
            word_overlap_score(norm_p, kp) * 0.4
        )
        if score > best_score and score > 0.4:
            best_score = score
            best_info  = info

    return best_info or {
        'min_score': 0.0,
        'capacity':  0,
        'avg_score': 0.0,
        'uni_type':  '',
        'location':  '',
        'major':     '',
    }
