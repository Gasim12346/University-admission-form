// قاعدة البيانات
const DB = {
    generateFormNumber: function(seatNumber) {
        const year = new Date().getFullYear();
        const random = Math.floor(1000 + Math.random() * 9000);
        return `${year}${seatNumber}${random}`;
    },
    
    saveApplication: function(application) {
        const applications = this.getApplications();
        applications.push(application);
        localStorage.setItem('applications', JSON.stringify(applications));
    },
    
    getApplications: function() {
        const apps = localStorage.getItem('applications');
        return apps ? JSON.parse(apps) : [];
    },
    
    checkSeatNumberExists: function(seatNumber) {
        const applications = this.getApplications();
        return applications.some(app => app.seatNumber === seatNumber);
    },
    
    
   
};
// Addmission.js كود داخل ملف 
document.addEventListener('DOMContentLoaded', function() {
    const universitySelect = document.getElementById('universitySelect');
    const programSelect = document.getElementById('programSelect');

    if (universitySelect) {
        universitySelect.addEventListener('change', function() {
            const universityId = this.value; // سيأخذ الـ ID من قاعدة البيانات

            // تفريغ قائمة الكليات
            programSelect.innerHTML = '<option value="">جاري تحميل الكليات...</option>';

            if (universityId) {
                // استدعاء الرابط الذي أنشأناه في urls.py
                fetch(`/get_programs/?university_id=${universityId}`)
                    .then(response => response.json())
                    .then(data => {
                        programSelect.innerHTML = '<option value="">اختر الكلية</option>';
                        data.forEach(prog => {
                            const option = document.createElement('option');
                            option.value = prog.id;
                            option.textContent = prog.name;
                            programSelect.appendChild(option);
                        });
                    })
                    .catch(error => console.error('Error:', error));
            } else {
                programSelect.innerHTML = '<option value="">اختر الجامعة أولاً</option>';
            }
        });
    }
});

// متغيرات عامة
let choices = [];
let formNumber = '';
const MAX_CHOICES = 20;

// تحميل الجامعات عند بدء الصفحة
document.addEventListener('DOMContentLoaded', function() {
    loadUniversities();
    
    // مستمع للمسار الدراسي لتحديث التخصصات
    document.getElementById('fieldOfStudy').addEventListener('change', function() {
        loadPrograms();
    });
});

// توليد رقم الاستمارة عند إدخال رقم الجلوس
document.getElementById('seatNumber').addEventListener('blur', function() {
    const seatNumber = this.value.trim();
    const studentName = document.getElementById('studentName').value.trim();
    
    if (seatNumber && studentName) {
        // التحقق من عدم تكرار رقم الجلوس
        if (DB.checkSeatNumberExists(seatNumber)) {
            showAlert('رقم الجلوس مستخدم مسبقاً. إذا كنت قدمت من قبل، يمكنك الاستعلام عن نتيجتك.', 'warning');
            this.value = '';
            return;
        }
        
        formNumber = DB.generateFormNumber(seatNumber);
        document.getElementById('generatedFormNumber').textContent = formNumber;
        document.getElementById('formNumberDisplay').style.display = 'block';
    }
});

