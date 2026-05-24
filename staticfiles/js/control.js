// قاعدة البيانات
const DB = {
    getApplicationTypes: function() {
        const types = localStorage.getItem('applicationTypes');
        if (!types) {
            const defaultTypes = [
                { id: 1, name: 'الدور الأول - عام', fee: 500, active: true },
                { id: 2, name: 'الشواغر', fee: 600, active: true },
                { id: 3, name: 'أبناء العاملين', fee: 450, active: true },
                { id: 4, name: 'الوافدين', fee: 800, active: true }
            ];
            localStorage.setItem('applicationTypes', JSON.stringify(defaultTypes));
            return defaultTypes;
        }
        return JSON.parse(types);
    },
    
    updateApplicationTypes: function(types) {
        localStorage.setItem('applicationTypes', JSON.stringify(types));
    },
    
    getPayments: function() {
        const payments = localStorage.getItem('payments');
        return payments ? JSON.parse(payments) : [];
    },
    
    getApplications: function() {
        const apps = localStorage.getItem('applications');
        return apps ? JSON.parse(apps) : [];
    },
    
    getResults: function() {
        const results = localStorage.getItem('results');
        return results ? JSON.parse(results) : [];
    },
    
    saveResult: function(result) {
        const results = this.getResults();
        const existingIndex = results.findIndex(r => r.formNumber === result.formNumber);
        
        if (existingIndex >= 0) {
            results[existingIndex] = result;
        } else {
            results.push(result);
        }
        
        localStorage.setItem('results', JSON.stringify(results));
    },
    
    getComplaints: function() {
        const complaints = localStorage.getItem('complaints');
        return complaints ? JSON.parse(complaints) : [];
    }
};

// تسجيل الدخول
document.getElementById('loginForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    if (username === 'admin' && password === 'admin123') {
        sessionStorage.setItem('adminLoggedIn', 'true');
        showAdminPanel();
    } else {
        showLoginAlert('اسم المستخدم أو كلمة المرور غير صحيحة', 'error');
    }
});

// تسجيل الخروج
document.getElementById('logoutBtn').addEventListener('click', function(e) {
    e.preventDefault();
    sessionStorage.removeItem('adminLoggedIn');
    location.reload();
});

// التحقق من تسجيل الدخول عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    if (sessionStorage.getItem('adminLoggedIn') === 'true') {
        showAdminPanel();
    }
});

function showAdminPanel() {
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('adminPanel').style.display = 'block';
    loadStatistics();
    loadApplicationTypes();
}

function showLoginAlert(message, type) {
    const container = document.getElementById('loginAlert');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    
    container.innerHTML = '';
    container.appendChild(alert);
    
    setTimeout(() => alert.remove(), 3000);
}

// التبويبات
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        const tabName = this.dataset.tab;
        
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
        
        this.classList.add('active');
        document.getElementById(tabName).style.display = 'block';
        
        // تحميل البيانات حسب التبويب
        if (tabName === 'payments') loadPayments();
        else if (tabName === 'applications') loadApplications();
        else if (tabName === 'results') loadResults();
        else if (tabName === 'complaints') loadComplaints();
    });
});

// تحميل الإحصائيات
function loadStatistics() {
    document.getElementById('paymentsCount').textContent = DB.getPayments().length;
    document.getElementById('applicationsCount').textContent = DB.getApplications().length;
    document.getElementById('complaintsCount').textContent = DB.getComplaints().length;
}

