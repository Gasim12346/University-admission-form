"""
ml_engine.py — محرك التوصيات بنموذج شجرة القرار
==================================================
يحمّل public_model.pkl و private_model.pkl ويُرجع
توصيات مرتبة بناءً على احتمالات النموذج.

بنية كل ملف .pkl:
  {
    'model':    DecisionTreeClassifier  (features: track_enc, major_enc, loc_enc, student_score)
    'encoders': {
        'track':    LabelEncoder  (7 فئات)
        'major':    LabelEncoder  (46 فئة)
        'location': LabelEncoder  (21 موقع)
        'college':  LabelEncoder  (478 كلية) — يُترجم التنبؤ لاسم الكلية
    }
  }
"""

import os
import re
import sys
import types
import logging
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

# ── مسارات ──────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR  = os.path.join(BASE_DIR, 'ml_models')
CSV_PATH    = os.path.join(MODELS_DIR, 'DATA_SET.csv')

PRIVATE_PKL = os.path.join(MODELS_DIR, 'private_model.pkl')
PUBLIC_PKL  = os.path.join(MODELS_DIR, 'public_model.pkl')

# ── تثبيت module وهمي لـ unpickling ─────────────────
def _register_fake_module():
    """
    الـ pickle يحتاج module اسمه 'DecisionTreeClassifier'
    نُسجّله كـ alias لـ sklearn الحقيقي.
    """
    if 'DecisionTreeClassifier' not in sys.modules:
        try:
            from sklearn.tree import DecisionTreeClassifier as _DTC
            fake = types.ModuleType('DecisionTreeClassifier')
            fake.DecisionTreeClassifier = _DTC
            for name in dir(np):
                try:
                    setattr(fake, name, getattr(np, name))
                except Exception:
                    pass
            sys.modules['DecisionTreeClassifier'] = fake
        except Exception as e:
            logger.error("_register_fake_module failed: %s", e)

_register_fake_module()


# ═══════════════════════════════════════════════════
#  1. دوال تطبيع النصوص العربية
# ═══════════════════════════════════════════════════

