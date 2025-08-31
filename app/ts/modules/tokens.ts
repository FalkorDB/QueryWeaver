/**
 * Token management functionality (TypeScript)
 */
interface Token {
    token_id: string;
    created_at: number;
}

interface TokenListResponse {
    tokens: Token[];
}

let currentDeleteTokenId: string | null = null;

export function setupTokenManagement() {
    const apiTokensBtn = document.getElementById('api-tokens-btn');
    const tokensModal = document.getElementById('tokens-modal');
    const closeTokensModal = document.getElementById('close-tokens-modal');
    const generateTokenBtn = document.getElementById('generate-token-btn');
    const copyTokenBtn = document.getElementById('copy-token-btn');
    const toggleTokenVisibilityBtn = document.getElementById('toggle-token-visibility');
    const deleteTokenModal = document.getElementById('delete-token-modal');
    const closeDeleteTokenModal = document.getElementById('close-delete-token-modal');
    const confirmDeleteToken = document.getElementById('confirm-delete-token');
    const cancelDeleteToken = document.getElementById('cancel-delete-token');

    if (!apiTokensBtn || !tokensModal) return;

    // Open tokens modal
    apiTokensBtn.addEventListener('click', async function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // Close user profile dropdown
        const userProfileDropdown = document.getElementById('user-profile-dropdown');
        if (userProfileDropdown) {
            userProfileDropdown.classList.remove('show');
        }
        
        // Use flex so the overlay uses its centering styles (align-items/justify-content)
        tokensModal.style.display = 'flex';
        await loadTokens();
    });

    // Close tokens modal
    closeTokensModal?.addEventListener('click', function() {
        tokensModal.style.display = 'none';
        hideTokenGenerated();
    });

    // Close modal when clicking outside
    tokensModal.addEventListener('click', function(e) {
        if (e.target === tokensModal) {
            tokensModal.style.display = 'none';
            hideTokenGenerated();
        }
    });

    // Generate new token
    generateTokenBtn?.addEventListener('click', async function() {
        await generateToken();
    });


    // Copy token to clipboard (read the input value directly)
    copyTokenBtn?.addEventListener('click', function() {
        const tokenInput = document.getElementById('new-token-value') as HTMLInputElement;
        if (tokenInput) {
            const value = tokenInput.value || '';
            if (value) {
                navigator.clipboard?.writeText(value).then(() => {
                    const originalText = copyTokenBtn.textContent;
                    copyTokenBtn.textContent = 'Copied!';
                    setTimeout(() => {
                        copyTokenBtn.textContent = originalText as string;
                    }, 2000);
                }).catch(() => {
                    tokenInput.select();
                    document.execCommand('copy');
                });
            }
        }
    });

    // Toggle token visibility: simply toggle input.type between password and text
    toggleTokenVisibilityBtn?.addEventListener('click', function() {
        const tokenInput = document.getElementById('new-token-value') as HTMLInputElement;
        if (!tokenInput) return;
        const btn = toggleTokenVisibilityBtn as HTMLButtonElement;
        if (tokenInput.type === 'password') {
            tokenInput.type = 'text';
            btn.textContent = 'Hide';
            setTimeout(() => tokenInput.select(), 50);
        } else {
            tokenInput.type = 'password';
            btn.textContent = 'Show';
        }
    });

    // Delete token modal handlers
    closeDeleteTokenModal?.addEventListener('click', function() {
        if (deleteTokenModal) {
            deleteTokenModal.style.display = 'none';
        }
        currentDeleteTokenId = null;
    });

    cancelDeleteToken?.addEventListener('click', function() {
        if (deleteTokenModal) {
            deleteTokenModal.style.display = 'none';
        }
        currentDeleteTokenId = null;
    });

    confirmDeleteToken?.addEventListener('click', async function() {
        if (currentDeleteTokenId) {
            await deleteToken(currentDeleteTokenId);
        }
    });

    // Close delete modal when clicking outside
    deleteTokenModal?.addEventListener('click', function(e) {
        if (e.target === deleteTokenModal) {
            deleteTokenModal.style.display = 'none';
            currentDeleteTokenId = null;
        }
    });

    // Handle escape key - check computed style to determine visibility
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            try {
                if (tokensModal && getComputedStyle(tokensModal).display !== 'none') {
                    tokensModal.style.display = 'none';
                    hideTokenGenerated();
                }
                if (deleteTokenModal && getComputedStyle(deleteTokenModal).display !== 'none') {
                    deleteTokenModal.style.display = 'none';
                    currentDeleteTokenId = null;
                }
            } catch (err) {
                // ignore if computed style fails for any reason
            }
        }
    });
}

