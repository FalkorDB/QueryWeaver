/**
 * Modal dialogs and authentication
 */

export function setupAuthenticationModal() {
    var isAuthenticated = window.isAuthenticated !== undefined ? window.isAuthenticated : false;
    var googleLoginModal = document.getElementById('google-login-modal');
    var container = document.getElementById('container');
    
    if (googleLoginModal && container) {
        if (!isAuthenticated) {
            googleLoginModal.style.display = 'flex';
            container.style.filter = 'blur(2px)';
        } else {
            googleLoginModal.style.display = 'none';
            container.style.filter = '';
        }
    }
}

export function setupPostgresModal() {
    var pgModal = document.getElementById('pg-modal');
    var openPgModalBtn = document.getElementById('open-pg-modal');
    var cancelPgModalBtn = document.getElementById('pg-modal-cancel');
    var connectPgModalBtn = document.getElementById('pg-modal-connect');
    var pgUrlInput = document.getElementById('pg-url-input');
    
    if (openPgModalBtn && pgModal) {
        openPgModalBtn.addEventListener('click', function() {
            pgModal.style.display = 'flex';
            // Focus the input field when modal opens
            if (pgUrlInput) {
                setTimeout(() => {
                    pgUrlInput.focus();
                }, 100);
            }
        });
    }
    
    if (cancelPgModalBtn && pgModal) {
        cancelPgModalBtn.addEventListener('click', function() {
            pgModal.style.display = 'none';
        });
    }
    
    // Allow closing Postgres modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (pgModal && pgModal.style.display === 'flex' && e.key === 'Escape') {
            pgModal.style.display = 'none';
        }
    });

    // Handle Connect button for Postgres modal
    if (connectPgModalBtn && pgUrlInput && pgModal) {
        // Add Enter key support for the input field
        pgUrlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                connectPgModalBtn.click();
            }
        });

        connectPgModalBtn.addEventListener('click', function() {
            const pgUrl = pgUrlInput.value.trim();
            if (!pgUrl) {
                alert('Please enter a Postgres URL.');
                return;
            }
            
            // Show loading state
            const connectText = connectPgModalBtn.querySelector('.pg-modal-connect-text');
            const loadingSpinner = connectPgModalBtn.querySelector('.pg-modal-loading-spinner');
            const cancelBtn = document.getElementById('pg-modal-cancel');
            
            connectText.style.display = 'none';
            loadingSpinner.style.display = 'flex';
            connectPgModalBtn.disabled = true;
            cancelBtn.disabled = true;
            pgUrlInput.disabled = true;
            
            fetch('/database', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: pgUrl })
            })
            .then(response => response.json())
            .then(data => {
                // Reset loading state
                connectText.style.display = 'inline';
                loadingSpinner.style.display = 'none';
                connectPgModalBtn.disabled = false;
                cancelBtn.disabled = false;
                pgUrlInput.disabled = false;
                
                if (data.success) {
                    pgModal.style.display = 'none'; // Close modal on success
                    // Refresh the graph list to show the new database
                    location.reload();
                } else {
                    alert('Failed to connect: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                // Reset loading state on error
                connectText.style.display = 'inline';
                loadingSpinner.style.display = 'none';
                connectPgModalBtn.disabled = false;
                cancelBtn.disabled = false;
                pgUrlInput.disabled = false;
                
                alert('Error connecting to database: ' + error.message);
            });
        });
    }
}
