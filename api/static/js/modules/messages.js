/**
 * Message handling and UI functions
 */

import { DOM, state } from './config.js';

export function addMessage(message, isUser = false, isFollowup = false, isFinalResult = false, isLoading = false, userInfo = null) {
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
        
        state.questions_history.push(message);
    } else if (isFinalResult) {
        state.result_history.push(message);
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

    DOM.chatMessages.appendChild(messageDivContainer);
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;

    return messageDiv;
}

export function removeLoadingMessage() {
    const loadingMessageContainer = document.getElementById("loading-message-container");
    if (loadingMessageContainer) {
        loadingMessageContainer.remove();
    }
}

export function moveLoadingMessageToBottom() {
    const loadingMessageContainer = document.getElementById("loading-message-container");
    if (loadingMessageContainer) {
        // Remove from current position and append to bottom
        loadingMessageContainer.remove();
        DOM.chatMessages.appendChild(loadingMessageContainer);
        DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
    }
}

export function formatBlock(text) {
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

export function initChat() {
    DOM.messageInput.value = '';
    DOM.chatMessages.innerHTML = '';
    [DOM.confValue, DOM.expValue, DOM.missValue].forEach((element) => {
        element.innerHTML = '';
    });
    
    // Check if we have graphs available
    if (DOM.graphSelect && DOM.graphSelect.options.length > 0 && DOM.graphSelect.options[0].value) {
        addMessage('Hello! How can I help you today?', false);
    } else {
        addMessage('Hello! Please select a graph from the dropdown above or upload a schema to get started.', false);
    }
    
    state.questions_history = [];
    state.result_history = [];
}
