import joblib
import os

# المسارات الحالية لملفاتك
models_dir = os.path.join('addmission_app', 'ml_models')
public_path = os.path.join(models_dir, 'public_model.pkl')

if os.path.exists(public_path):
    # تحميل النموذج الحالي
    model = joblib.load(public_path)
    # إعادة حفظه مع تفعيل خيار الضغط (رقم 3 أو 5 ممتاز)
    joblib.dump(model, public_path, compress=3)
    print("✅ تم ضغط ملف public_model.pkl بنجاح وأصبح حجمه أصغر بكثير!")