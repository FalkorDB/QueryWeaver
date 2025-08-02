/**
 * Graph loading and management functionality
 */

import { DOM } from './config.js';
import { addMessage, initChat } from './messages.js';

export function loadGraphs() {
    // Only fetch available graphs if user is authenticated
    const isAuthenticated = window.isAuthenticated !== undefined ? window.isAuthenticated : false;
    
    if (!isAuthenticated) {
        // User not authenticated - set appropriate placeholder
        DOM.graphSelect.innerHTML = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Please log in to access graphs";
        option.disabled = true;
        DOM.graphSelect.appendChild(option);
        
        DOM.messageInput.disabled = true;
        DOM.submitButton.disabled = true;
        DOM.messageInput.placeholder = "Please log in to start chatting";
        return;
    }

    // Fetch available graphs (only if authenticated)
    fetch("/graphs")
        .then(response => {
            if (!response.ok) {
                if (response.status === 401) {
                    throw new Error("Authentication required. Please log in to access graphs.");
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            DOM.graphSelect.innerHTML = "";
            
            if (!data || data.length === 0) {
                // No graphs available
                const option = document.createElement("option");
                option.value = "";
                option.textContent = "No graphs available";
                option.disabled = true;
                DOM.graphSelect.appendChild(option);
                
                // Disable chat input when no graphs are available
                DOM.messageInput.disabled = true;
                DOM.submitButton.disabled = true;
                DOM.messageInput.placeholder = "Please upload a schema or connect a database to start chatting";
                
                addMessage("No graphs are available. Please upload a schema file or connect to a database to get started.", false);
                return;
            }
            
            data.forEach(graph => {
                const option = document.createElement("option");
                option.value = graph;
                option.textContent = graph;
                option.title = graph;
                DOM.graphSelect.appendChild(option);
            });

            // Re-enable chat input when graphs are available
            DOM.messageInput.disabled = false;
            DOM.submitButton.disabled = false;
            DOM.messageInput.placeholder = "Describe the SQL query you want...";
        })
        .catch(error => {
            console.error("Error fetching graphs:", error);
            
            // Show appropriate error message and disable input
            if (error.message.includes("Authentication required")) {
                addMessage("Authentication required. Please log in to access your graphs.", false);
                // Don't disable input for auth errors as user needs to log in
            } else {
                addMessage("Sorry, there was an error fetching the available graphs: " + error.message, false);
                DOM.messageInput.disabled = true;
                DOM.submitButton.disabled = true;
                DOM.messageInput.placeholder = "Cannot connect to server";
            }
            
            // Add a placeholder option to show the error state
            DOM.graphSelect.innerHTML = "";
            const option = document.createElement("option");
            option.value = "";
            option.textContent = error.message.includes("Authentication") ? "Please log in" : "Error loading graphs";
            option.disabled = true;
            DOM.graphSelect.appendChild(option);
        });
}

export function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    fetch("/graphs", {
        method: 'POST',
        body: formData,
    }).then(response => {
        response.json()
    }).then(data => {
        console.log('File uploaded successfully', data);
    }).catch(error => {
        console.error('Error uploading file:', error);
        addMessage('Sorry, there was an error uploading your file: ' + error.message, false);
    });
}

export function onGraphChange() {
    initChat();
}
