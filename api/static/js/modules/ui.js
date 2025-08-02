/**
 * UI components and interactions
 */

import { DOM } from './config.js';

export function toggleMenu() {
    // Check if we're on mobile (768px breakpoint to match CSS)
    const isMobile = window.innerWidth <= 768;
    
    if (!DOM.menuContainer.classList.contains('open')) {
        DOM.menuContainer.classList.add('open');
        DOM.sideMenuButton.style.display = 'none';
        
        // Only adjust padding on desktop, not mobile (mobile uses overlay)
        if (!isMobile) {
            DOM.chatContainer.style.paddingRight = '10%';
            DOM.chatContainer.style.paddingLeft = '10%';
        }
    } else {
        DOM.menuContainer.classList.remove('open');
        DOM.sideMenuButton.style.display = 'block';
        
        // Only adjust padding on desktop, not mobile (mobile uses overlay)
        if (!isMobile) {
            DOM.chatContainer.style.paddingRight = '20%';
            DOM.chatContainer.style.paddingLeft = '20%';
        }
    }
}

export function showResetConfirmation() {
    DOM.resetConfirmationModal.style.display = 'flex';
    // Focus the Reset Session button when modal opens
    setTimeout(() => {
        DOM.resetConfirmBtn.focus();
    }, 100);
}

export function hideResetConfirmation() {
    DOM.resetConfirmationModal.style.display = 'none';
}

export function handleResetConfirmation() {
    hideResetConfirmation();
    // Import initChat dynamically to avoid circular dependency
    import('./messages.js').then(({ initChat }) => {
        initChat();
    });
}

export function setupUserProfileDropdown() {
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
}

export function setupThemeToggle() {
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
}

export function handleWindowResize() {
    const isMobile = window.innerWidth <= 768;
    
    // If menu is open and we switch to mobile, remove any desktop padding
    if (isMobile && DOM.menuContainer.classList.contains('open')) {
        DOM.chatContainer.style.paddingRight = '';
        DOM.chatContainer.style.paddingLeft = '';
    }
    // If menu is open and we switch to desktop, apply desktop padding
    else if (!isMobile && DOM.menuContainer.classList.contains('open')) {
        DOM.chatContainer.style.paddingRight = '10%';
        DOM.chatContainer.style.paddingLeft = '10%';
    }
    // If menu is closed and we're on desktop, ensure default desktop padding
    else if (!isMobile && !DOM.menuContainer.classList.contains('open')) {
        DOM.chatContainer.style.paddingRight = '20%';
        DOM.chatContainer.style.paddingLeft = '20%';
    }
}
