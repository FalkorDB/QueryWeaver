/**
 * Helper to manage the custom graph selector UI.
 * Exposes functions to get/set the selected graph and render the list.
 */
import { DOM } from './config';

export function getSelectedGraph(): string | null {
    const selectedLabel = document.getElementById('graph-selected');
    const text = selectedLabel?.querySelector('.dropdown-text')?.textContent;
    if (text) return text;
    return null;
}

export function setSelectedGraph(name: string) {
    const selectedLabel = document.getElementById('graph-selected');
    const textNode = selectedLabel?.querySelector('.dropdown-text');
    if (textNode) textNode.textContent = name;
}

export function clearGraphOptions() {
    const optionsContainer = document.getElementById('graph-options');
    if (optionsContainer) optionsContainer.innerHTML = '';
}

export function addGraphOption(name: string, onSelect: (_: string) => void, onDelete: (_: string) => void, isDemo: boolean = false) {
    const optionsContainer = document.getElementById('graph-options');
    if (!optionsContainer) return;
    const row = document.createElement('div');
    row.className = 'dropdown-option';
    row.setAttribute('data-value', name);
    row.setAttribute('data-is-demo', isDemo.toString());
    const icon = document.createElement('span');
    icon.className = 'db-icon';
    // optional: could add icons later
    const text = document.createElement('span');
    text.textContent = name;
    row.appendChild(icon);
    row.appendChild(text);

    const delBtn = document.createElement('button');
    delBtn.className = 'delete-btn';
    delBtn.title = isDemo ? 'Demo databases cannot be deleted' : `Delete ${name}`;
    delBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"></path></svg>`;
    
    // Disable delete button for demo databases
    if (isDemo) {
        delBtn.disabled = true;
    }
    
    row.appendChild(delBtn);

    row.addEventListener('click', () => {
        if (DOM.graphSelectRefresh && DOM.submitButton) {
            // Disable refresh button for demo databases
            DOM.graphSelectRefresh.disabled = isDemo;
            DOM.submitButton.disabled = false
        };
        setSelectedGraph(name);
        onSelect(name);
        optionsContainer.classList.remove('open');
    });

    delBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onDelete(name);
    });

    optionsContainer.appendChild(row);
}

export function toggleOptions() {
    const optionsContainer = document.getElementById('graph-options');
    if (optionsContainer) optionsContainer.classList.toggle('open');
}
