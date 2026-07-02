/* ---------------- IMAGE ANALYSIS ---------------- */

function previewImage() {
    const file = document.getElementById("imageInput").files[0];
    if (file) {
        document.getElementById("originalImage").src = URL.createObjectURL(file);
        const label = document.querySelector(".custom-file-upload span");
        if(label){
            label.innerText = file.name;
        }
    }
}

function uploadImage() {
    const fileInput = document.getElementById("imageInput");
    const file = fileInput.files[0];
    if (!file) {
        alert("Please select an image first");
        return;
    }

    const btn = document.querySelector(".btn-primary");
    const originalText = btn.innerText;
    btn.innerText = "Analyzing...";
    btn.disabled = true;

    const formData = new FormData();
    formData.append("image", file);

    fetch("/detect-image", {
        method: "POST",
        body: formData
    })
    .then(res => {
        if (!res.ok) throw new Error("Detection failed");
        return res.json();
    })
    .then(data => {
        const resultImage = document.getElementById("resultImage");
        resultImage.src = data.image;

        // Update diagnostics HUD cards
        document.getElementById("imgValState").innerText = data.state;
        document.getElementById("imgValEyes").innerText = data.eyes_found;
        document.getElementById("imgValTilt").innerText = data.head_tilt + "°";
        document.getElementById("imgValLeftEar").innerText = Number(data.left_ear).toFixed(2);
        document.getElementById("imgValRightEar").innerText = Number(data.right_ear).toFixed(2);

        // Update dynamic gauge progress bar lengths
        const fillLeft = document.getElementById("fillLeftEar");
        const fillRight = document.getElementById("fillRightEar");
        
        if (fillLeft) fillLeft.style.width = Math.min((data.left_ear / 0.40) * 100, 100) + "%";
        if (fillRight) fillRight.style.width = Math.min((data.right_ear / 0.40) * 100, 100) + "%";

        // Update insight card styles based on drowsiness state
        const statusCard = document.getElementById("imgStatusCard");
        if (statusCard) {
            if (data.state === "CLOSED") {
                statusCard.className = "bi-kpi-card bi-danger-kpi";
            } else {
                statusCard.className = "bi-kpi-card bi-success-kpi";
            }
        }

        const feedbackText = document.getElementById("diagnosticFeedback");
        if (feedbackText) {
            if (data.eyes_found === 0) {
                feedbackText.innerText = "No eyes detected in the image. Please ensure your face is fully visible, well-lit, and look directly at the camera.";
            } else if (data.state === "CLOSED") {
                feedbackText.innerText = `Eyelid closure detected! Eyelid Aperture (EAR) of ${data.ear} is below threshold. Head roll is at ${data.head_tilt}°. This indicates potential driver drowsiness.`;
            } else {
                feedbackText.innerText = `Attentive eye state detected! Eyelid Aperture (EAR) of ${data.ear} is healthy. Head posture is stable at ${data.head_tilt}° roll. No symptoms of drowsiness detected.`;
            }
        }
    })
    .catch(err => {
        alert(err.message);
    })
    .finally(() => {
        btn.innerText = originalText;
        btn.disabled = false;
    });
}


/* ---------------- LIVE MODE ---------------- */

let isLiveRunning = false;

function toggleLive() {
    if (!isLiveRunning) {
        startLive();
    } else {
        stopLive();
    }
}

function startLive() {
    const streamImg = document.getElementById("liveStream");
    const noFeed = document.getElementById("noFeed");
    const btn = document.getElementById("liveToggleBtn");

    streamImg.src = "/detect-live";
    if(noFeed){
        noFeed.classList.add("hidden");
    }

    btn.innerText = "Stop Vision Feed";
    btn.style.background = "#ef4444";
    isLiveRunning = true;
}

function stopLive() {
    const streamImg = document.getElementById("liveStream");
    const noFeed = document.getElementById("noFeed");
    const btn = document.getElementById("liveToggleBtn");

    streamImg.src = "";
    if(noFeed){
        noFeed.classList.remove("hidden");
    }

    fetch("/stop-live").catch(()=>{});
    if(btn){
        btn.innerText = "Start Intelligence Feed";
        btn.style.background = "var(--primary)";
    }
    isLiveRunning = false;
}


/* ---------------- DRIVING MODE ---------------- */