async function loadTokens(): Promise<void> {
    try {
        const response = await fetch('/api/tokens/list', {
            method: 'GET',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data: TokenListResponse = await response.json();
        displayTokens(data.tokens);
    } catch (error) {
        console.error('Error loading tokens:', error);
        showError('Failed to load tokens. Please try again.');
    }
}

function displayTokens(tokens: Token[]): void {
    const noTokensMessage = document.getElementById('no-tokens-message');
    const tokensTable = document.getElementById('tokens-table');
    const tokensTbody = document.getElementById('tokens-tbody');

    if (!noTokensMessage || !tokensTable || !tokensTbody) return;

    if (tokens.length === 0) {
        noTokensMessage.style.display = 'block';
        tokensTable.style.display = 'none';
    } else {
        noTokensMessage.style.display = 'none';
        tokensTable.style.display = 'block';

        tokensTbody.innerHTML = '';
        tokens.forEach(token => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>****${token.token_id}</td>
                <td>${formatDate(token.created_at)}</td>
                <td>
                    <button class="btn btn-danger btn-sm delete-token-btn" data-token-id="${token.token_id}">
                        Delete
                    </button>
                </td>
            `;
            tokensTbody.appendChild(row);
        });

        // Add event listeners to delete buttons
        const deleteButtons = tokensTbody.querySelectorAll('.delete-token-btn');
        deleteButtons.forEach(button => {
            button.addEventListener('click', function(ev) {
                const target = ev.currentTarget as HTMLElement;
                const tokenId = target.getAttribute('data-token-id');
                if (tokenId) {
                    showDeleteTokenModal(tokenId);
                }
            });
        });
    }
}

async function generateToken(): Promise<void> {
    const generateBtn = document.getElementById('generate-token-btn') as HTMLButtonElement;
    if (!generateBtn) return;

    try {
        generateBtn.disabled = true;
        generateBtn.textContent = 'Generating...';

        const response = await fetch('/api/tokens/generate', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data: Token = await response.json();
        showTokenGenerated(data.token_id);
        await loadTokens(); // Refresh the tokens list
    } catch (error) {
        console.error('Error generating token:', error);
        showError('Failed to generate token. Please try again.');
    } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate New Token';
    }
}

function showTokenGenerated(token: string): void {
    const tokenGenerated = document.getElementById('token-generated');
    const tokenInput = document.getElementById('new-token-value') as HTMLInputElement;

    if (tokenGenerated && tokenInput) {
        // Store the real token as the input's value and show it masked by default
        tokenInput.value = token;
        tokenInput.type = 'password';
        tokenGenerated.style.display = 'block';
    }
}

function hideTokenGenerated(): void {
    const tokenGenerated = document.getElementById('token-generated');
    const tokenInput = document.getElementById('new-token-value') as HTMLInputElement;

    if (tokenGenerated) {
        tokenGenerated.style.display = 'none';
    }
    if (tokenInput) {
        tokenInput.value = '';
    }
}

function showDeleteTokenModal(tokenId: string): void {
    const deleteTokenModal = document.getElementById('delete-token-modal');
    const deleteTokenLast4 = document.getElementById('delete-token-last4');

    if (deleteTokenModal && deleteTokenLast4) {
        currentDeleteTokenId = tokenId;
        deleteTokenLast4.textContent = tokenId;
        deleteTokenModal.style.display = 'flex'; // Use flex to ensure overlay centers content
    }
}

async function deleteToken(tokenId: string): Promise<void> {
    const confirmBtn = document.getElementById('confirm-delete-token') as HTMLButtonElement;
    if (!confirmBtn) return;

    try {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Deleting...';

        const response = await fetch(`/api/tokens/${tokenId}`, {
            method: 'DELETE',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        // Close modal and refresh tokens
        const deleteTokenModal = document.getElementById('delete-token-modal');
        if (deleteTokenModal) {
            deleteTokenModal.style.display = 'none';
        }
        currentDeleteTokenId = null;

        await loadTokens(); // Refresh the tokens list
        showSuccess('Token deleted successfully.');
    } catch (error) {
        console.error('Error deleting token:', error);
        showError('Failed to delete token. Please try again.');
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Delete Token';
    }
}

function formatDate(timestamp: number | null | undefined): string {
    if (!timestamp && timestamp !== 0) return '';

    // Backend may return created_at in seconds (10 digits) or milliseconds (13 digits).
    // Normalize to milliseconds for Date constructor.
    let ms = Number(timestamp);
    if (!isFinite(ms)) return '';

    // If the value looks like seconds (less than 1e12), convert to ms.
    // Current UNIX time in ms is ~1.7e12 (year 2024). Anything below 1e12 is almost certainly seconds.
    if (ms > 0 && ms < 1e12) {
        ms = ms * 1000;
    }

    const date = new Date(ms);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function showError(message: string): void {
    // You can implement a proper notification system here
    // For now, just use alert
    alert('Error: ' + message);
}

function showSuccess(message: string): void {
    // You can implement a proper notification system here
    // For now, just use alert
    alert(message);
}