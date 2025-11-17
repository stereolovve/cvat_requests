// CVAT Task List - JavaScript Module
// Handles dashboard, filters, sorting, and infinite scroll

// ==================== DASHBOARD ====================

let chartsInstances = {};
let currentQuickFilter = '30d';

/**
 * Load dashboard metrics from API
 */
async function loadDashboardData(quickFilter) {
    currentQuickFilter = quickFilter;

    // Show loading state
    showLoadingState();

    try {
        // Use Django's reverse URL instead of hardcoded path
        const url = window.DASHBOARD_API_URL || '/cvat/api/dashboard-metrics/';
        const response = await fetch(`${url}?quick_filter=${quickFilter}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Update metrics
        updateMetrics(data.metrics);

        // Update charts
        updateChart('chart-tasks', data.rankings.by_tasks, 'tasks_completed', 'Tasks Concluídas');
        updateChart('chart-anotacoes', data.rankings.by_anotacoes, 'total_anotacoes', 'Total Anotações');
        updateChart('chart-produtividade', data.rankings.by_productivity, 'productivity', 'Produtividade');

        // Update active filter button
        updateActiveFilterButton(quickFilter);

    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showErrorState(error.message);
    }
}

/**
 * Update metric cards with data
 */
function updateMetrics(metrics) {
    const elements = {
        'metric-total-tasks': metrics.total_tasks,
        'metric-concluidas': metrics.total_concluidas,
        'metric-taxa': `${metrics.taxa_conclusao}%`,
        'metric-tempo': `${metrics.tempo_medio_dias} dias`,
        'metric-anotacoes': metrics.total_anotacoes.toLocaleString('pt-BR')
    };

    Object.entries(elements).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });
}

/**
 * Show loading state in dashboard
 */
function showLoadingState() {
    const metricIds = ['metric-total-tasks', 'metric-concluidas', 'metric-taxa', 'metric-tempo', 'metric-anotacoes'];
    metricIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<span class="text-slate-500"><i class="fas fa-spinner fa-spin"></i></span>';
    });
}

/**
 * Show error state in dashboard
 */
function showErrorState(message) {
    const metricIds = ['metric-total-tasks', 'metric-concluidas', 'metric-taxa', 'metric-tempo', 'metric-anotacoes'];
    metricIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<span class="text-red-400" title="' + message + '">Erro</span>';
    });
}

/**
 * Update active filter button styling
 */
function updateActiveFilterButton(quickFilter) {
    document.querySelectorAll('[id^="filter-"]').forEach(btn => {
        btn.classList.remove('bg-blue-600', 'text-white');
        btn.classList.add('bg-slate-700', 'hover:bg-slate-600');
    });

    const activeBtn = document.getElementById('filter-' + quickFilter);
    if (activeBtn) {
        activeBtn.classList.remove('bg-slate-700', 'hover:bg-slate-600');
        activeBtn.classList.add('bg-blue-600', 'text-white');
    }
}

/**
 * Update or create chart
 */
function updateChart(canvasId, data, valueKey, label) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    // Destroy existing chart
    if (chartsInstances[canvasId]) {
        chartsInstances[canvasId].destroy();
    }

    // Prepare data
    const labels = data.map(item => item.assignee || item.username || 'Unknown');
    const values = data.map(item => item[valueKey]);

    // Create new chart
    chartsInstances[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                backgroundColor: 'rgba(59, 130, 246, 0.5)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 11 }
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 11 }
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// ==================== FILTERS ====================

/**
 * Debounce function for search input
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Handle search input with debounce
 */
const handleSearchInput = debounce(function(event) {
    // Auto-submit form after user stops typing
    const form = event.target.closest('form');
    if (form) {
        form.submit();
    }
}, 500);

/**
 * Remove individual filter
 */
function removeFilter(filterName) {
    const url = new URL(window.location.href);
    url.searchParams.delete(filterName);
    window.location.href = url.toString();
}

/**
 * Clear all filters
 */
function clearAllFilters() {
    const url = new URL(window.location.href);
    const view = url.searchParams.get('view') || 'list';
    window.location.href = `?view=${view}`;
}

// ==================== SORTING ====================

/**
 * Handle column sorting
 */
function sortTable(column) {
    const url = new URL(window.location.href);
    const currentSort = url.searchParams.get('sort');
    const currentOrder = url.searchParams.get('order') || 'asc';

    // Toggle order if clicking same column
    let newOrder = 'asc';
    if (currentSort === column) {
        newOrder = currentOrder === 'asc' ? 'desc' : 'asc';
    }

    url.searchParams.set('sort', column);
    url.searchParams.set('order', newOrder);

    window.location.href = url.toString();
}

/**
 * Get sort icon for column
 */
function getSortIcon(column) {
    const url = new URL(window.location.href);
    const currentSort = url.searchParams.get('sort');
    const currentOrder = url.searchParams.get('order') || 'asc';

    if (currentSort !== column) {
        return '<i class="fas fa-sort text-slate-500 ml-1"></i>';
    }

    const icon = currentOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
    return `<i class="fas ${icon} text-blue-400 ml-1"></i>`;
}

// ==================== GROUPED VIEW ====================

/**
 * Toggle group visibility
 */
function toggleGroup(statusValue) {
    const content = document.getElementById('group-content-' + statusValue);
    const chevron = document.getElementById('chevron-' + statusValue);

    if (!content || !chevron) return;

    const isHidden = content.style.display === 'none';

    if (isHidden) {
        content.style.display = 'block';
        chevron.style.transform = 'rotate(0deg)';
        localStorage.setItem('cvat_group_' + statusValue, 'open');
    } else {
        content.style.display = 'none';
        chevron.style.transform = 'rotate(-90deg)';
        localStorage.setItem('cvat_group_' + statusValue, 'closed');
    }
}

/**
 * Restore group states from localStorage
 */
function restoreGroupStates() {
    const groups = document.querySelectorAll('[data-status]');
    groups.forEach(group => {
        const statusValue = group.getAttribute('data-status');
        const savedState = localStorage.getItem('cvat_group_' + statusValue);

        if (savedState === 'closed') {
            toggleGroup(statusValue);
        }
    });
}

// ==================== INFINITE SCROLL ====================

let isLoadingMore = false;
let hasMoreTasks = true;
let currentPage = 1;

/**
 * Initialize infinite scroll for grouped view
 */
function initInfiniteScroll() {
    if (!document.querySelector('.grouped-view-container')) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !isLoadingMore && hasMoreTasks) {
                loadMoreTasks();
            }
        });
    }, {
        rootMargin: '200px'
    });

    const sentinel = document.getElementById('scroll-sentinel');
    if (sentinel) {
        observer.observe(sentinel);
    }
}

/**
 * Load more tasks for grouped view
 */
async function loadMoreTasks() {
    isLoadingMore = true;
    currentPage++;

    const url = new URL(window.location.href);
    url.searchParams.set('page', currentPage);
    url.searchParams.set('ajax', '1');

    try {
        const response = await fetch(url.toString());
        if (!response.ok) throw new Error('Failed to load more tasks');

        const data = await response.json();

        if (data.html) {
            // Append new tasks to respective groups
            appendTasksToGroups(data.html);
        }

        hasMoreTasks = data.has_more;

    } catch (error) {
        console.error('Error loading more tasks:', error);
    } finally {
        isLoadingMore = false;
    }
}

/**
 * Append tasks HTML to groups
 */
function appendTasksToGroups(html) {
    // Parse HTML and append to each status group
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Implementation depends on backend response format
    // This is a placeholder for the actual implementation
}

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', function() {

    // Dashboard: Load data if in dashboard view
    if (document.getElementById('dashboard-view')) {
        loadDashboardData(currentQuickFilter);
    }

    // Grouped view: Restore group collapse states
    if (document.querySelector('.grouped-view-container')) {
        restoreGroupStates();
        // initInfiniteScroll(); // Uncomment when backend supports AJAX pagination
    }

    // Search: Add debounce to search input
    const searchInput = document.querySelector('input[name="search"]');
    if (searchInput) {
        // Removed auto-submit for now - user must click filter button
        // searchInput.addEventListener('input', handleSearchInput);
    }

    // Add sort icons to sortable headers
    document.querySelectorAll('th[data-sortable]').forEach(th => {
        const column = th.getAttribute('data-sortable');
        th.innerHTML += getSortIcon(column);
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => sortTable(column));
    });
});

// Export functions for global access
window.loadDashboardData = loadDashboardData;
window.toggleGroup = toggleGroup;
window.sortTable = sortTable;
window.removeFilter = removeFilter;
window.clearAllFilters = clearAllFilters;
