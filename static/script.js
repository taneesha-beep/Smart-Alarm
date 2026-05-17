class SmartAlarm {
    constructor() {
        this.debounceTimers = {};
        this.activeRequests = {};
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setDefaultTimes();
        console.log("Smart Alarm initialized");
    }

    setDefaultTimes() {
        // Set arrival time to next hour by default
        const now = new Date();
        now.setHours(now.getHours() + 1, 0, 0, 0);
        const timeString = now.toTimeString().substring(0, 5);
        document.getElementById('arrival_time').value = timeString;
        console.log("Set default arrival time to:", timeString);
    }

    setupEventListeners() {
        // Autocomplete for start location
        document.getElementById('start_place').addEventListener('input', (e) => {
            this.handleAutocomplete(e.target.value, 'start');
        });

        // Autocomplete for destination
        document.getElementById('end_place').addEventListener('input', (e) => {
            this.handleAutocomplete(e.target.value, 'end');
        });

        // Form submission
        document.getElementById('alarmForm').addEventListener('submit', (e) => {
            this.handleSubmit(e);
        });

        // Close suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.matches('.autocomplete-container input')) {
                this.hideAllSuggestions();
            }
        });

        // Keyboard navigation
        this.setupKeyboardNavigation();
        
        console.log("Event listeners setup complete");
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            const activeElement = document.activeElement;
            if (!activeElement.matches('#start_place, #end_place')) return;

            const fieldType = activeElement.id === 'start_place' ? 'start' : 'end';
            const suggestions = document.getElementById(`${fieldType}_suggestions`);
            const items = suggestions.querySelectorAll('li');
            
            if (items.length === 0) return;

            const activeIndex = Array.from(items).findIndex(item => 
                item.classList.contains('active'));

            let newIndex = -1;

            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    newIndex = activeIndex < items.length - 1 ? activeIndex + 1 : 0;
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    newIndex = activeIndex > 0 ? activeIndex - 1 : items.length - 1;
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (activeIndex >= 0) {
                        items[activeIndex].click();
                    }
                    return;
                case 'Escape':
                    this.hideSuggestions(fieldType);
                    return;
            }

            if (newIndex >= 0) {
                items.forEach(item => item.classList.remove('active'));
                items[newIndex].classList.add('active');
            }
        });
    }

    handleAutocomplete = this.debounce((query, fieldType) => {
        console.log(`Autocomplete for ${fieldType}:`, query);
        this.fetchSuggestions(query, fieldType);
    }, 300);

    debounce(func, delay) {
        return (...args) => {
            clearTimeout(this.debounceTimers[func]);
            this.debounceTimers[func] = setTimeout(() => func.apply(this, args), delay);
        };
    }

    async fetchSuggestions(query, fieldType) {
        if (!query || query.length < 2) {
            this.hideSuggestions(fieldType);
            return;
        }

        // Cancel previous request for this field
        if (this.activeRequests[fieldType]) {
            this.activeRequests[fieldType].abort();
            console.log(`Cancelled previous ${fieldType} request`);
        }

        try {
            this.showLoading(fieldType);
            
            const controller = new AbortController();
            this.activeRequests[fieldType] = controller;

            console.log(`Fetching suggestions for ${fieldType}:`, query);
            const response = await fetch(`/autocomplete?q=${encodeURIComponent(query)}`, {
                signal: controller.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const suggestions = await response.json();
            console.log(`Received ${suggestions.length} suggestions for ${fieldType}`);
            this.displaySuggestions(suggestions, fieldType);
            
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log(`Request aborted for ${fieldType}`);
            } else {
                console.error(`Error fetching ${fieldType} suggestions:`, error);
                this.showAlert('Failed to fetch location suggestions. Please try again.', 'error');
                this.hideSuggestions(fieldType);
            }
        } finally {
            delete this.activeRequests[fieldType];
        }
    }

    displaySuggestions(suggestions, fieldType) {
        const listId = `${fieldType}_suggestions`;
        const list = document.getElementById(listId);
        
        if (!suggestions || suggestions.length === 0) {
            list.innerHTML = '<li class="no-results">No locations found</li>';
            list.style.display = 'block';
            return;
        }

        list.innerHTML = suggestions.map(place => `
            <li data-full-name="${this.escapeHtml(place.full_name)}">
                <i class="fas fa-map-marker-alt"></i>
                ${this.escapeHtml(place.display_name)}
            </li>
        `).join('');

        // Add click handlers
        list.querySelectorAll('li').forEach(li => {
            li.addEventListener('click', () => {
                const input = document.getElementById(`${fieldType}_place`);
                const fullName = li.getAttribute('data-full-name');
                input.value = fullName;
                this.hideSuggestions(fieldType);
                input.focus();
                console.log(`Selected ${fieldType} location:`, fullName);
            });

            li.addEventListener('mouseenter', () => {
                list.querySelectorAll('li').forEach(item => item.classList.remove('active'));
                li.classList.add('active');
            });
        });

        list.style.display = 'block';
    }

    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    showLoading(fieldType) {
        const list = document.getElementById(`${fieldType}_suggestions`);
        list.innerHTML = '<li><div class="loading"></div> Searching...</li>';
        list.style.display = 'block';
    }

    hideSuggestions(fieldType) {
        const list = document.getElementById(`${fieldType}_suggestions`);
        list.innerHTML = '';
        list.style.display = 'none';
    }

    hideAllSuggestions() {
        this.hideSuggestions('start');
        this.hideSuggestions('end');
    }

    showAlert(message, type = 'error') {
        const container = document.getElementById('alertContainer');
        container.innerHTML = `
            <div class="alert ${type}">
                <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : 'check-circle'}"></i>
                ${message}
            </div>
        `;
        
        if (type === 'error') {
            setTimeout(() => {
                if (container.innerHTML.includes(message)) {
                    container.innerHTML = '';
                }
            }, 5000);
        }
    }

    async handleSubmit(e) {
        e.preventDefault();
        console.log("Form submitted");
        
        const formData = new FormData(e.target);
        
        if (!this.validateForm(formData)) {
            return;
        }

        await this.calculateAlarmTime(formData);
    }

    validateForm(formData) {
        const startPlace = formData.get('start_place').trim();
        const endPlace = formData.get('end_place').trim();
        const arrivalTime = formData.get('arrival_time');
        const gettingReady = formData.get('getting_ready');
        
        if (!startPlace || !endPlace || !arrivalTime || !gettingReady) {
            this.showAlert('Please fill in all required fields.');
            return false;
        }
        
        if (startPlace === endPlace) {
            this.showAlert('Start location and destination cannot be the same.');
            return false;
        }

        return true;
    }

    async calculateAlarmTime(formData) {
        const submitBtn = document.getElementById('submitBtn');
        const resultDiv = document.getElementById('result');
        
        // Update UI for loading state
        submitBtn.innerHTML = '<div class="loading"></div> Calculating...';
        submitBtn.disabled = true;
        resultDiv.style.display = 'none';
        this.hideAllSuggestions();

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);

            console.log("Sending calculation request...");
            const response = await fetch('/calculate', {
                method: 'POST',
                body: formData,
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log("Calculation response:", data);
            
            if (data.error) {
                this.showAlert(data.error);
            } else {
                this.displayResults(data);
                this.scheduleAlarm(data.alarm_time);
            }

        } catch (error) {
            if (error.name === 'AbortError') {
                this.showAlert('Request timed out. Please check your internet connection and try again.');
            } else {
                this.showAlert('An error occurred while calculating. Please try again.');
            }
            console.error('Calculation error:', error);
        } finally {
            submitBtn.innerHTML = '<i class="fas fa-calculator"></i><span>Calculate Alarm Time</span>';
            submitBtn.disabled = false;
        }
    }

    displayResults(data) {
        const resultDiv = document.getElementById('result');
        
        let comparisonHtml = '';
        if (data.current_alarm) {
            comparisonHtml = `
                <div class="time-comparison">
                    <div class="time-box current">
                        <div>Current Alarm</div>
                        <div class="time-value">${data.current_alarm}</div>
                    </div>
                    <div class="time-box new">
                        <div>Recommended Alarm</div>
                        <div class="time-value" style="color: var(--success);">${data.alarm_time}</div>
                    </div>
                </div>
            `;
        }

        resultDiv.innerHTML = `
            <div class="result-item">
                <div class="result-label"><i class="fas fa-flag-checkered"></i> Arrival Time</div>
                <div class="result-value">${data.arrival_time}</div>
            </div>
            <div class="result-item">
                <div class="result-label"><i class="fas fa-shower"></i> Getting Ready</div>
                <div class="result-value">${data.getting_ready} minutes</div>
            </div>
            <div class="result-item">
                <div class="result-label"><i class="fas fa-car"></i> Travel Time</div>
                <div class="result-value">${data.eta} minutes</div>
            </div>
            <div class="result-item">
                <div class="result-label"><i class="fas fa-shield-alt"></i> Safety Buffer</div>
                <div class="result-value">${data.margin} minutes</div>
            </div>
            ${comparisonHtml}
            <div class="final-alarm">
                <div class="result-label"><i class="fas fa-bell"></i> SET YOUR ALARM FOR</div>
                <div class="result-value">${data.alarm_time}</div>
            </div>
        `;
        
        resultDiv.style.display = 'block';
        resultDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        this.showAlert('Alarm time calculated successfully!', 'success');
    }

    scheduleAlarm(alarmTime) {
        const [hour, minute] = alarmTime.split(':').map(Number);
        const now = new Date();
        const alarmDate = new Date();
        
        alarmDate.setHours(hour, minute, 0, 0);
        
        // If alarm time has passed for today, schedule for tomorrow
        if (alarmDate <= now) {
            alarmDate.setDate(alarmDate.getDate() + 1);
        }
        
        const timeUntilAlarm = alarmDate.getTime() - now.getTime();
        
        if (timeUntilAlarm > 0 && timeUntilAlarm < 24 * 60 * 60 * 1000) {
            setTimeout(() => {
                this.triggerAlarm();
            }, timeUntilAlarm);
            
            console.log(`Alarm scheduled for ${alarmDate}`);
        }
    }

    triggerAlarm() {
        try {
            document.getElementById('alarmAudio').play();
            if (Notification.permission === 'granted') {
                new Notification('⏰ Smart Alarm', {
                    body: 'Time to wake up!',
                    icon: '/favicon.ico'
                });
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        new Notification('⏰ Smart Alarm', {
                            body: 'Time to wake up!',
                            icon: '/favicon.ico'
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Error triggering alarm:', error);
            alert('⏰ Wake up! Time to get ready!');
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new SmartAlarm();
});

// Request notification permission on load
if ('Notification' in window) {
    Notification.requestPermission();
}