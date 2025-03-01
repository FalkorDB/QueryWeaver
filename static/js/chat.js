const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
let history = [];
let currentRequestController = null;

// Custom delimiter that's unlikely to appear in your data
const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

function addMessage(message, isUser = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.textContent = message;
    history.push(message);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return messageDiv;
}

function initChat() {
    chatMessages.innerHTML = '';
    addMessage('Hello! How can I help you today?', false);
    history = [];
}

initChat();

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;
    
    // Cancel any ongoing request
    if (currentRequestController) {
        currentRequestController.abort();
    }
    
    // Add user message to chat
    addMessage(message, true);
    messageInput.value = '';
    
    // Show typing indicator
    typingIndicator.style.display = 'block';
    
    try {
        const selectedValue = document.getElementById("graph-select").value;
        
        // Create an AbortController for this request
        currentRequestController = new AbortController();
        
        // Use fetch with streaming response (GET method)
        const response = await fetch('/graphs/' + selectedValue + '?q=' + encodeURIComponent(message), {
            method: 'GET',
            signal: currentRequestController.signal
        });
        
        // Check if the response is ok
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }
        
        // Get the reader from the response body stream
        const reader = response.body.getReader();
        let decoder = new TextDecoder();
        let buffer = '';
        
        // Hide typing indicator once we start receiving data
        typingIndicator.style.display = 'none';
        
        // Process the stream
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                // Process any remaining data in the buffer
                if (buffer.trim()) {
                    try {
                        const step = JSON.parse(buffer);
                        addMessage(step.message || JSON.stringify(step), false);
                    } catch (e) {
                        // If it's not valid JSON, just show it as text
                        addMessage(buffer, false);
                    }
                }
                break;
            }
            
            // Decode the chunk and add it to our buffer
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            
            // Process complete message objects from the buffer using custom delimiter
            let delimiterIndex;
            while ((delimiterIndex = buffer.indexOf(MESSAGE_DELIMITER)) !== -1) {
                const message = buffer.slice(0, delimiterIndex).trim();
                buffer = buffer.slice(delimiterIndex + MESSAGE_DELIMITER.length);
                
                if (!message) continue; // Skip empty messages
                
                try {
                    // Try to parse as JSON
                    const step = JSON.parse(message);
                    
                    // Handle different types of messages from server
                    if (step.type === 'reasoning_step') {
                        addMessage(step.message, false);
                    } else if (step.type === 'final_result') {
                        // Final result could be displayed differently
                        addMessage(step.message || JSON.stringify(step.data, null, 2), false);
                    } else if (step.type === 'followup_questions') {
                        step.questions.forEach(question => {
                            addMessage(question, false);
                        });
                    } else {
                        // Default handling
                        addMessage(step.message || JSON.stringify(step), false);
                    }
                } catch (e) {
                    // If it's not valid JSON, just show the message as text
                    addMessage(message, false);
                }
            }
        }
        
        currentRequestController = null;
        
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was aborted');
        } else {
            console.error('Error:', error);
            typingIndicator.style.display = 'none';
            addMessage('Sorry, there was an error processing your message: ' + error.message, false);
        }
        currentRequestController = null;
    }
}

// Event listeners
sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const chatMessages = document.getElementById("chat-messages");
    const graphSelect = document.getElementById("graph-select");
    
    fetch("/graphs")
        .then(response => response.json())
        .then(data => {
            graphSelect.innerHTML = "";
            data.forEach(graph => {
                const option = document.createElement("option");
                option.value = graph;
                option.textContent = graph;
                graphSelect.appendChild(option);
            });
        })
        .catch(error => console.error("Error fetching graphs:", error));
    
    graphSelect.addEventListener("change", function () {
        initChat();
    });
});