// تحميل الجامعات
function loadUniversities() {
    const universities = DB.getUniversities();
    const select = document.getElementById('newUniversity');
    
    select.innerHTML = '<option value="">اختر الجامعة</option>';
    universities.forEach(uni => {
        const option = document.createElement('option');
        option.value = JSON.stringify(uni);
        option.textContent = uni.name;
        select.appendChild(option);
    });
}
document.addEventListener('DOMContentLoaded', function() {
    // 1. ربط العناصر بالأسماء الموجودة في كود الـ HTML الخاص بك
    const uniSelect = document.getElementById('newUniversity');
    const progSelect = document.getElementById('newProgram');

    if (uniSelect && progSelect) {
        uniSelect.addEventListener('change', function() {
            const universityId = this.value;
            
            // 2. تصفير قائمة التخصصات وإظهار رسالة انتظار
            progSelect.innerHTML = '<option value="">جاري تحميل الكليات...</option>';

            if (universityId) {
                // 3. الطلب من السيرفر (تأكد أن الرابط يبدأ بـ /)
                fetch(`/get_programs/?university_id=${universityId}`)
                    .then(response => {
                        if (!response.ok) throw new Error('خطأ في الشبكة');
                        return response.json();
                    })
                    .then(data => {
                        // 4. مسح القائمة ووضع الكليات الجديدة
                        progSelect.innerHTML = '<option value="">اختر التخصص</option>';
                        
                        if (data.length === 0) {
                            progSelect.innerHTML = '<option value="">لا توجد كليات لهذه الجامعة</option>';
                        } else {
                            data.forEach(prog => {
                                const option = document.createElement('option');
                                // نضع ID الكلية في الـ value واسمها في النص
                                option.value = prog.id; 
                                option.textContent = prog.name;
                                progSelect.appendChild(option);
                            });
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        progSelect.innerHTML = '<option value="">فشل تحميل الكليات</option>';
                    });
            } else {
                progSelect.innerHTML = '<option value="">اختر الكلية أولاً</option>';
            }
        });
    }
});

// التبديل بين طرق الاختيار
document.querySelectorAll('input[name="selectionMethod"]').forEach(radio => {
    radio.addEventListener('change', function() {
        if (this.value === 'recommended') {
            document.getElementById('recommendationSection').style.display = 'block';
            document.getElementById('manualSelectionSection').style.display = 'none';
        } else {
            document.getElementById('recommendationSection').style.display = 'none';
            document.getElementById('manualSelectionSection').style.display = 'block';
        }
    });
});

// الحصول على التوصيات
document.getElementById('getRecommendationsBtn').addEventListener('click', function() {
    const percentage = parseFloat(document.getElementById('percentage').value);
    const field = document.getElementById('fieldOfStudy').value;
    const preferredField = document.getElementById('preferredField').value;
    const region = document.getElementById('preferredRegion').value;
    
    if (!percentage || !field) {
        showAlert('يرجى ملء النسبة والمسار الدراسي أولاً', 'error');
        return;
    }
    
    if (!preferredField) {
        showAlert('يرجى اختيار المجال المفضل', 'error');
        return;
    }
    
    // تصفية البرامج
    let programs = DB.getPrograms()
        .filter(p => p.field === field && p.minPercentage <= percentage);
    
    if (preferredField !== 'جميع') {
        programs = programs.filter(p => p.category === preferredField);
    }
    
    // ترتيب حسب الحد الأدنى (الأعلى أولاً)
    programs.sort((a, b) => b.minPercentage - a.minPercentage);
    
    // أخذ أول 20 برنامج
    programs = programs.slice(0, 20);
    
    if (programs.length === 0) {
        showAlert('لا توجد تخصصات متاحة تطابق معاييرك', 'warning');
        return;
    }
    
    // عرض التوصيات
    const container = document.getElementById('recommendationsContainer');
    container.innerHTML = `
        <div style="background: white; padding: 1rem; border-radius: 5px;">
            <h4 style="color: #667eea; margin-bottom: 1rem;">التوصيات (${programs.length} تخصص)</h4>
            <p style="color: #666; margin-bottom: 1rem; font-size: 0.9rem;">
                يمكنك إضافة جميع التوصيات أو اختيار ما يناسبك
            </p>
            
            <button type="button" onclick="addAllRecommendations()" class="btn btn-primary" style="width: 100%; margin-bottom: 1rem;">
                إضافة جميع التوصيات
            </button>
            
            <div style="max-height: 400px; overflow-y: auto;">
                ${programs.map((prog, index) => `
                    <div style="background: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 0.5rem; border-right: 3px solid #667eea;">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div style="flex: 1;">
                                <strong style="color: #333;">${index + 1}. ${prog.name}</strong>
                                <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem; flex-wrap: wrap;">
                                    <span style="background: #667eea; color: white; padding: 0.2rem 0.6rem; border-radius: 10px; font-size: 0.8rem;">
                                        ${prog.category}
                                    </span>
                                    <span style="background: #28a745; color: white; padding: 0.2rem 0.6rem; border-radius: 10px; font-size: 0.8rem;">
                                        ${prog.minPercentage}%
                                    </span>
                                </div>
                            </div>
                            <button type="button" onclick='addRecommendedChoice(${JSON.stringify(prog)})' 
                                    class="btn btn-secondary" style="padding: 0.5rem 1rem; font-size: 0.85rem; white-space: nowrap;">
                                إضافة
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    
    // حفظ التوصيات للاستخدام لاحقاً
    window.recommendedPrograms = programs;
});

// إضافة توصية واحدة
window.addRecommendedChoice = function(program) {
    const universities = DB.getUniversities();
    const region = document.getElementById('preferredRegion').value;
    
    // اختيار جامعة عشوائية (أو من المنطقة المفضلة)
    let availableUniversities = region ? 
        universities.filter(u => u.region === region) : 
        universities;
    
    if (availableUniversities.length === 0) {
        availableUniversities = universities;
    }
    
    const randomUni = availableUniversities[Math.floor(Math.random() * availableUniversities.length)];
    
    addChoiceToList(randomUni, program);
};

// إضافة جميع التوصيات
window.addAllRecommendations = function() {
    if (!window.recommendedPrograms || window.recommendedPrograms.length === 0) {
        showAlert('لا توجد توصيات لإضافتها', 'error');
        return;
    }
    
    const universities = DB.getUniversities();
    const region = document.getElementById('preferredRegion').value;
    
    let availableUniversities = region ? 
        universities.filter(u => u.region === region) : 
        universities;
    
    if (availableUniversities.length === 0) {
        availableUniversities = universities;
    }
    
    window.recommendedPrograms.forEach(program => {
        if (choices.length < MAX_CHOICES) {
            const randomUni = availableUniversities[Math.floor(Math.random() * availableUniversities.length)];
            addChoiceToList(randomUni, program, false);
        }
    });
    
    updateChoicesList();
    showAlert('تم إضافة جميع التوصيات بنجاح', 'success');
};

// إضافة رغبة يدوياً
document.getElementById('addChoiceBtn').addEventListener('click', function() {
    const uniSelect = document.getElementById('newUniversity');
    const progSelect = document.getElementById('newProgram');
    
    if (!uniSelect.value || !progSelect.value) {
        showAlert('يرجى اختيار الجامعة والتخصص', 'error');
        return;
    }
    
    const university = JSON.parse(uniSelect.value);
    const program = JSON.parse(progSelect.value);
    
    // التحقق من النسبة
    const percentage = parseFloat(document.getElementById('percentage').value);
    if (percentage < program.minPercentage) {
        showAlert(`نسبتك (${percentage}%) أقل من الحد الأدنى المطلوب لتخصص ${program.name} (${program.minPercentage}%)`, 'warning');
        return;
    }
    
    addChoiceToList(university, program);
    
    // إعادة تعيين القوائم
    uniSelect.value = '';
    progSelect.value = '';
});

// إضافة رغبة للقائمة
function addChoiceToList(university, program, showMessage = true) {
    if (choices.length >= MAX_CHOICES) {
        if (showMessage) showAlert('لقد وصلت للحد الأقصى من الرغبات (20 رغبة)', 'warning');
        return;
    }
    
    // التحقق من عدم التكرار
    const isDuplicate = choices.some(c => 
        c.university.id === university.id && c.program.id === program.id
    );
    
    if (isDuplicate) {
        if (showMessage) showAlert('هذه الرغبة موجودة مسبقاً', 'warning');
        return;
    }
    
    choices.push({
        university: university,
        program: program,
        priority: choices.length + 1
    });
    
    updateChoicesList();
    if (showMessage) showAlert('تمت إضافة الرغبة بنجاح', 'success');
}

// تحديث قائمة الرغبات
function updateChoicesList() {
    const container = document.getElementById('choicesList');
    document.getElementById('choicesCount').textContent = `${choices.length}/20`;
    
    if (choices.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #999; padding: 2rem;">لم تقم بإضافة أي رغبة بعد</p>';
        return;
    }
    
    container.innerHTML = choices.map((choice, index) => `
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 0.5rem; border-right: 4px solid #667eea;">
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 1rem;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <span style="background: #667eea; color: white; padding: 0.3rem 0.6rem; border-radius: 50%; font-weight: bold; font-size: 0.9rem;">
                            ${choice.priority}
                        </span>
                        <strong style="color: #333;">${choice.program.name}</strong>
                    </div>
                    <p style="margin: 0.3rem 0; color: #666; font-size: 0.9rem;">
                        📍 ${choice.university.name}
                    </p>
                    <p style="margin: 0.3rem 0; color: #666; font-size: 0.85rem;">
                        ${choice.university.region} • ${choice.program.category}
                    </p>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.3rem;">
                    ${index > 0 ? `<button type="button" onclick="moveChoice(${index}, 'up')" class="btn btn-secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;">↑</button>` : ''}
                    ${index < choices.length - 1 ? `<button type="button" onclick="moveChoice(${index}, 'down')" class="btn btn-secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;">↓</button>` : ''}
                    <button type="button" onclick="removeChoice(${index})" class="btn btn-secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem; background: #dc3545;">✕</button>
                </div>
            </div>
        </div>
    `).join('');
}

// حذف رغبة
window.removeChoice = function(index) {
    choices.splice(index, 1);
    // إعادة ترتيب الأولويات
    choices.forEach((choice, i) => {
        choice.priority = i + 1;
    });
    updateChoicesList();
    showAlert('تم حذف الرغبة', 'info');
};

// تحريك رغبة لأعلى أو لأسفل
window.moveChoice = function(index, direction) {
    if (direction === 'up' && index > 0) {
        [choices[index], choices[index - 1]] = [choices[index - 1], choices[index]];
    } else if (direction === 'down' && index < choices.length - 1) {
        [choices[index], choices[index + 1]] = [choices[index + 1], choices[index]];
    }
    
    // إعادة ترتيب الأولويات
    choices.forEach((choice, i) => {
        choice.priority = i + 1;
    });
    
    updateChoicesList();
};

// إرسال النموذج
document.getElementById('registrationForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const studentName = document.getElementById('studentName').value.trim();
    const seatNumber = document.getElementById('seatNumber').value.trim();
    const phoneNumber = document.getElementById('phoneNumber').value.trim();
    const email = document.getElementById('email').value.trim();
    const percentage = parseFloat(document.getElementById('percentage').value);
    const field = document.getElementById('fieldOfStudy').value;
    const region = document.getElementById('preferredRegion').value;
    
    if (!formNumber) {
        showAlert('يرجى إدخال رقم الجلوس والاسم لتوليد رقم الاستمارة', 'error');
        return;
    }
    
    if (choices.length === 0) {
        showAlert('يرجى إضافة رغبة واحدة على الأقل', 'error');
        return;
    }
    
    const application = {
        formNumber: formNumber,
        studentName: studentName,
        seatNumber: seatNumber,
        phoneNumber: phoneNumber,
        email: email,
        percentage: percentage,
        fieldOfStudy: field,
        preferredRegion: region,
        choices: choices.map(c => ({
            priority: c.priority,
            university: c.university.name,
            program: c.program.name,
            region: c.university.region,
            category: c.program.category
        })),
        submissionDate: new Date().toISOString(),
        status: 'قيد المراجعة'
    };
    
    DB.saveApplication(application);
    
    showAlert('تم إرسال طلبك بنجاح! رقم استمارتك: ' + formNumber, 'success');
    
 
});

// دالة عرض الرسائل
function showAlert(message, type) {
    const container = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    
    container.innerHTML = '';
    container.appendChild(alert);
    
    window.scrollTo({ top: 0, behavior: 'smooth' });
    
    setTimeout(() => {
        alert.remove();
    }, 5000);
}