def _norm(text):
    """تطبيع للمقارنة: إزالة التشكيل وتوحيد الحروف."""
    if not isinstance(text, str):
        return ''
    text = text.strip().lower()
    text = re.sub(r'[إأآٱ]', 'ا', text)
    text = re.sub(r'ة',      'ه', text)
    text = re.sub(r'ى',      'ي', text)
    text = re.sub(r'ـ',      '',  text)
    text = re.sub(r'[\u064B-\u065F]', '', text)
    text = re.sub(r'[،,\-–_()\[\]]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _best_match(query, choices, threshold=0.3):
    """
    يجد أفضل تطابق لـ query في قائمة choices
    بناءً على تشابه الكلمات المشتركة.
    """
    stop = {'في','من','و','ال','على','كليه','كلية','جامعه','جامعة','معهد'}
    q_words = set(_norm(query).split()) - stop
    if not q_words:
        return None

    best_item  = None
    best_score = threshold

    for choice in choices:
        c_words = set(_norm(choice).split()) - stop
        if not c_words:
            continue
        score = len(q_words & c_words) / len(q_words | c_words)
        if score > best_score:
            best_score = score
            best_item  = choice

    return best_item


# ═══════════════════════════════════════════════════
#  2. تحميل النماذج
# ═══════════════════════════════════════════════════

_MODELS = {}   # cache: 'private' | 'public' → dict

def _load_model(model_type):
    """يحمّل النموذج ويُخزّنه في cache."""
    if model_type in _MODELS:
        return _MODELS[model_type]

    _register_fake_module()

    # إذا طلب public وغير موجود، استخدم private كبديل
    path = PRIVATE_PKL if model_type == 'private' else PUBLIC_PKL
    fallback = PRIVATE_PKL  # بديل دائم

    if not os.path.exists(path):
        logger.warning("Model file not found: %s — trying fallback: %s", path, fallback)
        path = fallback
        if not os.path.exists(path):
            logger.error("No model file found at all.")
            return None

    try:
        import joblib
        obj = joblib.load(path)

        # تحقق من البنية المتوقعة
        if not isinstance(obj, dict):
            logger.error("Model is not a dict: %s (type=%s)", path, type(obj))
            return None
        if 'model' not in obj or 'encoders' not in obj:
            logger.error("Model dict missing 'model' or 'encoders' keys: %s", list(obj.keys()))
            return None
        if not isinstance(obj['encoders'], dict):
            logger.error("encoders is not a dict: %s", type(obj['encoders']))
            return None

        _MODELS[model_type] = obj
        logger.info("Loaded %s model OK: %d classes", model_type, len(obj['model'].classes_))
        return obj

    except Exception as e:
        logger.error("Failed to load model %s: %s", path, e)
        return None


# ═══════════════════════════════════════════════════
#  3. Lookup: college → {university, min_score, ...}
# ═══════════════════════════════════════════════════

_COLLEGE_LOOKUP = None

def _build_college_lookup():
    """يقرأ الداتاسيت ويبني lookup من college_normalized إلى بيانات الكلية."""
    global _COLLEGE_LOOKUP
    if _COLLEGE_LOOKUP is not None:
        return _COLLEGE_LOOKUP

    try:
        df = pd.read_csv(CSV_PATH, dtype=str)
        df['min_score']     = pd.to_numeric(df['min_score'],     errors='coerce').fillna(0)
        df['student_score'] = pd.to_numeric(df['student_score'], errors='coerce').fillna(0)

        # نأخذ min_score الأدنى لكل كلية (الحد الأدنى الفعلي للقبول)
        agg = df.groupby(['university', 'college', 'major', 'uni_location', 'uni_type']).agg(
            min_score=('min_score', 'min'),
            capacity =('student_score', 'count'),
        ).reset_index()

        lookup = {}
        for _, row in agg.iterrows():
            key = _norm(str(row['college']))
            lookup[key] = {
                'university':  row['university'],
                'college':     row['college'],
                'major':       row['major'],
                'location':    row['uni_location'],
                'uni_type':    row['uni_type'],
                'min_score':   float(row['min_score']),
                'capacity':    int(row['capacity']),
            }

        _COLLEGE_LOOKUP = lookup
        logger.info("CollegeLookup built: %d entries", len(lookup))
        return lookup

    except Exception as e:
        logger.error("_build_college_lookup error: %s", e)
        _COLLEGE_LOOKUP = {}
        return {}


def _get_college_info(college_name_from_model):
   
    lookup = _build_college_lookup()
    key    = _norm(college_name_from_model)

    # 1. مطابقة مباشرة
    if key in lookup:
        return lookup[key]

    # 2. مطابقة تقريبية
    best_key = _best_match(college_name_from_model, list(lookup.keys()), threshold=0.35)
    if best_key:
        return lookup[best_key]

    return None


# التخصصات العلمية البحتة التي لا يمكن لمسار أدبي الوصول إليها
_SCIENTIFIC_ONLY_MAJORS = {
    'طب', 'صيدله', 'طب الاسنان', 'مختبرات', 'تخدير',
    'الاشعه', 'البصريات', 'العلاج الطبيعي', 'الصحه العامه',
    'هندسه العماره', 'هندسه مدنيه', 'هندسه كهرباء', 'هندسه ميكانيكيه',
    'هندسه الطيران', 'هندسه النفط', 'هندسه كيميائيه', 'هندسه طبيه',
    'هندسه برمجيات', 'هندسـه الحاسـوب', 'هندسه الكترونيه',
    'هندسه الميكاترونيكس', 'هندسه مدنيه', 'علوم حاسوب',
    'كيميا', 'فيزيا', 'احيا', 'زراعه', 'طب بيطري',
}

# التخصصات الأدبية البحتة
_ARTS_ONLY_MAJORS = {
    'الدراسات الاسلاميه', 'اصول الدين', 'الشريعه والقانون',
    'الدعوه', 'الفنون والتصميم', 'لغات واداب',
    'الموسيقا والدراما', 'الاثار والمتاحف',
}

def _is_track_major_compatible(track_norm, major_norm):
    """
    يتحقق من توافق المسار مع التخصص.
    يُعيد (True, None) إذا متوافق أو (False, error_message) إذا غير متوافق.
    """
    is_adabi  = 'ادبي'  in track_norm
    is_ilmi   = 'علمي'  in track_norm

    # مسار أدبي + تخصص علمي بحت
    if is_adabi:
        for sci in _SCIENTIFIC_ONLY_MAJORS:
            if sci in major_norm or major_norm in sci:
                return False, (
                    'التخصص "' + major_norm + '" لا يتوافق مع المسار الأدبي. '
                    'يُرجى اختيار تخصص يناسب مسارك مثل: '
                    'إدارة أعمال، محاسبة، قانون، اقتصاد، تقنية معلومات، إعلام.'
                )

    return True, None


def _get_fallback_recommendations(enc_dict, model, track, location,
                                   student_score, exclude_ids, needed, min_prob=0.0):
    """
    يُولّد توصيات إضافية من نفس المسار بأي تخصص
    لكن يبقى في نفس المدينة التي اختارها الطالب فقط.
    """
    track_classes = list(enc_dict['track'].classes_)
    major_classes = list(enc_dict['major'].classes_)
    loc_classes   = list(enc_dict['location'].classes_)

    # طبّق track
    track_norm    = _norm(track)
    matched_track = None
    for c in track_classes:
        if _norm(c) == track_norm:
            matched_track = c
            break
    if matched_track is None:
        matched_track = _best_match(track, track_classes, threshold=0.2)
    if matched_track is None:
        return []

    # طبّق location — نفس المدينة فقط، إذا لم توجد نرجع قائمة فارغة
    loc_norm    = _norm(location)
    matched_loc = None
    for c in loc_classes:
        if _norm(c) == loc_norm:
            matched_loc = c
            break
    if matched_loc is None:
        matched_loc = _best_match(location, loc_classes, threshold=0.3)
    if matched_loc is None:
        return []   # المدينة غير موجودة في النموذج — لا نخرج بدائل

    fallback  = []
    seen_unis = {}

    try:
        t_enc = enc_dict['track'].transform([matched_track])[0]
        l_enc = enc_dict['location'].transform([matched_loc])[0]

        for maj in major_classes:
            if len(fallback) >= needed:
                break
            try:
                m_enc  = enc_dict['major'].transform([maj])[0]
                X      = np.array([[t_enc, m_enc, l_enc, float(student_score)]])
                proba  = model.predict_proba(X)[0]
                top_ix = np.argsort(proba)[::-1][:10]

                for idx in top_ix:
                    if len(fallback) >= needed:
                        break
                    class_id = model.classes_[idx]
                    if class_id in exclude_ids:
                        continue
                    college_name = enc_dict['college'].inverse_transform([class_id])[0]
                    info = _get_college_info(college_name)
                    if info is None:
                        continue
                    # تحقق أن الكلية فعلاً في نفس المدينة
                    if _norm(info.get('location', '')) != loc_norm:
                        continue
                    # ✅ فلتر النسبة
                    if info['min_score'] > float(student_score) + 2.0:
                        continue
                    uni_name = info['university']
                    if seen_unis.get(uni_name, 0) >= 2:
                        continue
                    seen_unis[uni_name] = seen_unis.get(uni_name, 0) + 1
                    exclude_ids.add(class_id)
                    fallback.append({
                        'id':          0,
                        'pName':       college_name,
                        'uName':       uni_name,
                        'min_score':   round(info['min_score'], 1),
                        'prob':        round(float(proba[idx]) * 100, 1),
                        'is_target':   float(student_score) >= info['min_score'],
                        'status_info': '🔄 بديل من مسارك',
                        'uni_type':    info.get('uni_type', ''),
                        'location':    info.get('location', ''),
                        'is_fallback': True,
                    })
            except Exception:
                continue
    except Exception as e:
        logger.warning("_get_fallback_recommendations error: %s", e)

    return fallback


# ═══════════════════════════════════════════════════
#  4. التطبيع للإدخال على النموذج
# ═══════════════════════════════════════════════════

def _encode_input(enc_dict, track, major, location, score):
    """
    يُشفّر المدخلات ويتحقق من التوافق.
    يُعيد (X, [], matched_track) أو (None, errors, None).

    إذا لم يجد التخصص في encoder النموذج مباشرة:
      - يبحث في الداتاسيت عن تخصص قريب ينتمي لنفس المسار
      - يُعيد أقرب تخصص موجود في encoder النموذج
    """
    errors = []

    # ── Track ──
    track_classes = list(enc_dict['track'].classes_)
    track_norm    = _norm(track)
    matched_track = None
    for c in track_classes:
        if _norm(c) == track_norm:
            matched_track = c
            break
    if matched_track is None:
        matched_track = _best_match(track, track_classes, threshold=0.2)
    if matched_track is None:
        errors.append("المسار '%s' غير موجود في النموذج." % track)

    # ── التحقق من توافق المسار والتخصص ──
    if matched_track is not None:
        compatible, err_msg = _is_track_major_compatible(_norm(matched_track), _norm(major))
        if not compatible:
            return None, [err_msg], None

    # ── Major: بحث في encoder ثم في الداتاسيت ──
    major_classes = list(enc_dict['major'].classes_)
    major_norm    = _norm(major)
    matched_major = None

    # 1. مطابقة مباشرة في encoder
    for c in major_classes:
        if _norm(c) == major_norm:
            matched_major = c
            break

    # 2. مطابقة تقريبية في encoder
    if matched_major is None:
        matched_major = _best_match(major, major_classes, threshold=0.3)

    # 3. إذا لم يجد في encoder → ابحث في الداتاسيت عن تخصصات المسار
    #    ثم جد أقرب تخصص منها موجود في encoder النموذج
    if matched_major is None and matched_track is not None:
        track_majors = _get_track_majors(_norm(matched_track))
        # ابحث عن أقرب تخصص من مسار الطالب موجود في encoder
        best_sim   = 0.0
        best_model_major = None
        for model_maj in major_classes:
            model_maj_norm = _norm(model_maj)
            # هل هذا التخصص ينتمي لمسار الطالب؟
            if model_maj_norm not in track_majors:
                continue
            sim = _major_similarity(major_norm, model_maj_norm)
            if sim > best_sim:
                best_sim = sim
                best_model_major = model_maj
        if best_model_major and best_sim >= 0.1:
            matched_major = best_model_major
            logger.info("Major '%s' mapped to encoder class '%s' (sim=%.2f)", major, matched_major, best_sim)

    # 4. إذا لم يجد أي تطابق → خطأ واضح
    if matched_major is None:
        # اقترح تخصصات المسار المتاحة
        if matched_track is not None:
            track_majors = _get_track_majors(_norm(matched_track))
            suggestions  = list(track_majors)[:6]
            errors.append(
                'التخصص "%s" غير موجود لمسار "%s". '
                'تخصصات متاحة: %s' % (major, track, '، '.join(suggestions))
            )
        else:
            errors.append('التخصص "%s" غير موجود.' % major)

    # ── Location ──
    loc_classes = list(enc_dict['location'].classes_)
    loc_norm    = _norm(location)
    matched_loc = None
    for c in loc_classes:
        if _norm(c) == loc_norm:
            matched_loc = c
            break
    if matched_loc is None:
        matched_loc = _best_match(location, loc_classes, threshold=0.4)
    if matched_loc is None:
        errors.append("الموقع '%s' غير موجود في النموذج." % location)

    if errors:
        return None, errors, None

    try:
        t_enc = enc_dict['track'].transform([matched_track])[0]
        m_enc = enc_dict['major'].transform([matched_major])[0]
        l_enc = enc_dict['location'].transform([matched_loc])[0]
        X = np.array([[t_enc, m_enc, l_enc, float(score)]])
        return X, [], matched_track
    except Exception as e:
        return None, [str(e)], None


# ═══════════════════════════════════════════════════
#  5. الدالة الرئيسية: get_dt_recommendations
# ═══════════════════════════════════════════════════

def _model_type_to_uni_norm(model_type):
    if model_type == 'public':
        return {'حكوميه', 'حكومية', 'حكومي'}
    return {'اهليه', 'اهلية', 'خاصه', 'خاصة', 'اهلي', 'اهليه / خاصه',
            'أهلية / خاصة', 'اهليه خاصه', 'اهلى', 'خاص', 'اهلي / خاصه'}


# ── خريطة المسار إلى تخصصاته المبنية من الداتاسيت ──
_TRACK_MAJORS_MAP = None

def _build_track_majors_map():
    """
    يبني خريطة: track_norm → set(major_norm)
    مباشرةً من الداتاسيت — لا قوائم يدوية.
    """
    global _TRACK_MAJORS_MAP
    if _TRACK_MAJORS_MAP is not None:
        return _TRACK_MAJORS_MAP

    try:
        df = pd.read_csv(CSV_PATH, dtype=str)
        result = {}
        for _, row in df[['study_track', 'major']].dropna().iterrows():
            t = _norm(str(row['study_track']))
            m = _norm(str(row['major']))
            if t and m:
                result.setdefault(t, set()).add(m)
        _TRACK_MAJORS_MAP = result
        logger.info("TrackMajorsMap built: %d tracks", len(result))
        return result
    except Exception as e:
        logger.error("_build_track_majors_map error: %s", e)
        _TRACK_MAJORS_MAP = {}
        return {}


def _get_track_majors(track_norm):
    """
    يُعيد set التخصصات المسموحة لمسار معين.
    يدعم تعدد الصيغ: 'علمي-أحياء' ← يجمع 'علمي احياء' و'علمي-احياء' و'علمي أحياء'.
    """
    tmap = _build_track_majors_map()
    # 1. مطابقة مباشرة
    if track_norm in tmap:
        return tmap[track_norm]
    # 2. بحث جزئي: كل مفاتيح الخريطة التي تشترك بنفس الكلمات
    track_words = set(track_norm.split())
    merged = set()
    for key, majors in tmap.items():
        key_words = set(key.split())
        if len(track_words & key_words) >= len(track_words):
            merged |= majors
    if merged:
        return merged
    # 3. fallback: كل التخصصات
    all_majors = set()
    for v in tmap.values():
        all_majors |= v
    return all_majors


def _major_similarity(a, b):
    stop = {'كليه', 'كلية', 'جامعه', 'جامعة', 'قسم'}
    wa = set(a.split()) - stop
    wb = set(b.split()) - stop
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def get_dt_recommendations(
    track, major, location, student_score,
    model_type, top_n=20, min_prob=0.0,
):
    """
    آلية العمل:
      1. النموذج يُرتّب كل الـ 478 كلية حسب الاحتمالية.
      2. نفلترها: نفس المدينة + نفس نوع الجامعة + نفس التخصص المطلوب.
         النتائج مرتبة بالاحتمالية (الأعلى أولاً).
      3. إذا < top_n: نُكمل بكليات من **نفس المسار فقط** في نفس المدينة
         (التخصصات المسموحة تُحدَّد من الداتاسيت مباشرة).
      4. لا يخرج عن المدينة أبداً.
      5. لا يُعطي بدائل من مسارات أخرى.
    """
    # ── 1. تحميل النموذج ──────────────────────────
    obj = _load_model(model_type)
    if obj is None:
        return {'error': 'لم يتم العثور على ملف النموذج في مجلد ml_models'}
    model_obj = obj['model']
    enc_dict  = obj['encoders']
    if not isinstance(enc_dict, dict):
        return {'error': 'بنية النموذج غير صحيحة'}

    # ── 2. التحقق من التوافق وترميز المدخلات ──────
    try:
        X, errors, matched_track = _encode_input(enc_dict, track, major, location, student_score)
    except Exception as e:
        return {'error': 'خطأ في المدخلات: %s' % str(e)}
    if X is None:
        return {'error': errors[0] if errors else 'خطأ في المدخلات'}

    # ── 3. تشغيل النموذج ──────────────────────────
    try:
        proba      = model_obj.predict_proba(X)[0]
        classes    = model_obj.classes_
        sorted_idx = np.argsort(proba)[::-1]
    except Exception as e:
        return {'error': 'خطأ في التنبؤ: %s' % str(e)}

    # ── 4. إعداد الفلاتر ──────────────────────────
    lookup     = _build_fast_lookup()
    loc_norm   = _norm(location)
    track_norm = _norm(matched_track or track)
    major_norm = _norm(major)
    uni_types  = _model_type_to_uni_norm(model_type)

    # تخصصات المسار من الداتاسيت (للبدائل)
    track_majors = _get_track_majors(track_norm)

    # ── 5. المرحلة الأولى: التخصص المطلوب فقط ────
    results      = []
    used_names   = set()
    s_score      = float(student_score)
    SCORE_MARGIN = 2.0   # نسمح بكليات أعلى من نسبة الطالب بـ 2 نقطة فقط

    for idx in sorted_idx:
        if len(results) >= top_n:
            break
        college_name = enc_dict['college'].inverse_transform([classes[idx]])[0]
        info         = lookup.get(_norm(college_name))
        if not info:
            continue
        if _norm(info['location']) != loc_norm:
            continue
        if _norm(info['uni_type']) not in uni_types:
            continue
        if _norm(info['major']) != major_norm:
            continue

        min_score = info['min_score']

        # ✅ فلتر النسبة: لا تُظهر كليات نسبتها الدنيا أعلى من نسبة الطالب + هامش 2
        if min_score > s_score + SCORE_MARGIN:
            continue

        is_target = s_score >= min_score
        results.append({
            'id':          0,
            'pName':       info.get('college', college_name),
            'uName':       info['university'],
            'min_score':   round(min_score, 1),
            'prob':        round(float(proba[idx]) * 100, 2),
            'is_target':   is_target,
            'uni_type':    info['uni_type'],
            'location':    info['location'],
            'is_fallback': False,
        })
        used_names.add(college_name)

    # ── 6. المرحلة الثانية: بدائل من نفس المسار فقط ──
    if len(results) < top_n:
        needed = top_n - len(results)
        added  = 0

        for idx in sorted_idx:
            if added >= needed:
                break
            college_name = enc_dict['college'].inverse_transform([classes[idx]])[0]
            if college_name in used_names:
                continue
            info = lookup.get(_norm(college_name))
            if not info:
                continue
            if _norm(info['location']) != loc_norm:
                continue
            if _norm(info['uni_type']) not in uni_types:
                continue
            info_major = _norm(info['major'])
            if info_major == major_norm:
                continue   # مكرر من المرحلة الأولى

            # ✅ الشرط الجوهري: التخصص يجب أن ينتمي لنفس المسار من الداتاسيت
            if info_major not in track_majors:
                continue

            min_score = info['min_score']

            # ✅ فلتر النسبة: لا تُظهر كليات نسبتها الدنيا أعلى من نسبة الطالب + هامش 2
            if min_score > s_score + SCORE_MARGIN:
                continue

            is_target = s_score >= min_score
            results.append({
                'id':          0,
                'pName':       info.get('college', college_name),
                'uName':       info['university'],
                'min_score':   round(min_score, 1),
                'prob':        round(float(proba[idx]) * 100, 2),
                'is_target':   is_target,
                'uni_type':    info['uni_type'],
                'location':    info['location'],
                'is_fallback': True,
            })
            used_names.add(college_name)
            added += 1

    if not results:
        return {
            'error': (
                'لا توجد كليات مناسبة لنسبتك (%.1f%%) في "%s" لمسار "%s". '
                'جميع الكليات المتاحة تشترط نسبة أعلى من نسبتك. '
                'جرّب مدينة أخرى أو تحقق من اسم التخصص.'
            ) % (float(student_score), location, track)
        }

    return results[:top_n]


def _build_fast_lookup():
    """
    Lookup سريع: college_norm → {university, location, uni_type, major, min_score, college}
    يأخذ الـ min_score الأدنى لكل كلية.
    """
    global _COLLEGE_LOOKUP
    if _COLLEGE_LOOKUP is not None:
        return _COLLEGE_LOOKUP
    return _build_college_lookup()


# ═══════════════════════════════════════════════════
#  6. دوال مساعدة لـ views.py
# ═══════════════════════════════════════════════════

def get_available_tracks(model_type='private'):
    """يُعيد قائمة المسارات الدراسية المتاحة في النموذج."""
    obj = _load_model(model_type)
    if obj is None:
        return []
    return list(obj['encoders']['track'].classes_)


def get_available_majors(model_type='private'):
    """يُعيد قائمة التخصصات المتاحة في النموذج."""
    obj = _load_model(model_type)
    if obj is None:
        return []
    return list(obj['encoders']['major'].classes_)


def get_available_locations(model_type='private'):
    """يُعيد قائمة المواقع المتاحة في النموذج."""
    obj = _load_model(model_type)
    if obj is None:
        return []
    return list(obj['encoders']['location'].classes_)


def get_model_info(model_type='private'):
    """معلومات النموذج للعرض في واجهة المستخدم."""
    obj = _load_model(model_type)
    if obj is None:
        return {}
    m = obj['model']
    return {
        'type':      model_type,
        'n_classes': len(m.classes_),
        'features':  list(m.feature_names_in_) if hasattr(m, 'feature_names_in_') else [],
        'depth':     m.get_depth(),
        'n_leaves':  m.get_n_leaves(),
    }
