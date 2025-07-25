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
const suggestionItems = document.querySelectorAll('.suggestion-item');

let questions_history = [];
let result_history = [];
let currentRequestController = null;

// Custom delimiter that's unlikely to appear in your data
const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

const urlParams = new URLSearchParams(window.location.search);

const TOKEN = urlParams.get('token');

function addMessage(message, isUser = false, isFollowup = false, isFinalResult = false, isLoading = false, userInfo = null) {
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
        
        // Add user profile image if userInfo is provided
        if (userInfo && userInfo.picture) {
            const userAvatar = document.createElement('img');
            userAvatar.src = userInfo.picture;
            userAvatar.alt = userInfo.name || 'User';
            userAvatar.className = 'user-message-avatar';
            messageDivContainer.appendChild(userAvatar);
            messageDivContainer.classList.add('has-avatar');
        }
        
        questions_history.push(message);
    } else if (isFinalResult) {
        result_history.push(message);
        messageDivContainer.className += " final-result-message-container";
        messageDiv.className += " final-result-message";
        // messageDiv.textContent = message;
    } else {
        messageDivContainer.className += " bot-message-container";
        messageDiv.className += " bot-message";
        if (isLoading) {
            messageDivContainer.id = "loading-message-container";
            messageDivContainer.className += " loading-message-container";
        }
    }

    const block = formatBlock(message)

    if (block) {
        block.forEach(lineDiv => {
            messageDiv.appendChild(lineDiv);
        });
    } else if (!isLoading) {
        messageDiv.textContent = message;
    }

    if (!isLoading) {
        messageDivContainer.appendChild(messageDiv);
    }
    chatMessages.appendChild(messageDivContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return messageDiv;
}

function removeLoadingMessage() {
    const loadingMessageContainer = document.getElementById("loading-message-container");
    if (loadingMessageContainer) {
        loadingMessageContainer.remove();
    }
}

