/**
 * UI components and interactions (TypeScript)
 */

import { DOM } from './config';

export function toggleContainer(container: HTMLElement, onOpen?: () => void) {
    const isMobile = window.innerWidth <= 768;

    const allContainers = document.querySelectorAll('.sidebar-container');
    allContainers.forEach((c) => {
        if (c !== container && c.classList.contains('open')) {
            c.classList.remove('open');
        }
    });

    if (!container.classList.contains('open')) {
        container.classList.add('open');

        if (!isMobile && DOM.chatContainer) {
            DOM.chatContainer.style.paddingRight = '10%';
            DOM.chatContainer.style.paddingLeft = '10%';
        }
        if (onOpen) onOpen();
    } else {
        container.classList.remove('open');

        if (!isMobile && DOM.chatContainer) {
            DOM.chatContainer.style.paddingRight = '20%';
            DOM.chatContainer.style.paddingLeft = '20%';
        }
    }
}

export function showResetConfirmation() {
    if (DOM.resetConfirmationModal) DOM.resetConfirmationModal.style.display = 'flex';
    setTimeout(() => {
        DOM.resetConfirmBtn?.focus();
    }, 100);
}

export function hideResetConfirmation() {
    if (DOM.resetConfirmationModal) DOM.resetConfirmationModal.style.display = 'none';
}

export function handleResetConfirmation() {
    hideResetConfirmation();
    import('./messages').then(({ initChat }) => {
        initChat();
    });
}

export function setupUserProfileDropdown() {
    const userProfileBtn = document.getElementById('user-profile-btn');
    const userProfileDropdown = document.getElementById('user-profile-dropdown');

    if (userProfileBtn && userProfileDropdown) {
        userProfileBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            userProfileDropdown.classList.toggle('show');
        });

        document.addEventListener('click', function(e) {
            if (!userProfileBtn.contains(e.target as Node) && !userProfileDropdown.contains(e.target as Node)) {
                userProfileDropdown.classList.remove('show');
            }
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && userProfileDropdown.classList.contains('show')) {
                userProfileDropdown.classList.remove('show');
            }
        });

        userProfileDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
}

export function setupThemeToggle() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const currentTheme = localStorage.getItem('theme') || 'system';
    document.documentElement.setAttribute('data-theme', currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            let newTheme: string;

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

            const titles: Record<string, string> = {
                dark: 'Switch to Light Mode',
                light: 'Switch to System Mode',
                system: 'Switch to Dark Mode'
            };
            (themeToggleBtn as HTMLElement).title = titles[newTheme];
        });

        const titles: Record<string, string> = {
            dark: 'Switch to Light Mode',
            light: 'Switch to System Mode',
            system: 'Switch to Dark Mode'
        };
        (themeToggleBtn as HTMLElement).title = titles[currentTheme];
    }
}

export function setupToolbar() {
    const toolbar = document.getElementById('toolbar-buttons');
    if (toolbar) {
        const buttons = Array.from(toolbar.querySelectorAll('button.toolbar-button')) as HTMLButtonElement[];
        buttons.forEach((b, i) => b.setAttribute('tabindex', i === 0 ? '0' : '-1'));

        toolbar.addEventListener('keydown', (e) => {
            const focused = document.activeElement as HTMLElement | null;
            const idx = buttons.indexOf(focused as HTMLButtonElement);
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                e.preventDefault();
                const next = buttons[(idx + 1) % buttons.length];
                if (next) {
                    buttons.forEach(b => b.setAttribute('tabindex', '-1'));
                    next.setAttribute('tabindex', '0');
                    next.focus();
                }
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const prev = buttons[(idx - 1 + buttons.length) % buttons.length];
                if (prev) {
                    buttons.forEach(b => b.setAttribute('tabindex', '-1'));
                    prev.setAttribute('tabindex', '0');
                    prev.focus();
                }
            } else if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (focused) (focused as HTMLElement).click();
            }
        });
    }
}

export function handleWindowResize() {
    const isMobile = window.innerWidth <= 768;

    const allContainers = document.querySelectorAll('.sidebar-container');
    allContainers.forEach((c) => {
        if (isMobile && c.classList.contains('open') && DOM.chatContainer) {
            DOM.chatContainer.style.paddingRight = '';
            DOM.chatContainer.style.paddingLeft = '';
        } else if (!isMobile && c.classList.contains('open') && DOM.chatContainer) {
            DOM.chatContainer.style.paddingRight = '10%';
            DOM.chatContainer.style.paddingLeft = '10%';
        } else if (!isMobile && !c.classList.contains('open') && DOM.chatContainer) {
            DOM.chatContainer.style.paddingRight = '20%';
            DOM.chatContainer.style.paddingLeft = '20%';
        }
    });
}

export function setupCustomDropdown() {
    const dropdown = document.getElementById('database-type-dropdown') as HTMLElement;
    const selected = dropdown?.querySelector('.dropdown-selected') as HTMLElement;
    const options = dropdown?.querySelector('.dropdown-options') as HTMLElement;
    const hiddenInput = document.getElementById('database-type-select') as HTMLInputElement;

    selected.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('open');
        selected.classList.toggle('active');
    });

    options.addEventListener('click', (e) => {
        const option = (e.target as HTMLElement).closest('.dropdown-option') as HTMLElement;
        if (!option) return;

        const value = option.dataset.value || '';
        const text = option.querySelector('span')?.textContent || '';
        const icon = option.querySelector('.db-icon')?.cloneNode(true) as Node | null;

        const dropdownText = selected.querySelector('.dropdown-text') as HTMLElement | null;
        if (dropdownText) dropdownText.innerHTML = '';
        if (icon && dropdownText) dropdownText.appendChild(icon);
        if (dropdownText) dropdownText.appendChild(document.createTextNode(text));

        hiddenInput.value = value;
        dropdown.classList.remove('open');
        selected.classList.remove('active');

        const changeEvent = new Event('change', { bubbles: true });
        hiddenInput.dispatchEvent(changeEvent);
    });

    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target as Node)) {
            dropdown.classList.remove('open');
            selected.classList.remove('active');
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && dropdown.classList.contains('open')) {
            dropdown.classList.remove('open');
            selected.classList.remove('active');
        }
    });
}
