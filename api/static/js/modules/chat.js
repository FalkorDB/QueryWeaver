/**
 * Chat API and messaging functionality
 */

import { DOM, state, MESSAGE_DELIMITER } from './config.js';
import { addMessage, removeLoadingMessage, moveLoadingMessageToBottom } from './messages.js';

export async function sendMessage() {
    const message = DOM.messageInput.value.trim();
    if (!message) return;

    // Check if a graph is selected
    const selectedValue = DOM.graphSelect.value;
    if (!selectedValue) {
        addMessage("Please select a graph from the dropdown before sending a message.", false, true);
        return;
    }

    // Cancel any ongoing request
    if (state.currentRequestController) {
        state.currentRequestController.abort();
    }

    // Add user message to chat
    addMessage(message, true, false, false, false, window.currentUser);
    DOM.messageInput.value = '';

    // Show typing indicator
    DOM.inputContainer.classList.add('loading');
    DOM.submitButton.style.display = 'none';
    DOM.pauseButton.style.display = 'block';
    DOM.newChatButton.disabled = true;
    addMessage("", false, false, false, true);

    [DOM.confValue, DOM.expValue, DOM.missValue, DOM.ambValue].forEach((element) => {
        element.innerHTML = '';
    });

    try {
        // Create an AbortController for this request
        state.currentRequestController = new AbortController();

        // Use fetch with streaming response (POST method)
        const response = await fetch('/graphs/' + selectedValue + '?q=' + encodeURIComponent(message), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chat: state.questions_history,
                result: state.result_history,
                instructions: DOM.expInstructions.value,
            }),
            signal: state.currentRequestController.signal
        });

        // Check if the response is ok
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }

        // Process the streaming response
        await processStreamingResponse(response);
        state.currentRequestController = null;

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was aborted');
        } else {
            console.error('Error:', error);
            resetUIState();
            addMessage('Sorry, there was an error processing your message: ' + error.message, false);
        }
        state.currentRequestController = null;
    }
}

async function processStreamingResponse(response) {
    const reader = response.body.getReader();
    let decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();

        if (done) {
            // Process any remaining data in the buffer
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

        // Decode the chunk and add it to our buffer
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Process complete message objects from the buffer using custom delimiter
        let delimiterIndex;
        while ((delimiterIndex = buffer.indexOf(MESSAGE_DELIMITER)) !== -1) {
            const message = buffer.slice(0, delimiterIndex).trim();
            buffer = buffer.slice(delimiterIndex + MESSAGE_DELIMITER.length);

            if (!message) continue;

            try {
                const step = JSON.parse(message);
                handleStreamMessage(step);
            } catch (e) {
                addMessage("Failed: " + message, false);
            }
        }
    }
}

function handleStreamMessage(step) {
    if (step.type === 'reasoning_step') {
        addMessage(step.message, false);
        moveLoadingMessageToBottom();
    } else if (step.type === 'final_result') {
        handleFinalResult(step);
    } else if (step.type === 'followup_questions') {
        handleFollowupQuestions(step);
    } else if (step.type === 'query_result') {
        handleQueryResult(step);
    } else if (step.type === 'ai_response') {
        addMessage(step.message, false, false, true);
    } else if (step.type === 'destructive_confirmation') {
        addDestructiveConfirmationMessage(step);
    } else if (step.type === 'operation_cancelled') {
        addMessage(step.message, false, true);
    } else {
        addMessage(step.message || JSON.stringify(step), false);
    }
    
    if (step.type !== 'reasoning_step') {
        resetUIState();
    }
}

function handleFinalResult(step) {
    DOM.confValue.textContent = `${step.conf}%`;

    [[step.exp, DOM.expValue], [step.miss, DOM.missValue], [step.amb, DOM.ambValue]].forEach(([value, element]) => {
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
    });

    let message = step.message || JSON.stringify(step.data, null, 2);
    if (step.is_valid) {
        addMessage(message, false, false, true);
    } else {
        addMessage("Sorry, we couldn't generate a valid SQL query. Please try rephrasing your question or add more details. For help, check the explanation window.", false, true);
    }
}

function handleFollowupQuestions(step) {
    DOM.expValue.textContent = "N/A";
    DOM.confValue.textContent = "N/A";
    DOM.missValue.textContent = "N/A";
    DOM.ambValue.textContent = "N/A";
    addMessage(step.message, false, true);
}

function handleQueryResult(step) {
    if (step.data) {
        addMessage(`Query Result: ${JSON.stringify(step.data)}`, false, false, true);
    } else {
        addMessage("No results found for the query.", false);
    }
}

function resetUIState() {
    DOM.inputContainer.classList.remove('loading');
    DOM.submitButton.style.display = 'block';
    DOM.pauseButton.style.display = 'none';
    DOM.newChatButton.disabled = false;
    removeLoadingMessage();
}

export function pauseRequest() {
    if (state.currentRequestController) {
        state.currentRequestController.abort();
        state.currentRequestController = null;
        
        resetUIState();
        addMessage("Request was paused by user.", false, true);
    }
}

/**
 * Escapes a string for safe embedding in a single-quoted JavaScript string literal.
 * Replaces backslashes and single quotes.
 */
function escapeForSingleQuotedJsString(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

export function addDestructiveConfirmationMessage(step) {
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
                <button class="confirm-btn danger" onclick="handleDestructiveConfirmation('CONFIRM', '${escapeForSingleQuotedJsString(step.sql_query)}', '${confirmationId}')">
                    CONFIRM - Execute Query
                </button>
                <button class="cancel-btn" onclick="handleDestructiveConfirmation('CANCEL', '${escapeForSingleQuotedJsString(step.sql_query)}', '${confirmationId}')">
                    CANCEL - Abort Operation
                </button>
            </div>
        </div>
    `;
    
    messageDiv.innerHTML = confirmationHTML;
    
    messageDivContainer.appendChild(messageDiv);
    DOM.chatMessages.appendChild(messageDivContainer);
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
    
    // Disable the main input while waiting for confirmation
    DOM.messageInput.disabled = true;
    DOM.submitButton.disabled = true;
}

export async function handleDestructiveConfirmation(confirmation, sqlQuery, confirmationId) {
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
    DOM.messageInput.disabled = false;
    DOM.submitButton.disabled = false;
    
    // Add user's choice as a message
    addMessage(`User choice: ${confirmation}`, true, false, false, false, window.currentUser);
    
    if (confirmation === 'CANCEL') {
        addMessage("Operation cancelled. The destructive SQL query was not executed.", false, true);
        return;
    }
    
    // If confirmed, send confirmation to server
    try {
        const selectedValue = DOM.graphSelect.value;
        
        const response = await fetch('/graphs/' + selectedValue + '/confirm', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                confirmation: confirmation,
                sql_query: sqlQuery,
                chat: state.questions_history
            })
        });
        
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }
        
        // Process the streaming response
        await processStreamingResponse(response);
        
    } catch (error) {
        console.error('Error:', error);
        addMessage('Sorry, there was an error processing the confirmation: ' + error.message, false);
    }
}

// Make functions globally available for onclick handlers
window.handleDestructiveConfirmation = handleDestructiveConfirmation;
