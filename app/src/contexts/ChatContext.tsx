import React, { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react';
import { useDatabase } from '@/contexts/DatabaseContext';
import type { ConversationMessage } from '@/types/api';

interface ChatMessageData {
  id: string;
  type: 'user' | 'ai' | 'ai-steps' | 'sql-query' | 'query-result' | 'confirmation';
  content: string;
  steps?: Array<{
    icon: 'search' | 'database' | 'code' | 'message';
    text: string;
  }>;
  queryData?: any[];
  analysisInfo?: {
    confidence?: number;
    missing?: string;
    ambiguities?: string;
    explanation?: string;
    isValid?: boolean;
  };
  confirmationData?: {
    sqlQuery: string;
    operationType: string;
    message: string;
    chatHistory: string[];
  };
  timestamp: Date;
}

interface ChatContextType {
  messages: ChatMessageData[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessageData[]>>;
  conversationHistory: React.MutableRefObject<ConversationMessage[]>;
  isProcessing: boolean;
  setIsProcessing: React.Dispatch<React.SetStateAction<boolean>>;
  resetChat: () => void;
}

const initialMessage: ChatMessageData = {
  id: "1",
  type: "ai",
  content: "Hello! Describe what you'd like to ask your database",
  timestamp: new Date(),
};

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { selectedGraph } = useDatabase();
  const [messages, setMessages] = useState<ChatMessageData[]>([initialMessage]);
  const [isProcessing, setIsProcessing] = useState(false);
  const conversationHistory = useRef<ConversationMessage[]>([]);
  const previousGraphIdRef = useRef<string | undefined>(undefined);

  // Reset conversation when the selected graph changes to avoid leaking
  // conversation history between different databases.
  useEffect(() => {
    // Only reset if the graph actually changed (not on initial mount with same graph)
    if (previousGraphIdRef.current !== undefined && previousGraphIdRef.current !== selectedGraph?.id) {
      conversationHistory.current = [];
      setMessages([{
        ...initialMessage,
        id: Date.now().toString(),
        timestamp: new Date(),
      }]);
    }
    previousGraphIdRef.current = selectedGraph?.id;
  }, [selectedGraph?.id]);

  const resetChat = useCallback(() => {
    conversationHistory.current = [];
    setMessages([{
      ...initialMessage,
      id: Date.now().toString(),
      timestamp: new Date(),
    }]);
  }, []);

  return (
    <ChatContext.Provider value={{
      messages,
      setMessages,
      conversationHistory,
      isProcessing,
      setIsProcessing,
      resetChat,
    }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
