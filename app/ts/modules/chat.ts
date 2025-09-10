/**
 * Chat API and messaging functionality (TypeScript)
 */

import { DOM, state, MESSAGE_DELIMITER } from './config';
import { addMessage, removeLoadingMessage, moveLoadingMessageToBottom } from './messages';
import { getSelectedGraph } from './graph_select';
import { adjustTextareaHeight } from './input';

export async function sendMessage() {
    const message = (DOM.messageInput?.value || '').trim();
    
    if (!message) return;

    const selectedValue = getSelectedGraph();
    
    if (!selectedValue || selectedValue === "Select Database") return console.debug("No selected graph");

    if (state.currentRequestController) {
        state.currentRequestController.abort();
    }

    addMessage(message, "user", false, (window as any).currentUser || null);
    if (DOM.messageInput) {
        DOM.messageInput.value = '';
        adjustTextareaHeight();
    }

    // Show typing indicator
    DOM.inputContainer?.classList.add('loading');
    if (DOM.submitButton) DOM.submitButton.style.display = 'none';
    if (DOM.pauseButton) DOM.pauseButton.style.display = 'flex';
    if (DOM.newChatButton) DOM.newChatButton.disabled = true;
    addMessage('', "loading");

    [DOM.confValue, DOM.expValue, DOM.missValue, DOM.ambValue].forEach((element) => {
        if (element) element.innerHTML = '';
    });

    try {
        state.currentRequestController = new AbortController();

        const response = await fetch('/graphs/' + encodeURIComponent(selectedValue) + '?q=' + encodeURIComponent(message), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chat: state.questions_history,
                result: state.result_history,
                instructions: DOM.expInstructions?.value
            }),
            signal: state.currentRequestController.signal
        });

        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }

        await processStreamingResponse(response);
        state.currentRequestController = null;
    } catch (error: any) {
        if (error.name === 'AbortError') {
            console.log('Request was aborted');
        } else {
            console.error('Error:', error);
            resetUIState();
            addMessage('Sorry, there was an error processing your message: ' + (error.message || String(error)));
        }
        state.currentRequestController = null;
    }
}

async function processStreamingResponse(response: Response) {
    if (!response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            if (buffer.trim()) {
                try {
                    const step = JSON.parse(buffer);
                    addMessage(step.message || JSON.stringify(step));
                } catch {
                    addMessage(buffer);
                }
            }
            break;
        }

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        let delimiterIndex: number;
        while ((delimiterIndex = buffer.indexOf(MESSAGE_DELIMITER)) !== -1) {
            const message = buffer.slice(0, delimiterIndex).trim();
            buffer = buffer.slice(delimiterIndex + MESSAGE_DELIMITER.length);

            if (!message) continue;

            try {
                const step = JSON.parse(message);
                handleStreamMessage(step);
            } catch {
                addMessage('Failed: ' + message);
            }
        }
    }
}

function handleStreamMessage(step: any) {
    // Save to result_history if this is a final response, regardless of step type
    if (step.final_response === true) {
        state.result_history.push(step.message);
    }
    
    if (step.type === 'reasoning_step') {
        addMessage(step.message);
        moveLoadingMessageToBottom();
    } else if (step.type === 'final_result') {
        handleFinalResult(step);
    } else if (step.type === 'sql_query') {
        handleFinalResult(step, true);
    } else if (step.type === 'followup_questions') {
        handleFollowupQuestions(step);
    } else if (step.type === 'query_result') {
        handleQueryResult(step);
    } else if (step.type === 'ai_response') {
        addMessage(step.message, "final-result");
    } else if (step.type === 'destructive_confirmation') {
        addDestructiveConfirmationMessage(step);
    } else if (step.type === 'operation_cancelled') {
        addMessage(step.message, "followup");
    } else {
        addMessage(step.message || JSON.stringify(step));
    }

    if (step.type !== 'reasoning_step') {
        resetUIState();
    }
}

