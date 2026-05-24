// قاعدة البيانات
const DB = {
    getApplications: function() {
        const apps = localStorage.getItem('applications');
        return apps ? JSON.parse(apps) : [];
    },
    
    getApplicationByFormNumber: function(formNumber) {
        const applications = this.getApplications();
        return applications.find(app => app.formNumber === formNumber);
    },
    
    getApplicationBySeatNumber: function(seatNumber) {
        const applications = this.getApplications();
        return applications.find(app => app.seatNumber === seatNumber);
    },
    
    getApplicationBygender: function(gender) {
        const applications = this.getApplications();
        return applications.find(app => app.gender === gender);
    },
    
    getResults: function() {
        const results = localStorage.getItem('results');
        return results ? JSON.parse(results) : [];
    },
    
    getResultByFormNumber: function(formNumber) {
        const results = this.getResults();
        return results.find(r => r.formNumber === formNumber);
    }
};

// الاستعلام عن النتيجة
document.getElementById('checkResultBtn').addEventListener('click', function() {
    const formNumber = document.getElementById('formNumber').value.trim();
    
    if (!formNumber) {
        showAlert('يرجى إدخال رقم الاستمارة أو رقم الجلوس', 'error');
        return;
    }
    
    // البحث برقم الاستمارة أو رقم الجلوس
    let application = DB.getApplicationByFormNumber(formNumber);
    
    if (!application) {
        application = DB.getApplicationBySeatNumber(formNumber);
    }
    
    if (!application) {
        showAlert('الرقم المدخل غير موجود. يرجى التأكد من رقم الاستمارة أو رقم الجلوس.', 'error');
        return;
    }
    
    // التحقق من وجود نتيجة
    const result = DB.getResultByFormNumber(application.formNumber);
    
    const resultContainer = document.getElementById('resultContainer');
    resultContainer.style.display = 'block';
    
    if (!result) {
        // لا توجد نتيجة بعد
        resultContainer.innerHTML = `
            <div class="alert alert-info">
                <h3 style="margin-bottom: 1rem;">حالة الطلب</h3>
                <p><strong>رقم الاستمارة:</strong> ${application.formNumber}</p>
                <p><strong>اسم الطالب:</strong> ${application.studentName}</p>
                <p><strong> الجنس:</strong> ${application.gender}</p>
                <p><strong>رقم الجلوس:</strong> ${application.seatNumber}</p>
                <p><strong>النسبة المئوية:</strong> ${application.percentage}%</p>
                <p><strong>حالة الطلب:</strong> ${application.status}</p>
                <p style="margin-top: 1rem;">طلبك قيد المراجعة. سيتم الإعلان عن النتائج قريباً.</p>
            </div>
            
            <div style="background: white; padding: 1.5rem; border-radius: 10px; margin-top: 1.5rem; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h4 style="color: #9097b4; margin-bottom: 1rem;">رغباتك (${application.choices.length} رغبة):</h4>
                <div style="max-height: 400px; overflow-y: auto;">
                    ${application.choices.map((choice, index) => `
                        <div style="background: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 0.5rem; border-right: 4px solid #667eea;">
                            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
                                <span style="background: #333747; color: white; padding: 0.3rem 0.6rem; border-radius: 50%; font-weight: bold; font-size: 0.85rem;">
                                    ${choice.priority}
                                </span>
                                <strong style="color: #333;">${choice.program}</strong>
                            </div>
                            <p style="margin: 0.2rem 0 0 0; color: #666; font-size: 0.9rem;">
                                 ${choice.university} - ${choice.region}
                            </p>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        return;
    }
    
    // عرض النتيجة
    displayResult(result, application);
});

