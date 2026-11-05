class VideoMonitoring {
    constructor() {
        this.token = localStorage.getItem('token');
        this.processBtn = document.getElementById('process-btn');
        this.videoUpload = document.getElementById('video-upload');
        this.resultSection = document.getElementById('result-section');
        this.processedVideo = document.getElementById('processed-video');
        this.fallAlerts = document.getElementById('fall-alerts');
        this.initEventListeners();
    }

    initEventListeners() {
        if (this.processBtn) {
            this.processBtn.addEventListener('click', () => this.processVideo());
        }
    }

    showLoading(show) {
        const spinner = this.processBtn.querySelector('.spinner-border');
        const text = this.processBtn.querySelector('.process-text');
        
        if (show) {
            spinner.classList.remove('d-none');
            text.textContent = 'Processing...';
            this.processBtn.disabled = true;
        } else {
            spinner.classList.add('d-none');
            text.textContent = 'Process Video';
            this.processBtn.disabled = false;
        }
    }

    showAlert(message, type = 'danger') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        this.fallAlerts.appendChild(alertDiv);
    }

    async processVideo() {
        const file = this.videoUpload.files[0];
        if (!file) {
            this.showAlert('Please select a video file first');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        
        try {
            this.showLoading(true);
            this.fallAlerts.innerHTML = '';

            const response = await fetch('/fall-detection/process-video', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`
                },
                body: formData
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                this.showProcessedVideo(result.processed_video);
            } else {
                throw new Error(result.message || 'Failed to process video');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showAlert(error.message || 'An error occurred while processing the video');
        } finally {
            this.showLoading(false);
        }
    }

    showProcessedVideo(videoUrl) {
        this.resultSection.style.display = 'block';
        this.processedVideo.src = videoUrl;
        this.processedVideo.load();
    }
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if the component exists on the page
    if (document.getElementById('video-monitoring-container')) {
        window.videoMonitoring = new VideoMonitoring();
    }
});