function handleFinalResult(step: any, isQuery = false) {
    if (DOM.confValue) DOM.confValue.textContent = `${step.conf}%`;

    [[step.exp, DOM.expValue], [step.miss, DOM.missValue], [step.amb, DOM.ambValue]].forEach(([value, element]: any) => {
        if (!element) return;
        element.innerHTML = '';
        let ul = document.getElementById(`${element.id}-list`) as HTMLUListElement | null;

        ul = document.createElement('ul');
        ul.className = `final-result-list`;
        ul.id = `${element.id}-list`;
        element.appendChild(ul);

        (value || '').split('-').forEach((item: string, i: number) => {
            if (item === '') return;

            let li = document.getElementById(`${element.id}-${i}-li`);

            li = document.createElement('li');
            li.id = `${element.id}-${i}-li`;
            ul.appendChild(li);

            li.textContent = i === 0 ? `${item}` : `- ${item}`;
        });
    });

    const message = step.message || JSON.stringify(step.data, null, 2);
    if (step.is_valid) {
        const messageElement = addMessage(message, "final-result", isQuery);
        
        // Add feedback buttons for SQL queries
        if (isQuery && step.data) {
            addFeedbackButtons(messageElement, step.data, state.questions_history[state.questions_history.length - 1] || '');
        }
    }
}

function handleFollowupQuestions(step: any) {
    if (DOM.expValue) DOM.expValue.textContent = 'N/A';
    if (DOM.confValue) DOM.confValue.textContent = 'N/A';
    if (DOM.missValue) DOM.missValue.textContent = 'N/A';
    if (DOM.ambValue) DOM.ambValue.textContent = 'N/A';
    addMessage(step.message, "followup");
}

function handleQueryResult(step: any) {
    if (step.data) {
        addMessage("Query Result", "query-final-result", false, null, step.data);
    } else {
        addMessage('No results found for the query.');
    }
}

function resetUIState() {
    DOM.inputContainer?.classList.remove('loading');
    if (DOM.submitButton) DOM.submitButton.style.display = 'flex';
    if (DOM.pauseButton) DOM.pauseButton.style.display = 'none';
    if (DOM.newChatButton) DOM.newChatButton.disabled = false;
    removeLoadingMessage();
}

export function pauseRequest() {
    if (state.currentRequestController) {
        state.currentRequestController.abort();
        state.currentRequestController = null;

        resetUIState();
        addMessage('Request was paused by user.', "followup");
    }
}

function escapeForSingleQuotedJsString(str: string) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

export function addDestructiveConfirmationMessage(step: any) {
    const messageDiv = document.createElement('div');
    const messageDivContainer = document.createElement('div');

    messageDivContainer.className = 'message-container bot-message-container destructive-confirmation-container';
    messageDiv.className = 'message bot-message destructive-confirmation-message';

    const confirmationId = 'confirmation-' + Date.now();

    const confirmationHTML = `
        <div class="destructive-confirmation" data-confirmation-id="${confirmationId}">
            <div class="confirmation-text">${(step.message || '').replace(/\n/g, '<br>')}</div>
            <div class="confirmation-buttons">
                <button class="confirm-btn danger" onclick="handleDestructiveConfirmation('CONFIRM', '${escapeForSingleQuotedJsString(step.sql_query || '')}', '${confirmationId}')">
                    CONFIRM - Execute Query
                </button>
                <button class="cancel-btn" onclick="handleDestructiveConfirmation('CANCEL', '${escapeForSingleQuotedJsString(step.sql_query || '')}', '${confirmationId}')">
                    CANCEL - Abort Operation
                </button>
            </div>
        </div>
    `;

    messageDiv.innerHTML = confirmationHTML;

    messageDivContainer.appendChild(messageDiv);
    if (DOM.chatMessages) DOM.chatMessages.appendChild(messageDivContainer);
    if (DOM.chatMessages) DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;

    if (DOM.messageInput) DOM.messageInput.disabled = true;
    if (DOM.submitButton) DOM.submitButton.disabled = true;
}

