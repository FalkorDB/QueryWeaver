const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');

let history = []

function addMessage(message, isUser = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.textContent = message;
    history.push(message);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
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

    // Add user message to chat
    addMessage(message, true);
    messageInput.value = '';

    // Show typing indicator
    typingIndicator.style.display = 'block';

    try {
        const selectedValue = document.getElementById("graph-select").value;

        // Send message to Flask backend
        const response = await fetch('/graph/' + selectedValue + '?q='+ message);

        const data = await response.json();

        // Hide typing indicator
        typingIndicator.style.display = 'none';

        followup_questions = data[0].followup_questions
        if( followup_questions) {
            followup_questions.forEach( (element) => {
                addMessage(element);
            });
        } else {
            // Add bot response to chat
            addMessage(JSON.stringify(data));
        }
    } catch (error) {
        console.error('Error:', error);
        typingIndicator.style.display = 'none';
        addMessage('Sorry, there was an error processing your message.', false);
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