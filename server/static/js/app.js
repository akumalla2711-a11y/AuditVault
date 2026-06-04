/**
 * AuditVault V2.2 — Frontend Application Logic
 * Implements Command Center layout, Vertical Timeline, and Health Cards.
 */

document.addEventListener('DOMContentLoaded', () => {
    
    // --- State ---
    let currentTimelinePage = 1;
    const TIMELINE_LIMIT = 50;
    
    // --- Navigation ---
    const navItems = document.querySelectorAll('.nav-item[data-target]');
    const sections = document.querySelectorAll('.content-section');
    const pageTitle = document.getElementById('current-page-title');
    const pageSubtitle = document.getElementById('current-page-subtitle');
    
    function switchTab(targetId, title, subtitle) {
        navItems.forEach(nav => nav.classList.remove('active'));
        const activeNav = document.querySelector(`.nav-item[data-target="${targetId}"]`);
        if(activeNav) activeNav.classList.add('active');
        
        sections.forEach(sec => sec.classList.remove('active'));
        document.getElementById(targetId).classList.add('active');
        
        pageTitle.textContent = title;
        pageSubtitle.textContent = subtitle;
    }

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetId = item.getAttribute('data-target');
            let title = item.textContent.replace(/[^a-zA-Z\s]/g, '').trim();
            let subtitle = "";
            if (targetId === 'view-overview') subtitle = "Global threat and health overview";
            else if (targetId === 'view-timeline') subtitle = "Search and filter universal events";
            else if (targetId === 'view-alerts') subtitle = "Manage automated security alerts";
            else if (targetId === 'view-endpoints') subtitle = "View active and approved endpoints";
            else if (targetId === 'view-approvals') subtitle = "Review new endpoints requesting access";
            else if (targetId === 'view-endpoint-details') subtitle = "Detailed machine investigation";
            
            switchTab(targetId, title, subtitle);
            refreshData();
        });
    });

    // --- Investigation Tabs ---
    const invTabs = document.querySelectorAll('.inv-tab');
    const invContents = document.querySelectorAll('.inv-tab-content');
    invTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            invTabs.forEach(t => t.classList.remove('active'));
            invContents.forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.getAttribute('data-tab')).classList.add('active');
        });
    });

    // --- API Fetcher ---
    async function fetchAPI(endpoint, method = 'GET') {
        try {
            const res = await fetch(endpoint, { method });
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            return await res.json();
        } catch (error) {
            console.error("API Error:", error);
            return null;
        }
    }

    // --- Core Sync ---
    async function refreshData() {
        document.getElementById('last-refresh').textContent = "Syncing...";
        await Promise.all([
            loadStats(),
            loadEndpoints(),
            loadAlerts(),
            loadTimeline()
        ]);
        const now = new Date();
        document.getElementById('last-refresh').textContent = `Last sync: ${now.toLocaleTimeString()}`;
    }

    // --- Dashboard Loaders ---
    async function loadStats() {
        const stats = await fetchAPI('/api/stats');
        if (!stats) return;
        document.getElementById('kpi-endpoints').textContent = `${stats.online_endpoints} / ${stats.total_endpoints}`;
        document.getElementById('kpi-critical-alerts').textContent = stats.critical_alerts || 0;
        document.getElementById('kpi-warning-alerts').textContent = stats.warning_alerts || 0;
        document.getElementById('kpi-total-events').textContent = stats.total_events || 0;
    }

    async function loadEndpoints() {
        const endpoints = await fetchAPI('/api/endpoints');
        if (!endpoints) return;
        
        const tbodyEndpoints = document.getElementById('table-endpoints');
        const tbodyApprovals = document.getElementById('table-approvals');
        const tbodyRisk = document.getElementById('table-risk-endpoints');
        
        const searchInput = document.getElementById('endpoints-search').value.toLowerCase();
        const tagFilter = document.getElementById('endpoints-tag-filter').value;
        
        tbodyEndpoints.innerHTML = '';
        tbodyApprovals.innerHTML = '';
        tbodyRisk.innerHTML = '';
        
        let pendingCount = 0;
        let riskCount = 0;

        endpoints.forEach(ep => {
            if (ep.approval_state === 'Pending') {
                pendingCount++;
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${ep.hostname || 'Unknown'}</td>
                    <td><code style="font-size: 0.8em; color: var(--text-muted);">${ep.machine_guid}</code></td>
                    <td>${ep.ip_address}</td>
                    <td>${new Date(ep.first_seen).toLocaleString()}</td>
                    <td><button class="btn btn-primary btn-sm" onclick="approveEndpoint(${ep.id})">Approve</button></td>
                `;
                tbodyApprovals.appendChild(row);
            } 
            else if (ep.approval_state === 'Approved' || ep.approval_state === 'Active') {
                const statusBadge = ep.is_online ? 
                    '<span class="badge badge-success badge-pulse"><span class="badge-dot"></span>Online</span>' :
                    '<span class="badge badge-danger"><span class="badge-dot"></span>Offline</span>';
                
                const epTags = ep.tags || '';
                
                // Tag Filtering
                let show = true;
                if (searchInput && !(ep.hostname.toLowerCase().includes(searchInput) || ep.ip_address.includes(searchInput))) show = false;
                if (tagFilter) {
                    if (tagFilter === 'NONE' && epTags) show = false;
                    else if (tagFilter !== 'NONE' && !epTags.includes(tagFilter)) show = false;
                }
                
                if (show) {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${ep.hostname}</td>
                        <td>${ep.ip_address}</td>
                        <td>${ep.os_caption || 'Unknown'}</td>
                        <td><span class="badge badge-info">${epTags || 'NONE'}</span></td>
                        <td>${statusBadge}</td>
                        <td>${new Date(ep.last_seen).toLocaleString()}</td>
                        <td><button class="btn btn-ghost btn-sm" onclick="viewEndpoint(${ep.id})">View</button></td>
                    `;
                    tbodyEndpoints.appendChild(row);
                }
                
                if (riskCount < 5) {
                    const riskRow = document.createElement('tr');
                    riskRow.innerHTML = `<td>${ep.hostname}</td><td>${statusBadge}</td>`;
                    tbodyRisk.appendChild(riskRow);
                    riskCount++;
                }
            }
        });
        
        if (pendingCount === 0) tbodyApprovals.innerHTML = '<tr><td colspan="5" class="table-empty">No pending endpoints.</td></tr>';
        if (tbodyEndpoints.children.length === 0) tbodyEndpoints.innerHTML = '<tr><td colspan="7" class="table-empty">No matching endpoints found.</td></tr>';
        if (riskCount === 0) tbodyRisk.innerHTML = '<tr><td colspan="2" class="table-empty">No active endpoints.</td></tr>';
    }

    async function loadAlerts() {
        const alerts = await fetchAPI('/api/alerts');
        if (!alerts) return;
        
        const tbodyAlerts = document.getElementById('table-alerts');
        const summaryAlerts = document.getElementById('table-alert-summary');
        
        tbodyAlerts.innerHTML = '';
        summaryAlerts.innerHTML = '';
        
        const typeCounts = {};

        alerts.forEach(alert => {
            const isCritical = alert.severity === 'Critical';
            const badgeClass = isCritical ? 'badge-danger' : 'badge-warning';
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${new Date(alert.timestamp).toLocaleString()}</td>
                <td><span class="badge ${badgeClass}">${alert.severity}</span></td>
                <td>${alert.alert_type}</td>
                <td>${alert.hostname || 'Unknown'}</td>
                <td style="max-width:300px; white-space:normal;">${alert.description}</td>
                <td>${alert.status}</td>
                <td>
                    ${alert.status === 'Open' ? `<button class="btn btn-ghost btn-sm" style="margin-right:0.5rem;" onclick="acknowledgeAlert(${alert.alert_id})">Acknowledge</button>` : ''}
                    ${alert.status !== 'Resolved' ? `<button class="btn btn-primary btn-sm" onclick="resolveAlert(${alert.alert_id})">Resolve</button>` : ''}
                </td>
            `;
            tbodyAlerts.appendChild(tr);
            
            if(alert.status !== 'Resolved') {
                typeCounts[alert.alert_type] = (typeCounts[alert.alert_type] || 0) + 1;
            }
        });
        
        Object.keys(typeCounts).forEach(type => {
            summaryAlerts.innerHTML += `<tr><td>${type}</td><td><span class="badge badge-danger">${typeCounts[type]}</span></td></tr>`;
        });
        
        if (alerts.length === 0) tbodyAlerts.innerHTML = '<tr><td colspan="7" class="table-empty">No alerts found.</td></tr>';
        if (Object.keys(typeCounts).length === 0) summaryAlerts.innerHTML = '<tr><td colspan="2" class="table-empty">No open alerts.</td></tr>';
    }

    // --- Formatter ---
    function formatEventName(eventType) {
        const mappings = {
            'USB_INSERTED': '🔌 USB Inserted',
            'USB_REMOVED': '🔌 USB Removed',
            'LOGIN_FAILED': '❌ Login Failed',
            'LOGIN_SUCCESS': '✅ Login Success',
            'SOFTWARE_INSTALLED': '📦 Software Installed',
            'SOFTWARE_REMOVED': '🗑️ Software Removed',
            'SOFTWARE_UPDATED': '🔄 Software Updated',
            'DEFENDER_ENABLED': '🛡️ Defender Enabled',
            'DEFENDER_DISABLED': '⚠️ Defender Disabled',
            'REALTIME_PROTECTION_ENABLED': '🛡️ Realtime Protection Enabled',
            'REALTIME_PROTECTION_DISABLED': '⚠️ Realtime Protection Disabled'
        };
        return mappings[eventType] || eventType;
    }

    // --- Repetitive Event Grouping ---
    function groupEvents(events) {
        let grouped = [];
        events.forEach(ev => {
            if (grouped.length > 0) {
                let last = grouped[grouped.length - 1];
                // Group if same type, description, and endpoint
                if (last.event_type === ev.event_type && last.description === ev.description && last.endpoint_id === ev.endpoint_id) {
                    last.count = (last.count || 1) + 1;
                    // Keep the most recent timestamp (since descending order, ev is older, so last has the newest)
                    return;
                }
            }
            grouped.push({...ev, count: 1});
        });
        return grouped;
    }

    async function loadTimeline() {
        const eventsRaw = await fetchAPI(`/api/events?page=${currentTimelinePage}&limit=${TIMELINE_LIMIT}`);
        if (!eventsRaw) return;
        
        const events = groupEvents(eventsRaw);
        
        document.getElementById('timeline-page-indicator').textContent = `Page ${currentTimelinePage}`;
        
        const cardContainer = document.getElementById('timeline-cards-container');
        const overviewRecent = document.getElementById('overview-recent-events');
        const overviewTimeline = document.getElementById('overview-timeline-preview');
        
        cardContainer.innerHTML = '';
        if(currentTimelinePage === 1) {
            overviewRecent.innerHTML = '';
            overviewTimeline.innerHTML = '';
        }
        
        let recentCount = 0;

        events.forEach(ev => {
            let badgeClass = 'badge-info';
            let cardClass = '';
            if (ev.severity === 'Critical') { badgeClass = 'badge-danger'; cardClass = 'card-critical'; }
            if (ev.severity === 'Warning') { badgeClass = 'badge-warning'; cardClass = 'card-warning'; }
            
            let countBadge = ev.count > 1 ? `<span class="badge badge-warning" style="margin-left:0.5rem;">${ev.count}x</span>` : '';
            let displayEvent = formatEventName(ev.event_type);
            
            // Populate Explorer Cards
            const card = document.createElement('div');
            card.className = `event-card ${cardClass}`;
            card.innerHTML = `
                <div class="event-card-header">
                    <span style="font-weight:700; color:var(--text-primary);"><span class="badge ${badgeClass}">${ev.severity}</span> ${displayEvent} ${countBadge}</span>
                </div>
                <div class="event-card-body">${ev.description}</div>
                <div class="event-card-footer">
                    <span><span style="color:var(--text-secondary);">Endpoint:</span> ${ev.hostname || 'Unknown'}</span>
                    <span>${new Date(ev.timestamp).toLocaleString()}</span>
                </div>
            `;
            cardContainer.appendChild(card);
            
            // Populate Dashboard Widgets
            if (currentTimelinePage === 1) {
                if (recentCount < 5) {
                    const rec = document.createElement('div');
                    rec.style.cssText = 'padding: 0.75rem 0; border-bottom: 1px solid var(--border); font-size: 0.85rem;';
                    rec.innerHTML = `
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">
                            <span style="font-weight:600; color:var(--text-primary);">${displayEvent} ${countBadge}</span>
                            <span style="color:var(--text-muted);">${new Date(ev.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                        <div style="color:var(--text-secondary);">${ev.hostname || 'Unknown'}</div>
                    `;
                    overviewRecent.appendChild(rec);
                    recentCount++;
                }
                
                // Timeline Preview
                const pCard = document.createElement('div');
                pCard.className = `event-card ${cardClass}`;
                pCard.style.cssText = 'min-width: 250px; flex-shrink: 0; margin-bottom: 0;';
                pCard.innerHTML = `
                    <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:0.25rem;">${new Date(ev.timestamp).toLocaleTimeString()}</div>
                    <div style="font-weight:600; font-size:0.85rem; margin-bottom:0.25rem; color:var(--text-primary);">${displayEvent} ${countBadge}</div>
                    <div style="font-size:0.8rem; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${ev.hostname}</div>
                `;
                overviewTimeline.appendChild(pCard);
            }
        });
        
        if (events.length === 0) {
            cardContainer.innerHTML = '<div class="table-empty">No events recorded.</div>';
            if(currentTimelinePage === 1) {
                overviewRecent.innerHTML = '<div class="table-empty">No recent events.</div>';
                overviewTimeline.innerHTML = '<div class="table-empty">No timeline data.</div>';
            }
        }
    }

    // --- Timeline Pagination Controls ---
    document.getElementById('btn-timeline-prev').addEventListener('click', () => {
        if (currentTimelinePage > 1) {
            currentTimelinePage--;
            loadTimeline();
        }
    });
    
    document.getElementById('btn-timeline-next').addEventListener('click', () => {
        currentTimelinePage++;
        loadTimeline();
    });

    document.getElementById('endpoints-search').addEventListener('input', loadEndpoints);
    document.getElementById('endpoints-tag-filter').addEventListener('change', loadEndpoints);


    // --- Endpoint Investigation Page Logic ---
    window.viewEndpoint = async (id) => {
        switchTab('view-endpoint-details', 'Endpoint Investigation', 'Command Center forensic details');
        
        const [summary, softwareRaw, usb, timelineRaw, alerts, defender] = await Promise.all([
            fetchAPI(`/api/endpoints/${id}`),
            fetchAPI(`/api/endpoints/${id}/software`),
            fetchAPI(`/api/endpoints/${id}/usb`),
            fetchAPI(`/api/endpoints/${id}/timeline?page=1&limit=100`),
            fetchAPI(`/api/endpoints/${id}/alerts`),
            fetchAPI(`/api/endpoints/${id}/defender`)
        ]);
        
        if (!summary) return;
        
        // Group timeline
        const timeline = groupEvents(timelineRaw || []);
        
        // 1. Hero & Overview
        document.getElementById('inv-hostname').textContent = summary.hostname || 'Unknown';
        document.getElementById('inv-guid').textContent = summary.machine_guid || 'N/A';
        document.getElementById('inv-os').textContent = summary.os_caption || 'N/A';
        document.getElementById('inv-ip').textContent = summary.ip_address || 'N/A';
        
        document.getElementById('inv-agent-version').textContent = summary.agent_version || 'Unknown';
        document.getElementById('inv-total-events').textContent = summary.total_events ? summary.total_events.toLocaleString() : '0';
        document.getElementById('inv-total-alerts').textContent = alerts.length.toLocaleString();
        
        const lastSeenMs = new Date(summary.last_seen).getTime();
        const diffMins = Math.floor((Date.now() - lastSeenMs) / 60000);
        let relTime = diffMins < 1 ? 'Just now' : (diffMins < 60 ? `${diffMins} min ago` : (diffMins < 1440 ? `${Math.floor(diffMins/60)} hr ago` : `${Math.floor(diffMins/1440)} days ago`));
        document.getElementById('inv-lastseen').textContent = relTime;
        
        document.getElementById('inv-open-alerts').textContent = summary.open_alerts;
        
        document.getElementById('inv-status').innerHTML = summary.is_online ? 
            '<span class="badge badge-success badge-pulse"><span class="badge-dot"></span>Online</span>' :
            '<span class="badge badge-danger"><span class="badge-dot"></span>Offline</span>';
            
        // 2. Health Cards Calculations
        let authSuccess = 0, authFailed = 0;
        let failedLogins24h = 0;
        let usbUsed24h = new Set();
        let softwareChanges24h = 0;
        const nowMs = Date.now();
        
        timelineRaw.forEach(ev => {
            const isRecent = (nowMs - new Date(ev.timestamp).getTime() < 86400000);
            
            if (ev.event_type.includes('LOGON') || ev.event_type === 'LOGIN_SUCCESS') authSuccess++;
            if (ev.event_type.includes('FAILED_LOGIN') || ev.event_type === 'LOGIN_FAILED') authFailed++;
            
            if (isRecent) {
                if (ev.event_type === 'LOGIN_FAILED' || ev.event_type === 'FAILED_LOGIN') failedLogins24h++;
                if (ev.event_type === 'USB_INSERTED') usbUsed24h.add(ev.description);
                if (ev.event_type.startsWith('SOFTWARE_')) softwareChanges24h++;
            }
        });
        
        document.getElementById('inv-24h-failed-logins').textContent = failedLogins24h;
        document.getElementById('inv-24h-usb').textContent = usbUsed24h.size;
        document.getElementById('inv-24h-software').textContent = softwareChanges24h;
        document.getElementById('inv-24h-alerts').textContent = summary.open_alerts;
        document.getElementById('inv-auth-success').textContent = authSuccess;
        document.getElementById('inv-auth-failed').textContent = authFailed;
        document.getElementById('inv-usb-known').textContent = usb.length;
        
        const defStateEl = document.getElementById('inv-defender-state');
        if (defender && defender.enabled) {
            defStateEl.innerHTML = `<span style="color: var(--success);">Enabled</span>`;
            document.getElementById('inv-defender-threats').textContent = defender.threat_count || 0;
        } else {
            defStateEl.innerHTML = `<span style="color: var(--danger);">Disabled</span>`;
            document.getElementById('inv-defender-threats').textContent = '-';
        }
        
        // 3. Recent Security Activity (Storytelling)
        const recentAct = document.getElementById('inv-recent-activity');
        recentAct.innerHTML = '';
        
        let allActivity = [];
        timelineRaw.forEach(ev => allActivity.push({
            type: 'event',
            timestamp: new Date(ev.timestamp).getTime(),
            timeStr: ev.timestamp,
            title: formatEventName(ev.event_type),
            severity: ev.severity
        }));
        alerts.forEach(al => allActivity.push({
            type: 'alert',
            timestamp: new Date(al.timestamp).getTime(),
            timeStr: al.timestamp,
            title: `${al.alert_type} Alert`,
            severity: al.severity
        }));
        
        allActivity.sort((a, b) => b.timestamp - a.timestamp); // newest first
        let top10 = allActivity.slice(0, 10);
        top10.sort((a, b) => a.timestamp - b.timestamp); // chronologically (oldest to newest for reading)
        
        top10.forEach(act => {
            let color = 'var(--text-primary)';
            if (act.severity === 'Critical') color = 'var(--danger)';
            if (act.severity === 'Warning') color = 'var(--warning)';
            
            recentAct.innerHTML += `
                <div style="display: flex; gap: 1rem; align-items: baseline; font-size: 0.85rem;">
                    <span style="color: var(--text-muted); font-family: monospace; white-space: nowrap;">${new Date(act.timeStr).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span style="color: ${color}; font-weight: ${act.type === 'alert' ? 'bold' : 'normal'};">${act.title}</span>
                </div>
            `;
        });
        
        if(top10.length === 0) recentAct.innerHTML = '<div class="table-empty">No security activity.</div>';
        
        // 4. Inventory Tabs (Software & USB)
        const tbSw = document.getElementById('inv-table-software');
        tbSw.innerHTML = '';
        softwareRaw.forEach(sw => {
            tbSw.innerHTML += `<tr><td>${sw.name}</td><td>${sw.version}</td></tr>`;
        });
        if(softwareRaw.length === 0) tbSw.innerHTML = '<tr><td colspan="2" class="table-empty">No software.</td></tr>';
        
        const tbUsb = document.getElementById('inv-table-usb');
        tbUsb.innerHTML = '';
        usb.forEach(u => {
            let sText = u.status === 'Currently Connected' ? 'Connected' : u.status;
            let sStyle = sText === 'Connected' ? 'color: var(--success); font-weight: 500;' : 'color: var(--text-muted);';
            let dOpts = { month: 'short', day: 'numeric' };
            
            tbUsb.innerHTML += `<tr>
                <td>${u.device_name}</td>
                <td style="${sStyle}">${sText}</td>
                <td>${new Date(u.first_seen).toLocaleDateString(undefined, dOpts)}</td>
                <td>${new Date(u.last_seen).toLocaleDateString(undefined, dOpts)}</td>
            </tr>`;
        });
        if(usb.length === 0) tbUsb.innerHTML = '<tr><td colspan="4" class="table-empty">No USB history.</td></tr>';
        
        // 4. Alerts Tab
        const tbAlerts = document.getElementById('inv-table-alerts');
        tbAlerts.innerHTML = '';
        alerts.forEach(a => {
            let bClass = a.severity === 'Critical' ? 'badge-danger' : 'badge-warning';
            let actions = `
                ${a.status === 'Open' ? `<button class="btn btn-ghost btn-sm" style="margin-right:0.5rem;" onclick="acknowledgeAlert(${a.alert_id})">Acknowledge</button>` : ''}
                ${a.status !== 'Resolved' ? `<button class="btn btn-primary btn-sm" onclick="resolveAlert(${a.alert_id})">Resolve</button>` : ''}
            `;
            tbAlerts.innerHTML += `<tr><td>${new Date(a.timestamp).toLocaleString()}</td><td><span class="badge ${bClass}">${a.severity}</span></td><td>${a.alert_type}</td><td>${a.description}</td><td>${a.status}</td><td>${actions}</td></tr>`;
        });
        if(alerts.length === 0) tbAlerts.innerHTML = '<tr><td colspan="6" class="table-empty">No alerts.</td></tr>';
        
        // 5. Vertical Timeline Tab
        const vTime = document.getElementById('inv-vertical-timeline');
        vTime.innerHTML = '';
        timeline.forEach(ev => {
            let dotClass = '';
            if (ev.severity === 'Critical') dotClass = 'dot-critical';
            if (ev.severity === 'Warning') dotClass = 'dot-warning';
            
            let countBadge = ev.count > 1 ? `<span class="badge badge-warning" style="margin-left:0.5rem; font-size: 0.7rem;">${ev.count}x</span>` : '';
            let displayEvent = formatEventName(ev.event_type);
            
            const tItem = document.createElement('div');
            tItem.className = 'timeline-item';
            tItem.innerHTML = `
                <div class="timeline-dot ${dotClass}"></div>
                <div class="timeline-content">
                    <div class="timeline-time">${new Date(ev.timestamp).toLocaleString()}</div>
                    <div class="timeline-title">${displayEvent} ${countBadge}</div>
                    <div class="timeline-desc">${ev.description}</div>
                </div>
            `;
            vTime.appendChild(tItem);
        });
        if(timeline.length === 0) vTime.innerHTML = '<div style="color:var(--text-muted); padding:1rem;">No events recorded.</div>';
    };


    // --- Global Actions ---
    window.approveEndpoint = async (id) => {
        await fetchAPI(`/api/endpoints/${id}/approve`, 'POST');
        refreshData();
    };
    window.acknowledgeAlert = async (id) => {
        await fetchAPI(`/api/alerts/${id}/acknowledge`, 'POST');
        refreshData();
    };
    window.resolveAlert = async (id) => {
        await fetchAPI(`/api/alerts/${id}/resolve`, 'POST');
        refreshData();
    };

    document.getElementById('btn-refresh').addEventListener('click', refreshData);
    
    // Initial Load
    refreshData();
    setInterval(refreshData, 15000);
});
