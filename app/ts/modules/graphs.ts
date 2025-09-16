/**
 * Graph loading and management functionality (TypeScript)
 */

import { DOM } from "./config";
import { addMessage, initChat } from "./messages";
import {
  addGraphOption,
  clearGraphOptions,
  setSelectedGraph,
  toggleOptions,
  getSelectedGraph,
} from "./graph_select";

export function loadGraphs() {
  const isAuthenticated =
    (window as any).isAuthenticated !== undefined
      ? (window as any).isAuthenticated
      : false;

  if (!isAuthenticated) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Please log in to access graphs";
    option.disabled = true;

    if (DOM.messageInput) DOM.messageInput.disabled = true;
    if (DOM.submitButton) DOM.submitButton.disabled = true;
    if (DOM.messageInput)
      DOM.messageInput.placeholder = "Please log in to start chatting";
    return;
  }

  fetch("/graphs")
    .then((response) => {
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error(
            "Authentication required. Please log in to access graphs."
          );
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return response.json();
    })
    .then((data: string[]) => {
      if (!data || data.length === 0) {
        // Clear custom dropdown and show no graphs state
        clearGraphOptions();

        if (DOM.messageInput) DOM.messageInput.disabled = true;
        if (DOM.submitButton) DOM.submitButton.disabled = true;
        if (DOM.messageInput)
          DOM.messageInput.placeholder =
            "Please upload a schema or connect a database to start chatting";

        addMessage(
          "No graphs are available. Please upload a schema file or connect to a database to get started."
        );

        // Update the visible selected label to show no graphs state
        const selectedLabel = document.getElementById("graph-selected");
        if (selectedLabel) {
          const dropdownText = selectedLabel.querySelector(".dropdown-text");
          if (dropdownText) {
            dropdownText.textContent = "Select Database";
          }
        }
        return;
      }

      // populate hidden select for legacy code
      data.forEach((graph) => {
        const option = document.createElement("option");
        option.value = graph;
        option.textContent = graph;
        option.title = graph;
      });

      // populate custom dropdown
      try {
        clearGraphOptions();
        data.forEach((graph) => {
          // Check if this graph is a demo database
          const generalPrefix = (window as any).generalPrefix;
          const isDemo = !!(generalPrefix && graph.startsWith(generalPrefix));
          
          addGraphOption(
            graph,
            (name) => {
              // onSelect
              setSelectedGraph(name);
              initChat();
              if (typeof (window as any).updateInputState === 'function') {
                (window as any).updateInputState();
              }
            },
            async (name) => {
              // onDelete
              const confirmed = confirm(
                `Delete graph "${name}"? This action cannot be undone.`
              );
              if (!confirmed) return;
              try {
                const resp = await fetch(
                  `/graphs/${encodeURIComponent(name)}`,
                  { method: "DELETE" }
                );
                if (!resp.ok) {
                  const text = await resp.text();
                  throw new Error(`Delete failed: ${resp.status} ${text}`);
                }
                addMessage(`Graph "${name}" deleted.`);
              } catch (err) {
                console.error("Error deleting graph:", err);
                addMessage("Error deleting graph: " + (err as Error).message);
              } finally {
                // Always refresh the graph list after delete attempt
                loadGraphs();
              }
            },
            isDemo
          );
        });

        const sel = document.getElementById("graph-selected");
        if (sel) sel.addEventListener("click", () => toggleOptions());
      } catch (e) {
        console.warn("Custom graph dropdown not available", e);
      }

      // Attach delete button handler if present
      const deleteBtn = document.getElementById("delete-graph-btn");
      if (deleteBtn) {
        deleteBtn.removeEventListener("click", onDeleteClick as EventListener);
        deleteBtn.addEventListener("click", onDeleteClick as EventListener);
      }
    })
    .catch((error) => {
      console.error("Error fetching graphs:", error);

      if ((error as Error).message.includes("Authentication required")) {
        addMessage(
          "Authentication required. Please log in to access your graphs."
        );
      } else {
        addMessage(
          "Sorry, there was an error fetching the available graphs: " +
            (error as Error).message
        );
        if (DOM.messageInput) DOM.messageInput.disabled = true;
        if (DOM.submitButton) DOM.submitButton.disabled = true;
        if (DOM.messageInput)
          DOM.messageInput.placeholder = "Cannot connect to server";
      }

      const option = document.createElement("option");
      option.value = "";
      option.textContent = (error as Error).message.includes("Authentication")
        ? "Please log in"
        : "Error loading graphs";
      option.disabled = true;
    });
}

async function onDeleteClick() {
  const graphName = getSelectedGraph();
  if (!graphName) {
    addMessage("Please select a graph to delete.");
    return;
  }

  const confirmed = confirm(
    `Are you sure you want to delete the graph '${graphName}'? This action cannot be undone.`
  );
  if (!confirmed) return;

  try {
    const resp = await fetch(`/graphs/${encodeURIComponent(graphName)}`, {
      method: "DELETE",
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Failed to delete graph: ${resp.status} ${text}`);
    }
    addMessage(`Graph '${graphName}' deleted.`);
    // Clear current chat state if the deleted graph was selected
    if (window && (window as any).currentGraph === graphName) {
      (window as any).currentGraph = undefined;
    }
  } catch (err) {
    console.error("Error deleting graph:", err);
    addMessage("Error deleting graph: " + (err as Error).message);
  } finally {
    // Always reload graphs list after delete attempt
    loadGraphs();
  }
}

export function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement | null;
  const file = target?.files ? target.files[0] : null;
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  fetch("/graphs", {
    method: "POST",
    body: formData,
  })
    .then((response) => response.json())
    .then((data) => {
      console.log("File uploaded successfully", data);
    })
    .catch((error) => {
      console.error("Error uploading file:", error);
      addMessage(
        "Sorry, there was an error uploading your file: " +
          (error as Error).message
      );
    });
}

export function onGraphChange() {
  initChat();
  if (typeof (window as any).updateInputState === 'function') {
    (window as any).updateInputState();
  }
}
