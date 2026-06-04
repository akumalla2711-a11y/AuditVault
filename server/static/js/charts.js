/* AuditVault — Chart.js Visualizations */

window.AuditCharts = (function() {
    // Chart instances
    let timelineChart = null;
    let publishersChart = null;
    let loginsChart = null;
    
    // Theme configuration
    const theme = {
        primary: '#6366f1',
        primaryGlow: 'rgba(99, 102, 241, 0.2)',
        accent: '#22d3ee',
        accentGlow: 'rgba(34, 211, 238, 0.2)',
        danger: '#ef4444',
        warning: '#f59e0b',
        success: '#10b981',
        text: '#94a3b8',
        grid: 'rgba(255, 255, 255, 0.05)'
    };
    
    // Global defaults
    Chart.defaults.color = theme.text;
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.9)';
    Chart.defaults.plugins.tooltip.titleColor = '#f1f5f9';
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.1)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;

    function initOrUpdateTimeline(data) {
        const ctx = document.getElementById('timelineChart');
        if (!ctx) return;
        
        // Data format from API: [{date: '2023-10-01', count: 5}, ...]
        // We need to reverse it so oldest is first (left to right)
        const sortedData = [...data].reverse();
        
        const labels = sortedData.map(d => {
            const date = new Date(d.date);
            return `${date.getMonth()+1}/${date.getDate()}`;
        });
        const counts = sortedData.map(d => d.count);
        
        if (timelineChart) {
            timelineChart.data.labels = labels;
            timelineChart.data.datasets[0].data = counts;
            timelineChart.update();
            return;
        }
        
        timelineChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Audits Received',
                    data: counts,
                    borderColor: theme.accent,
                    backgroundColor: theme.accentGlow,
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointBackgroundColor: theme.accent,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { 
                        beginAtZero: true,
                        grid: { color: theme.grid },
                        border: { display: false }
                    }
                }
            }
        });
    }

    function initOrUpdatePublishers(data) {
        const ctx = document.getElementById('publishersChart');
        if (!ctx) return;
        
        const labels = data.map(d => {
            // Truncate long publisher names
            return d.publisher.length > 20 ? d.publisher.substring(0, 20) + '...' : d.publisher;
        });
        const counts = data.map(d => d.count);
        
        if (publishersChart) {
            publishersChart.data.labels = labels;
            publishersChart.data.datasets[0].data = counts;
            publishersChart.update();
            return;
        }
        
        publishersChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Software Count',
                    data: counts,
                    backgroundColor: theme.primary,
                    borderRadius: 4,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y', // Horizontal bar chart
                plugins: { legend: { display: false } },
                scales: {
                    x: { 
                        beginAtZero: true,
                        grid: { color: theme.grid },
                        border: { display: false }
                    },
                    y: { grid: { display: false } }
                }
            }
        });
    }

    function initOrUpdateLogins(data) {
        const ctx = document.getElementById('loginsChart');
        if (!ctx) return;
        
        // Process data
        let failed = 0;
        let explicit = 0;
        let success = 0;
        
        data.forEach(d => {
            if (d.event_id === 4625) failed += d.count;
            else if (d.event_id === 4648) explicit += d.count;
            else if (d.event_id === 4624) success += d.count;
            else success += d.count; // Default bucket
        });
        
        const chartData = [failed, explicit, success];
        const labels = ['Failed (4625)', 'Explicit Creds (4648)', 'Success (4624)'];
        const colors = [theme.danger, theme.warning, theme.success];
        
        if (loginsChart) {
            loginsChart.data.datasets[0].data = chartData;
            loginsChart.update();
            return;
        }
        
        loginsChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: chartData,
                    backgroundColor: colors,
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { padding: 20, usePointStyle: true, color: theme.text }
                    }
                }
            }
        });
    }

    // Public API
    return {
        update: function(statsData) {
            if (statsData.audits_by_day) initOrUpdateTimeline(statsData.audits_by_day);
            if (statsData.top_publishers) initOrUpdatePublishers(statsData.top_publishers);
            if (statsData.login_by_type) initOrUpdateLogins(statsData.login_by_type);
        }
    };
})();