function moveLoadingMessageToBottom() {
    const loadingMessageContainer = document.getElementById("loading-message-container");
    if (loadingMessageContainer) {
        // Remove from current position and append to bottom
        loadingMessageContainer.remove();
        chatMessages.appendChild(loadingMessageContainer);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function formatBlock(text) {
    // Remove surrounding quotes if present
    text = text.replace(/^"(.*)"$/, '$1').trim();

    // SQL block
    if (text.startsWith('```sql') && text.endsWith('```')) {
        const sql = text.slice(6, -3).trim();
        return sql.split('\n').map((line, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'sql-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }

    // Array block
    if (text.includes('[') && text.includes(']')) {
        const parts = text.split('[');
        const formattedParts = parts.map((part, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'array-line';
            part = part.replaceAll(']', '');
            lineDiv.textContent = part;
            return lineDiv;
        });
        return formattedParts;
    }

    // Generic multi-line block (replace \n with real newlines first)
    text = text.replace(/\\n/g, '\n');
    if (text.includes('\n')) {
        return text.split('\n').map((line, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'plain-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }
    if (text.includes('\n')) {
        return text.split('\n').map((line, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'plain-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }
    if (text.includes('\n')) {
        return text.split('\n').map((line, i) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'plain-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }
}

function initChat() {
    messageInput.value = '';
    suggestionItems.forEach(item => {
        item.classList.remove('active');
    });
    chatMessages.innerHTML = '';
    [confValue, expValue, missValue, ambValue].forEach((element) => {
        element.innerHTML = '';
    });
    addMessage('Hello! How can I help you today?', false);
    suggestionsContainer.style.display = 'flex';
    questions_history = [];
    result_history = [];
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
    addMessage(message, true, false, false, false, window.currentUser);
    messageInput.value = '';

    // Show typing indicator
    inputContainer.classList.add('loading');
    submitButton.style.display = 'none';
    pauseButton.style.display = 'block';
    newChatButton.disabled = true;
    addMessage("", false, false, false, true);

    [confValue, expValue, missValue, ambValue].forEach((element) => {
        element.innerHTML = '';
    });

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
                result: result_history,
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
                        // Move loading message to bottom when we receive reasoning steps
                        addMessage(step.message, false);
                        moveLoadingMessageToBottom();
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

                        let message = step.message || JSON.stringify(step.data, null, 2);
                        if (step.is_valid){
                            addMessage(message, false, false, true);
                        } else {
                            addMessage("Sorry, we couldn't generate a valid SQL query. Please try rephrasing your question or add more details. For help, check the explanation window.", false, true);
                        }
                    } else if (step.type === 'followup_questions') {
                        expValue.textContent = "N/A";
                        confValue.textContent = "N/A";
                        missValue.textContent = "N/A";
                        ambValue.textContent = "N/A";
                        // graph.Labels.findIndex(l => l.name === cat.name)(step.message, false, true);
                        addMessage(step.message, false, true);
                    } else if (step.type === 'query_result') {
                        // Handle query result
                        if (step.data) {
                            addMessage(`Query Result: ${JSON.stringify(step.data)}`, false, false, true);
                        } else {
                            addMessage("No results found for the query.", false);
                        }
                    } else if (step.type === 'ai_response') {
                        // Handle AI-generated user-friendly response
                        addMessage(step.message, false, false, true);
                    } else if (step.type === 'destructive_confirmation') {
                        // Handle destructive operation confirmation request
                        addDestructiveConfirmationMessage(step);
                    } else if (step.type === 'operation_cancelled') {
                        // Handle cancelled operation
                        addMessage(step.message, false, true);
                    } else {
                        // Default handling
                        addMessage(step.message || JSON.stringify(step), false);
                    }
                    if (step.type !== 'reasoning_step') {
                        inputContainer.classList.remove('loading');
                        submitButton.style.display = 'block';
                        pauseButton.style.display = 'none';
                        newChatButton.disabled = false;
                        removeLoadingMessage();
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
            newChatButton.disabled = false;
            removeLoadingMessage();
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

function pauseRequest() {
    if (currentRequestController) {
        // Abort the current request
        currentRequestController.abort();
        currentRequestController = null;
        
        // Reset UI state
        inputContainer.classList.remove('loading');
        submitButton.style.display = 'block';
        pauseButton.style.display = 'none';
        newChatButton.disabled = false;
        
        // Remove loading message
        removeLoadingMessage();
        
        // Add a message indicating the request was paused
        addMessage("Request was paused by user.", false, true);
        
        // Show suggestions again since we're ready for new input
        suggestionsContainer.style.display = 'flex';
    }
}

function addDestructiveConfirmationMessage(step) {
    const messageDiv = document.createElement('div');
    const messageDivContainer = document.createElement('div');
    
    messageDivContainer.className = "message-container bot-message-container destructive-confirmation-container";
    messageDiv.className = "message bot-message destructive-confirmation-message";
    
    // Generate a unique ID for this confirmation dialog
    const confirmationId = 'confirmation-' + Date.now();
    
    // Create the confirmation UI
    const confirmationHTML = `
        <div class="destructive-confirmation" data-confirmation-id="${confirmationId}">
            <div class="confirmation-text">${step.message.replace(/\n/g, '<br>')}</div>
            <div class="confirmation-buttons">
                <button class="confirm-btn danger" onclick="handleDestructiveConfirmation('CONFIRM', '${step.sql_query.replace(/'/g, "\\'")}', '${confirmationId}')">
                    CONFIRM - Execute Query
                </button>
                <button class="cancel-btn" onclick="handleDestructiveConfirmation('CANCEL', '${step.sql_query.replace(/'/g, "\\'")}', '${confirmationId}')">
                    CANCEL - Abort Operation
                </button>
            </div>
        </div>
    `;
    
    messageDiv.innerHTML = confirmationHTML;
    
    messageDivContainer.appendChild(messageDiv);
    chatMessages.appendChild(messageDivContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Disable the main input while waiting for confirmation
    messageInput.disabled = true;
    submitButton.disabled = true;
}

async function handleDestructiveConfirmation(confirmation, sqlQuery, confirmationId) {
    // Find the specific confirmation dialog using the unique ID
    const confirmationDialog = document.querySelector(`[data-confirmation-id="${confirmationId}"]`);
    if (confirmationDialog) {
        // Disable both confirmation buttons within this specific dialog
        const confirmBtn = confirmationDialog.querySelector('.confirm-btn');
        const cancelBtn = confirmationDialog.querySelector('.cancel-btn');
        if (confirmBtn) confirmBtn.disabled = true;
        if (cancelBtn) cancelBtn.disabled = true;
    }
    
    // Re-enable the input
    messageInput.disabled = false;
    submitButton.disabled = false;
    
    // Add user's choice as a message
    addMessage(`User choice: ${confirmation}`, true, false, false, false, window.currentUser);
    
    if (confirmation === 'CANCEL') {
        addMessage("Operation cancelled. The destructive SQL query was not executed.", false, true);
        return;
    }
    
    // If confirmed, send confirmation to server
    try {
        const selectedValue = document.getElementById("graph-select").value;
        
        const response = await fetch('/graphs/' + selectedValue + '/confirm', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                confirmation: confirmation,
                sql_query: sqlQuery,
                chat: questions_history
            })
        });
        
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }
        
        // Process the streaming response
        const reader = response.body.getReader();
        let decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                if (buffer.trim()) {
                    try {
                        const step = JSON.parse(buffer);
                        addMessage(step.message || JSON.stringify(step), false);
                    } catch (e) {
                        addMessage(buffer, false);
                    }
                }
                break;
            }
            
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            
            let delimiterIndex;
            while ((delimiterIndex = buffer.indexOf(MESSAGE_DELIMITER)) !== -1) {
                const message = buffer.slice(0, delimiterIndex).trim();
                buffer = buffer.slice(delimiterIndex + MESSAGE_DELIMITER.length);
                
                if (!message) continue;
                
                try {
                    const step = JSON.parse(message);
                    
                    if (step.type === 'reasoning_step') {
                        addMessage(step.message, false);
                    } else if (step.type === 'query_result') {
                        if (step.data) {
                            addMessage(`Query Result: ${JSON.stringify(step.data)}`, false, false, true);
                        } else {
                            addMessage("No results found for the query.", false);
                        }
                    } else if (step.type === 'ai_response') {
                        addMessage(step.message, false, false, true);
                    } else if (step.type === 'error') {
                        addMessage(`Error: ${step.message}`, false, true);
                    } else {
                        addMessage(step.message || JSON.stringify(step), false);
                    }
                } catch (e) {
                    addMessage("Failed: " + message, false);
                }
            }
        }
        
    } catch (error) {
        console.error('Error:', error);
        addMessage('Sorry, there was an error processing the confirmation: ' + error.message, false);
    }
}

// Event listeners
submitButton.addEventListener('click', sendMessage);
pauseButton.addEventListener('click', pauseRequest);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

messageInput.addEventListener('input', (e) => {
    suggestionItems.forEach(item => {
        if (e.target.value && item.querySelector('p').textContent === e.target.value) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
})

menuButton.addEventListener('click', toggleMenu);

sideMenuButton.addEventListener('click', toggleMenu);

newChatButton.addEventListener('click', initChat);

// Add event listener to each suggestion item
suggestionItems.forEach(item => {
    item.addEventListener('click', () => {
        // Set the value of the message input to the text of the clicked suggestion item
        const text = item.querySelector('p').textContent;
        messageInput.value = text;
        // Remove 'active' from all suggestion items
        document.querySelectorAll('.suggestion-item.active').forEach(item => {
            item.classList.remove('active');
        });
        // Add 'active' to the clicked suggestion item
        item.classList.add('active');
    });
});

document.addEventListener("DOMContentLoaded", function () {
    const chatMessages = document.getElementById("chat-messages");
    const graphSelect = document.getElementById("graph-select");

    // Fetch available graphs
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

            // Fetch suggestions for the first graph (if any)
            if (data.length > 0) {
                fetchSuggestions();
            }
        })
        .catch(error => {
            console.error("Error fetching graphs:", error);
            addMessage("Sorry, there was an error fetching the available graphs: " + error.message, false);
        });

    // Function to fetch suggestions based on selected graph
    function fetchSuggestions() {
        const graphSelect = document.getElementById("graph-select");
        const selectedGraph = graphSelect.value;

        if (!selectedGraph) {
            // Hide suggestions if no graph is selected
            suggestionItems.forEach(item => {
                item.style.display = 'none';
            });
            return;
        }

        suggestionItems.forEach(item => {
            item.style.display = 'flex';
            item.classList.remove('loaded');
            item.classList.add('loading');
            const button = item.querySelector('button');
            const p = item.querySelector('p');
            button.title = "Loading suggestion...";
            p.textContent = "";
        });

        // Fetch suggestions for the selected graph
        fetch(`/suggestions?token=${TOKEN}&graph_id=${selectedGraph}`)
            .then(response => response.json())
            .then(suggestions => {
                // If no suggestions for this graph, hide the suggestions
                if (!suggestions || suggestions.length === 0) {
                    suggestionItems.forEach(item => {
                        item.style.display = 'none';
                    });
                    return;
                }

                // Hide unused suggestion slots
                for (let i = suggestions.length; i < suggestionItems.length; i++) {
                    suggestionItems[i].style.display = 'none';
                }

                // Update each suggestion with fetched data and add loaded styling
                suggestions.forEach((suggestion, index) => {
                    if (suggestionItems[index]) {
                        const item = suggestionItems[index];
                        const button = item.querySelector('button');
                        const p = item.querySelector('p');

                        // Add a slight delay for staggered animation
                        setTimeout(() => {
                            // Remove loading state and add content
                            item.classList.remove('loading');
                            item.classList.add('loaded');

                            // Update content
                            p.textContent = suggestion;
                            button.title = suggestion;

                            // Enable click functionality
                            button.style.cursor = 'pointer';
                        }, index * 300); // 300ms delay between each suggestion
                    }
                });
            })
            .catch(error => {
                console.error("Error fetching suggestions:", error);

                // Hide suggestions on error
                suggestionItems.forEach(item => {
                    item.style.display = 'none';
                });
            });
    }

    graphSelect.addEventListener("change", function () {
        initChat();
        fetchSuggestions(); // Fetch new suggestions when graph changes
    });
});


fileUpload.addEventListener('change', function (e) {
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

document.addEventListener('DOMContentLoaded', function() {
    // Authentication modal logic
    var isAuthenticated = window.isAuthenticated !== undefined ? window.isAuthenticated : false;
    var googleLoginModal = document.getElementById('google-login-modal');
    var container = document.getElementById('container');
    if (googleLoginModal && container) {
        if (!isAuthenticated) {
            googleLoginModal.style.display = 'flex';
            container.style.filter = 'blur(2px)';
        } else {
            googleLoginModal.style.display = 'none';
            container.style.filter = '';
        }
    }
    // Postgres modal logic
    var pgModal = document.getElementById('pg-modal');
    var openPgModalBtn = document.getElementById('open-pg-modal');
    var cancelPgModalBtn = document.getElementById('pg-modal-cancel');
    var connectPgModalBtn = document.getElementById('pg-modal-connect');
    var pgUrlInput = document.getElementById('pg-url-input');
    if (openPgModalBtn && pgModal) {
        openPgModalBtn.addEventListener('click', function() {
            pgModal.style.display = 'flex';
        });
    }
    if (cancelPgModalBtn && pgModal) {
        cancelPgModalBtn.addEventListener('click', function() {
            pgModal.style.display = 'none';
        });
    }
    // Allow closing Postgres modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (pgModal && pgModal.style.display === 'flex' && e.key === 'Escape') {
            pgModal.style.display = 'none';
        }
    });
    // Optional: Close Google login modal with Escape (if ever needed)
    document.addEventListener('keydown', function(e) {
        if (googleLoginModal && googleLoginModal.style.display === 'flex' && e.key === 'Escape') {
            googleLoginModal.style.display = 'none';
            container.style.filter = '';
        }
    });

    // Handle Connect button for Postgres modal
    if (connectPgModalBtn && pgUrlInput && pgModal) {
        connectPgModalBtn.addEventListener('click', function() {
            const pgUrl = pgUrlInput.value.trim();
            if (!pgUrl) {
                alert('Please enter a Postgres URL.');
                return;
            }
            
            // Show loading state
            const connectText = connectPgModalBtn.querySelector('.pg-modal-connect-text');
            const loadingSpinner = connectPgModalBtn.querySelector('.pg-modal-loading-spinner');
            const cancelBtn = document.getElementById('pg-modal-cancel');
            
            connectText.style.display = 'none';
            loadingSpinner.style.display = 'flex';
            connectPgModalBtn.disabled = true;
            cancelBtn.disabled = true;
            pgUrlInput.disabled = true;
            
            fetch('/database', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: pgUrl })
            })
            .then(response => response.json())
            .then(data => {
                // Reset loading state
                connectText.style.display = 'inline';
                loadingSpinner.style.display = 'none';
                connectPgModalBtn.disabled = false;
                cancelBtn.disabled = false;
                pgUrlInput.disabled = false;
                
                if (data.success) {
                    pgModal.style.display = 'none'; // Close modal on success
                    // Refresh the graph list to show the new database
                    location.reload();
                } else {
                    alert('Failed to connect: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                // Reset loading state on error
                connectText.style.display = 'inline';
                loadingSpinner.style.display = 'none';
                connectPgModalBtn.disabled = false;
                cancelBtn.disabled = false;
                pgUrlInput.disabled = false;
                
                alert('Error connecting to database: ' + error.message);
            });
        });
    }
});

// User Profile Dropdown Functionality
document.addEventListener('DOMContentLoaded', function() {
    const userProfileBtn = document.getElementById('user-profile-btn');
    const userProfileDropdown = document.getElementById('user-profile-dropdown');

    if (userProfileBtn && userProfileDropdown) {
        // Toggle dropdown when profile button is clicked
        userProfileBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            userProfileDropdown.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!userProfileBtn.contains(e.target) && !userProfileDropdown.contains(e.target)) {
                userProfileDropdown.classList.remove('show');
            }
        });

        // Prevent dropdown from closing when clicking inside it
        userProfileDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
});