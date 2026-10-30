(() => {
  "use strict";
  const video = document.getElementById("camera");
  const canvas = document.getElementById("canvas");
  const startButton = document.getElementById("startCamera");
  const captureButton = document.getElementById("capturePhoto");
  const photoData = document.getElementById("photoData");
  const photoFile = document.getElementById("photoFile");
  const preview = document.getElementById("preview");
  const cameraStatus = document.getElementById("cameraStatus");
  const gpsStatus = document.getElementById("gpsStatus");
  const latInput = document.getElementById("latitude");
  const lonInput = document.getElementById("longitude");
  const gpsButton = document.getElementById("getLocation");
  const form = document.getElementById("complaintForm");
  let cameraStream = null;
  let cameraBusy = false;
  let gpsBusy = false;

  const secureContextHelp =
    "Camera/GPS needs a secure connection. On this computer open exactly http://127.0.0.1:5000 . For an online website, use its HTTPS address.";

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      cameraStream = null;
    }
    if (video) {
      video.pause();
      video.srcObject = null;
      video.hidden = true;
    }
    if (captureButton) captureButton.disabled = true;
  }

  async function openCamera() {
    if (cameraBusy || !startButton) return;
    cameraBusy = true;
    startButton.disabled = true;
    if (cameraStatus) cameraStatus.textContent = "Waiting for camera permission…";
    try {
      if (!window.isSecureContext) throw new Error(secureContextHelp);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("This browser does not provide camera access here. Open the localhost/HTTPS address or choose a photo below.");
      }
      stopCamera();
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      video.srcObject = cameraStream;
      video.hidden = false;
      await video.play();
      captureButton.disabled = false;
      startButton.textContent = "Restart camera";
      if (cameraStatus) cameraStatus.textContent = "Camera ready. Take a photo of the campus issue.";
    } catch (error) {
      let message = error && error.message ? error.message : "Camera could not be opened.";
      if (error && error.name === "NotAllowedError") message = "Camera permission is blocked. Click the site icon beside Chrome’s address bar, set Camera to Allow, reload, and retry.";
      if (error && error.name === "NotFoundError") message = "No camera was detected on this device. You can choose an image file instead.";
      if (error && error.name === "NotReadableError") message = "Camera is busy in another app. Close that app and retry.";
      if (cameraStatus) cameraStatus.textContent = message;
      stopCamera();
    } finally {
      cameraBusy = false;
      startButton.disabled = false;
    }
  }

  startButton?.addEventListener("click", openCamera);

  captureButton?.addEventListener("click", () => {
    if (!video || !video.videoWidth || !canvas) {
      if (cameraStatus) cameraStatus.textContent = "Camera is not ready yet. Wait a moment and try again.";
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      if (cameraStatus) cameraStatus.textContent = "Could not capture the photo. Please retry or choose a file.";
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    photoData.value = canvas.toDataURL("image/jpeg", 0.84);
    preview.src = photoData.value;
    preview.hidden = false;
    if (photoFile) photoFile.value = "";
    stopCamera();
    startButton.textContent = "Retake photo";
    if (cameraStatus) cameraStatus.textContent = "Photo captured successfully. You can submit the complaint.";
  });

  photoFile?.addEventListener("change", () => {
    if (photoFile.files && photoFile.files.length) {
      photoData.value = "";
      preview.removeAttribute("src");
      preview.hidden = true;
      stopCamera();
      if (cameraStatus) cameraStatus.textContent = "Photo selected. Submit the complaint when ready.";
    }
  });

  gpsButton?.addEventListener("click", () => {
    if (gpsBusy) return;
    if (!window.isSecureContext) {
      if (gpsStatus) gpsStatus.textContent = secureContextHelp;
      return;
    }
    if (!navigator.geolocation) {
      if (gpsStatus) gpsStatus.textContent = "This browser does not support GPS location. Try the latest Chrome browser.";
      return;
    }
    gpsBusy = true;
    gpsButton.disabled = true;
    latInput.value = "";
    lonInput.value = "";
    if (gpsStatus) gpsStatus.textContent = "Getting your location… Please allow location access in Chrome.";
    navigator.geolocation.getCurrentPosition(position => {
      latInput.value = String(position.coords.latitude);
      lonInput.value = String(position.coords.longitude);
      if (gpsStatus) gpsStatus.textContent =
        `Location captured (accuracy about ${Math.round(position.coords.accuracy)} m). Campus boundary will be checked when submitted.`;
      gpsBusy = false;
      gpsButton.disabled = false;
    }, error => {
      const messages = {
        1: "Location permission denied. Allow Location for this site in Chrome settings, then retry.",
        2: "Your location is unavailable. Turn on device location/GPS and retry.",
        3: "Location request timed out. Move near a window or retry."
      };
      if (gpsStatus) gpsStatus.textContent = messages[error.code] || "Could not get location. Check browser permission and retry.";
      gpsBusy = false;
      gpsButton.disabled = false;
    }, { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 });
  });

  form?.addEventListener("submit", event => {
    if (!latInput.value || !lonInput.value) {
      event.preventDefault();
      alert("First click “Verify my location” and wait until location is captured.");
    } else if (!photoData.value && !(photoFile && photoFile.files && photoFile.files.length)) {
      event.preventDefault();
      alert("First capture a photo or choose an image file.");
    }
  });

  window.addEventListener("pagehide", stopCamera);
})();
