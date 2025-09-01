/**
 * Modal dialogs and authentication (TypeScript)
 */

export function setupAuthenticationModal() {
    const isAuthenticated = (window as any).isAuthenticated !== undefined ? (window as any).isAuthenticated : false;
    const googleLoginModal = document.getElementById('google-login-modal') as HTMLElement | null;
    const container = document.getElementById('container') as HTMLElement | null;

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

function setLoadingState(isLoading: boolean, connectBtn: HTMLButtonElement, urlInput: HTMLInputElement) {
    const connectText = connectBtn.querySelector('.db-modal-connect-text') as HTMLElement | null;
    const loadingSpinner = connectBtn.querySelector('.db-modal-loading-spinner') as HTMLElement | null;
    const cancelBtn = document.getElementById('db-modal-cancel') as HTMLButtonElement | null;

    if (connectText) connectText.style.display = isLoading ? 'none' : 'inline';
    if (loadingSpinner) loadingSpinner.style.display = isLoading ? 'flex' : 'none';
    connectBtn.disabled = isLoading;
    if (cancelBtn) cancelBtn.disabled = isLoading;
    urlInput.disabled = isLoading;
}

export function setupDatabaseModal() {
    const dbModal = document.getElementById('db-modal') as HTMLElement;
    // Select any connect buttons by id or class to be resilient to template variations
    const openConnectBtns = Array.from(document.querySelectorAll('#connect-database-btn, .connect-database-btn, #connect-database')) as HTMLButtonElement[];
    const cancelDbModalBtn = document.getElementById('db-modal-cancel') as HTMLButtonElement;
    const connectDbModalBtn = document.getElementById('db-modal-connect') as HTMLButtonElement;
    const dbUrlInput = document.getElementById('db-url-input') as HTMLInputElement;
    // This is a hidden input used by the custom dropdown UI
    const dbTypeSelect = document.getElementById('database-type-select') as HTMLInputElement;

    const databaseConfig: Record<string, { placeholder: string; example: string }> = {
        postgresql: {
            placeholder: 'postgresql://username:password@host:port/database',
            example: 'postgresql://myuser:mypass@localhost:5432/mydb'
        },
        mysql: {
            placeholder: 'mysql://username:password@host:port/database',
            example: 'mysql://myuser:mypass@localhost:3306/mydb'
        }
    };

    const openModal = function() {
        if (connectDbModalBtn) connectDbModalBtn.disabled = true;
        if (dbTypeSelect) dbTypeSelect.value = '';
        const steps = document.getElementById('db-connection-steps-list') as HTMLUListElement | null;
        if (steps) steps.innerHTML = '';
        dbModal.style.display = 'flex';
    };

    // Open modal from any connect-database button (header and toolbar)
    if (openConnectBtns && openConnectBtns.length > 0) {
        openConnectBtns.forEach(b => b.addEventListener('click', openModal));
    }

    
    // Helpers for displaying incremental connection steps in the modal (static elements in template)
    function addStep(text: string, status: 'pending' | 'success' | 'error' = 'pending') {
        const list = document.getElementById('db-connection-steps-list') as HTMLUListElement | null;
        if (!list) return;

        // Mark the previous pending step as completed (✓) when adding a new step
        const prevLi = list.lastElementChild as HTMLLIElement | null;
        if (prevLi) {
            const prevIcon = prevLi.querySelector('.step-icon') as HTMLElement | null;
            if (prevIcon && prevIcon.classList.contains('pending')) {
                prevIcon.className = 'step-icon success';
                prevIcon.textContent = '✓';
            }
        }

        const li = document.createElement('li');
        li.className = 'db-connection-step';

        const icon = document.createElement('span');
        icon.className = 'step-icon ' + status;
        if (status === 'pending') icon.textContent = '⭮';
        else if (status === 'success') icon.textContent = '✓';
        else icon.textContent = '✕';

        const textNode = document.createElement('span');
        textNode.textContent = text;

        li.appendChild(icon);
        li.appendChild(textNode);
        list.appendChild(li);
        list.scrollTop = list.scrollHeight;
    }

    dbTypeSelect.addEventListener('change', function(this: HTMLInputElement) {
        const selectedType = this.value;
        if (selectedType && databaseConfig[selectedType]) {
            dbUrlInput.disabled = false;
            dbUrlInput.placeholder = databaseConfig[selectedType].placeholder;
            dbModal.style.display = 'flex';
            // clear previous connection steps
            const existingList = document.getElementById('db-connection-steps-list') as HTMLUListElement | null;
            if (existingList) existingList.innerHTML = '';
            connectDbModalBtn.disabled = false;
            setTimeout(() => dbUrlInput.focus(), 100);
        } else {
            dbUrlInput.disabled = true;
            dbUrlInput.placeholder = 'Select database type first...';
            connectDbModalBtn.disabled = true;
        }
    });

    if (cancelDbModalBtn && dbModal) {
        cancelDbModalBtn.addEventListener('click', function() {
            dbModal.style.display = 'none';
            if (dbTypeSelect) dbTypeSelect.value = '';
            if (connectDbModalBtn) connectDbModalBtn.disabled = true;
        });
    }

    document.addEventListener('keydown', function(e) {
        if (dbModal && dbModal.style.display === 'flex' && e.key === 'Escape') {
            dbModal.style.display = 'none';
        }
    });

    dbUrlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            connectDbModalBtn.click();
        }
    });

    connectDbModalBtn.addEventListener('click', function() {
    if (!connectDbModalBtn || !dbUrlInput) return;
    const connectBtn = connectDbModalBtn as HTMLButtonElement;
    const urlInput = dbUrlInput as HTMLInputElement;
    const dbUrl = urlInput.value.trim();
        const selectedType = dbTypeSelect.value;

        if (!selectedType) {
            alert('Please select a database type.');
            return;
        }
        if (!dbUrl) {
            alert('Please enter a database URL.');
            return;
        }

        if (selectedType === 'postgresql' && !dbUrl.startsWith('postgresql://') && !dbUrl.startsWith('postgres://')) {
            alert('PostgreSQL URL must start with postgresql:// or postgres://');
            return;
        }
        if (selectedType === 'mysql' && !dbUrl.startsWith('mysql://')) {
            alert('MySQL URL must start with mysql://');
            return;
        }

    setLoadingState(true, connectBtn, urlInput);

    fetch('/database', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: dbUrl, type: selectedType }),
        }).then(response => {
            if (!response.ok) throw new Error(`Network response was not ok (${response.status})`);

            const reader = response.body!.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const delimiter = '|||FALKORDB_MESSAGE_BOUNDARY|||';

            function processChunk(text: string) {
                if (!text || !text.trim()) return;
                let obj: any = null;
                try {
                    obj = JSON.parse(text);
                } catch (e) {
                    console.error('Failed to parse chunk as JSON', e, text);
                    return;
                }

                if (obj.type === 'reasoning_step') {
                    // show incremental step
                    addStep(obj.message || 'Working...', 'pending');
                } else if (obj.type === 'final_result') {
                    // mark last step as success and finish
                    addStep(obj.message || 'Completed', obj.success ? 'success' : 'error');
                    setLoadingState(false, connectBtn, urlInput);
                    if (obj.success) {
                        if (dbModal) dbModal.style.display = 'none';
                        if (dbTypeSelect) dbTypeSelect.value = '';
                        if (connectBtn) connectBtn.disabled = true;
                        location.reload();
                    } else {
                        alert('Failed to connect: ' + (obj.message || 'Unknown error'));
                    }
                } else if (obj.type === 'error') {
                    addStep(obj.message || 'Error', 'error');
                    setLoadingState(false, connectBtn, urlInput);
                    alert('Error connecting to database: ' + (obj.message || 'Unknown error'));
                } else {
                    // handle other message types if needed
                    console.log('Stream message', obj);
                }
            }

            function pump(): Promise<any> {
                return reader.read().then(({ done, value }) => {
                    if (done) {
                        if (buffer.length > 0) {
                            processChunk(buffer);
                        }
                        setLoadingState(false, connectBtn, urlInput);
                        return;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const parts = buffer.split(delimiter);
                    // last piece is possibly incomplete
                    buffer = parts.pop() || '';
                    for (const part of parts) {
                        processChunk(part);
                    }
                    return pump();
                });
            }

            return pump();
        }).catch(error => {
            setLoadingState(false, connectBtn, urlInput);
            alert('Error connecting to database: ' + (error as Error).message);
        });
    });
}
