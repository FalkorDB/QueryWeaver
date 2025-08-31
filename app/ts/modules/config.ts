/**
 * TypeScript: Constants and configuration for the chat application
 */

export const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

export const SELECTORS = {
    messageInput: '#message-input',
    submitButton: '#submit-button',
    pauseButton: '#pause-button',
    newChatButton: '#reset-button',
    chatMessages: '#chat-messages',
    expValue: '#exp-value',
    confValue: '#conf-value',
    missValue: '#info-value',
    ambValue: '#amb-value',
    fileUpload: '#schema-upload',
    fileLabel: '#custom-file-upload',
    sideMenuButton: '#side-menu-button',
    menuButton: '#menu-button',
    schemaButton: '#schema-button',
    menuContainer: '#menu-container',
    schemaContainer: '#schema-container',
    chatContainer: '#chat-container',
    leftToolbar: '#left-toolbar',
    toolbarButtons: '#toolbar-buttons',
    leftToolbarInner: '#left-toolbar-inner',
    expInstructions: '#instructions-textarea',
    inputContainer: '#input-container',
    resetConfirmationModal: '#reset-confirmation-modal',
    resetConfirmBtn: '#reset-confirm-btn',
    resetCancelBtn: '#reset-cancel-btn'
} as const;

function getElement<T extends HTMLElement | null>(id: string): T {
    return document.getElementById(id) as T;
}

export const DOM = {
    messageInput: getElement<HTMLInputElement | null>('message-input'),
    submitButton: getElement<HTMLButtonElement | null>('submit-button'),
    pauseButton: getElement<HTMLButtonElement | null>('pause-button'),
    newChatButton: getElement<HTMLButtonElement | null>('reset-button'),
    chatMessages: getElement<HTMLElement | null>('chat-messages'),
    expValue: getElement<HTMLElement | null>('exp-value'),
    confValue: getElement<HTMLElement | null>('conf-value'),
    missValue: getElement<HTMLElement | null>('info-value'),
    ambValue: getElement<HTMLElement | null>('amb-value'),
    fileUpload: getElement<HTMLInputElement | null>('schema-upload'),
    fileLabel: getElement<HTMLElement | null>('custom-file-upload'),
    menuButton: getElement<HTMLButtonElement | null>('menu-button'),
    schemaButton: getElement<HTMLButtonElement | null>('schema-button'),
    menuContainer: getElement<HTMLElement | null>('menu-container'),
    schemaContainer: getElement<HTMLElement | null>('schema-container'),
    chatContainer: getElement<HTMLElement | null>('chat-container'),
    leftToolbar: getElement<HTMLElement | null>('left-toolbar'),
    toolbarButtons: getElement<HTMLElement | null>('toolbar-buttons'),
    leftToolbarInner: getElement<HTMLElement | null>('left-toolbar-inner'),
    expInstructions: getElement<HTMLTextAreaElement | null>('instructions-textarea'),
    inputContainer: getElement<HTMLElement | null>('input-container'),
    resetConfirmationModal: getElement<HTMLElement | null>('reset-confirmation-modal'),
    resetConfirmBtn: getElement<HTMLButtonElement | null>('reset-confirm-btn'),
    resetCancelBtn: getElement<HTMLButtonElement | null>('reset-cancel-btn')
};

export type AppState = {
    questions_history: string[];
    result_history: string[];
    currentRequestController: AbortController | null;
};

export const state: AppState = {
    questions_history: [],
    result_history: [],
    currentRequestController: null
};

export const urlParams = new URLSearchParams(window.location.search);
