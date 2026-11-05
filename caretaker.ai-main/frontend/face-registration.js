// Face Registration Utility for register.html
class FaceRegistration {
    constructor() {
        this.faceDescriptor = null;
        this.isFaceCaptured = false;

        this.video = document.getElementById('webcam');
        this.canvas = document.getElementById('canvas');
        this.captureBtn = document.getElementById('captureFaceBtn');
        this.retakeBtn = document.getElementById('retakeFaceBtn');
        this.imageInput = document.getElementById('faceImageUpload');
        this.statusEl = document.getElementById('faceStatus');
        this.descriptorInput = document.getElementById('faceDescriptor');
        this.modelsLoaded = false;
    }

    async initialize() {
        try {
            this.updateStatus('Loading face detection models...', 'info');

            // Load face-api.js models from a working public CDN
            await Promise.all([
                faceapi.nets.tinyFaceDetector.loadFromUri('https://justadudewhohacks.github.io/face-api.js/models'),
                faceapi.nets.faceLandmark68Net.loadFromUri('https://justadudewhohacks.github.io/face-api.js/models'),
                faceapi.nets.faceRecognitionNet.loadFromUri('https://justadudewhohacks.github.io/face-api.js/models')
            ]);

            this.modelsLoaded = true;
            await this.setupWebcam();
            this.setupEventListeners();
            this.updateStatus('✅ Ready to capture face - Click "Capture Face" when you are ready', 'success');
        } catch (error) {
            console.error('Error initializing face registration:', error);
            this.updateStatus('⚠️ Face capture unavailable - You can still register without face capture', 'warning');
            if (this.captureBtn) {
                this.captureBtn.disabled = true;
                this.captureBtn.textContent = 'Face Capture Unavailable';
            }
        }
    }

    async setupWebcam() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                video: { 
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                } 
            });
            this.video.srcObject = stream;
            
            // Wait for video to be ready
            this.video.addEventListener('loadeddata', () => {
                this.updateStatus('Camera ready - Click "Capture Face" when ready', 'info');
            });
            
        } catch (error) {
            console.error('Error accessing webcam:', error);
            this.updateStatus('❌ Webcam access denied - Face capture disabled', 'error');
            if (this.captureBtn) {
                this.captureBtn.disabled = true;
                this.captureBtn.textContent = 'Webcam Not Available';
            }
        }
    }

    setupEventListeners() {
        this.captureBtn.addEventListener('click', () => this.captureFace());
        this.retakeBtn.addEventListener('click', () => this.retakeFace());

        if (this.imageInput) {
            this.imageInput.addEventListener('change', (e) => this.captureFromImage(e));
        }
    }

    async captureFace() {
        if (!this.modelsLoaded) {
            this.updateStatus('❌ Face models not loaded yet', 'error');
            return;
        }

        try {
            this.updateStatus('🔍 Detecting face... Please look at the camera', 'info');
            this.captureBtn.disabled = true;
            this.captureBtn.textContent = 'Detecting...';

            // small delay so the status/button update is visible
            await new Promise(resolve => setTimeout(resolve, 300));

            // Add a timeout so we don't hang forever if detection stalls
            // Give it more time (20s) because TFJS + face-api can be slow on some machines
            const detection = await Promise.race([
                faceapi
                    .detectSingleFace(this.video, new faceapi.TinyFaceDetectorOptions())
                    .withFaceLandmarks()
                    .withFaceDescriptor(),
                new Promise((_, reject) => setTimeout(() => reject(new Error('Face detection timeout')), 20000))
            ]);

            if (detection) {
                // Store face descriptor
                this.faceDescriptor = Array.from(detection.descriptor);
                this.descriptorInput.value = JSON.stringify(this.faceDescriptor);

                // Show success feedback
                this.isFaceCaptured = true;
                this.captureBtn.style.display = 'none';
                this.retakeBtn.style.display = 'inline-block';
                this.updateStatus('✅ Face captured successfully! The system will recognize you for monitoring.', 'success');

                // Draw face bounding box on canvas for visual feedback
                const displaySize = {
                    width: this.video.videoWidth || 640,
                    height: this.video.videoHeight || 480
                };
                this.canvas.width = displaySize.width;
                this.canvas.height = displaySize.height;
                faceapi.matchDimensions(this.canvas, displaySize);

                const resizedDetection = faceapi.resizeResults(detection, displaySize);
                const ctx = this.canvas.getContext('2d');
                ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

                // Draw detection
                faceapi.draw.drawDetections(this.canvas, resizedDetection);
                faceapi.draw.drawFaceLandmarks(this.canvas, resizedDetection);

                // Show canvas instead of video
                this.video.style.display = 'none';
                this.canvas.style.display = 'block';
                this.canvas.style.width = '100%';
                this.canvas.style.maxWidth = '400px';
                this.canvas.style.border = '2px solid #28a745';
                this.canvas.style.borderRadius = '5px';

            } else {
                this.updateStatus('❌ No face detected. Please ensure your face is visible and well-lit.', 'error');
            }
        } catch (error) {
            console.error('Error capturing face:', error);
            if (error && error.message === 'Face detection timeout') {
                this.updateStatus('❌ Face detection took too long. Try moving closer to the camera and ensure good lighting, then try again.', 'error');
            } else {
                this.updateStatus('❌ Error capturing face. Please try again.', 'error');
            }
        } finally {
            // Always reset button so it doesn't stay stuck on "Detecting..."
            this.captureBtn.disabled = false;
            if (!this.isFaceCaptured) {
                this.captureBtn.textContent = '📷 Capture Face';
            }
        }
    }

    retakeFace() {
        this.faceDescriptor = null;
        this.descriptorInput.value = '';
        this.isFaceCaptured = false;
        this.captureBtn.style.display = 'inline-block';
        this.retakeBtn.style.display = 'none';
        this.captureBtn.disabled = false;
        this.captureBtn.textContent = '📷 Capture Face';
        this.updateStatus('Ready to capture face', 'info');
        
        // Switch back to video
        this.canvas.style.display = 'none';
        this.video.style.display = 'block';
        
        // Clear canvas
        const ctx = this.canvas.getContext('2d');
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    updateStatus(message, type) {
        this.statusEl.textContent = message;
        this.statusEl.style.backgroundColor = 
            type === 'success' ? '#d4edda' :
            type === 'error' ? '#f8d7da' :
            type === 'warning' ? '#fff3cd' : '#d1ecf1';
        this.statusEl.style.color = 
            type === 'success' ? '#155724' :
            type === 'error' ? '#721c24' :
            type === 'warning' ? '#856404' : '#0c5460';
        this.statusEl.style.border = 
            type === 'success' ? '1px solid #c3e6cb' :
            type === 'error' ? '1px solid #f5c6cb' :
            type === 'warning' ? '1px solid #ffeaa7' : '#bee5eb';
    }

    getFaceData() {
        return this.faceDescriptor;
    }
}

// Initialize when page loads
let faceRegistration;

document.addEventListener('DOMContentLoaded', async () => {
    faceRegistration = new FaceRegistration();
    await faceRegistration.initialize();
});