let isDrivingRunning = false;
let pollingInterval = null;
let alertAudio = null;

function toggleDriving() {
    if (!isDrivingRunning) {
        startDriving();
    } else {
        stopDriving();
    }
}

function startDriving() {
    const streamImg = document.getElementById("drivingStream");
    const status = document.getElementById("drivingStatus");
    const btn = document.getElementById("drivingToggleBtn");

    streamImg.src = "/detect-drowsy";
    if(status){
        status.classList.add("hidden");
    }

    btn.innerText = "Stop Driving Mode";
    btn.style.background = "#ef4444";
    isDrivingRunning = true;

    // Start background polling for audio alerts
    startPolling();
}

function stopDriving() {
    const streamImg = document.getElementById("drivingStream");
    const status = document.getElementById("drivingStatus");
    const btn = document.getElementById("drivingToggleBtn");

    streamImg.src = "";
    if(status){
        status.classList.remove("hidden");
    }

    fetch("/stop-live").catch(()=>{});
    btn.innerText = "Start Monitoring";
    btn.style.background = "var(--primary)";
    isDrivingRunning = false;

    // Stop background polling and clear audio
    stopPolling();
}

function startPolling() {
    alertAudio = document.getElementById('alertAudio');

    pollingInterval = setInterval(() => {
        fetch('/api/live-stats')
            .then(res => res.json())
            .then(data => {
                updateDashboard(data);
            })
            .catch(err => console.error("Error fetching live stats:", err));
    }, 500);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }

    if (alertAudio) {
        alertAudio.pause();
        alertAudio.currentTime = 0;
    }

    const videoWrapper = document.getElementById("videoWrapper");
    const alarmOverlay = document.getElementById("alarmOverlay");

    if (videoWrapper) videoWrapper.classList.remove("drowsy-active");
    if (alarmOverlay) alarmOverlay.classList.add("hidden");
}

function updateDashboard(data) {
    if (!data) return;

    const videoWrapper = document.getElementById("videoWrapper");
    const alarmOverlay = document.getElementById("alarmOverlay");

    // Audio & HUD Warning trigger
    if (data.drowsy) {
        if (alertAudio && alertAudio.paused) {
            alertAudio.play().catch(e => console.warn("Browser blocked auto-playback of sound until user interaction."));
        }
        if (videoWrapper) videoWrapper.classList.add("drowsy-active");
        if (alarmOverlay) alarmOverlay.classList.remove("hidden");
    } else {
        if (alertAudio && !alertAudio.paused) {
            alertAudio.pause();
            alertAudio.currentTime = 0;
        }
        if (videoWrapper) videoWrapper.classList.remove("drowsy-active");
        if (alarmOverlay) alarmOverlay.classList.add("hidden");
    }
}


/* ---------------- HISTORICAL ANALYTICS (POWER BI DESIGN) ---------------- */

let allSessionsData = [];
let activePeriodFilter = 'all';

function loadHistory() {
    const tableBody = document.getElementById("historyTableBody");
    if (!tableBody) return;

    fetch('/api/history')
        .then(res => res.json())
        .then(sessions => {
            allSessionsData = sessions;
            applyPeriodFilter();
        })
        .catch(err => {
            console.error("Error loading session history:", err);
            tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 2rem;">Error fetching history log from server.</td></tr>`;
        });
}

function changePeriodFilter(period) {
    activePeriodFilter = period;
    
    // Update active filter button states
    const btnAll = document.getElementById("btnFilterAll");
    const btn7d = document.getElementById("btnFilter7d");
    const btn24h = document.getElementById("btnFilter24h");
    
    if (btnAll) btnAll.classList.remove("active");
    if (btn7d) btn7d.classList.remove("active");
    if (btn24h) btn24h.classList.remove("active");
    
    if (period === 'all' && btnAll) btnAll.classList.add("active");
    if (period === '7days' && btn7d) btn7d.classList.add("active");
    if (period === '24hours' && btn24h) btn24h.classList.add("active");
    
    applyPeriodFilter();
}

function applyPeriodFilter() {
    if (!allSessionsData) return;
    
    let filteredSessions = [...allSessionsData];
    const now = new Date();
    
    if (activePeriodFilter === '7days') {
        const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        filteredSessions = allSessionsData.filter(s => new Date(s.session_start) >= sevenDaysAgo);
    } else if (activePeriodFilter === '24hours') {
        const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        filteredSessions = allSessionsData.filter(s => new Date(s.session_start) >= oneDayAgo);
    }
    
    renderHistoryDashboard(filteredSessions);
}

