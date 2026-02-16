// ==================== GLOBAL VARIABLES ====================
let sidebarCollapsed = false;
let historicalChart = null;
let currentChartType = 'bar';
let autoHideErrorTimeout = null;
let refreshInterval = null;
let clockInterval = null;

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded - Initializing...');

    // Initialize dark mode
    initDarkMode();

    // Start clock
    clockInterval = setInterval(updateClock, 1000);
    updateClock();

    // Start stats refresh
    refreshInterval = setInterval(refreshStats, 1000);

    // Set default dates in report modal
    setDefaultReportDates();

    // Load historical data if chart exists
    if (document.getElementById('historicalChart')) {
        loadHistoricalData();
    }

    // Initialize report type selection
    initReportTypeSelection();

    // Set default selected report type
    const visitorCard = document.querySelector('[data-type="visitor"]');
    if (visitorCard) {
        visitorCard.classList.add('selected');
    }

    // Initialize modal close buttons
    initModalCloseButtons();

    // Load sidebar state
    loadSidebarState();

    // Check for flash messages
    checkFlashMessages();

    console.log('Initialization complete');
});

// Clean up intervals on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) clearInterval(refreshInterval);
    if (clockInterval) clearInterval(clockInterval);
});

// ==================== SIDEBAR FUNCTIONS ====================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarTexts = document.querySelectorAll('.sidebar-text');

    if (!sidebarCollapsed) {
        sidebarTexts.forEach(t => t.style.display = 'none');
        sidebar.style.width = '80px';
    } else {
        sidebar.style.width = '256px';
        setTimeout(() => {
            sidebarTexts.forEach(t => t.style.display = 'inline');
        }, 200);
    }
    sidebarCollapsed = !sidebarCollapsed;

    // Save state to localStorage
    localStorage.setItem('sidebarCollapsed', sidebarCollapsed);
}

// Load sidebar state from localStorage
function loadSidebarState() {
    const savedState = localStorage.getItem('sidebarCollapsed');
    if (savedState !== null) {
        sidebarCollapsed = savedState === 'true';
        const sidebar = document.getElementById('sidebar');
        const sidebarTexts = document.querySelectorAll('.sidebar-text');

        if (sidebarCollapsed) {
            sidebarTexts.forEach(t => t.style.display = 'none');
            sidebar.style.width = '80px';
        } else {
            sidebar.style.width = '256px';
            sidebarTexts.forEach(t => t.style.display = 'inline');
        }
    }
}

// ==================== MODAL FUNCTIONS ====================
function initModalCloseButtons() {
    // Close modal with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closeAllModals();
        }
    });

    // Close modal when clicking overlay
    const overlay = document.getElementById('modalOverlay');
    if (overlay) {
        overlay.addEventListener('click', function() {
            closeAllModals();
        });
    }
}

function closeAllModals() {
    const loginModal = document.getElementById('loginModal');
    const reportModal = document.getElementById('reportModal');
    const overlay = document.getElementById('modalOverlay');
    const loginContainer = document.getElementById('loginModalContainer');
    const reportContainer = document.getElementById('reportModalContainer');

    if (loginModal && !loginModal.classList.contains('hidden')) {
        loginModal.classList.add('hidden');
        if (overlay) overlay.classList.remove('active');
        if (loginContainer) loginContainer.classList.remove('active');
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.width = '';
        document.body.style.height = '';
        removeLoginError();

        // Reset login form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) loginForm.reset();
    }

    if (reportModal && !reportModal.classList.contains('hidden')) {
        reportModal.classList.add('hidden');
        if (overlay) overlay.classList.remove('active');
        if (reportContainer) reportContainer.classList.remove('active');
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.width = '';
        document.body.style.height = '';
    }
}

