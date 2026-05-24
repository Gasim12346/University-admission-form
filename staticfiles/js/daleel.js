// قاعدة البيانات
const universities = [
    { id: 1, name: 'جامعة الخرطوم', region: 'الخرطوم' },
    { id: 2, name: 'جامعة أم درمان الإسلامية', region: 'أم درمان' },
    { id: 3, name: 'جامعة السودان للعلوم والتكنولوجيا', region: 'الخرطوم' },
    { id: 4, name: 'جامعة النيلين', region: 'الخرطوم' },
    { id: 5, name: 'جامعة بحري', region: 'بحري' },
    { id: 6, name: 'جامعة سنار', region: 'سنار' },
    { id: 7, name: 'جامعة كسلا', region: 'كسلا' },
    { id: 8, name: 'جامعة البحر الأحمر', region: 'بورتسودان' }
];

const programs = [
    { id: 1, name: 'الطب البشري', field: 'علمي', minPercentage: 90, category: 'طبية', description: 'دراسة الطب البشري والعلوم الطبية' },
    { id: 2, name: 'طب الأسنان', field: 'علمي', minPercentage: 88, category: 'طبية', description: 'دراسة طب وجراحة الأسنان' },
    { id: 3, name: 'الصيدلة', field: 'علمي', minPercentage: 85, category: 'طبية', description: 'دراسة الأدوية والعقاقير الطبية' },
    { id: 4, name: 'التمريض', field: 'علمي', minPercentage: 75, category: 'طبية', description: 'دراسة علوم التمريض والرعاية الصحية' },
    { id: 5, name: 'الهندسة المدنية', field: 'علمي', minPercentage: 80, category: 'هندسية', description: 'تصميم وبناء المنشآت والبنية التحتية' },
    { id: 6, name: 'هندسة الحاسوب', field: 'علمي', minPercentage: 82, category: 'هندسية', description: 'دراسة الحاسبات والأنظمة الرقمية' },
    { id: 7, name: 'الهندسة الكهربائية', field: 'علمي', minPercentage: 80, category: 'هندسية', description: 'دراسة الكهرباء والأنظمة الكهربائية' },
    { id: 8, name: 'الهندسة الميكانيكية', field: 'علمي', minPercentage: 80, category: 'هندسية', description: 'دراسة الآلات والأنظمة الميكانيكية' },
    { id: 9, name: 'علوم الحاسوب', field: 'علمي', minPercentage: 75, category: 'علوم', description: 'دراسة البرمجة وعلوم الكمبيوتر' },
    { id: 10, name: 'الرياضيات', field: 'علمي', minPercentage: 70, category: 'علوم', description: 'دراسة الرياضيات التطبيقية والنظرية' },
    { id: 11, name: 'الفيزياء', field: 'علمي', minPercentage: 70, category: 'علوم', description: 'دراسة الظواهر الطبيعية والفيزيائية' },
    { id: 12, name: 'الكيمياء', field: 'علمي', minPercentage: 70, category: 'علوم', description: 'دراسة المواد وتفاعلاتها الكيميائية' },
    { id: 13, name: 'القانون', field: 'أدبي', minPercentage: 75, category: 'قانونية', description: 'دراسة القوانين والأنظمة القانونية' },
    { id: 14, name: 'إدارة الأعمال', field: 'أدبي', minPercentage: 70, category: 'إدارية', description: 'دراسة الإدارة والأعمال التجارية' },
    { id: 15, name: 'المحاسبة', field: 'أدبي', minPercentage: 70, category: 'إدارية', description: 'دراسة المحاسبة المالية والإدارية' },
    { id: 16, name: 'الاقتصاد', field: 'أدبي', minPercentage: 68, category: 'إدارية', description: 'دراسة النظريات الاقتصادية والمالية' },
    { id: 17, name: 'اللغة العربية', field: 'أدبي', minPercentage: 65, category: 'أدبية', description: 'دراسة اللغة العربية وآدابها' },
    { id: 18, name: 'اللغة الإنجليزية', field: 'أدبي', minPercentage: 65, category: 'أدبية', description: 'دراسة اللغة الإنجليزية وآدابها' },
    { id: 19, name: 'التاريخ', field: 'أدبي', minPercentage: 65, category: 'أدبية', description: 'دراسة التاريخ والحضارات' },
    { id: 20, name: 'الجغرافيا', field: 'أدبي', minPercentage: 65, category: 'أدبية', description: 'دراسة الجغرافيا الطبيعية والبشرية' }
];

let filteredData = { universities, programs };

// تحميل البيانات عند بدء الصفحة
document.addEventListener('DOMContentLoaded', function() {
    displayGuide();
    
    // إضافة مستمعي الأحداث للفلاتر
    document.getElementById('filterRegion').addEventListener('change', applyFilters);
    document.getElementById('filterField').addEventListener('change', applyFilters);
    document.getElementById('filterCategory').addEventListener('change', applyFilters);
});

// تطبيق الفلاتر
function applyFilters() {
    const region = document.getElementById('filterRegion').value;
    const field = document.getElementById('filterField').value;
    const category = document.getElementById('filterCategory').value;
    
    filteredData.universities = universities.filter(uni => {
        return !region || uni.region === region;
    });
    
    filteredData.programs = programs.filter(prog => {
        let match = true;
        if (field) match = match && prog.field === field;
        if (category) match = match && prog.category === category;
        return match;
    });
    
    displayGuide();
}

// عرض الدليل
function displayGuide() {
    const container = document.getElementById('guideContainer');
    
    if (filteredData.universities.length === 0 || filteredData.programs.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666; padding: 3rem;">لا توجد نتائج تطابق معايير البحث</p>';
        return;
    }
    
    container.innerHTML = filteredData.universities.map(uni => `
        <div style="background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 2rem;">
            <h3 style="color: #667eea; margin-bottom: 0.5rem;">${uni.name}</h3>
            <p style="color: #666; margin-bottom: 1.5rem;">📍 ${uni.region}</p>
            
            <h4 style="color: #667eea; margin-bottom: 1rem;">التخصصات المتاحة:</h4>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem;">
                ${filteredData.programs.map(prog => `
                    <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 8px; border-right: 4px solid #667eea;">
                        <h5 style="color: #333; margin-bottom: 0.5rem;">${prog.name}</h5>
                        <p style="color: #666; font-size: 0.9rem; margin-bottom: 0.5rem;">${prog.description}</p>
                        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">
                            <span style="background: #667eea; color: white; padding: 0.3rem 0.8rem; border-radius: 15px; font-size: 0.85rem;">
                                ${prog.field}
                            </span>
                            <span style="background: #28a745; color: white; padding: 0.3rem 0.8rem; border-radius: 15px; font-size: 0.85rem;">
                                ${prog.category}
                            </span>
                            <span style="background: #ffc107; color: #333; padding: 0.3rem 0.8rem; border-radius: 15px; font-size: 0.85rem;">
                                الحد الأدنى: ${prog.minPercentage}%
                            </span>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}