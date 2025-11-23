import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";
import { useIsMobile } from "@/hooks/use-mobile";
import { useDatabase } from "@/contexts/DatabaseContext";
import { useAuth } from "@/contexts/AuthContext";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { Skeleton } from "@/components/ui/skeleton";
import ChatMessage from "./ChatMessage";
import QueryInput from "./QueryInput";
import SuggestionCards from "../SuggestionCards";
import { ChatService } from "@/services/chat";
import type { ConversationMessage } from "@/types/api";

interface ChatMessageData {
  id: string;
  type: 'user' | 'ai' | 'ai-steps' | 'sql-query' | 'query-result';
  content: string;
  steps?: Array<{
    icon: 'search' | 'database' | 'code' | 'message';
    text: string;
  }>;
  queryData?: any[]; // For table data
  analysisInfo?: {
    confidence?: number;
    missing?: string;
    ambiguities?: string;
    explanation?: string;
    isValid?: boolean;
  };
  timestamp: Date;
}

interface ChatInterfaceProps {
  className?: string;
}

const ChatInterface = ({ className }: ChatInterfaceProps) => {
  const { toast } = useToast();
  const isMobile = useIsMobile();
  const { selectedGraph } = useDatabase();
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const conversationHistory = useRef<ConversationMessage[]>([]);

  // Auto-scroll to bottom function
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Loading message component using skeleton
  const LoadingMessage = () => (
    <div className="px-6">
      <div className="flex gap-3 mb-6 items-start">
        <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
          <span className="text-white text-xs font-bold">QW</span>
        </div>
        <div className="flex-1 min-w-0 space-y-2">
          <Skeleton className="h-4 w-3/4 bg-gray-700" />
          <Skeleton className="h-4 w-1/2 bg-gray-700" />
          <Skeleton className="h-4 w-2/3 bg-gray-700" />
        </div>
      </div>
    </div>
  );

  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessageData[]>([
    {
      id: "1",
      type: "ai",
      content: "Hello! Describe what you'd like to ask your database",
      timestamp: new Date(),
    }
  ]);

  const suggestions = [
    "Show me five customers",
    "Show me the top customers by revenue", 
    "What are the pending orders?"
  ];

  // Scroll to bottom whenever messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages, isProcessing]);

  const handleSendMessage = async (query: string) => {
    if (isProcessing) return; // Prevent multiple submissions

    if (!selectedGraph) {
      toast({
        title: "No Database Available",
        description: "Please upload a database schema first, or start the QueryWeaver backend to use real databases.",
        variant: "destructive",
      });
      return;
    }

    // Snapshot history before adding the current user message so the backend
    // sees only prior turns in `history` and the current query in `query`.
    const historySnapshot = [...conversationHistory.current];

    setIsProcessing(true);

    // Add user message
    const userMessage: ChatMessageData = {
      id: Date.now().toString(),
      type: "user",
      content: query,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    conversationHistory.current.push({ role: 'user', content: query });
    
    // Scroll to bottom immediately after adding user message
    setTimeout(() => scrollToBottom(), 100);
    
    // Show processing toast
    toast({
      title: "Processing Query",
      description: "Analyzing your question and generating response...",
    });
    
    try {
      // No need for a steps accumulator message - we'll add each step as a separate AI message
      let finalContent = "";
      let sqlQuery = "";
      let queryResults: any[] | null = null;
      let analysisInfo: {
        confidence?: number;
        missing?: string;
        ambiguities?: string;
        explanation?: string;
        isValid?: boolean;
      } = {};

      // Stream the query
      for await (const message of ChatService.streamQuery({
        query,
        database: selectedGraph.id,
        history: historySnapshot,
      })) {
        console.log('📨 Received stream message:', message);
        
        if (message.type === 'status' || message.type === 'reasoning' || message.type === 'reasoning_step') {
          // Add each reasoning step as a separate AI message (like the old UI)
          const stepText = message.content || message.message || '';
          console.log('🔄 Adding reasoning step as AI message:', stepText);
          
          const stepMessage: ChatMessageData = {
            id: `step-${Date.now()}-${Math.random()}`,
            type: "ai",
            content: stepText,
            timestamp: new Date(),
          };
          
          console.log('Adding step message to state:', stepMessage);
          setMessages(prev => {
            console.log('Previous messages count:', prev.length);
            const newMessages = [...prev, stepMessage];
            console.log('New messages count:', newMessages.length);
            return newMessages;
          });
        } else if (message.type === 'sql_query') {
          // Store SQL query to display - backend sends it in 'data' field
          sqlQuery = message.data || message.content || message.message || '';
          // Also capture analysis information
          analysisInfo = {
            confidence: message.conf,
            missing: message.miss,
            ambiguities: message.amb,
            explanation: message.exp,
            isValid: message.is_valid
          };
          console.log('SQL Query generated:', sqlQuery);
          console.log('Analysis info:', analysisInfo);
        } else if (message.type === 'query_result') {
          // Store query results to display as table - backend sends it in 'data' field
          queryResults = message.data || [];
          console.log('Query results received:', queryResults?.length || 0, 'rows');
        } else if (message.type === 'ai_response') {
          // AI-generated response - this is what we show to the user
          const responseContent = (message.message || message.content || '').trim();
          console.log('🤖 AI Response received:', responseContent.substring(0, 200) + '...');
          console.log('Full AI Response length:', responseContent.length);
          finalContent = responseContent;
        } else if (message.type === 'followup_questions') {
          // Follow-up questions when query is unclear or off-topic
          const followupContent = (message.message || message.content || '').trim();
          console.log('❓ Follow-up questions received:', followupContent);
          finalContent = followupContent;
        } else if (message.type === 'error') {
          // Handle error
          toast({
            title: "Query Failed",
            description: message.content,
            variant: "destructive",
          });
          finalContent = `Error: ${message.content}`;
        } else if (message.type === 'confirmation') {
          // Handle confirmation request
          finalContent = `⚠️ This operation requires confirmation:\n\n${message.content}`;
        } else {
          console.warn('⚠️ Unknown message type received:', message.type, message);
        }
        
        setTimeout(() => scrollToBottom(), 50);
      }

      console.log('✅ Stream complete. Final content length:', finalContent.length);
      console.log('Final content:', finalContent);

      // Add SQL query message with analysis info (even if SQL is empty)
      if (sqlQuery !== undefined || Object.keys(analysisInfo).length > 0) {
        const sqlMessage: ChatMessageData = {
          id: (Date.now() + 2).toString(),
          type: "sql-query",
          content: sqlQuery,
          analysisInfo: analysisInfo,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, sqlMessage]);
      }
      
      // Add query results table if available
      if (queryResults && queryResults.length > 0) {
        const resultsMessage: ChatMessageData = {
          id: (Date.now() + 3).toString(),
          type: "query-result",
          content: "Query Results",
          queryData: queryResults,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, resultsMessage]);
      }
      
      // Add AI final response if we have one
      if (finalContent) {
        const finalResponse: ChatMessageData = {
          id: (Date.now() + 4).toString(),
          type: "ai",
          content: finalContent,
          timestamp: new Date(),
        };
        
        setMessages(prev => [...prev, finalResponse]);
        conversationHistory.current.push({ role: 'assistant', content: finalContent });
      }
      
      // Show success toast
      toast({
        title: "Query Complete",
        description: "Successfully processed your database query!",
      });
    } catch (error) {
      console.error('Query failed:', error);
      
      const errorMessage: ChatMessageData = {
        id: (Date.now() + 2).toString(),
        type: "ai",
        content: `Failed to process query: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      
      setMessages(prev => [...prev, errorMessage]);
      
      toast({
        title: "Query Failed",
        description: error instanceof Error ? error.message : "Failed to process query",
        variant: "destructive",
      });
    } finally {
      setIsProcessing(false);
      setTimeout(() => scrollToBottom(), 100);
    }
  };

  const handleSuggestionSelect = (suggestion: string) => {
    handleSendMessage(suggestion);
  };

  return (
    <div className={cn("flex flex-col h-full bg-gray-900", className)}>
      {/* Messages Area */}
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto scrollbar-hide overflow-x-hidden">
        <div className="space-y-6 py-6 max-w-full">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              type={msg.type}
              content={msg.content}
              steps={msg.steps}
              queryData={msg.queryData}
              analysisInfo={msg.analysisInfo}
              user={user}
            />
          ))}
          {/* Show loading skeleton when processing */}
          {isProcessing && <LoadingMessage />}
          {/* Invisible div to scroll to */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Bottom Section with Suggestions and Input */}
      <div className="border-t border-gray-700 bg-gray-900">
        <div className="p-6">
          {/* Suggestion Cards */}
          <SuggestionCards 
            suggestions={suggestions}
            onSelect={handleSuggestionSelect}
          />
          
          {/* Query Input */}
          <QueryInput 
            onSubmit={handleSendMessage}
            placeholder="Ask me anything about your database..."
            disabled={isProcessing}
          />
          
          {/* Show loading indicator when processing */}
          {isProcessing && (
            <div className="flex items-center justify-center gap-2 mt-2">
              <LoadingSpinner size="sm" />
              <span className="text-gray-400 text-sm">Processing your query...</span>
            </div>
          )}
          
          {/* Footer */}
          <div className="text-center mt-4">
            <p className="text-gray-500 text-sm">Powered by FalkorDB</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;