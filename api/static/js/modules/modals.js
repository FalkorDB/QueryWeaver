/**
 * Modal dialogs and authentication
 */

export function setupAuthenticationModal() {
    var isAuthenticated = window.isAuthenticated !== undefined ? window.isAuthenticated : false;
    var googleLoginModal = document.getElementById('google-login-modal');
    var signupModal = document.getElementById('signup-modal');
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
    
    // Setup modal switching
    setupModalSwitching();
    // Setup email authentication forms
    setupEmailAuthentication();
}

function setupModalSwitching() {
    const showSignupLink = document.getElementById('show-signup');
    const showSigninLink = document.getElementById('show-signin');
    const loginModal = document.getElementById('google-login-modal');
    const signupModal = document.getElementById('signup-modal');
    
    if (showSignupLink && signupModal && loginModal) {
        showSignupLink.addEventListener('click', function(e) {
            e.preventDefault();
            loginModal.style.display = 'none';
            signupModal.style.display = 'flex';
        });
    }
    
    if (showSigninLink && loginModal && signupModal) {
        showSigninLink.addEventListener('click', function(e) {
            e.preventDefault();
            signupModal.style.display = 'none';
            loginModal.style.display = 'flex';
        });
    }
}

function setupEmailAuthentication() {
    // Setup login form
    const loginForm = document.getElementById('email-login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            handleEmailLogin();
        });
    }
    
    // Setup signup form
    const signupForm = document.getElementById('email-signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', function(e) {
            e.preventDefault();
            handleEmailSignup();
        });
    }
}

function handleEmailLogin() {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const submitBtn = document.querySelector('.email-login-btn');
    
    if (!email || !password) {
        alert('Please fill in all fields');
        return;
    }
    
    // Set loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in...';
    
    fetch('/email-login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            email: email,
            password: password
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload();
        } else {
            alert(data.error || 'Login failed');
        }
    })
    .catch(error => {
        alert('Error during login: ' + error.message);
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign in with Email';
    });
}

function handleEmailSignup() {
    const firstName = document.getElementById('signup-firstname').value;
    const lastName = document.getElementById('signup-lastname').value;
    const email = document.getElementById('signup-email').value;
    const password = document.getElementById('signup-password').value;
    const confirmPassword = document.getElementById('signup-confirm-password').value;
    const submitBtn = document.querySelector('.email-signup-btn');
    
    if (!firstName || !lastName || !email || !password || !confirmPassword) {
        alert('Please fill in all fields');
        return;
    }
    
    if (password !== confirmPassword) {
        alert('Passwords do not match');
        return;
    }
    
    if (password.length < 8) {
        alert('Password must be at least 8 characters long');
        return;
    }
    
    // Set loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating account...';
    
    fetch('/email-signup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            firstName: firstName,
            lastName: lastName,
            email: email,
            password: password
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Account created successfully! Please sign in.');
            // Switch back to login modal
            document.getElementById('signup-modal').style.display = 'none';
            document.getElementById('google-login-modal').style.display = 'flex';
            // Clear signup form
            document.getElementById('email-signup-form').reset();
        } else {
            alert(data.error || 'Signup failed');
        }
    })
    .catch(error => {
        alert('Error during signup: ' + error.message);
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign up';
    });
}

function setLoadingState(isLoading, connectBtn, urlInput) {
    const connectText = connectBtn.querySelector('.pg-modal-connect-text');
    const loadingSpinner = connectBtn.querySelector('.pg-modal-loading-spinner');
    const cancelBtn = document.getElementById('pg-modal-cancel');
    
    connectText.style.display = isLoading ? 'none' : 'inline';
    loadingSpinner.style.display = isLoading ? 'flex' : 'none';
    connectBtn.disabled = isLoading;
    cancelBtn.disabled = isLoading;
    urlInput.disabled = isLoading;
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
            setLoadingState(true, connectPgModalBtn, pgUrlInput);
            
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
                setLoadingState(false, connectPgModalBtn, pgUrlInput);

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
                setLoadingState(false, connectPgModalBtn, pgUrlInput);
                
                alert('Error connecting to database: ' + error.message);
            });
        });
    }
}