function displayResult(result, application) {
    const resultContainer = document.getElementById('resultContainer');
    
    const isAccepted = result.status === 'مقبول';
    const alertClass = isAccepted ? 'alert-success' : 'alert-warning';
    
    let resultHTML = `
        <div class="alert ${alertClass}">
            <h3 style="margin-bottom: 1rem;">🎉 نتيجة القبول</h3>
            <p><strong>رقم الاستمارة:</strong> ${result.formNumber}</p>
            <p><strong>اسم الطالب:</strong> ${application.studentName}</p>
            <p><strong>رقم الجلوس:</strong> ${application.seatNumber}</p>
            <p><strong>الحالة:</strong> <span style="font-size: 1.2rem; font-weight: bold;">${result.status}</span></p>
        </div>
    `;
    
    if (isAccepted) {
        resultHTML += `
            <div style="background: white; padding: 2rem; border-radius: 10px; margin-top: 1.5rem; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h4 style="color: #667eea; margin-bottom: 1rem;">🎊 تفاصيل القبول:</h4>
                <div style="background: #d4edda; padding: 1.5rem; border-radius: 5px; border: 2px solid #28a745;">
                    <p style="font-size: 1.1rem; margin-bottom: 0.5rem;"><strong>الجامعة:</strong> ${result.acceptedUniversity}</p>
                    <p style="font-size: 1.1rem; margin-bottom: 0.5rem;"><strong>التخصص:</strong> ${result.acceptedProgram}</p>
                    <p style="font-size: 1.1rem;"><strong>رقم القيد:</strong> ${result.registrationNumber || 'سيتم إرساله لاحقاً'}</p>
                </div>
                
                <div style="background: #fff3cd; padding: 1rem; border-radius: 5px; margin-top: 1rem;">
                    <p style="color: #856404; margin: 0;">
                        ⚠️ يرجى مراجعة الجامعة خلال الفترة المحددة لإكمال إجراءات التسجيل
                    </p>
                </div>
                
                <h4 style="color: #667eea; margin: 2rem 0 1rem;"> الخطوات القادمة:</h4>
                <ol style="margin-right: 1.5rem;">
                    <li style="margin-bottom: 0.5rem;">طباعة نتيجة القبول</li>
                    <li style="margin-bottom: 0.5rem;">مراجعة الجامعة بالمستندات المطلوبة</li>
                    <li style="margin-bottom: 0.5rem;">دفع رسوم التسجيل</li>
                    <li style="margin-bottom: 0.5rem;">استلام الجدول الدراسي</li>
                </ol>
                
                <button onclick="window.print()" class="btn btn-primary" style="margin-top: 1.5rem; width: 100%;">
                     طباعة النتيجة
                </button>
            </div>
        `;
    } else {
        resultHTML += `
            <div style="background: white; padding: 2rem; border-radius: 10px; margin-top: 1.5rem; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h4 style="color: #667eea; margin-bottom: 1rem;">رغباتك (${application.choices.length} رغبة):</h4>
                <div style="max-height: 400px; overflow-y: auto;">
                    ${application.choices.map((choice, index) => `
                        <div style="background: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 0.5rem;">
                            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
                                <span style="background: #667eea; color: white; padding: 0.3rem 0.6rem; border-radius: 50%; font-weight: bold; font-size: 0.85rem;">
                                    ${choice.priority}
                                </span>
                                <strong style="color: #333;">${choice.program}</strong>
                            </div>
                            <p style="margin: 0.2rem 0 0 0; color: #666; font-size: 0.9rem;">
                                📍 ${choice.university} - ${choice.region}
                            </p>
                        </div>
                    `).join('')}
                </div>
                
                <div style="background: #d1ecf1; padding: 1rem; border-radius: 5px; margin-top: 1rem;">
                    <p style="color: #0c5460; margin: 0;">
                        💡 يمكنك التقديم في الشواغر أو الدور الثاني. تابع الإعلانات على موقعنا.
                    </p>
                </div>
                
             
            </div>
        `;
    }
    
    resultContainer.innerHTML = resultHTML;
}

function showAlert(message, type) {
    const container = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    
    container.innerHTML = '';
    container.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 5000);
}