function toggleLoginModal() {
    const modal = document.getElementById('loginModal');
    const overlay = document.getElementById('modalOverlay');
    const modalContainer = document.getElementById('loginModalContainer');

    if (modal && overlay && modalContainer) {
        modal.classList.toggle('hidden');
        overlay.classList.toggle('active');
        modalContainer.classList.toggle('active');

        // Prevent body scrolling when modal is open
        if (!modal.classList.contains('hidden')) {
            document.body.classList.add('modal-open');
            document.body.style.overflow = 'hidden';
            document.body.style.position = 'fixed';
            document.body.style.width = '100%';
            document.body.style.height = '100%';

            // Focus on username input
            setTimeout(() => {
                const usernameInput = document.querySelector('#loginForm input[name="username"]');
                if (usernameInput) usernameInput.focus();
            }, 100);
        } else {
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.position = '';
            document.body.style.width = '';
            document.body.style.height = '';
            // Reset form jika modal ditutup
            const form = document.getElementById('loginForm');
            if (form) form.reset();
            // Hapus pesan error jika ada
            removeLoginError();
        }
    }
}

function toggleReportModal() {
    const modal = document.getElementById('reportModal');
    const overlay = document.getElementById('modalOverlay');
    const modalContainer = document.getElementById('reportModalContainer');

    if (modal && overlay && modalContainer) {
        modal.classList.toggle('hidden');
        overlay.classList.toggle('active');
        modalContainer.classList.toggle('active');

        // Prevent body scrolling when modal is open
        if (!modal.classList.contains('hidden')) {
            document.body.classList.add('modal-open');
            document.body.style.overflow = 'hidden';
            document.body.style.position = 'fixed';
            document.body.style.width = '100%';
            document.body.style.height = '100%';

            // Reset to default dates when opening
            setDefaultReportDates();
        } else {
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.position = '';
            document.body.style.width = '';
            document.body.style.height = '';
        }
    }
}

// ==================== LOGIN FUNCTIONS ====================
async function handleLogin(event) {
    event.preventDefault();

    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const username = form.querySelector('input[name="username"]').value.trim();
    const password = form.querySelector('input[name="password"]').value;

    // Hapus pesan error sebelumnya
    removeLoginError();

    // Clear any existing timeout
    if (autoHideErrorTimeout) {
        clearTimeout(autoHideErrorTimeout);
        autoHideErrorTimeout = null;
    }

    // Validasi sederhana
    if (!username || !password) {
        showLoginError('Username dan password tidak boleh kosong!');
        return;
    }

    if (username.length < 3) {
        showLoginError('Username minimal 3 karakter!');
        return;
    }

    if (password.length < 3) {
        showLoginError('Password minimal 3 karakter!');
        return;
    }

    // Tampilkan loading
    submitBtn.classList.add('loading');
    submitBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await response.json();

            if (data.success) {
                showLoginSuccess();

                setTimeout(() => {
                    window.location.href = data.redirect;
                }, 1500);
            } else {
                showLoginError(data.message || 'Username atau password salah!');

                submitBtn.classList.remove('loading');
                submitBtn.disabled = false;

                form.querySelector('input[name="password"]').value = '';
                form.querySelector('input[name="password"]').focus();
            }
        } else {
            const text = await response.text();
            console.error('Unexpected response:', text);
            showLoginError('Terjadi kesalahan pada server. Silakan coba lagi.');

            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    } catch (error) {
        console.error('Login error:', error);
        showLoginError('Terjadi kesalahan koneksi. Silakan coba lagi nanti.');

        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
    }
}

function showLoginError(message) {
    removeLoginError();

    const errorContainer = document.getElementById('loginErrorContainer');
    if (!errorContainer) return;

    const errorDiv = document.createElement('div');
    errorDiv.className = 'login-error-container';
    errorDiv.id = 'loginErrorMessage';

    errorDiv.innerHTML = `
        <div class="login-error-icon">!</div>
        <div class="login-error-content">
            <div class="login-error-title">Login Gagal</div>
            <div class="login-error-message">${message}</div>
        </div>
        <div class="login-error-close" onclick="this.parentElement.remove()">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        </div>
    `;

    errorContainer.appendChild(errorDiv);

    autoHideErrorTimeout = setTimeout(() => {
        const error = document.getElementById('loginErrorMessage');
        if (error) error.remove();
    }, 5000);
}

function removeLoginError() {
    const existingError = document.getElementById('loginErrorMessage');
    if (existingError) existingError.remove();

    if (autoHideErrorTimeout) {
        clearTimeout(autoHideErrorTimeout);
        autoHideErrorTimeout = null;
    }
}

function showLoginSuccess() {
    const modalContent = document.querySelector('.login-modal-content');
    if (!modalContent) return;

    modalContent.innerHTML = `
        <div class="login-success">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <h3>Login Berhasil!</h3>
            <p>Selamat datang kembali</p>
        </div>
    `;
}

