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
            handleEmailLogin(loginForm);
        });
    }
    
    // Setup signup form
    const signupForm = document.getElementById('email-signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', function(e) {
            e.preventDefault();
            handleEmailSignup(signupForm);
        });
    }
}

async function handleEmailLogin(form) {
    const email = form.querySelector('#login-email').value.trim();
    const password = form.querySelector('#login-password').value.trim();
    const submitBtn = form.querySelector('.email-login-btn');

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

function handleEmailSignup(form) {
    const firstName = form.querySelector('#signup-firstname').value.trim();
    const lastName = form.querySelector('#signup-lastname').value.trim();
    const email = form.querySelector('#signup-email').value.trim();
    const password = form.querySelector('#signup-password').value.trim();
    const confirmPassword = form.querySelector('#signup-confirm-password').value.trim();

    const submitBtn = form.querySelector('.email-signup-btn');

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
    const connectText = connectBtn.querySelector('.db-modal-connect-text');
    const loadingSpinner = connectBtn.querySelector('.db-modal-loading-spinner');
    const cancelBtn = document.getElementById('db-modal-cancel');
    
    connectText.style.display = isLoading ? 'none' : 'inline';
    loadingSpinner.style.display = isLoading ? 'flex' : 'none';
    connectBtn.disabled = isLoading;
    cancelBtn.disabled = isLoading;
    urlInput.disabled = isLoading;
}

export function setupDatabaseModal() {
    var dbModal = document.getElementById('db-modal');
    var cancelDbModalBtn = document.getElementById('db-modal-cancel');
    var connectDbModalBtn = document.getElementById('db-modal-connect');
    var dbUrlInput = document.getElementById('db-url-input');
    var dbTypeSelect = document.getElementById('database-type-select');
    var dbModalTitle = document.getElementById('db-modal-title');

    // Database URL templates and titles
    const databaseConfig = {
        postgresql: {
            title: 'Connect to PostgreSQL',
            placeholder: 'postgresql://username:password@host:port/database',
            example: 'postgresql://myuser:mypass@localhost:5432/mydb'
        },
        mysql: {
            title: 'Connect to MySQL',
            placeholder: 'mysql://username:password@host:port/database',
            example: 'mysql://myuser:mypass@localhost:3306/mydb'
        }
    };

    // Handle database type selection
    dbTypeSelect.addEventListener('change', function() {
        const selectedType = this.value;
        if (selectedType && databaseConfig[selectedType]) {
            dbUrlInput.disabled = false;
            dbUrlInput.placeholder = databaseConfig[selectedType].placeholder;
            dbModal.style.display = 'flex';
            dbModalTitle.textContent = databaseConfig[selectedType].title;
            dbUrlInput.placeholder = databaseConfig[selectedType].placeholder;
            // Enable Connect button when modal opens
            connectDbModalBtn.disabled = false;
            // Focus the input field when modal opens
            if (dbUrlInput) {
                setTimeout(() => {
                    dbUrlInput.focus();
                }, 100);
            }
        } else {
            // Disable if no valid selection
            dbUrlInput.disabled = true;
            dbUrlInput.placeholder = 'Select database type first...';
            connectDbModalBtn.disabled = true;
        }
    });
    
    if (cancelDbModalBtn && dbModal) {
        cancelDbModalBtn.addEventListener('click', function() {
            dbModal.style.display = 'none';
            // Reset dropdown to 'Select Database' after closing modal
            dbTypeSelect.selectedIndex = 0;
            // Reset Connect button state
            connectDbModalBtn.disabled = true;
        });
    }
    
    // Allow closing database modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (dbModal && dbModal.style.display === 'flex' && e.key === 'Escape') {
            dbModal.style.display = 'none';
        }
    });

    // Handle Connect button for database modal

    // Add Enter key support for the input field
    dbUrlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            connectDbModalBtn.click();
        }
    });

    connectDbModalBtn.addEventListener('click', function() {
        const dbUrl = dbUrlInput.value.trim();
        const selectedType = dbTypeSelect.value;
        
        if (!selectedType) {
            alert('Please select a database type.');
            return;
        }
        
        if (!dbUrl) {
            alert('Please enter a database URL.');
            return;
        }
        
        // Validate URL format based on selected type
        const config = databaseConfig[selectedType];
        if (selectedType === 'postgresql' && !dbUrl.startsWith('postgresql://') && !dbUrl.startsWith('postgres://')) {
            alert('PostgreSQL URL must start with postgresql:// or postgres://');
            return;
        }
        if (selectedType === 'mysql' && !dbUrl.startsWith('mysql://')) {
            alert('MySQL URL must start with mysql://');
            return;
        }
        
        // Show loading state
        setLoadingState(true, connectDbModalBtn, dbUrlInput);
        
        fetch('/database', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: dbUrl })
        })
        .then(response => response.json())
        .then(data => {
            // Reset loading state
            setLoadingState(false, connectDbModalBtn, dbUrlInput);

            if (data.success) {
                dbModal.style.display = 'none'; // Close modal on success
                // Reset dropdown to 'Select Database' after closing modal
                dbTypeSelect.selectedIndex = 0;
                // Reset Connect button state
                connectDbModalBtn.disabled = true;
                // Refresh the graph list to show the new database
                location.reload();
            } else {
                alert('Failed to connect: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            // Reset loading state on error
            setLoadingState(false, connectDbModalBtn, dbUrlInput);
            
            alert('Error connecting to database: ' + error.message);
        });
    });
}
