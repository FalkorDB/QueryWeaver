/**
 * Main application entry point (TypeScript)
 */

import { DOM } from './modules/config';
import { initChat } from './modules/messages';
import { sendMessage, pauseRequest } from './modules/chat';
import { loadGraphs, handleFileUpload, onGraphChange } from './modules/graphs';
import { getSelectedGraph } from './modules/graph_select';
import {
    toggleContainer,
    showResetConfirmation,
    hideResetConfirmation,
    handleResetConfirmation,
    setupUserProfileDropdown,
    setupThemeToggle,
    setupToolbar,
    handleWindowResize,
    setupCustomDropdown
} from './modules/ui';
import { setupAuthenticationModal, setupDatabaseModal } from './modules/modals';
import { resizeGraph, showGraph } from './modules/schema';
import { setupTokenManagement } from './modules/tokens';
import { initLeftToolbar } from './modules/left_toolbar';

async function loadAndShowGraph(selected: string | undefined) {
    if (!selected) return;
    try {
        const resp = await fetch(`/graphs/${encodeURIComponent(selected)}/data`);
        if (!resp.ok) {
            console.error('Failed to load graph data:', resp.status, resp.statusText);
            return;
        }

        const data = await resp.json();

        if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.links)) {
            console.warn('Graph data returned in unexpected shape, showing empty message', data);
            return;
        }

        const container = document.getElementById('schema-graph');
        if (container) container.innerHTML = '';

        showGraph(data);
    } catch (err) {
        console.error('Error fetching graph data:', err);
    }
}

function initializeApp() {
    initChat();
    setupEventListeners();
    setupUIComponents();
    loadInitialData();
}

function setupEventListeners() {
    DOM.submitButton?.addEventListener('click', sendMessage);
    DOM.pauseButton?.addEventListener('click', pauseRequest);
    DOM.messageInput?.addEventListener('keypress', (e: KeyboardEvent) => {
        if ((e as KeyboardEvent).key === 'Enter') sendMessage();
    });

    DOM.menuButton?.addEventListener('click', () => toggleContainer(DOM.menuContainer as HTMLElement));

    DOM.schemaButton?.addEventListener('click', () => {
        toggleContainer(DOM.schemaContainer as HTMLElement, async () => {
            const selected = getSelectedGraph();
            if (!selected) return;
            loadAndShowGraph(selected);
            setTimeout(resizeGraph, 450);
        });
    });

    DOM.newChatButton?.addEventListener('click', showResetConfirmation);
    DOM.resetConfirmBtn?.addEventListener('click', handleResetConfirmation);
    DOM.resetCancelBtn?.addEventListener('click', hideResetConfirmation);

    DOM.resetConfirmationModal?.addEventListener('click', (e) => {
        if (e.target === DOM.resetConfirmationModal) hideResetConfirmation();
    });

    document.addEventListener('keydown', (e) => {
        if ((e as KeyboardEvent).key === 'Escape' && DOM.resetConfirmationModal && DOM.resetConfirmationModal.style.display === 'flex') {
            hideResetConfirmation();
        }
    });

    // Legacy select is hidden; custom UI will trigger load via graph_select helper
    document.getElementById('graph-options')?.addEventListener('click', async () => {
        onGraphChange();
        const selected = getSelectedGraph();
        if (!selected) return;
        if (DOM.schemaContainer && DOM.schemaContainer.classList.contains('open')) {
            loadAndShowGraph(selected);
            setTimeout(resizeGraph, 450);
        }
    });

    DOM.fileUpload?.addEventListener('change', handleFileUpload);
    window.addEventListener('resize', handleWindowResize);
}

function setupUIComponents() {
    setupUserProfileDropdown();
    setupThemeToggle();
    setupAuthenticationModal();
    setupDatabaseModal();
    setupTokenManagement();
    setupToolbar();
    // initialize left toolbar behavior (burger, responsive default)
    initLeftToolbar();
    setupCustomDropdown();
}

function loadInitialData() {
    loadGraphs();
}

document.addEventListener('DOMContentLoaded', initializeApp);
