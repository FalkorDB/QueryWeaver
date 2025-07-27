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
const expInstructions = document.getElementById('instructions-textarea');
const inputContainer = document.getElementById('input-container');

let questions_history = [];
let result_history = [];
let currentRequestController = null;

// Custom delimiter that's unlikely to appear in your data
const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

const urlParams = new URLSearchParams(window.location.search);

function addMessage(message, isUser = false, isFollowup = false, isFinalResult = false, isLoading = false, userInfo = null) {
    const messageDiv = document.createElement('div');
    const messageDivContainer = document.createElement('div');

    messageDiv.className = "message";
    messageDivContainer.className = "message-container";

    let userAvatar = null;

    if (isFollowup) {
        messageDivContainer.className += " followup-message-container";
        messageDiv.className += " followup-message";
        messageDiv.textContent = message;
    } else if (isUser) {
        messageDivContainer.className += " user-message-container";
        messageDiv.className += " user-message";
        
        // Prepare user avatar if userInfo is provided
        if (userInfo && userInfo.picture) {
            userAvatar = document.createElement('img');
            userAvatar.src = userInfo.picture;
            userAvatar.alt = userInfo.name?.charAt(0).toUpperCase() || 'User';
            userAvatar.className = 'user-message-avatar';
            messageDivContainer.classList.add('has-avatar');
        }
        
        questions_history.push(message);
    } else if (isFinalResult) {
        result_history.push(message);
        messageDivContainer.className += " final-result-message-container";
        messageDiv.className += " final-result-message";
    } else {
        messageDivContainer.className += " bot-message-container";
        messageDiv.className += " bot-message";
        if (isLoading) {
            messageDivContainer.id = "loading-message-container";
            messageDivContainer.className += " loading-message-container";
        }
    }

    const block = formatBlock(message);

    if (block) {
        block.forEach(lineDiv => {
            messageDiv.appendChild(lineDiv);
        });
    } else if (!isLoading) {
        messageDiv.textContent = message;
    }

    if (!isLoading) {
        messageDivContainer.appendChild(messageDiv);
        if (userAvatar) {
            messageDivContainer.appendChild(userAvatar);
        }
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
}

function initChat() {
    messageInput.value = '';
    chatMessages.innerHTML = '';
    [confValue, expValue, missValue].forEach((element) => {
        element.innerHTML = '';
    });
    
    // Check if we have graphs available
    const graphSelect = document.getElementById("graph-select");
    if (graphSelect && graphSelect.options.length > 0 && graphSelect.options[0].value) {
        addMessage('Hello! How can I help you today?', false);
    } else {
        addMessage('Hello! Please select a graph from the dropdown above or upload a schema to get started.', false);
    }
    
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

    // Check if a graph is selected
    const selectedValue = document.getElementById("graph-select").value;
    if (!selectedValue) {
        addMessage("Please select a graph from the dropdown before sending a message.", false, true);
        return;
    }

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

        // Create an AbortController for this request
        currentRequestController = new AbortController();

        // Use fetch with streaming response (GET method)
        const response = await fetch('/graphs/' + selectedValue + '?q=' + encodeURIComponent(message), {
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
    // Check if we're on mobile (768px breakpoint to match CSS)
    const isMobile = window.innerWidth <= 768;
    
    if (!menuContainer.classList.contains('open')) {
        menuContainer.classList.add('open');
        sideMenuButton.style.display = 'none';
        
        // Only adjust padding on desktop, not mobile (mobile uses overlay)
        if (!isMobile) {
            chatContainer.style.paddingRight = '10%';
            chatContainer.style.paddingLeft = '10%';
        }
    } else {
        menuContainer.classList.remove('open');
        sideMenuButton.style.display = 'block';
        
        // Only adjust padding on desktop, not mobile (mobile uses overlay)
        if (!isMobile) {
            chatContainer.style.paddingRight = '20%';
            chatContainer.style.paddingLeft = '20%';
        }
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

menuButton.addEventListener('click', toggleMenu);

sideMenuButton.addEventListener('click', toggleMenu);

// Reset confirmation modal elements
const resetConfirmationModal = document.getElementById('reset-confirmation-modal');
const resetConfirmBtn = document.getElementById('reset-confirm-btn');
const resetCancelBtn = document.getElementById('reset-cancel-btn');

// Show reset confirmation modal instead of directly resetting
newChatButton.addEventListener('click', () => {
    resetConfirmationModal.style.display = 'flex';
    // Focus the Reset Session button when modal opens
    setTimeout(() => {
        resetConfirmBtn.focus();
    }, 100); // Small delay to ensure modal is fully rendered
});

// Handle reset confirmation
resetConfirmBtn.addEventListener('click', () => {
    resetConfirmationModal.style.display = 'none';
    initChat();
});

// Handle reset cancellation
resetCancelBtn.addEventListener('click', () => {
    resetConfirmationModal.style.display = 'none';
});

// Close modal when clicking outside of it
resetConfirmationModal.addEventListener('click', (e) => {
    if (e.target === resetConfirmationModal) {
        resetConfirmationModal.style.display = 'none';
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && resetConfirmationModal.style.display === 'flex') {
        resetConfirmationModal.style.display = 'none';
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const chatMessages = document.getElementById("chat-messages");
    const graphSelect = document.getElementById("graph-select");

    // Fetch available graphs
    fetch("/graphs")
        .then(response => {
            if (!response.ok) {
                if (response.status === 401) {
                    throw new Error("Authentication required. Please log in to access graphs.");
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            graphSelect.innerHTML = "";
            
            if (!data || data.length === 0) {
                // No graphs available
                const option = document.createElement("option");
                option.value = "";
                option.textContent = "No graphs available";
                option.disabled = true;
                graphSelect.appendChild(option);
                
                // Disable chat input when no graphs are available
                messageInput.disabled = true;
                submitButton.disabled = true;
                messageInput.placeholder = "Please upload a schema or connect a database to start chatting";
                
                addMessage("No graphs are available. Please upload a schema file or connect to a database to get started.", false);
                return;
            }
            
            data.forEach(graph => {
                const option = document.createElement("option");
                option.value = graph;
                option.textContent = graph;
                option.title = graph;
                graphSelect.appendChild(option);
            });

            // Re-enable chat input when graphs are available
            messageInput.disabled = false;
            submitButton.disabled = false;
            messageInput.placeholder = "Describe the SQL query you want...";
        })
        .catch(error => {
            console.error("Error fetching graphs:", error);
            
            // Show appropriate error message and disable input
            if (error.message.includes("Authentication required")) {
                addMessage("Authentication required. Please log in to access your graphs.", false);
                // Don't disable input for auth errors as user needs to log in
            } else {
                addMessage("Sorry, there was an error fetching the available graphs: " + error.message, false);
                messageInput.disabled = true;
                submitButton.disabled = true;
                messageInput.placeholder = "Cannot connect to server";
            }
            
            // Add a placeholder option to show the error state
            graphSelect.innerHTML = "";
            const option = document.createElement("option");
            option.value = "";
            option.textContent = error.message.includes("Authentication") ? "Please log in" : "Error loading graphs";
            option.disabled = true;
            graphSelect.appendChild(option);
        });

    graphSelect.addEventListener("change", function () {
        initChat();
    });
});


fileUpload.addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    // document.getElementById('file-name').textContent = file.name;

    const formData = new FormData();
    formData.append('file', file);

    fetch("/graphs", {
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
            // Focus the input field when modal opens
            if (pgUrlInput) {
                setTimeout(() => {
                    pgUrlInput.focus();
                }, 100); // Small delay to ensure modal is fully rendered
            }
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
    // Do NOT allow closing Google login modal with Escape or any other means except successful login

    // Handle Connect button for Postgres modal
    if (connectPgModalBtn && pgUrlInput && pgModal) {
        // Add Enter key support for the input field
        pgUrlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                connectPgModalBtn.click();
            }
        });

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

        // Close dropdown with Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && userProfileDropdown.classList.contains('show')) {
                userProfileDropdown.classList.remove('show');
            }
        });

        // Prevent dropdown from closing when clicking inside it
        userProfileDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
});

// Theme Toggle Functionality
document.addEventListener('DOMContentLoaded', function() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    
    // Get theme from localStorage or default to 'system'
    const currentTheme = localStorage.getItem('theme') || 'system';
    document.documentElement.setAttribute('data-theme', currentTheme);
    
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            let newTheme;
            
            // Cycle through themes: dark -> light -> system -> dark
            switch (currentTheme) {
                case 'dark':
                    newTheme = 'light';
                    break;
                case 'light':
                    newTheme = 'system';
                    break;
                case 'system':
                default:
                    newTheme = 'dark';
                    break;
            }
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            // Update button title
            const titles = {
                'dark': 'Switch to Light Mode',
                'light': 'Switch to System Mode', 
                'system': 'Switch to Dark Mode'
            };
            themeToggleBtn.title = titles[newTheme];
        });
        
        // Set initial title
        const titles = {
            'dark': 'Switch to Light Mode',
            'light': 'Switch to System Mode',
            'system': 'Switch to Dark Mode'
        };
        themeToggleBtn.title = titles[currentTheme];
    }
});

// Handle window resize to ensure proper menu behavior across breakpoints
window.addEventListener('resize', function() {
    const isMobile = window.innerWidth <= 768;
    
    // If menu is open and we switch to mobile, remove any desktop padding
    if (isMobile && menuContainer.classList.contains('open')) {
        chatContainer.style.paddingRight = '';
        chatContainer.style.paddingLeft = '';
    }
    // If menu is open and we switch to desktop, apply desktop padding
    else if (!isMobile && menuContainer.classList.contains('open')) {
        chatContainer.style.paddingRight = '10%';
        chatContainer.style.paddingLeft = '10%';
    }
    // If menu is closed and we're on desktop, ensure default desktop padding
    else if (!isMobile && !menuContainer.classList.contains('open')) {
        chatContainer.style.paddingRight = '20%';
        chatContainer.style.paddingLeft = '20%';
    }
});