// ==================== REPORT FUNCTIONS ====================
function initReportTypeSelection() {
    const visitorCard = document.querySelector('[data-type="visitor"]');
    const reservationCard = document.querySelector('[data-type="reservation"]');
    const visitorRadio = document.querySelector('input[name="type"][value="visitor"]');
    const reservationRadio = document.querySelector('input[name="type"][value="reservation"]');

    if (visitorCard) {
        visitorCard.addEventListener('click', () => {
            visitorCard.classList.add('selected');
            if (reservationCard) reservationCard.classList.remove('selected');
            if (visitorRadio) visitorRadio.checked = true;
        });
    }

    if (reservationCard) {
        reservationCard.addEventListener('click', () => {
            reservationCard.classList.add('selected');
            if (visitorCard) visitorCard.classList.remove('selected');
            if (reservationRadio) reservationRadio.checked = true;
        });
    }
}

function setDefaultReportDates() {
    const today = new Date();
    const formattedToday = formatDate(today);
    const startInput = document.querySelector('input[name="start_date"]');
    const endInput = document.querySelector('input[name="end_date"]');

    if (startInput && endInput) {
        startInput.value = formattedToday;
        endInput.value = formattedToday;
    }
}

function setQuickRange(range) {
    const today = new Date();
    let startDate, endDate;

    switch(range) {
        case 'today':
            startDate = endDate = today;
            break;
        case 'yesterday':
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            startDate = endDate = yesterday;
            break;
        case 'thisweek':
            const firstDay = new Date(today);
            const day = today.getDay();
            const diff = day === 0 ? 6 : day - 1;
            firstDay.setDate(today.getDate() - diff);
            startDate = firstDay;
            endDate = today;
            break;
        case 'lastweek':
            const lastWeekStart = new Date(today);
            lastWeekStart.setDate(today.getDate() - today.getDay() - 7);
            const lastWeekEnd = new Date(lastWeekStart);
            lastWeekEnd.setDate(lastWeekStart.getDate() + 6);
            startDate = lastWeekStart;
            endDate = lastWeekEnd;
            break;
        case 'thismonth':
            startDate = new Date(today.getFullYear(), today.getMonth(), 1);
            endDate = today;
            break;
        case 'lastmonth':
            startDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            endDate = new Date(today.getFullYear(), today.getMonth(), 0);
            break;
        default:
            return;
    }

    const startInput = document.querySelector('input[name="start_date"]');
    const endInput = document.querySelector('input[name="end_date"]');

    if (startInput && endInput) {
        startInput.value = formatDate(startDate);
        endInput.value = formatDate(endDate);
    }

    highlightActiveRangeButton(range);
}

function highlightActiveRangeButton(activeRange) {
    const buttons = document.querySelectorAll('.quick-range-btn');
    buttons.forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick')?.includes(activeRange)) {
            btn.classList.add('active');
        }
    });
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// ==================== CLOCK FUNCTION ====================
function updateClock() {
    const clock = document.getElementById('clock');
    if (clock) {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        clock.textContent = `${hours}:${minutes}:${seconds}`;
    }
}

// ==================== DARK MODE FUNCTIONS ====================
function toggleDarkMode() {
    document.documentElement.classList.toggle('dark');
    const isDark = document.documentElement.classList.contains('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');

    if (historicalChart) {
        updateChartColors();
    }

    showToast(isDark ? 'Mode Gelap Diaktifkan' : 'Mode Terang Diaktifkan', 'info');
}

function initDarkMode() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
}

function updateChartColors() {
    if (!historicalChart) return;

    const textColor = document.documentElement.classList.contains('dark') ? '#fff' : '#374151';
    const gridColor = document.documentElement.classList.contains('dark') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';

    historicalChart.options.plugins.legend.labels.color = textColor;
    historicalChart.options.scales.y.ticks.color = textColor;
    historicalChart.options.scales.x.ticks.color = textColor;
    historicalChart.options.scales.y.grid.color = gridColor;

    historicalChart.update();
}

