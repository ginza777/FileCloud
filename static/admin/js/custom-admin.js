// Custom Admin JavaScript for FileFinder Dashboard

// Global variables - check if already declared to avoid duplicate declaration
if (typeof window.dashboardData === 'undefined') {
    window.dashboardData = {};
}
let refreshInterval = null;

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('FileFinder Admin Dashboard initialized');
    initializeDashboard();
});

// Initialize dashboard functionality
function initializeDashboard() {
    // Load initial data
    loadAdminStats();
    
    // Set up auto-refresh every 3 minutes (180000 ms)
    refreshInterval = setInterval(loadAdminStats, 180000);
    
    // Set up manual refresh button if exists
    const refreshButton = document.getElementById('refresh-stats');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            loadAdminStats();
        });
    }
    
    // Initialize charts if Chart.js is available
    if (typeof Chart !== 'undefined') {
        initializeCharts();
    }
}

// Load admin statistics from API
async function loadAdminStats() {
    try {
        console.log('Loading admin statistics...');
        
        // Show loading state
        showLoadingState();
        
        // Fetch data from API
        const response = await fetch('/admin/api/stats/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Admin stats loaded:', data);
        
        // Check if the response is successful
        if (!data.success) {
            throw new Error(data.error || 'API request failed');
        }
        
        // Store data globally
        window.dashboardData = data;
        
        // Update UI with new data
        updateDashboardUI(data);
        
        // Hide loading state
        hideLoadingState();
        
    } catch (error) {
        console.error('Error loading stats:', error);
        // Only show error if error element exists to avoid null reference errors
        try {
            const errorElement = document.getElementById('error-message');
            if (errorElement) {
        showErrorState('Xatolik: Statistikalarni yuklashda muammo yuz berdi');
            }
        } catch (e) {
            // Silently ignore if error element doesn't exist
        }
        hideLoadingState();
    }
}

// Update dashboard UI with new data
function updateDashboardUI(data) {
    // Update stat cards
    updateStatCards(data.stats);
    
    // Update charts
    updateCharts(data.charts);
    
    // Update activities
    updateActivities(data.activities);
    
    // Update system health
    updateSystemHealth(data.system_health);
    
    // Update last refresh time
    updateLastRefreshTime();
}

// Update stat cards
function updateStatCards(stats) {
    if (!stats) return;
    
    const statElements = {
        'total-documents': stats.total_documents || 0,
        'completed-documents': stats.completed_documents || 0,
        'pending-documents': stats.pending_documents || 0,
        'failed-documents': stats.failed_documents || 0,
        'total-products': stats.total_products || 0,
        'total-users': stats.total_users || 0,
        'telegram-sent': stats.telegram_sent || 0,
        'total-errors': stats.total_errors || 0,
        'total-docs': stats.total_documents || 0,  // Alternative ID
        'total-products': stats.total_products || 0,  // Alternative ID
        'total-users': stats.total_users || 0,  // Alternative ID
        'system-health': 'OK'  // System health indicator
    };
    
    Object.entries(statElements).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = typeof value === 'number' ? value.toLocaleString() : value;
        }
    });
}

// Update charts
function updateCharts(chartData) {
    if (!chartData || typeof Chart === 'undefined') {
        return;
    }
    
    // Update daily activity chart
    if (chartData.daily && window.dailyChart) {
        window.dailyChart.data.labels = chartData.daily.labels;
        window.dailyChart.data.datasets[0].data = chartData.daily.data;
        window.dailyChart.update();
    }
    
    // Update status distribution chart
    if (chartData.status && window.statusChart) {
        window.statusChart.data.datasets[0].data = [
            chartData.status.completed || 0,
            chartData.status.processing || 0,
            chartData.status.failed || 0,
            chartData.status.pending || 0
        ];
        window.statusChart.update();
    }
    
    // Update error types chart
    if (chartData.errors && window.errorChart) {
        window.errorChart.data.labels = chartData.errors.types || [];
        window.errorChart.data.datasets[0].data = chartData.errors.counts || [];
        window.errorChart.update();
    }
}

// Update activities list
function updateActivities(activities) {
    const activitiesContainer = document.getElementById('activities-list');
    if (!activitiesContainer || !activities) {
        return;
    }
    
    activitiesContainer.innerHTML = '';
    
    activities.forEach(activity => {
        const activityElement = createActivityElement(activity);
        activitiesContainer.appendChild(activityElement);
    });
}

