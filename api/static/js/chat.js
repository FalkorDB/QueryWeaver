const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const newChatButton = document.getElementById('new-chat-button');
const analysisCheckbox = document.getElementById('analysis-checkbox');
const analysisContainer = document.getElementById('analysis-container');
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
const expValue = document.getElementById('exp-value');
const confValue = document.getElementById('conf-value');
const missValue = document.getElementById('miss-value');
const ambValue = document.getElementById('amb-value');
const instrucitonsContainer = document.getElementById('instructions-container');
const instructionsCheckbox = document.getElementById('instructions-checkbox');
const expInstructions = document.getElementById('exp-instructions');

let questions_history = [];
let currentRequestController = null;

// Custom delimiter that's unlikely to appear in your data
const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

const urlParams = new URLSearchParams(window.location.search);

const TOKEN = urlParams.get('token');

function addMessage(message, isUser = false, isFollowup = false, isFinalResult = false) {
    const messageDiv = document.createElement('div');
    if (isFollowup) {
        messageDiv.className = "message followup-message";
        messageDiv.textContent = message;
    }
    else if (isUser) {
        messageDiv.className = "message user-message";
        questions_history.push(message);
    }
    else if (isFinalResult) {
        messageDiv.className = "message final-result-message";
        // messageDiv.textContent = message;
    }
    else {
        messageDiv.className = "message bot-message";
    }
    ;

    const block = formatBlock(message)
    if (block) {
        block.forEach(lineDiv => {
            messageDiv.appendChild(lineDiv);
        });
    }
    else {
        messageDiv.textContent = message;
    }

    chatMessages.appendChild(messageDiv);
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
    // debugger
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
    typingIndicator.style.display = 'flex';

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

        let streamListining = true;
        // Process the stream
        while (streamListining) {
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
                        let confValueDiv = document.getElementById("conf-value-div");
                        let confValueTitle = document.getElementById("conf-value-title");
                        
                        if (!confValueDiv) {
                            confValueDiv = document.createElement("div");
                            confValueDiv.id = "conf-value-div";
                            confValue.appendChild(confValueDiv);
                        }

                        if (!confValueTitle) {
                            confValueTitle = document.createElement("div");
                            confValueTitle.id = "conf-value-title";
                            confValue.appendChild(confValueTitle);
                        }

                        confValueTitle.textContent = `${step.conf}%`;
                        confValueDiv.style.background = getBackgroundStyle(step.conf);
                        console.log(step);
                        [[step.exp, expValue], [step.miss, missValue], [step.amb, ambValue]].forEach(([value, element]) => {
                            if (!value || typeof value == "object") return;
                            let ul = document.getElementById(`${element.id}-list`);

                            if (!ul) {
                                ul = document.createElement("ul");
                                ul.className = `final-result-list`;
                                ul.id = `${element.id}-list`;
                                element.appendChild(ul);
                            }

                            value.split('-').forEach((item, i) => {
                                if (item === '') return;

                                let li = document.getElementById(`${element.id}-${i}-li`);

                                if (!li) {
                                    li = document.createElement("li");
                                    li.id = `${element.id}-${i}-li`;
                                    ul.appendChild(li);
                                }

                                li.textContent = i === 0 ? `${item}` : `- ${item}`;
                            });
                        })
                        if (!step.data) {
                            step.data = "Unfortunately, an SQL query could not be created based on the extracted tables and your instructions. Please see the Explanation for more details.";
                            addMessage(step.message || JSON.stringify(step.data, null, 2), false, true);
                        }
                        else addMessage(step.message || JSON.stringify(step.data, null, 2), false, false, true);
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
                    } else if (step.type === 'error') {
                        addMessage(step.message || JSON.stringify(step), false, true);
                        streamListining = false;
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
            // typingIndicator.style.display = 'none';
            addMessage('Sorry, there was an error processing your message: ' + error.message, false);
        }
        currentRequestController = null;
    } finally {
                    // Hide typing indicator once we start receiving data
                    typingIndicator.style.display = 'none';
                }
}

function handleShowAnalysis(e) {
    if (e.target.checked) {
        analysisContainer.style.display = 'flex';
    } else {
        analysisContainer.style.display = 'none';
    }
}

function handleShowInstructions(e) {
    if (e.target.checked) {
        instrucitonsContainer.style.display = 'flex';
    } else {
        instrucitonsContainer.style.display = 'none';
    }
}

function handleInstructionsChange(e) {
    console.log(e.target.value);
}

// Event listeners
sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

analysisCheckbox.addEventListener('change', handleShowAnalysis);
instructionsCheckbox.addEventListener('change', handleShowInstructions);
expInstructions.addEventListener('change', handleInstructionsChange);
newChatButton.addEventListener('click', initChat);



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

// Add file upload functionality
document.getElementById('upload-button').addEventListener('click', function () {
    document.getElementById('file-upload').click();
});

document.getElementById('file-upload').addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    // document.getElementById('file-name').textContent = file.name;

    const formData = new FormData();
    formData.append('file', file);

    fetch("/graphs?token=" + TOKEN, {
        method: 'POST',
        body: formData, // ✅ Correct, no need to set Content-Type manually
    }).then(response => {
        response.json()
    }).then(data => {
        console.log('File uploaded successfully', data);
    }).catch(error => {
        console.error('Error uploading file:', error);
        addMessage('Sorry, there was an error uploading your file: ' + error.message, false);
    });
});