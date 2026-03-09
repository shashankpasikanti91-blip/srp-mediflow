// Get current time
function getTime() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const mins = String(now.getMinutes()).padStart(2, '0');
    return `${hours}:${mins}`;
}

let currentLanguage = 'en';
let sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

// Language switcher
function switchLanguage(lang) {
    currentLanguage = lang;
    
    // Update language button active state
    const langBtns = document.querySelectorAll('.lang-btn');
    langBtns.forEach(btn => btn.classList.remove('active'));
    
    // Set language for voice recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition && window.recognition) {
        if (lang === 'te') {
            window.recognition.lang = 'te-IN';
        } else if (lang === 'hi') {
            window.recognition.lang = 'hi-IN';
        } else {
            window.recognition.lang = 'en-IN';
        }
    }
    
    // Add visual indicator
    event.target.classList.add('active');
}

// Send message to chatbot
async function sendMessage(msg = null) {
    const input = document.getElementById('messageInput');
    const message = msg || input.value.trim();
    
    // Validate message
    if (!message || message.length === 0) {
        console.warn('Empty message, not sending');
        return;
    }
    
    console.log('Sending message:', message);
    
    // Clear input
    input.value = '';
    
    // Add user message to chat
    addMessage(message, 'user');
    
    try {
        // Send to server with session ID
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: message,
                session_id: sessionId
            })
        });
        
        console.log('Response status:', response.status);
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data && data.message) {
            // Add bot response
            console.log('Adding bot message:', data.message);
            addMessage(data.message, 'bot');
        } else if (data && data.error) {
            console.error('Server error:', data.error);
            addMessage(`Error: ${data.error}`, 'bot');
        } else {
            // Fallback if response is malformed
            console.warn('Unexpected response format:', data);
            addMessage('Sorry, I did not understand that properly. Please try again.', 'bot');
        }
    } catch (error) {
        console.error('Fetch error:', error);
        addMessage('Sorry, I encountered an error. Please try again.', 'bot');
    }
}

// Add message to chat
function addMessage(text, sender) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const p = document.createElement('p');
    p.textContent = text;
    
    const small = document.createElement('small');
    small.textContent = getTime();
    
    messageDiv.appendChild(p);
    messageDiv.appendChild(small);
    
    container.appendChild(messageDiv);
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Handle Enter key
function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

// Open register form
function openRegisterForm() {
    document.getElementById('registerModal').style.display = 'block';
}

// Close register form
function closeRegisterForm() {
    document.getElementById('registerModal').style.display = 'none';
}

// Submit register form
async function submitRegisterForm(event) {
    event.preventDefault();
    
    const form = document.getElementById('registerForm');
    const formData = new FormData(form);
    const data = Object.fromEntries(formData);
    
    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.status === 'ok') {
            addMessage('Your OPD registration is confirmed! Our team will contact you soon.', 'bot');
            closeRegisterForm();
            form.reset();
        } else {
            alert('Registration failed: ' + result.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error submitting form');
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('registerModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}

// Focus input on load
window.addEventListener('load', function() {
    document.getElementById('messageInput').focus();
    initVoiceChat();
});

// ============= VOICE CHAT FEATURE WITH KIE AI =============
function initVoiceChat() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceStatus = document.getElementById('voiceStatus');
    const messageInput = document.getElementById('messageInput');
    
    if (!voiceBtn) return;
    
    // Check if browser supports Web Speech API
    if (!SpeechRecognition) {
        console.log('Speech Recognition not supported in this browser');
        voiceBtn.title = 'Voice recognition not available in this browser';
        voiceBtn.style.opacity = '0.5';
        voiceBtn.disabled = true;
        return;
    }
    
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-IN';
    
    // Store in global scope for language switching
    window.recognition = recognition;
    
    let isListening = false;
    
    voiceBtn.textContent = 'Speak';
    voiceBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!isListening) {
            try {
                recognition.start();
                voiceBtn.classList.add('listening');
                voiceStatus.textContent = 'Listening with Web Speech API...';
                isListening = true;
            } catch (e) {
                console.error('Error starting recognition:', e);
                voiceStatus.textContent = 'Error: Try again';
            }
        } else {
            recognition.stop();
            voiceBtn.classList.remove('listening');
            isListening = false;
        }
    });
    
    recognition.onstart = () => {
        voiceBtn.classList.add('listening');
        voiceStatus.textContent = 'Listening...';
    };
    
    recognition.onresult = (event) => {
        console.log('onresult event:', event);
        console.log('results length:', event.results.length);
        
        let interim = '';
        let final = '';
        let hasFinal = false;
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            // FIX: Access transcript from result[0], not result.transcript
            const transcript = result[0].transcript || '';
            const isFinal = result.isFinal;
            
            console.log(`Result ${i}:`, transcript, 'isFinal:', isFinal);
            
            if (isFinal) {
                final += transcript + ' ';
                hasFinal = true;
            } else {
                interim += transcript;
            }
        }
        
        console.log('final text:', final);
        console.log('interim text:', interim);
        
        // ONLY process if we have a final result
        if (hasFinal && final && final.trim().length > 0) {
            const finalText = final.trim();
            messageInput.value = finalText;
            voiceStatus.textContent = 'Understood: ' + finalText;
            console.log('Calling sendMessage with:', finalText);
            // Stop recognition immediately
            try {
                recognition.stop();
            } catch(e) {
                // Already stopped
            }
            // Send IMMEDIATELY without delay
            sendMessage(finalText);
        } else if (interim && interim.trim().length > 0) {
            // Show interim results while listening
            messageInput.value = interim;
            voiceStatus.textContent = 'Hearing: ' + interim;
        }
    };
    
    recognition.onerror = (event) => {
        let errorMsg = 'Error: ';
        if (event.error === 'no-speech') {
            errorMsg += 'No speech detected. Please try again.';
        } else if (event.error === 'network') {
            errorMsg += 'Network error. Check your connection.';
        } else if (event.error === 'not-allowed') {
            errorMsg += 'Microphone access denied.';
        } else {
            errorMsg += event.error;
        }
        voiceStatus.textContent = errorMsg;
        voiceBtn.classList.remove('listening');
        isListening = false;
    };
    
    recognition.onend = () => {
        voiceBtn.classList.remove('listening');
        isListening = false;
        setTimeout(() => {
            if (voiceStatus.textContent && voiceStatus.textContent.startsWith('Understood')) {
                // Keep message visible
            } else {
                voiceStatus.textContent = '';
            }
        }, 2000);
    };
}