// ==================== STATISTICS FUNCTIONS ====================
function refreshStats() {
    fetch('/api/stats')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const m = document.getElementById('display-masuk');
            const k = document.getElementById('display-keluar');
            const t = document.getElementById('display-total');
            const dalamRuangan = document.getElementById('dalam-ruangan');

            if(m) m.innerText = data.masuk;
            if(k) k.innerText = data.keluar;
            if(t) t.innerText = data.total;
            if(dalamRuangan) dalamRuangan.innerText = data.masuk - data.keluar;

            const todayMasuk = document.getElementById('today-masuk');
            const todayKeluar = document.getElementById('today-keluar');

            if(todayMasuk) todayMasuk.textContent = data.masuk;
            if(todayKeluar) todayKeluar.textContent = data.keluar;
        })
        .catch(error => console.error('Gagal mengambil data IoT:', error));
}

// ==================== HISTORICAL CHART FUNCTIONS ====================
async function loadHistoricalData() {
    try {
        const response = await fetch('/api/historical_stats');
        if (!response.ok) {
            throw new Error('Failed to fetch historical data');
        }
        const data = await response.json();

        if (data && data.data && data.labels) {
            if (!historicalChart) {
                initHistoricalChart(data.labels, data.data);
            } else {
                updateHistoricalChart(data.labels, data.data);
            }
            updateDailyData(data.data);
        }
    } catch (error) {
        console.error('Gagal memuat data historis:', error);
    }
}