// إدارة أنواع التقديم
function loadApplicationTypes() {
    const types = DB.getApplicationTypes();
    const container = document.getElementById('typesContainer');
    
    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>النوع</th>
                    <th>الرسوم (جنيه)</th>
                    <th>الحالة</th>
                    <th>إجراءات</th>
                </tr>
            </thead>
            <tbody>
                ${types.map(type => `
                    <tr>
                        <td>${type.name}</td>
                        <td>${type.fee}</td>
                        <td>
                            <span style="color: ${type.active ? '#28a745' : '#dc3545'}">
                                ${type.active ? '✓ مفعّل' : '✗ معطّل'}
                            </span>
                        </td>
                        <td>
                            <button onclick="toggleTypeStatus(${type.id})" class="btn btn-secondary" style="padding: 0.5rem 1rem; font-size: 0.9rem;">
                                ${type.active ? 'تعطيل' : 'تفعيل'}
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

window.toggleTypeStatus = function(typeId) {
    const types = DB.getApplicationTypes();
    const type = types.find(t => t.id === typeId);
    if (type) {
        type.active = !type.active;
        DB.updateApplicationTypes(types);
        loadApplicationTypes();
    }
};

// عرض المدفوعات
function loadPayments() {
    const payments = DB.getPayments();
    const container = document.getElementById('paymentsContainer');
    
    if (payments.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">لا توجد مدفوعات بعد</p>';
        return;
    }
    
    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>رقم الاستمارة</th>
                    <th>اسم الطالب</th>
                    <th>نوع التقديم</th>
                    <th>الرسوم</th>
                    <th>التاريخ</th>
                    <th>حالة التسجيل</th>
                </tr>
            </thead>
            <tbody>
                ${payments.map(p => `
                    <tr>
                        <td><strong>${p.formNumber}</strong></td>
                        <td>${p.studentName}</td>
                        <td>${p.applicationType}</td>
                        <td>${p.fee} جنيه</td>
                        <td>${new Date(p.paymentDate).toLocaleDateString('ar-SA')}</td>
                        <td>
                            <span style="color: ${p.registrationCompleted ? '#28a745' : '#ffc107'}">
                                ${p.registrationCompleted ? '✓ مكتمل' : '⏳ غير مكتمل'}
                            </span>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// عرض الطلبات
function loadApplications() {
    const applications = DB.getApplications();
    const container = document.getElementById('applicationsContainer');
    
    if (applications.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">لا توجد طلبات بعد</p>';
        return;
    }
    
    container.innerHTML = applications.map(app => `
        <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin-bottom: 1rem;">
            <h4 style="color: #667eea; margin-bottom: 1rem;">رقم الاستمارة: ${app.formNumber}</h4>
            <p><strong>النسبة:</strong> ${app.percentage}%</p>
            <p><strong>المجال:</strong> ${app.fieldOfStudy}</p>
            <p><strong>المنطقة المفضلة:</strong> ${app.preferredRegion}</p>
            <p><strong>تاريخ التقديم:</strong> ${new Date(app.submissionDate).toLocaleDateString('ar-SA')}</p>
            
            <h5 style="margin-top: 1rem; color: #667eea;">الاختيارات:</h5>
            <ol>
                ${app.choices.map(choice => `
                    <li>${choice.university} - ${choice.program}</li>
                `).join('')}
            </ol>
        </div>
    `).join('');
}

// إدارة النتائج
function loadResults() {
    const applications = DB.getApplications();
    const results = DB.getResults();
    const container = document.getElementById('resultsContainer');
    
    if (applications.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">لا توجد طلبات لإضافة نتائج لها</p>';
        return;
    }
    
    container.innerHTML = applications.map(app => {
        const existingResult = results.find(r => r.formNumber === app.formNumber);
        
        return `
            <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin-bottom: 1rem;">
                <h4 style="color: #667eea; margin-bottom: 1rem;">رقم الاستمارة: ${app.formNumber}</h4>
                <p><strong>النسبة:</strong> ${app.percentage}%</p>
                
                ${existingResult ? `
                    <div style="background: #d4edda; padding: 1rem; border-radius: 5px; margin-top: 1rem;">
                        <p><strong>الحالة:</strong> ${existingResult.status}</p>
                        ${existingResult.status === 'مقبول' ? `
                            <p><strong>الجامعة:</strong> ${existingResult.acceptedUniversity}</p>
                            <p><strong>التخصص:</strong> ${existingResult.acceptedProgram}</p>
                        ` : ''}
                    </div>
                ` : `
                    <div style="margin-top: 1rem;">
                        <select id="status_${app.formNumber}" class="form-control" style="margin-bottom: 0.5rem; padding: 0.5rem; width: 100%; border: 2px solid #e1e8ed; border-radius: 5px;">
                            <option value="">اختر الحالة</option>
                            <option value="مقبول">مقبول</option>
                            <option value="غير مقبول">غير مقبول</option>
                        </select>
                        <select id="uni_${app.formNumber}" class="form-control" style="margin-bottom: 0.5rem; padding: 0.5rem; width: 100%; border: 2px solid #e1e8ed; border-radius: 5px; display: none;">
                            <option value="">اختر الجامعة</option>
                            ${app.choices.map(c => `<option value="${c.university}">${c.university}</option>`).join('')}
                        </select>
                        <select id="prog_${app.formNumber}" class="form-control" style="margin-bottom: 0.5rem; padding: 0.5rem; width: 100%; border: 2px solid #e1e8ed; border-radius: 5px; display: none;">
                            <option value="">اختر التخصص</option>
                            ${app.choices.map(c => `<option value="${c.program}">${c.program}</option>`).join('')}
                        </select>
                        <button onclick="saveResult('${app.formNumber}')" class="btn btn-primary">حفظ النتيجة</button>
                    </div>
                `}
            </div>
        `;
    }).join('');
    
    // إضافة مستمع الأحداث لتغيير الحالة
    applications.forEach(app => {
        const statusSelect = document.getElementById(`status_${app.formNumber}`);
        if (statusSelect) {
            statusSelect.addEventListener('change', function() {
                const uniSelect = document.getElementById(`uni_${app.formNumber}`);
                const progSelect = document.getElementById(`prog_${app.formNumber}`);
                
                if (this.value === 'مقبول') {
                    uniSelect.style.display = 'block';
                    progSelect.style.display = 'block';
                } else {
                    uniSelect.style.display = 'none';
                    progSelect.style.display = 'none';
                }
            });
        }
    });
}

window.saveResult = function(formNumber) {
    const status = document.getElementById(`status_${formNumber}`).value;
    
    if (!status) {
        alert('يرجى اختيار الحالة');
        return;
    }
    
    const result = {
        formNumber: formNumber,
        status: status,
        publishDate: new Date().toISOString()
    };
    
    if (status === 'مقبول') {
        const university = document.getElementById(`uni_${formNumber}`).value;
        const program = document.getElementById(`prog_${formNumber}`).value;
        
        if (!university || !program) {
            alert('يرجى اختيار الجامعة والتخصص');
            return;
        }
        
        result.acceptedUniversity = university;
        result.acceptedProgram = program;
        result.registrationNumber = 'REG' + Math.floor(100000 + Math.random() * 900000);
    }
    
    DB.saveResult(result);
    loadResults();
    alert('تم حفظ النتيجة بنجاح');
};

// عرض الشكاوى
function loadComplaints() {
    const complaints = DB.getComplaints();
    const container = document.getElementById('complaintsContainer');
    
    if (complaints.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">لا توجد شكاوى بعد</p>';
        return;
    }
    
    container.innerHTML = complaints.reverse().map((complaint, index) => `
        <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin-bottom: 1rem;">
            <p><strong>الرسالة:</strong></p>
            <p style="background: white; padding: 1rem; border-radius: 5px;">${complaint.message}</p>
            <p style="margin-top: 0.5rem;"><strong>التاريخ:</strong> ${new Date(complaint.timestamp).toLocaleString('ar-SA')}</p>
            <p><strong>الحالة:</strong> <span style="color: #ffc107;">${complaint.status}</span></p>
        </div>
    `).join('');
}

// تطبيق الستايل على التبويبات النشطة
const style = document.createElement('style');
style.textContent = `
    .tab-btn.active {
        background: white !important;
        color: #667eea;
        font-weight: bold;
        border-bottom: 3px solid #667eea;
    }
    .tab-btn:hover {
        background: #e9ecef;
    }
`;
document.head.appendChild(style);