let isLiveRunning = false;

function goHome() {
    stopLive();
    showSection("homeSection");
}

function openUpload() {
    stopLive();
    showSection("uploadSection");
}

function openLive() {
    showSection("liveSection");
}

function showSection(id) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.add('hidden'));
    document.getElementById(id).classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function previewImage() {
    const file = document.getElementById("imageInput").files[0];
    if (file) {
        document.getElementById("originalImage").src = URL.createObjectURL(file);
        document.querySelector(".custom-file-upload span").innerText = file.name;
    }
}

function uploadImage() {
    let fileInput = document.getElementById("imageInput");
    let file = fileInput.files[0];
    if (!file) {
        alert("Please select an image first");
        return;
    }

    const btn = event.target;
    const originalText = btn.innerText;
    btn.innerText = "Analyzing...";
    btn.disabled = true;

    let formData = new FormData();
    formData.append("image", file);

    fetch("/detect-image", {
        method: "POST",
        body: formData
    })
    .then(res => {
        if (!res.ok) throw new Error("Detection failed");
        return res.blob();
    })
    .then(blob => {
        document.getElementById("resultImage").src = URL.createObjectURL(blob);
    })
    .catch(err => {
        alert(err.message);
    })
    .finally(() => {
        btn.innerText = originalText;
        btn.disabled = false;
    });
}

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
    noFeed.classList.add("hidden");
    
    btn.innerText = "Stop Vision Feed";
    btn.style.background = "#ef4444";
    btn.style.boxShadow = "0 4px 6px -1px rgba(239, 68, 68, 0.3)";

    isLiveRunning = true;
}

function stopLive() {
    const streamImg = document.getElementById("liveStream");
    const noFeed = document.getElementById("noFeed");
    const btn = document.getElementById("liveToggleBtn");

    streamImg.src = "";
    if (noFeed) noFeed.classList.remove("hidden");
    
    fetch("/stop-live").catch(() => {});

    if (btn) {
        btn.innerText = "Start Intelligence Feed";
        btn.style.background = "var(--primary)";
        btn.style.boxShadow = "0 4px 6px -1px rgba(79, 70, 229, 0.3)";
    }

    isLiveRunning = false;
}