function renderHistoryDashboard(sessions) {
    const tableBody = document.getElementById("historyTableBody");
    if (!tableBody) return;

    if (!sessions || sessions.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">No sessions logged for this filter. Try Driving Mode!</td></tr>`;
        updateKPIs([]);
        renderAnalyticsCharts([]);
        return;
    }

    // Render table rows
    let html = "";
    sessions.forEach((session, idx) => {
        const dateObj = new Date(session.session_start);
        const dateStr = isNaN(dateObj.getTime()) ? "Unknown Date" : dateObj.toLocaleString();
        
        const durationSec = session.duration_seconds || 0;
        const mins = Math.floor(durationSec / 60);
        const secs = Math.round(durationSec % 60);
        const durationStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

        const drowsyEvs = session.drowsy_events || 0;
        const statusBadge = drowsyEvs > 0 
            ? `<span class="badge badge-danger">Alerted (${drowsyEvs})</span>` 
            : `<span class="badge badge-success">Attentive</span>`;

        html += `
            <tr class="clickable-row" onclick="openSessionModal(${idx}, this)" title="Click to view details">
                <td>${dateStr}</td>
                <td>${durationStr}</td>
                <td>${session.total_blinks || 0}</td>
                <td>${drowsyEvs}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    });
    tableBody.innerHTML = html;

    // Update aggregate KPIs
    updateKPIs(sessions);

    // Build trend charts
    renderAnalyticsCharts(sessions);
}

function updateKPIs(sessions) {
    const totalSessionsVal = document.getElementById("totalSessions");
    const totalDurationVal = document.getElementById("totalDuration");
    const totalBlinksVal = document.getElementById("totalBlinks");
    const totalDrowsyVal = document.getElementById("totalDrowsy");

    if (!totalSessionsVal) return;

    const totalSessions = sessions.length;
    let totalSecs = 0;
    let totalBlinks = 0;
    let totalDrowsy = 0;

    sessions.forEach(s => {
        totalSecs += s.duration_seconds || 0;
        totalBlinks += s.total_blinks || 0;
        totalDrowsy += s.drowsy_events || 0;
    });

    const totalMins = Math.round(totalSecs / 60);

    totalSessionsVal.innerText = totalSessions;
    totalDurationVal.innerText = totalMins + " min";
    totalBlinksVal.innerText = totalBlinks;
    totalDrowsyVal.innerText = totalDrowsy;
}

let historyChart1 = null;
let historyChart2 = null;

function renderAnalyticsCharts(sessions) {
    const chart1Ctx = document.getElementById("sessionComparisonChart");
    const chart2Ctx = document.getElementById("alertnessTrendChart");
    if (!chart1Ctx || !chart2Ctx) return;

    if (historyChart1) historyChart1.destroy();
    if (historyChart2) historyChart2.destroy();

    if (sessions.length === 0) return;

    // Last 10 sessions, sorted chronological (oldest first for line graph)
    const sortedSessions = [...sessions].reverse().slice(-10);

    const labels = sortedSessions.map((s, idx) => {
        const d = new Date(s.session_start);
        return isNaN(d.getTime()) ? `S#${idx+1}` : `${d.getMonth() + 1}/${d.getDate()} #${idx + 1}`;
    });

    const blinksData = sortedSessions.map(s => s.total_blinks || 0);
    const drowsyData = sortedSessions.map(s => s.drowsy_events || 0);
    
    // Alerts/Minutes ratio
    const drowsinessDensity = sortedSessions.map(s => {
        const mins = (s.duration_seconds || 1) / 60;
        return Number((s.drowsy_events / mins).toFixed(2));
    });

    // Chart 1: Bar chart comparing blinks and drowsy events
    historyChart1 = new Chart(chart1Ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Total Blinks',
                    data: blinksData,
                    backgroundColor: '#6366f1',
                    borderRadius: 4
                },
                {
                    label: 'Drowsy Alerts',
                    data: drowsyData,
                    backgroundColor: '#ef4444',
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: {
                legend: { labels: { color: '#f8fafc' } }
            }
        }
    });

    // Chart 2: Alert Frequency per minute
    historyChart2 = new Chart(chart2Ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Drowsiness Frequency (Alerts/Min)',
                data: drowsinessDensity,
                borderColor: '#10b981',
                borderWidth: 2.5,
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { min: 0, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: {
                legend: { labels: { color: '#f8fafc' } }
            }
        }
    });
}

