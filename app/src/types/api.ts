// API Types and Interfaces

// User types
export interface User {
  id: string;
  email: string;
  name?: string;
  picture?: string;
  provider?: 'google' | 'github';
}

// Authentication types
export interface AuthStatus {
  authenticated: boolean;
  user?: User;
}

// Graph/Database types
export interface Graph {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  table_count?: number;
  schema?: any;
}

export interface GraphUploadResponse {
  graph_id: string;
  message: string;
  tables?: string[];
}

// Chat message types
export interface ChatRequest {
  query: string;
  database: string;
  history?: ConversationMessage[];
}

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
}

// Streaming response types
export type StreamMessageType = 
  | 'reasoning'
  | 'reasoning_step'  // Backend sends this for step updates
  | 'sql'
  | 'sql_query'       // Backend sends this for SQL queries
  | 'result'
  | 'query_result'    // Backend sends this for query results
  | 'ai_response'     // Backend sends this for AI-generated responses
  | 'error'
  | 'followup'
  | 'followup_questions' // Backend sends this when query needs clarification
  | 'confirmation'
  | 'destructive_confirmation' // Backend sends this for destructive operations
  | 'schema_refresh'  // Backend sends this after schema modifications
  | 'status';

export interface StreamMessage {
  type: StreamMessageType;
  content?: string;
  message?: string;    // Some backend messages use 'message' instead of 'content'
  data?: any;
  step?: string;
  require_confirmation?: boolean;
  confirmation_id?: string;
  final_response?: boolean;
  conf?: number;       // Confidence score
  miss?: string;       // Missing information
  amb?: string;        // Ambiguities
  exp?: string;        // Explanation
  is_valid?: boolean;
  missing_information?: string; // For followup_questions
  ambiguities?: string;         // For followup_questions
  sql_query?: string;           // For destructive_confirmation
  operation_type?: string;      // For destructive_confirmation
  refresh_status?: string;      // For schema_refresh
}

// Confirmation types
export interface ConfirmRequest {
  confirmation_id: string;
  confirmed: boolean;
  database: string;
}

// Upload types
export interface SchemaUploadRequest {
  file: File;
  database_name?: string;
  description?: string;
}

// API Error
export interface ApiError {
  error: string;
  detail?: string;
  status?: number;
}

