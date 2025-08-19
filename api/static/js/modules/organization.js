/**
 * Organization Management Functions
 */

let organizationData = null;

export function openOrganizationModal() {
    document.getElementById('organization-modal').style.display = 'block';
    loadOrganizationStatus();
}

export function closeOrganizationModal() {
    document.getElementById('organization-modal').style.display = 'none';
}

async function loadOrganizationStatus() {
    try {
        const response = await fetch('/api/organization/status');
        const data = await response.json();
        
        if (response.ok) {
            organizationData = data;
            renderOrganizationContent(data);
        } else {
            showError(data.error || 'Failed to load organization status');
        }
    } catch (error) {
        console.error('Error loading organization status:', error);
        showError('Failed to load organization information');
    }
}

function renderOrganizationContent(data) {
    const content = document.getElementById('organization-content');
    
    if (!data.has_organization) {
        content.innerHTML = `
            <div class="organization-info">
                <p>You are not part of any organization yet. Organizations are automatically created based on your email domain when you log in.</p>
            </div>
        `;
        return;
    }
    
    const org = data.organization;
    const role = data.user_role;
    
    let html = `
        <div class="organization-info" style="background: var(--falkor-secondary); border: 1.5px solid #b9aaf7; border-radius: 18px; padding: 2.2em 2.5em 1.5em 2.5em; margin-bottom: 2.5em;">
            <h3>${org.name}</h3>
            <p><strong>Domain:</strong> ${org.domain}</p>
            <p><strong>Your Role:</strong> ${role.is_admin ? 'Administrator' : (role.role ? role.role.charAt(0).toUpperCase() + role.role.slice(1) : 'Member')}</p>
            ${role.is_pending ? '<p class="warning">⚠️ Your membership is pending admin approval</p>' : ''}
        </div>
    `;
    
    if (role.is_admin) {
        html += `
            <div class="admin-section" style="background: var(--falkor-secondary); border: 1.5px solid #b9aaf7; border-radius: 18px; padding: 2.2em 2.5em 1.5em 2.5em;">
                <h4 style="font-family: 'Fira Mono', monospace; font-size: 1.5em; font-weight: 700; margin-bottom: 1.2em;">Admin Controls</h4>
                <div class="admin-actions" style="margin-bottom: 1.2em;">
                    <button onclick="loadOrganizationUsers()" class="btn btn-primary">View Members</button>
                    <button onclick="loadPendingUsers()" class="btn btn-secondary">View Pending Users</button>
                </div>
                <div id="admin-content"></div>
            </div>
        `;
        // Show members by default
        setTimeout(() => loadOrganizationUsers(), 0);
    }
    
    content.innerHTML = html;
}

window.loadOrganizationUsers = async function() {
    try {
        const response = await fetch('/api/organization/users');
        const data = await response.json();
        
        if (response.ok) {
            renderUsersList(data.users, 'Organization Members');
        } else {
            showError(data.error || 'Failed to load organization users');
        }
    } catch (error) {
        console.error('Error loading organization users:', error);
        showError('Failed to load organization users');
    }
}

window.loadPendingUsers = async function() {
    try {
        const response = await fetch('/api/organization/pending');
        const data = await response.json();
        
        if (response.ok) {
            renderPendingUsersList(data.pending_users);
        } else {
            showError(data.error || 'Failed to load pending users');
        }
    } catch (error) {
        console.error('Error loading pending users:', error);
        showError('Failed to load pending users');
    }
}

function renderUsersList(users, title) {
    const adminContent = document.getElementById('admin-content');
    
    let html = `<h5>${title}</h5>`;
    if (users.length === 0) {
        html += '<p>No users found.</p>';
    } else {
        html += `
        <table class="users-table" style="width:100%; border-collapse:separate; border-spacing: 0 0.5em;">
            <thead>
                <tr>
                    <th style="padding: 0.5em 2em 0.5em 1em; text-align:left;">First Name</th>
                    <th style="padding: 0.5em 2em 0.5em 1em; text-align:left;">Last Name</th>
                    <th style="padding: 0.5em 2em 0.5em 1em; text-align:left;">Email</th>
                    <th style="padding: 0.5em 2em 0.5em 1em; text-align:left;">Role</th>
                    <th style="padding: 0.5em 2em 0.5em 1em; text-align:left;">Status</th>
                </tr>
            </thead>
            <tbody>
        `;
        // Add user row (admin only)
        if (organizationData.user_role.is_admin) {
            html += `
                <tr>
                    <td style="padding: 0.5em 2em 0.5em 1em;"><input type="text" id="new-user-first-name" placeholder="First Name" required style="width: 98%"></td>
                    <td style="padding: 0.5em 2em 0.5em 1em;"><input type="text" id="new-user-last-name" placeholder="Last Name" required style="width: 98%"></td>
                    <td style="padding: 0.5em 2em 0.5em 1em;"><input type="email" id="new-user-email" placeholder="Enter user email" required style="width: 98%"></td>
                    <td style="padding: 0.5em 2em 0.5em 1em;"></td>
                    <td style="padding: 0.5em 2em 0.5em 1em;"><button onclick="addUserToOrganization()" class="btn btn-primary btn-sm">Add User</button></td>
                </tr>
            `;
        }
        users.forEach((user, idx) => {
            const roleDisplay = user.is_admin ? 'Admin' : (user.role || 'Member');
            const status = user.is_pending ? 'Pending' : 'Active';
            html += `
                <tr>
                    <td style="padding: 0.5em 2em 0.5em 1em; font-weight: bold;">${user.first_name ? user.first_name : ''}</td>
                    <td style="padding: 0.5em 2em 0.5em 1em; font-weight: bold;">${user.last_name ? user.last_name : ''}</td>
                    <td style="padding: 0.5em 2em 0.5em 1em;">${user.email}</td>
                    <td style="padding: 0.5em 2em 0.5em 1em;" class="user-role">
                        <span class="role-display" id="role-display-${idx}" onclick="showRoleDropdown(${idx}, '${user.email}')" style="cursor:pointer;">${roleDisplay}</span>
                        <select id="role-select-${idx}" class="role-select" style="display:none; min-width:90px;" onchange="updateUserRole('${user.email}', this.value); hideRoleDropdown(${idx});">
                            <option value="">Change Role...</option>
                            <option value="user">User</option>
                            <option value="admin">Admin</option>
                            <option value="analyst">Analyst</option>
                            <option value="viewer">Viewer</option>
                            <option value="manager">Manager</option>
                        </select>
                    </td>
                    <td style="padding: 0.5em 2em 0.5em 1em;">${status}</td>
                </tr>
            `;
        });
        html += '</tbody></table>';
    }
    adminContent.innerHTML = html;
    // Add Enter key listeners to the add user form inputs
    const emailInput = document.getElementById('new-user-email');
    const firstNameInput = document.getElementById('new-user-first-name');
    const lastNameInput = document.getElementById('new-user-last-name');
    [emailInput, firstNameInput, lastNameInput].forEach(input => {
        if (input) {
            input.addEventListener('keypress', function(event) {
                if (event.key === 'Enter') {
                    addUserToOrganization();
                }
            });
        }
    });
}