// export data to CSV file (PowerBI requirement)
function exportToCSV() {
    if (!allSessionsData || allSessionsData.length === 0) {
        alert("No session data available to export.");
        return;
    }
    
    let csvRows = [];
    // Headers
    csvRows.push("Session ID,Start Time,End Time,Duration (Seconds),Total Blinks,Drowsy Alerts Count");
    
    allSessionsData.forEach((s, idx) => {
        const id = s.id || idx + 1;
        const start = s.session_start ? `"${new Date(s.session_start).toISOString()}"` : "N/A";
        const end = s.session_end ? `"${new Date(s.session_end).toISOString()}"` : "N/A";
        const duration = s.duration_seconds || 0;
        const blinks = s.total_blinks || 0;
        const drowsy = s.drowsy_events || 0;
        
        csvRows.push(`${id},${start},${end},${duration},${blinks},${drowsy}`);
    });
    
    const csvString = csvRows.join("\n");
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `driver_telemetry_history_${new Date().toISOString().slice(0,10)}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Modal Drill Down Display
let activeFilteredSessions = [];

function openSessionModal(index, rowElement) {
    const modal = document.getElementById("sessionModal");
    if (!modal) return;
    
    // Determine which sessions are currently displayed (filtered ones)
    let displayedSessions = [...allSessionsData];
    const now = new Date();
    
    if (activePeriodFilter === '7days') {
        const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        displayedSessions = allSessionsData.filter(s => new Date(s.session_start) >= sevenDaysAgo);
    } else if (activePeriodFilter === '24hours') {
        const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        displayedSessions = allSessionsData.filter(s => new Date(s.session_start) >= oneDayAgo);
    }
    
    const session = displayedSessions[index];
    if (!session) return;
    
    // Format values
    const dateObj = new Date(session.session_start);
    const startStr = isNaN(dateObj.getTime()) ? "Unknown" : dateObj.toLocaleString();
    const endObj = new Date(session.session_end);
    const endStr = isNaN(endObj.getTime()) ? "Unknown" : endObj.toLocaleString();
    
    const durationSec = session.duration_seconds || 0;
    const mins = Math.floor(durationSec / 60);
    const secs = Math.round(durationSec % 60);
    const durationStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
    
    const blinks = session.total_blinks || 0;
    const drowsy = session.drowsy_events || 0;
    
    const blinkRateProj = durationSec > 0 ? Math.round((blinks / durationSec) * 60) : 0;
    
    // Safety rating assessment
    let safetyStatus = "Safe & Attentive";
    let safetyColor = "#10b981";
    if (drowsy > 5 || blinkRateProj > 25) {
        safetyStatus = "Critical fatigue risk";
        safetyColor = "#ef4444";
    } else if (drowsy > 0 || blinkRateProj > 18) {
        safetyStatus = "Moderate fatigue detected";
        safetyColor = "#f59e0b";
    }
    
    // Populate elements
    document.getElementById("modalValDuration").innerText = durationStr;
    document.getElementById("modalValBlinks").innerText = blinks;
    document.getElementById("modalValDrowsy").innerText = drowsy;
    document.getElementById("modalValStart").innerText = startStr;
    document.getElementById("modalValEnd").innerText = endStr;
    document.getElementById("modalValBlinkRate").innerText = `${blinkRateProj} blinks / min`;
    
    const statusVal = document.getElementById("modalValStatus");
    statusVal.innerText = safetyStatus;
    statusVal.style.color = safetyColor;
    
    // Show modal
    modal.classList.remove("hidden");
}

function closeSessionModal() {
    const modal = document.getElementById("sessionModal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

function clearHistory() {
    if (!confirm("Are you sure you want to permanently clear all completed session logs?")) {
        return;
    }

    fetch('/api/history/clear', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                loadHistory();
            } else {
                alert("Failed to clear logs.");
            }
        })
        .catch(err => console.error("Error clearing logs:", err));
}

// User Profile & Dropdown menu logic
function toggleProfileMenu(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    const dropdown = document.getElementById("profileDropdown");
    if (dropdown) {
        dropdown.classList.toggle("hidden");
    }
}

function injectProfileModalHTML() {
    if (document.getElementById("profileModal")) return;
    
    const modalHTML = `
        <div class="modal-content glass-card">
            <div class="modal-header">
                <h3>Update Profile Details</h3>
                <button class="btn-close" onclick="closeProfileModal()">&times;</button>
            </div>
            <form id="profileForm" onsubmit="submitProfileUpdate(event)">
                <div class="input-group">
                    <label for="profileEmail">Email Address</label>
                    <input type="email" id="profileEmail" readonly disabled style="opacity: 0.7;">
                </div>
                <div class="input-group">
                    <label for="profileFullName">Full Name</label>
                    <input type="text" id="profileFullName" placeholder="Enter your full name">
                </div>
                <div class="input-group">
                    <label for="profilePhone">Phone Number</label>
                    <input type="tel" id="profilePhone" placeholder="Enter your phone number">
                </div>
                <div class="input-group">
                    <label for="profileAge">Age</label>
                    <input type="number" id="profileAge" min="1" max="120" placeholder="Enter your age">
                </div>
                <div id="profileError" class="auth-error-box hidden"></div>
                <div id="profileSuccess" class="success-box hidden">Profile updated successfully!</div>
                <div class="modal-actions">
                    <button type="button" class="btn-secondary" onclick="closeProfileModal()">Cancel</button>
                    <button type="submit" class="btn-primary">Save Changes</button>
                </div>
            </form>
        </div>
    `;
    
    const modalDiv = document.createElement("div");
    modalDiv.id = "profileModal";
    modalDiv.className = "modal hidden";
    modalDiv.innerHTML = modalHTML;
    document.body.appendChild(modalDiv);
}

function openProfileModal(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    // Close dropdown
    const dropdown = document.getElementById("profileDropdown");
    if (dropdown) dropdown.classList.add("hidden");
    
    const modal = document.getElementById("profileModal");
    if (!modal) return;
    
    fetch("/api/profile")
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.getElementById("profileEmail").value = data.profile.email;
                document.getElementById("profileFullName").value = data.profile.full_name;
                document.getElementById("profilePhone").value = data.profile.phone;
                document.getElementById("profileAge").value = data.profile.age;
                
                document.getElementById("profileError").classList.add("hidden");
                document.getElementById("profileSuccess").classList.add("hidden");
                
                modal.classList.remove("hidden");
            } else {
                alert("Error loading profile: " + data.message);
            }
        })
        .catch(err => {
            console.error("Error loading profile:", err);
            alert("Failed to load profile details.");
        });
}

function closeProfileModal() {
    const modal = document.getElementById("profileModal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

function submitProfileUpdate(event) {
    event.preventDefault();
    
    const fullName = document.getElementById("profileFullName").value.trim();
    const phone = document.getElementById("profilePhone").value.trim();
    const age = document.getElementById("profileAge").value.trim();
    
    const errorBox = document.getElementById("profileError");
    const successBox = document.getElementById("profileSuccess");
    
    errorBox.classList.add("hidden");
    successBox.classList.add("hidden");
    
    fetch("/api/profile/update", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            full_name: fullName,
            phone: phone,
            age: age ? parseInt(age) : ""
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            successBox.classList.remove("hidden");
            setTimeout(() => {
                closeProfileModal();
            }, 1200);
        } else {
            errorBox.textContent = data.message || "Failed to update profile.";
            errorBox.classList.remove("hidden");
        }
    })
    .catch(err => {
        console.error("Error updating profile:", err);
        errorBox.textContent = "Connection error. Please try again.";
        errorBox.classList.remove("hidden");
    });
}

// Auto-initialize components on page load
document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("historyTableBody")) {
        loadHistory();
    }
    
    if (document.querySelector(".user-profile")) {
        injectProfileModalHTML();
        
        // Close dropdown when clicking outside
        window.addEventListener("click", (e) => {
            const dropdown = document.getElementById("profileDropdown");
            const avatar = document.querySelector(".avatar");
            if (dropdown && !dropdown.classList.contains("hidden")) {
                if (!dropdown.contains(e.target) && (!avatar || !avatar.contains(e.target))) {
                    dropdown.classList.add("hidden");
                }
            }
        });
    }
});