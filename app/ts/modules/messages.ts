/**
 * Message handling and UI functions (TypeScript)
 */

import { DOM, state } from './config';
import { getSelectedGraph } from './graph_select';

export function addMessage(
    message: string,
    isUser = false,
    isFollowup = false,
    isFinalResult = false,
    isLoading = false,
    userInfo: { picture?: string; name?: string } | null = null
) {
    const messageDiv = document.createElement('div');
    const messageDivContainer = document.createElement('div');

    messageDiv.className = 'message';
    messageDivContainer.className = 'message-container';

    let userAvatar: HTMLImageElement | null = null;

    if (isFollowup) {
        messageDivContainer.className += ' followup-message-container';
        messageDiv.className += ' followup-message';
        messageDiv.textContent = message;
    } else if (isUser) {
        messageDivContainer.className += ' user-message-container';
        messageDiv.className += ' user-message';

        if (userInfo && userInfo.picture) {
            userAvatar = document.createElement('img');
            userAvatar.src = userInfo.picture;
            userAvatar.alt = (userInfo.name?.charAt(0).toUpperCase() as string) || 'User';
            userAvatar.className = 'user-message-avatar';
            messageDivContainer.classList.add('has-avatar');
        }

        state.questions_history.push(message);
    } else if (isFinalResult) {
        messageDivContainer.className += ' final-result-message-container';
        messageDiv.className += ' final-result-message';
    } else {
        messageDivContainer.className += ' bot-message-container';
        messageDiv.className += ' bot-message';
        if (isLoading) {
            messageDivContainer.id = 'loading-message-container';
            messageDivContainer.className += ' loading-message-container';
        }
    }

    const block = formatBlock(message);

    if (block) {
        block.forEach((lineDiv) => {
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

    DOM.chatMessages?.appendChild(messageDivContainer);
    if (DOM.chatMessages) DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;

    return messageDiv;
}

export function removeLoadingMessage() {
    const loadingMessageContainer = document.getElementById('loading-message-container');
    if (loadingMessageContainer) {
        loadingMessageContainer.remove();
    }
}

export function moveLoadingMessageToBottom() {
    const loadingMessageContainer = document.getElementById('loading-message-container');
    if (loadingMessageContainer && DOM.chatMessages) {
        loadingMessageContainer.remove();
        DOM.chatMessages.appendChild(loadingMessageContainer);
        DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
    }
}

export function formatBlock(text: string) {
    text = text.replace(/^"(.*)"$/, '$1').trim();

    // SQL block
    if (text.startsWith('```sql') && text.endsWith('```')) {
        const sql = text.slice(6, -3).trim();
        return sql.split('\n').map((line) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'sql-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }

    // Array block
    if (text.includes('[') && text.includes(']')) {
        const parts = text.split('[');
        const formattedParts = parts.map((part) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'array-line';
            part = part.replaceAll(']', '');
            lineDiv.textContent = part;
            return lineDiv;
        });
        return formattedParts;
    }

    // Generic multi-line block
    text = text.replace(/\\n/g, '\n');
    if (text.includes('\n')) {
        return text.split('\n').map((line) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'plain-line';
            lineDiv.textContent = line;
            return lineDiv;
        });
    }

    return null;
}

export function initChat() {
    if (DOM.messageInput) DOM.messageInput.value = '';
    if (DOM.chatMessages) DOM.chatMessages.innerHTML = '';
    [DOM.confValue, DOM.expValue, DOM.missValue].forEach((element) => {
        if (element) element.innerHTML = '';
    });

    const selected = getSelectedGraph();
    if (selected) {
        addMessage('Hello! How can I help you today?', false);
    } else {
        addMessage('Hello! Please select a graph from the dropdown above, upload a schema or connect to a database to get started.', false);
    }

    state.questions_history = [];
    state.result_history = [];
}
