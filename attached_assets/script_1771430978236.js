// --------- LIVE STATE ---------
let isLiveRunning = false;

// ---------- HOME NAVIGATION ----------
function goHome() {
  stopLive(); // ensure webcam off
  document.getElementById("homeSection").style.display = "block";
  document.getElementById("uploadSection").style.display = "none";
  document.getElementById("liveSection").style.display = "none";
}

// ---------- OPEN UPLOAD ----------
function openUpload() {
  stopLive(); // stop webcam if running
  document.getElementById("homeSection").style.display = "none";
  document.getElementById("uploadSection").style.display = "block";
  document.getElementById("liveSection").style.display = "none";
}

// ---------- OPEN LIVE ----------
function openLive() {
  document.getElementById("homeSection").style.display = "none";
  document.getElementById("uploadSection").style.display = "none";
  document.getElementById("liveSection").style.display = "block";
}

// ---------- IMAGE DETECTION ----------
function uploadImage() {
  let fileInput = document.getElementById("imageInput");
  let file = fileInput.files[0];
  if (!file) return;

  // Show original
  document.getElementById("originalImage").src =
    URL.createObjectURL(file);

  let formData = new FormData();
  formData.append("image", file);

  fetch("/detect-image", {
    method: "POST",
    body: formData
  })
  .then(res => res.blob())
  .then(blob => {
    document.getElementById("resultImage").src =
      URL.createObjectURL(blob);
  });
}

// ---------- TOGGLE LIVE ----------
function toggleLive() {
  if (!isLiveRunning) {
    startLive();
  } else {
    stopLive();
  }
}

// ---------- START LIVE ----------
function startLive() {
  document.getElementById("liveStream").src = "/detect-live";

  const btn = document.getElementById("liveToggleBtn");
  btn.innerText = "Stop Webcam";
  btn.style.background = "#c0392b";

  isLiveRunning = true;
}

// ---------- STOP LIVE ----------
function stopLive() {
  // Stop browser stream
  document.getElementById("liveStream").src = "";

  // Tell Flask to release camera
  fetch("/stop-live").catch(() => {});

  const btn = document.getElementById("liveToggleBtn");
  if (btn) {
    btn.innerText = "Start Webcam";
    btn.style.background = "#2a5298";
  }

  isLiveRunning = false;
}