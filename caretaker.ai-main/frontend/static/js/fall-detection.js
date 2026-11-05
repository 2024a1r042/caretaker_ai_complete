// Fall Detection Module
document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const videoSection = document.getElementById('video-section');
    
    // Create the video monitoring interface
    function createVideoMonitoringUI() {
        // Create the main container
        const container = document.createElement('div');
        container.className = 'video-monitoring-container';
        container.innerHTML = `
            <div class="mode-selector">
                <button id="liveFeedBtn" class="mode-btn active">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polygon points="10 8 16 12 10 16 10 8"></polygon>
                    </svg>
                    Live Feed
                </button>
                <button id="uploadVideoBtn" class="mode-btn">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="17 8 12 3 7 8"></polyline>
                        <line x1="12" y1="3" x2="12" y2="15"></line>
                    </svg>
                    Upload Video
                </button>
            </div>
            
            <!-- Live Feed Pane -->
            <div id="liveFeedPane" class="content-pane active">
                <div class="video-container">
                    <video id="videoFeed" playsinline></video>
                    <div class="video-placeholder">
                        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M23 7l-7 5 7 5V7z"></path>
                            <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                        </svg>
                        <p>Live feed is not active</p>
                    </div>
                    <div id="liveFeedOverlay" class="processing-overlay" style="display: none;">
                        <div class="spinner"></div>
                        <p>Processing video stream...</p>
                    </div>
                </div>
                <button id="startFeedBtn" class="primary-btn">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polygon points="10 8 16 12 10 16 10 8"></polygon>
                    </svg>
                    Start Live Feed
                </button>
                <div class="status-text" id="liveFeedStatus">Click "Start Live Feed" to begin camera feed.</div>
                <div class="capture-controls" style="display: none; margin-top: 16px;">
                    <button id="captureBtn" class="secondary-btn">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            <circle cx="8.5" cy="8.5" r="1.5"></circle>
                            <polyline points="21 15 16 10 5 21"></polyline>
                        </svg>
                        Capture Image
                    </button>
                    <div class="capture-preview" id="capturePreview"></div>
                </div>
            </div>
            
            <!-- Upload Video Pane -->
            <div id="uploadPane" class="content-pane">
                <div class="upload-area" id="uploadArea">
                    <div class="upload-prompt">
                        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="17 8 12 3 7 8"></polyline>
                            <line x1="12" y1="3" x2="12" y2="15"></line>
                        </svg>
                        <h3>Upload Video for Fall Detection</h3>
                        <p>Drag & drop a video file here or click to browse</p>
                        <input type="file" id="videoUpload" accept="video/*" style="display: none;">
                        <button id="browseBtn" class="primary-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="17 8 12 3 7 8"></polyline>
                                <line x1="12" y1="3" x2="12" y2="15"></line>
                            </svg>
                            Select Video
                        </button>
                    </div>
                </div>
                
                <div id="processingSection" style="display: none; text-align: center; padding: 40px 20px;">
                    <div class="spinner"></div>
                    <p>Processing video for fall detection...</p>
                    <div id="processingProgress" style="margin-top: 20px;"></div>
                </div>
                
                <div id="resultSection" style="display: none; margin-top: 20px;">
                    <div class="video-container">
                        <video id="processedVideo" controls style="width: 100%; height: 100%; object-fit: contain; display: none;"></video>
                        <div id="fallDetectionResults" style="padding: 16px;"></div>
                    </div>
                </div>
            </div>
        `;
        
        return container;
    }
    
    // Initialize the video monitoring section
    function initVideoMonitoring() {
        const videoSection = document.getElementById('video-section');
        if (!videoSection) return;
        
        // Clear existing content
        const panelBody = videoSection.querySelector('.panel-body');
        if (panelBody) {
            videoSection.removeChild(panelBody);
        }
        
        // Create and append the video monitoring UI
        const panelBodyNew = document.createElement('div');
        panelBodyNew.className = 'panel-body';
        panelBodyNew.style.padding = '20px';
        panelBodyNew.appendChild(createVideoMonitoringUI());
        videoSection.appendChild(panelBodyNew);
        
        // Initialize event listeners
        initEventListeners();
    }
    
    // Initialize event listeners
    function initEventListeners() {
        // Mode switching
        const liveFeedBtn = document.getElementById('liveFeedBtn');
        const uploadVideoBtn = document.getElementById('uploadVideoBtn');
        const liveFeedPane = document.getElementById('liveFeedPane');
        const uploadPane = document.getElementById('uploadPane');
        
        if (liveFeedBtn && uploadVideoBtn) {
            liveFeedBtn.addEventListener('click', () => {
                liveFeedBtn.classList.add('active');
                uploadVideoBtn.classList.remove('active');
                liveFeedPane.classList.add('active');
                uploadPane.classList.remove('active');
                
                // Stop any active video feed when switching to upload mode
                if (window.videoStream) {
                    stopVideoFeed();
                }
            });
            
            uploadVideoBtn.addEventListener('click', () => {
                uploadVideoBtn.classList.add('active');
                liveFeedBtn.classList.remove('active');
                uploadPane.classList.add('active');
                liveFeedPane.classList.remove('active');
            });
        }
        
        // Live feed controls
        const startFeedBtn = document.getElementById('startFeedBtn');
        const videoFeed = document.getElementById('videoFeed');
        const liveFeedStatus = document.getElementById('liveFeedStatus');
        const captureBtn = document.getElementById('captureBtn');
        const capturePreview = document.getElementById('capturePreview');
        
        if (startFeedBtn) {
            startFeedBtn.addEventListener('click', toggleVideoFeed);
        }
        
        if (captureBtn) {
            captureBtn.addEventListener('click', captureImage);
        }
        
        // Upload controls
        const uploadArea = document.getElementById('uploadArea');
        const browseBtn = document.getElementById('browseBtn');
        const videoUpload = document.getElementById('videoUpload');
        
        if (browseBtn && videoUpload) {
            browseBtn.addEventListener('click', () => videoUpload.click());
            
            videoUpload.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    handleFileUpload(file);
                }
            });
        }
        
        // Drag and drop for upload area
        if (uploadArea) {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, preventDefaults, false);
            });
            
            ['dragenter', 'dragover'].forEach(eventName => {
                uploadArea.addEventListener(eventName, highlight, false);
            });
            
            ['dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, unhighlight, false);
            });
            
            uploadArea.addEventListener('drop', handleDrop, false);
        }
    }
    
    // Video feed functions
    async function toggleVideoFeed() {
        const startFeedBtn = document.getElementById('startFeedBtn');
        const videoFeed = document.getElementById('videoFeed');
        const liveFeedStatus = document.getElementById('liveFeedStatus');
        const captureControls = document.querySelector('.capture-controls');
        
        try {
            if (window.videoStream) {
                // Stop video feed
                stopVideoFeed();
                startFeedBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polygon points="10 8 16 12 10 16 10 8"></polygon>
                    </svg>
                    Start Live Feed
                `;
                liveFeedStatus.textContent = 'Live feed stopped. Click "Start Live Feed" to begin.';
                if (captureControls) captureControls.style.display = 'none';
            } else {
                // Start video feed
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        width: { ideal: 1280 },
                        height: { ideal: 720 },
                        facingMode: 'environment'
                    },
                    audio: false
                });
                
                window.videoStream = stream;
                videoFeed.srcObject = stream;
                videoFeed.play();
                
                // Show video and hide placeholder
                videoFeed.style.display = 'block';
                const placeholder = document.querySelector('.video-placeholder');
                if (placeholder) placeholder.style.display = 'none';
                
                // Update UI
                startFeedBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <rect x="6" y="6" width="12" height="12" rx="1"></rect>
                    </svg>
                    Stop Live Feed
                `;
                liveFeedStatus.textContent = 'Live feed is active. Click "Capture Image" to take a photo.';
                if (captureControls) captureControls.style.display = 'flex';
            }
        } catch (error) {
            console.error('Error accessing camera:', error);
            liveFeedStatus.textContent = 'Error: Could not access camera. ' + error.message;
        }
    }
    
    function stopVideoFeed() {
        const videoFeed = document.getElementById('videoFeed');
        const placeholder = document.querySelector('.video-placeholder');
        
        if (window.videoStream) {
            window.videoStream.getTracks().forEach(track => track.stop());
            window.videoStream = null;
        }
        
        if (videoFeed) {
            videoFeed.pause();
            videoFeed.srcObject = null;
            videoFeed.style.display = 'none';
        }
        
        if (placeholder) {
            placeholder.style.display = 'flex';
        }
    }
    
    function captureImage() {
        const videoFeed = document.getElementById('videoFeed');
        const capturePreview = document.getElementById('capturePreview');
        const liveFeedStatus = document.getElementById('liveFeedStatus');
        
        if (!videoFeed || !capturePreview) return;
        
        // Create canvas to capture the image
        const canvas = document.createElement('canvas');
        canvas.width = videoFeed.videoWidth;
        canvas.height = videoFeed.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoFeed, 0, 0, canvas.width, canvas.height);
        
        // Create image element for preview
        const img = document.createElement('img');
        img.src = canvas.toDataURL('image/jpeg', 0.9);
        img.alt = 'Captured image';
        img.style.cursor = 'pointer';
        img.style.width = '100px';
        img.style.height = '75px';
        img.style.objectFit = 'cover';
        img.style.borderRadius = '6px';
        img.style.border = '2px solid var(--border)';
        img.style.transition = 'all 0.2s ease';
        
        // Add click to view full size
        img.addEventListener('click', () => {
            const win = window.open('', '_blank');
            win.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Captured Image</title>
                    <style>
                        body { margin: 0; padding: 20px; background: #f5f5f5; text-align: center; }
                        img { max-width: 90%; max-height: 90vh; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
                    </style>
                </head>
                <body>
                    <img src="${img.src}" alt="Captured Image">
                </body>
                </html>
            `);
        });
        
        // Add hover effect
        img.addEventListener('mouseenter', () => {
            img.style.transform = 'scale(1.05)';
            img.style.borderColor = 'var(--accent)';
        });
        
        img.addEventListener('mouseleave', () => {
            img.style.transform = 'scale(1)';
            img.style.borderColor = 'var(--border)';
        });
        
        // Add to preview container
        capturePreview.insertBefore(img, capturePreview.firstChild);
        
        // Show success message
        liveFeedStatus.textContent = 'Image captured! Click on the thumbnail to view full size.';
        setTimeout(() => {
            if (window.videoStream) {
                liveFeedStatus.textContent = 'Live feed is active. Click "Capture Image" to take a photo.';
            }
        }, 3000);
    }
    
    // File upload functions
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        const uploadArea = document.getElementById('uploadArea');
        if (uploadArea) uploadArea.classList.add('highlight');
    }
    
    function unhighlight() {
        const uploadArea = document.getElementById('uploadArea');
        if (uploadArea) uploadArea.classList.remove('highlight');
    }
    
    async function handleDrop(e) {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        
        if (file) {
            try {
                await handleFileUpload(file);
            } catch (error) {
                console.error('Error processing video:', error);
                showError(error.message || 'An error occurred while processing the video.');
            }
        }
    
    // Helper function to poll for processing status
    async function pollProcessingStatus(processId) {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/api/fall-detection/status/${processId}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`Failed to get status: ${response.status}`);
            }
            
            const statusData = await response.json();
            
            // Update progress
            if (statusData.progress !== undefined) {
                processingProgress.innerHTML = `
                    <div class="progress-container">
                        <div class="progress-bar" style="width: ${statusData.progress}%"></div>
                    </div>
                    <div class="progress-text">${statusData.progress}% - ${statusData.message || 'Processing...'}</div>
                `;
            }
            
            // Check if processing is complete
            if (statusData.status === 'completed') {
                // Get the final results
                await showProcessingResults(processId);
            } else if (statusData.status === 'error') {
                throw new Error(statusData.message || 'Processing failed');
            } else {
                // Continue polling
                setTimeout(() => pollProcessingStatus(processId), 2000);
            }
            
        } catch (error) {
            console.error('Error polling status:', error);
            showError(error.message || 'Error checking processing status');
        }
    }
    
    // Show the final processing results
    async function showProcessingResults(processId) {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/api/fall-detection/results/${processId}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`Failed to get results: ${response.status}`);
            }
            
            const result = await response.json();
            
            // Update the UI with results
            processedVideo.src = result.processed_video;
            processedVideo.style.display = 'block';
            
            // Display fall detection results
            if (result.falls_detected && result.falls_detected.length > 0) {
                let resultsHTML = `
                    <div class="results-summary">
                        <h4>Fall Detection Results</h4>
                        <p>Video duration: ${formatDuration(result.duration)}</p>
                        <p>Total frames processed: ${result.total_frames}</p>
                        <p>Falls detected: <strong>${result.falls_detected.length}</strong></p>
                    </div>
                    <div class="falls-list">
                        <h5>Detected Falls:</h5>
                        <ul>
                `;
                
                result.falls_detected.forEach((fall, index) => {
                    const time = formatTime(fall.time);
                    const confidence = (fall.confidence * 100).toFixed(1);
                    resultsHTML += `
                        <li class="fall-item">
                            <span class="fall-time">${time}</span>
                            <span class="fall-confidence">${confidence}% confidence</span>
                        </li>
                    `;
                });
                
                resultsHTML += `
                        </ul>
                    </div>
                `;
                
                fallDetectionResults.innerHTML = resultsHTML;
            } else {
                fallDetectionResults.innerHTML = `
                    <div class="no-falls">
                        <p> No falls detected in this video.</p>
                        <p>Duration: ${formatDuration(result.duration)}</p>
                        <p>Frames processed: ${result.total_frames}</p>
                    </div>
                `;
            }
            
            // Show result section
            processingSection.style.display = 'none';
            resultSection.style.display = 'block';
            
        } catch (error) {
            console.error('Error getting results:', error);
            showError(error.message || 'Failed to get processing results');
        }
    }
    
    // Show error message
    function showError(message) {
        fallDetectionResults.innerHTML = `
            <div class="error-message">
                <h4>Error Processing Video</h4>
                <p>${message}</p>
                <button id="retryUpload" class="primary-btn" style="margin-top: 10px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18-5M22 12.5a10 10 0 0 1-18 5"></path>
                    </svg>
                    Try Again
                </button>
            </div>
        `;
        
        // Add retry handler
        const retryBtn = document.getElementById('retryUpload');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                uploadArea.style.display = 'block';
                resultSection.style.display = 'none';
                const videoUpload = document.getElementById('videoUpload');
                if (videoUpload) videoUpload.value = '';
                
                if (window.videoStream) {
                    stopVideoFeed();
                }
            });
        }