// Show/hide role dropdown for inline role editing
window.showRoleDropdown = function(idx, email) {
    document.getElementById(`role-display-${idx}`).style.display = 'none';
    document.getElementById(`role-select-${idx}`).style.display = 'inline-block';
    document.getElementById(`role-select-${idx}`).focus();
}
window.hideRoleDropdown = function(idx) {
    document.getElementById(`role-select-${idx}`).style.display = 'none';
    document.getElementById(`role-display-${idx}`).style.display = 'inline';
}

function renderPendingUsersList(pendingUsers) {
    const adminContent = document.getElementById('admin-content');
    
    let html = '<h5>Pending Users</h5>';
    
    if (pendingUsers.length === 0) {
        html += '<p>No pending users.</p>';
    } else {
        html += '<div class="users-list">';
        pendingUsers.forEach(user => {
            html += `
                <div class="user-item">
                    <div class="user-info">
                        <strong>${user.first_name} ${user.last_name}</strong>
                        <br>
                        <span class="user-email">${user.email}</span>
                        <br>
                        <small>Invited by: ${user.invited_by}</small>
                    </div>
                    <div class="user-actions">
                        <button onclick="approveUser('${user.email}')" class="btn btn-sm btn-success">Approve</button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }
    
    adminContent.innerHTML = html;
}



window.addUserToOrganization = async function() {
    const email = document.getElementById('new-user-email').value.trim();
    const first_name = document.getElementById('new-user-first-name').value.trim();
    const last_name = document.getElementById('new-user-last-name').value.trim();
    if (!email) {
        showError('Please enter a valid email address');
        return;
    }
    if (!first_name) {
        showError('Please enter a first name');
        return;
    }
    if (!last_name) {
        showError('Please enter a last name');
        return;
    }
    try {
        const response = await fetch('/api/organization/add-user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email: email, first_name: first_name, last_name: last_name })
        });
        const data = await response.json();
        if (response.ok) {
            loadOrganizationUsers(); // Refresh the users list, no alert
        } else {
            showError(data.error || 'Failed to add user');
        }
    } catch (error) {
        console.error('Error adding user:', error);
        showError('Failed to add user to organization');
    }
}

window.approveUser = async function(email) {
    try {
        const response = await fetch('/api/organization/approve-user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email: email })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadPendingUsers(); // Refresh the pending users list
        } else {
            showError(data.error || 'Failed to approve user');
        }
    } catch (error) {
        console.error('Error approving user:', error);
        showError('Failed to approve user');
    }
}

window.updateUserRole = async function(email, newRole) {
    if (!newRole) return; // No role selected
    
    try {
        const response = await fetch('/api/organization/update-role', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                target_email: email,
                new_role: newRole
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadOrganizationUsers(); // Refresh the users list
        } else {
            showError(data.error || 'Failed to update user role');
        }
    } catch (error) {
        console.error('Error updating user role:', error);
        showError('Failed to update user role');
    }
}

function showError(message) {
    // You can customize this based on your existing error handling
    alert('Error: ' + message);
}

function showSuccess(message) {
    // You can customize this based on your existing success handling
    alert('Success: ' + message);
}

// Close modal when clicking outside of it
window.addEventListener('click', function(event) {
    const modal = document.getElementById('organization-modal');
    if (event.target === modal) {
        closeOrganizationModal();
    }
});

// Close modal on ESC key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('organization-modal');
        if (modal && modal.style.display === 'block') {
            closeOrganizationModal();
        }
    }
});
