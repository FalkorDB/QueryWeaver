const messageInput = document.getElementById('message-input');
const submitButton = document.getElementById('submit-button');
const pauseButton = document.getElementById('pause-button');
const newChatButton = document.getElementById('reset-button');
const chatMessages = document.getElementById('chat-messages');
const expValue = document.getElementById('exp-value');
const confValue = document.getElementById('conf-value');
const missValue = document.getElementById('info-value');
const ambValue = document.getElementById('amb-value');
const fileUpload = document.getElementById('schema-upload');
const fileLabel = document.getElementById('custom-file-upload');
const sideMenuButton = document.getElementById('side-menu-button');
const menuButton = document.getElementById('menu-button');
const menuContainer = document.getElementById('menu-container');
const chatContainer = document.getElementById('chat-container');
const suggestionsContainer = document.getElementById('suggestions-container');
const expInstructions = document.getElementById('instructions-textarea');
const inputContainer = document.getElementById('input-container');



let questions_history = [];
let currentRequestController = null;

// Custom delimiter that's unlikely to appear in your data
const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

const urlParams = new URLSearchParams(window.location.search);

const TOKEN = urlParams.get('token');

function addMessage(message, isUser = false, isFollowup = false, isFinalResult = false) {
    const messageDiv = document.createElement('div');
    const messageDivContainer = document.createElement('div');

    messageDiv.className = "message";
    messageDivContainer.className = "message-container";

    if (isFollowup) {
        messageDivContainer.className += " followup-message-container";
        messageDiv.className += " followup-message";
        messageDiv.textContent = message;
    } else if (isUser) {
        suggestionsContainer.style.display = 'none';
        messageDivContainer.className += " user-message-container";
        messageDiv.className += " user-message";
        questions_history.push(message);
    } else if (isFinalResult) {
        messageDivContainer.className += " final-result-message-container";
        messageDiv.className += " final-result-message";
        // messageDiv.textContent = message;
    } else {
        messageDivContainer.className += " bot-message-container";
        messageDiv.className += " bot-message";
    }

    const block = formatBlock(message)
    if (block) {
        block.forEach(lineDiv => {
            messageDiv.appendChild(lineDiv);
        });
    }
    else {
        messageDiv.textContent = message;
    }

    messageDivContainer.appendChild(messageDiv);
    chatMessages.appendChild(messageDivContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return messageDiv;
}

function formatBlock(text) {

    if (text.startsWith('"```sql') && text.endsWith('```"')) {
        const sql = text.slice(7, -4).trim();
        return sql.split('\\n').map((line, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'sql-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }

    if (text.includes('[') && text.includes(']')) {
        const parts = text.split('[');
        const formattedParts = parts.map((part, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'array-line';

            // remove all closing if exists in the text
            part = part.replaceAll(']', '');

            lineDiv.textContent = part;
            return lineDiv;
        });
        return formattedParts;
    }
}

function initChat() {
    chatMessages.innerHTML = '';
    addMessage('Hello! How can I help you today?', false);
    suggestionsContainer.style.display = 'flex';
    questions_history = [];
}

initChat();

const getBackgroundStyle = (value) => {
    return `linear-gradient(to right,
    var(--falkor-primary) 0%,
    var(--falkor-primary) ${value}%,
    white ${value}%,
    white 100%)`
}

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
    inputContainer.classList.add('loading');
    submitButton.style.display = 'none';
    pauseButton.style.display = 'block';

    try {
        const selectedValue = document.getElementById("graph-select").value;

        // Create an AbortController for this request
        currentRequestController = new AbortController();

        // Use fetch with streaming response (GET method)
        const response = await fetch('/graphs/' + selectedValue + '?q=' + encodeURIComponent(message) + '&token=' + TOKEN, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chat: questions_history,
                instructions: expInstructions.value,
            }),
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
        inputContainer.classList.remove('loading');
        submitButton.style.display = 'block';
        pauseButton.style.display = 'none';

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
                    debugger;
                    // Try to parse as JSON
                    const step = JSON.parse(message);

                    // Handle different types of messages from server
                    if (step.type === 'reasoning_step') {
                        addMessage(step.message, false);
                    } else if (step.type === 'final_result') {
                        // Final result could be displayed differently
                        confValue.textContent = `${step.conf}%`;

                        [[step.exp, expValue], [step.miss, missValue], [step.amb, ambValue]].forEach(([value, element]) => {
                            element.innerHTML = '';
                            let ul = document.getElementById(`${element.id}-list`);

                            ul = document.createElement("ul");
                            ul.className = `final-result-list`;
                            ul.id = `${element.id}-list`;
                            element.appendChild(ul);

                            value.split('-').forEach((item, i) => {
                                if (item === '') return;

                                let li = document.getElementById(`${element.id}-${i}-li`);

                                li = document.createElement("li");
                                li.id = `${element.id}-${i}-li`;
                                ul.appendChild(li);

                                li.textContent = i === 0 ? `${item}` : `- ${item}`;
                            });
                        })

                        addMessage(step.message || JSON.stringify(step.data, null, 2), false, false, true);
                    } else if (step.type === 'followup_questions') {
                        // step.questions.forEach(question => {
                        //     addMessage(question, false);
                        // });
                        expValue.textContent = "N/A";
                        confValue.textContent = "N/A";
                        missValue.textContent = "N/A";
                        ambValue.textContent = "N/A";
                        // graph.Labels.findIndex(l => l.name === cat.name)(step.message, false, true);
                        addMessage(step.message, false, true);
                    } else {
                        // Default handling
                        addMessage(step.message || JSON.stringify(step), false);
                    }
                } catch (e) {
                    // If it's not valid JSON, just show the message as text
                    addMessage("Faild: " + message, false);
                }

            }
        }

        currentRequestController = null;

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was aborted');
        } else {
            console.error('Error:', error);
            inputContainer.classList.remove('loading');
            submitButton.style.display = 'block';
            pauseButton.style.display = 'none';
            addMessage('Sorry, there was an error processing your message: ' + error.message, false);
        }
        currentRequestController = null;
    }
}

function toggleMenu() {
    if (!menuContainer.classList.contains('open')) {
        menuContainer.classList.add('open');
        sideMenuButton.style.display = 'none';
        chatContainer.style.paddingRight = '10%';
        chatContainer.style.paddingLeft = '10%';
    } else {
        menuContainer.classList.remove('open');
        sideMenuButton.style.display = 'block';
        chatContainer.style.paddingRight = '20%';
        chatContainer.style.paddingLeft = '20%';
    }
}

// Event listeners
submitButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

menuButton.addEventListener('click', toggleMenu);

sideMenuButton.addEventListener('click', toggleMenu);

newChatButton.addEventListener('click', initChat);

for (let i = 0; i < suggestionsContainer.children.length; i++) {
    const item = suggestionsContainer.children.item(i).children.item(0);

    item.addEventListener('click', () => {
        messageInput.value = item.textContent;
    });
}

document.addEventListener("DOMContentLoaded", function () {
    const chatMessages = document.getElementById("chat-messages");
    const graphSelect = document.getElementById("graph-select");

    fetch("/graphs?token=" + TOKEN)
        .then(response => response.json())
        .then(data => {
            graphSelect.innerHTML = "";
            data.forEach(graph => {
                const option = document.createElement("option");
                option.value = graph;
                option.textContent = graph;
                option.title = graph;
                graphSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error("Error fetching graphs:", error);
            addMessage("Sorry, there was an error fetching the available graphs: " + error.message, false);
        });

    graphSelect.addEventListener("change", function () {
        initChat();
    });
});