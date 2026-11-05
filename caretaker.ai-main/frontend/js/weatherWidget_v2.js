// e:\model_test\caretaker\frontend\js\weatherWidget.js
class WeatherWidget {
    constructor(containerId, apiBaseUrl) {
        this.containerId = containerId;
        this.API_BASE_URL = apiBaseUrl || 'http://127.0.0.1:8000/api';
        this.TOKEN = localStorage.getItem('token');
        this.init();
    }

    // Initialize the widget
    init() {
        this.createWidget();
        this.updateTime();
        this.updateWeatherDisplay();

        // Update time every minute
        setInterval(() => this.updateTime(), 60000);

        // Update weather every 5 minutes
        setInterval(() => this.updateWeatherDisplay(), 300000);
    }

    // Create the widget HTML
    createWidget() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        container.innerHTML = `
            <div class="weather-widget" style="
                background: linear-gradient(135deg, rgba(87, 139, 135, 0.8), rgba(87, 139, 135, 0.9));
                border-radius: 16px;
                padding: 20px;
                border: 1px solid rgba(240, 231, 231, 0.1);
                margin-bottom: 20px;
            ">
                <div style="text-align: center; margin-bottom: 15px;">
                    <p id="current-time" style="margin: 4px 0 0; color: #cbd5e1; font-size: 0.9rem;">--:-- --</p>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; text-align: center;">
                    <div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: #ffffff;" id="tempValue">--°C</div>
                        <div style="font-size: 0.85rem; color: #cbd5e1;">Temperature</div>
                    </div>
                    <div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: #ffffff;" id="humidityValue">--%</div>
                        <div style="font-size: 0.85rem; color: #cbd5e1;">Humidity</div>
                    </div>
                    <div>
                        <div style="font-size: 1.8rem; font-weight: 700; color: #ffffff;" id="aqiValue">--</div>
                        <div style="font-size: 0.85rem; color: #cbd5e1;">AQI</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Update time display
    updateTime() {
        const now = new Date();
        const timeElement = document.getElementById('current-time');
        if (timeElement) {
            timeElement.textContent = now.toLocaleString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    }

    // Set current recipient and refresh
    setRecipient(recipientId) {
        this.recipientId = recipientId;
        this.updateWeatherDisplay();
    }

    // Fetch weather data
    async fetchWeatherData() {
        try {
            const url = this.recipientId
                ? `${this.API_BASE_URL}/weather/current?recipient_id=${this.recipientId}`
                : `${this.API_BASE_URL}/weather/current`;

            const response = await fetch(url, {
                headers: {
                    'Authorization': `Bearer ${this.TOKEN}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Failed to fetch weather data');
            }

            return await response.json();
        } catch (error) {
            console.error('Error fetching weather data:', error);
            return null;
        }
    }

    // Update weather display
    async updateWeatherDisplay() {
        const data = await this.fetchWeatherData();
        if (!data) {
            console.log('No weather data available');
            return;
        }

        // Weather data fetched


        // Update stats
        const updateElement = (id, value, suffix = '') => {
            const element = document.getElementById(id);
            if (element) {
                if (value === 'N/A' || value === undefined) {
                    element.textContent = '--' + suffix;
                } else {
                    element.textContent = value + suffix;
                }
            }
        };

        updateElement('tempValue', data.temperature, '°C');
        updateElement('humidityValue', data.humidity, '%');
        updateElement('aqiValue', data.aqi);
    }
}

// Export the WeatherWidget class
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WeatherWidget;
}