function initHistoricalChart(labels, data) {
    const canvas = document.getElementById('historicalChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    const masukData = data.map(day => day.masuk);
    const keluarData = data.map(day => day.keluar);
    const totalData = data.map(day => day.total);

    const textColor = document.documentElement.classList.contains('dark') ? '#fff' : '#374151';
    const gridColor = document.documentElement.classList.contains('dark') ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
    const tooltipBg = document.documentElement.classList.contains('dark') ? '#1f2937' : 'white';
    const tooltipTitleColor = document.documentElement.classList.contains('dark') ? '#f9fafb' : '#111827';
    const tooltipBodyColor = document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#4b5563';
    const tooltipBorderColor = document.documentElement.classList.contains('dark') ? '#374151' : '#e5e7eb';

    historicalChart = new Chart(ctx, {
        type: currentChartType,
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Masuk',
                    data: masukData,
                    backgroundColor: 'rgba(34, 197, 94, 0.3)',
                    borderColor: 'rgb(34, 197, 94)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: currentChartType === 'line'
                },
                {
                    label: 'Keluar',
                    data: keluarData,
                    backgroundColor: 'rgba(239, 68, 68, 0.3)',
                    borderColor: 'rgb(239, 68, 68)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: currentChartType === 'line'
                },
                {
                    label: 'Total Traffic',
                    data: totalData,
                    backgroundColor: 'rgba(168, 85, 247, 0.3)',
                    borderColor: 'rgb(168, 85, 247)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: currentChartType === 'line',
                    hidden: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColor,
                        font: { size: 12 },
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: tooltipBg,
                    titleColor: tooltipTitleColor,
                    bodyColor: tooltipBodyColor,
                    borderColor: tooltipBorderColor,
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw} orang`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        callback: function(value) {
                            return value + ' orang';
                        },
                        color: textColor
                    },
                    grid: {
                        color: gridColor
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        color: textColor,
                        maxRotation: 0,
                        maxTicksLimit: 7
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'nearest'
            }
        }
    });
}

function updateHistoricalChart(labels, data) {
    if (!historicalChart) return;

    const masukData = data.map(day => day.masuk);
    const keluarData = data.map(day => day.keluar);
    const totalData = data.map(day => day.total);

    historicalChart.data.labels = labels;
    historicalChart.data.datasets[0].data = masukData;
    historicalChart.data.datasets[1].data = keluarData;
    historicalChart.data.datasets[2].data = totalData;

    historicalChart.update();
}

function changeChartType(type) {
    currentChartType = type;

    const btnBar = document.getElementById('btn-bar');
    const btnLine = document.getElementById('btn-line');

    if(btnBar) {
        btnBar.className = type === 'bar'
            ? 'px-3 py-1 text-sm rounded bg-purple-600 text-white font-medium'
            : 'px-3 py-1 text-sm rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium';
    }

    if(btnLine) {
        btnLine.className = type === 'line'
            ? 'px-3 py-1 text-sm rounded bg-purple-600 text-white font-medium'
            : 'px-3 py-1 text-sm rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium';
    }

    if (historicalChart) {
        historicalChart.config.type = type;
        historicalChart.data.datasets.forEach(dataset => {
            dataset.fill = type === 'line';
        });
        historicalChart.update();
    }
}

function updateDailyData(data) {
    const dailyDataContainer = document.getElementById('daily-data');
    const dailyTotalContainer = document.getElementById('daily-total');
    if (!dailyDataContainer || !dailyTotalContainer) return;

    let dataHtml = '';
    let totalHtml = '';

    for (let i = 0; i < 7; i++) {
        if (i < data.length) {
            const day = data[i];
            dataHtml += `<div class="bg-gray-50 dark:bg-gray-900/30 p-2 rounded">
                            <span class="font-bold text-green-600">${day.masuk}</span>
                            <span class="text-gray-400">/</span>
                            <span class="font-bold text-red-600">${day.keluar}</span>
                        </div>`;
            totalHtml += `<div class="bg-purple-50 dark:bg-purple-900/20 p-2 rounded font-bold text-purple-600 dark:text-purple-400">
                            ${day.total}
                        </div>`;
        } else {
            dataHtml += `<div class="bg-gray-50 dark:bg-gray-900/30 p-2 rounded text-gray-400">-</div>`;
            totalHtml += `<div class="bg-gray-50 dark:bg-gray-900/30 p-2 rounded text-gray-400">-</div>`;
        }
    }

    dailyDataContainer.innerHTML = dataHtml;
    dailyTotalContainer.innerHTML = totalHtml;
}

// ==================== CONFIRMATION FUNCTIONS ====================
function promptReason(form) {
    let reason = prompt("Masukkan alasan penolakan:", "Jadwal bentrok");
    if (reason === null || reason.trim() === "") return false;
    form.querySelector('input[name="reason"]').value = reason;
    return true;
}

// ==================== FLASH MESSAGES ====================
function checkFlashMessages() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        const type = alert.classList.contains('alert-success') ? 'success' :
                    alert.classList.contains('alert-danger') ? 'error' :
                    alert.classList.contains('alert-warning') ? 'warning' : 'info';
        const message = alert.textContent;

        showToast(message, type);
        alert.remove();
    });
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;

    let icon = '';
    switch(type) {
        case 'success':
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
            break;
        case 'error':
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
            break;
        case 'warning':
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>';
            break;
        default:
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
    }

    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.minWidth = '250px';
    toast.style.padding = '12px 16px';
    toast.style.borderRadius = '8px';
    toast.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    toast.style.display = 'flex';
    toast.style.alignItems = 'center';
    toast.style.gap = '12px';
    toast.style.zIndex = '9999';
    toast.style.animation = 'slideIn 0.3s ease-out';

    switch(type) {
        case 'success':
            toast.style.backgroundColor = '#10b981';
            toast.style.color = 'white';
            break;
        case 'error':
            toast.style.backgroundColor = '#ef4444';
            toast.style.color = 'white';
            break;
        case 'warning':
            toast.style.backgroundColor = '#f59e0b';
            toast.style.color = 'white';
            break;
        default:
            toast.style.backgroundColor = '#3b82f6';
            toast.style.color = 'white';
    }

    toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; flex: 1;">
            ${icon}
            <span style="font-size: 14px; font-weight: 500;">${message}</span>
        </div>
        <div style="cursor: pointer; opacity: 0.8;" onclick="this.parentElement.remove()">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        </div>
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                if (toast.parentNode) toast.remove();
            }, 300);
        }
    }, 3000);
}

// ==================== EXPORT FUNCTIONS TO GLOBAL SCOPE ====================
window.toggleSidebar = toggleSidebar;
window.toggleLoginModal = toggleLoginModal;
window.toggleReportModal = toggleReportModal;
window.handleLogin = handleLogin;
window.toggleDarkMode = toggleDarkMode;
window.setQuickRange = setQuickRange;
window.changeChartType = changeChartType;
window.promptReason = promptReason;
window.removeLoginError = removeLoginError;
window.closeAllModals = closeAllModals;
window.loadHistoricalData = loadHistoricalData;
window.refreshStats = refreshStats;
window.showToast = showToast;