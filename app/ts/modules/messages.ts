/**
 * Message handling and UI functions (TypeScript)
 */

import { DOM, state } from "./config";
import { getSelectedGraph } from "./graph_select";
import { adjustTextareaHeight } from "./input";

export function addMessage(
  message: string,
  type:
    | "user"
    | "bot"
    | "followup"
    | "final-result"
    | "query-final-result"
    | "loading" = "bot",
  isQuery = false,
  userInfo: { picture?: string; name?: string } | null = null,
  queryResult: any = null
) {
  const messageDiv = document.createElement("div");
  const messageDivContainer = document.createElement("div");

  messageDiv.className = "message";
  messageDivContainer.className = "message-container";

  let userAvatar: HTMLImageElement | null = null;

  switch (type) {
    case "followup":
      messageDivContainer.className += " followup-message-container";
      messageDiv.className += " followup-message";
      messageDiv.textContent = message;
      break;
    case "user":
      messageDivContainer.className += " user-message-container";
      messageDiv.className += " user-message";

      if (userInfo && userInfo.picture) {
        userAvatar = document.createElement("img");
        userAvatar.src = userInfo.picture;
        userAvatar.alt =
          (userInfo.name?.charAt(0).toUpperCase() as string) || "User";
        userAvatar.className = "user-message-avatar";
        messageDivContainer.classList.add("has-avatar");
      }

      state.questions_history.push(message);
      break;
    case "bot":
      messageDivContainer.className += " bot-message-container";
      messageDiv.className += " bot-message";
      break;
    case "final-result":
      state.result_history.push(message);
      messageDivContainer.className += " final-result-message-container";
      messageDiv.className += " final-result-message";
      if (isQuery) messageDiv.classList.add("query-text");
      break;
    case "query-final-result":
      messageDivContainer.className += " final-result-message-container";
      messageDiv.className += " final-result-message";
      messageDiv.style.overflow = "auto";
      const table = document.createElement("table");
      table.id = "query-final-result-table";
      const tableHeader = document.createElement("thead");
      const headerRow = document.createElement("tr");
      Object.keys(queryResult[0]).forEach((column: any) => {
        const headerCell = document.createElement("th");
        headerCell.textContent = column;
        headerRow.appendChild(headerCell);
      });
      tableHeader.appendChild(headerRow);
      table.appendChild(tableHeader);
      const tableBody = document.createElement("tbody");
      queryResult.forEach((row: any) => {
        const rowRow = document.createElement("tr");
        Object.values(row).forEach((value: any) => {
          const cell = document.createElement("td");
          cell.textContent = value;
          rowRow.appendChild(cell);
        });
        tableBody.appendChild(rowRow);
      });
      table.appendChild(tableBody);
      messageDiv.appendChild(table);
      break;
    case "loading":
      messageDivContainer.className += " bot-message-container";
      messageDiv.className += " bot-message";
      messageDivContainer.id = "loading-message-container";
      messageDivContainer.className += " loading-message-container";
      break;
  }

  const block = formatBlock(message);

  if (block) {
    block.forEach((lineDiv) => {
      messageDiv.appendChild(lineDiv);
    });
  } else if (type !== "loading" && type !== "query-final-result") {
    messageDiv.textContent = message;
  }

  if (type !== "loading") {
    messageDivContainer.appendChild(messageDiv);
    if (userAvatar) {
      messageDivContainer.appendChild(userAvatar);
    }
  }

  DOM.chatMessages?.appendChild(messageDivContainer);
  if (DOM.chatMessages)
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;

  return messageDiv;
}

export function removeLoadingMessage() {
  const loadingMessageContainer = document.getElementById(
    "loading-message-container"
  );
  if (loadingMessageContainer) {
    loadingMessageContainer.remove();
  }
}

export function moveLoadingMessageToBottom() {
  const loadingMessageContainer = document.getElementById(
    "loading-message-container"
  );
  if (loadingMessageContainer && DOM.chatMessages) {
    loadingMessageContainer.remove();
    DOM.chatMessages.appendChild(loadingMessageContainer);
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
  }
}

export function formatBlock(text: string) {
  text = text.replace(/^"(.*)"$/, "$1").trim();

  // SQL block
  if (text.startsWith("```sql") && text.endsWith("```")) {
    const sql = text.slice(6, -3).trim();
    return sql.split("\n").map((line) => {
      const lineDiv = document.createElement("div");
      lineDiv.textContent = line;
      return lineDiv;
    });
  }

  // Array block
  if (text.includes("[") && text.includes("]")) {
    const parts = text.split("[");
    const formattedParts = parts.map((part) => {
      const lineDiv = document.createElement("div");
      part = part.replace(/\]/g, "");
      lineDiv.textContent = part;
      return lineDiv;
    });
    return formattedParts;
  }

  // Generic multi-line block
  text = text.replace(/\\n/g, "\n");
  if (text.includes("\n")) {
    return text.split("\n").map((line) => {
      const lineDiv = document.createElement("div");
      lineDiv.textContent = line;
      return lineDiv;
    });
  }

  return null;
}

export function initChat() {
  if (DOM.messageInput) {
    DOM.messageInput.value = "";
    adjustTextareaHeight();
  }
  if (DOM.chatMessages) DOM.chatMessages.innerHTML = "";
  [DOM.confValue, DOM.expValue, DOM.missValue].forEach((element) => {
    if (element) element.innerHTML = "";
  });

  const selected = getSelectedGraph();
  if (selected) {
    addMessage("Hello! How can I help you today?");
  } else {
    addMessage(
      "Hello! Please select a graph from the dropdown above, upload a schema or connect to a database to get started."
    );
  }

  state.questions_history = [];
  state.result_history = [];
}