// Create activity element
function createActivityElement(activity) {
    const div = document.createElement('div');
    div.className = 'activity-item';
    
    div.innerHTML = `
        <div class="activity-icon">${activity.icon || '📄'}</div>
        <div class="activity-content">
            <div class="activity-title">${activity.title || 'Noma\'lum faoliyat'}</div>
            <div class="activity-time">${activity.time || 'Vaqt noma\'lum'}</div>
        </div>
        <div class="activity-status ${activity.status || 'secondary'}">
            ${activity.status || 'secondary'}
        </div>
    `;
    
    return div;
}

// Update system health
function updateSystemHealth(health) {
    if (!health) return;
    
    const healthElements = {
        'database-status': health.database_status || 'N/A',
        'celery-status': health.celery_status || 'N/A',
        'elasticsearch-status': health.elasticsearch_status || 'N/A',
        'redis-status': health.redis_status || 'N/A',
        'disk-usage': health.disk_usage || 'N/A',
        'memory-usage': health.memory_usage || 'N/A',
        'cpu-usage': health.cpu_usage || 'N/A'
    };
    
    Object.entries(healthElements).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
            
            // Update status classes
            const statusElement = element.parentElement.querySelector('.health-status');
            if (statusElement) {
                statusElement.className = 'health-status';
                if (value === 'OK') {
                    statusElement.classList.add('ok');
                } else if (value === 'ERROR') {
                    statusElement.classList.add('error');
                }
            }
        }
    });
}

// Update last refresh time
function updateLastRefreshTime() {
    const timeElement = document.getElementById('last-refresh-time');
    if (timeElement) {
        const now = new Date();
        timeElement.textContent = now.toLocaleTimeString('uz-UZ');
    }
}

// Initialize charts
function initializeCharts() {
    // Daily activity chart
    const dailyCtx = document.getElementById('daily-chart');
    if (dailyCtx) {
        window.dailyChart = new Chart(dailyCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Kunlik faoliyat',
                    data: [],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }
    
    // Status distribution chart
    const statusCtx = document.getElementById('status-chart');
    if (statusCtx) {
        window.statusChart = new Chart(statusCtx, {
            type: 'doughnut',
            data: {
                labels: ['Tugallangan', 'Jarayonda', 'Xatolik', 'Kutilmoqda'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        '#2ed573',
                        '#3742fa',
                        '#ff4757',
                        '#ffa502'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
    
    // Error types chart
    const errorCtx = document.getElementById('error-chart');
    if (errorCtx) {
        window.errorChart = new Chart(errorCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Xatoliklar soni',
                    data: [],
                    backgroundColor: '#ff4757'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }
}

// Show loading state
function showLoadingState() {
    const loadingElement = document.getElementById('loading-indicator');
    if (loadingElement) {
        loadingElement.style.display = 'flex';
    }
    
    // Disable refresh button
    const refreshButton = document.getElementById('refresh-stats');
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.textContent = 'Yuklanmoqda...';
    }
}

// Hide loading state
function hideLoadingState() {
    const loadingElement = document.getElementById('loading-indicator');
    if (loadingElement) {
        loadingElement.style.display = 'none';
    }
    
    // Enable refresh button
    const refreshButton = document.getElementById('refresh-stats');
    if (refreshButton) {
        refreshButton.disabled = false;
        refreshButton.textContent = 'Yangilash';
    }
}

// Show error state
function showErrorState(message) {
    const errorElement = document.getElementById('error-message');
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    } else {
        // Create error element if it doesn't exist
        const errorDiv = document.createElement('div');
        errorDiv.id = 'error-message';
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        
        const container = document.querySelector('.dashboard-container');
        if (container) {
            container.insertBefore(errorDiv, container.firstChild);
        }
    }
    
    // Hide error after 5 seconds
    setTimeout(() => {
        const errorElement = document.getElementById('error-message');
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    }, 5000);
}

// Get CSRF token
function getCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// Utility function to format numbers
function formatNumber(num) {
    return new Intl.NumberFormat('uz-UZ').format(num);
}

// Utility function to format dates
function formatDate(date) {
    return new Intl.DateTimeFormat('uz-UZ', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    }).format(new Date(date));
}

// Export functions for global access
window.FileFinderAdmin = {
    loadAdminStats,
    updateDashboardUI,
    initializeCharts,
    formatNumber,
    formatDate
};