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

export function addGraphOption(name: string, onSelect: (n: string) => void, onDelete: (n: string) => void) {
    const optionsContainer = document.getElementById('graph-options');
    if (!optionsContainer) return;
    const row = document.createElement('div');
    row.className = 'dropdown-option';
    row.setAttribute('data-value', name);
    const icon = document.createElement('span');
    icon.className = 'db-icon';
    // optional: could add icons later
    const text = document.createElement('span');
    text.textContent = name;
    row.appendChild(icon);
    row.appendChild(text);

    const delBtn = document.createElement('button');
    delBtn.className = 'delete-btn';
    delBtn.title = `Delete ${name}`;
    delBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"></path></svg>`;
    row.appendChild(delBtn);

    row.addEventListener('click', () => {
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