export async function handleDestructiveConfirmation(confirmation: string, sqlQuery: string, confirmationId: string) {
    const confirmationDialog = document.querySelector(`[data-confirmation-id="${confirmationId}"]`);
    if (confirmationDialog) {
        const confirmBtn = confirmationDialog.querySelector('.confirm-btn') as HTMLButtonElement | null;
        const cancelBtn = confirmationDialog.querySelector('.cancel-btn') as HTMLButtonElement | null;
        if (confirmBtn) confirmBtn.disabled = true;
        if (cancelBtn) cancelBtn.disabled = true;
    }

    if (DOM.messageInput) DOM.messageInput.disabled = false;
    if (DOM.submitButton) DOM.submitButton.disabled = false;

    addMessage(`User choice: ${confirmation}`, "user", (window as any).currentUser || null);

    if (confirmation === 'CANCEL') {
        addMessage('Operation cancelled. The destructive SQL query was not executed.', "followup");
        return;
    }

    try {
        const selectedValue = getSelectedGraph() || '';

        const response = await fetch('/graphs/' + encodeURIComponent(selectedValue) + '/confirm', {
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

        if (!response.ok) throw new Error(`Server responded with ${response.status}`);

        await processStreamingResponse(response);
    } catch (error: any) {
        console.error('Error:', error);
        addMessage('Sorry, there was an error processing the confirmation: ' + (error.message || String(error)));
    }
}

function addFeedbackButtons(messageElement: HTMLElement, sqlQuery: string, userQuery: string) {
    const feedbackId = 'feedback-' + Date.now();
    
    const feedbackContainer = document.createElement('div');
    feedbackContainer.className = 'sql-feedback-container';
    feedbackContainer.setAttribute('data-feedback-id', feedbackId);
    
    const feedbackHTML = `
        <div class="sql-feedback-buttons">
            <span class="feedback-label">Was this SQL helpful?</span>
            <button class="feedback-btn thumbs-up" onclick="handleSqlFeedback('thumbs_up', '${escapeForSingleQuotedJsString(sqlQuery)}', '${escapeForSingleQuotedJsString(userQuery)}', '${feedbackId}')" title="Thumbs up - This SQL was helpful">
                👍
            </button>
            <button class="feedback-btn thumbs-down" onclick="handleSqlFeedback('thumbs_down', '${escapeForSingleQuotedJsString(sqlQuery)}', '${escapeForSingleQuotedJsString(userQuery)}', '${feedbackId}')" title="Thumbs down - This SQL was not helpful">
                👎
            </button>
        </div>
    `;
    
    feedbackContainer.innerHTML = feedbackHTML;
    
    // Add the feedback container to the message element's parent container
    const messageContainer = messageElement.parentElement;
    if (messageContainer) {
        messageContainer.appendChild(feedbackContainer);
    }
}

export async function handleSqlFeedback(feedback: string, sqlQuery: string, userQuery: string, feedbackId: string) {
    const feedbackContainer = document.querySelector(`[data-feedback-id="${feedbackId}"]`);
    if (feedbackContainer) {
        const buttons = feedbackContainer.querySelectorAll('.feedback-btn');
        buttons.forEach(btn => (btn as HTMLButtonElement).disabled = true);
        
        // Visual feedback
        const clickedButton = feedbackContainer.querySelector(`.${feedback.replace('_', '-')}`);
        if (clickedButton) {
            clickedButton.classList.add('selected');
        }
    }

    try {
        const selectedValue = getSelectedGraph() || '';

        const response = await fetch('/graphs/' + encodeURIComponent(selectedValue) + '/feedback', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                sql_query: sqlQuery,
                user_query: userQuery,
                feedback: feedback,
                chat: state.questions_history
            })
        });

        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }

        // Show feedback confirmation
        if (feedbackContainer) {
            const buttonsContainer = feedbackContainer.querySelector('.sql-feedback-buttons');
            if (buttonsContainer) {
                buttonsContainer.innerHTML = `
                    <span class="feedback-thanks">${feedback === 'thumbs_up' ? '👍' : '👎'}</span>
                `;
            }
        }

    } catch (error: any) {
        console.error('Error submitting feedback:', error);
        
        // Re-enable buttons on error
        if (feedbackContainer) {
            const buttons = feedbackContainer.querySelectorAll('.feedback-btn');
            buttons.forEach(btn => (btn as HTMLButtonElement).disabled = false);
            
            const clickedButton = feedbackContainer.querySelector(`.${feedback.replace('_', '-')}`);
            if (clickedButton) {
                clickedButton.classList.remove('selected');
            }
        }
        
        addMessage('Sorry, there was an error submitting your feedback: ' + (error.message || String(error)));
    }
}

// Expose global for inline onclick handlers
(window as any).handleDestructiveConfirmation = handleDestructiveConfirmation;
(window as any).handleSqlFeedback = handleSqlFeedback;
