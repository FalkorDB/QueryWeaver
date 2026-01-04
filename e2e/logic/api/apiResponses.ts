/* eslint-disable @typescript-eslint/no-explicit-any */

// ==================== AUTHENTICATION RESPONSES ====================

export interface User {
  id: string;
  email: string;
  name: string;
  picture: string;
  provider: 'google' | 'github' | 'email';
}

export interface AuthStatusResponse {
  authenticated: boolean;
  user?: User;
}

export interface LoginResponse {
  success: boolean;
  error?: string;
}

export interface SignupResponse {
  success: boolean;
  error?: string;
}

export interface LogoutResponse {
  success: true;
}

// ==================== GRAPH/DATABASE RESPONSES ====================

export type GraphsListResponse = string[];

export interface GraphColumn {
  name: string;
  type: string | null;
}

export interface GraphNode {
  id: string;
  name: string;
  columns: GraphColumn[];
}

export interface GraphLink {
  source: string;
  target: string;
}

export interface GraphDataResponse {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface GraphUploadResponse {
  graph_id: string;
  message: string;
  tables?: string[];
}

export interface DeleteGraphResponse {
  success?: boolean;
  message?: string;
  error?: string;
}

// ==================== STREAMING RESPONSES ====================

export type StreamMessageType =
  | 'reasoning'
  | 'reasoning_step'
  | 'sql'
  | 'sql_query'
  | 'result'
  | 'query_result'
  | 'ai_response'
  | 'error'
  | 'followup'
  | 'followup_questions'
  | 'confirmation'
  | 'destructive_confirmation'
  | 'schema_refresh'
  | 'status'
  | 'final_result';

export interface StreamMessage {
  type: StreamMessageType;
  content?: string;
  message?: string;
  data?: any;
  step?: string;
  require_confirmation?: boolean;
  confirmation_id?: string;
  final_response?: boolean;
  conf?: number;
  miss?: string;
  amb?: string;
  exp?: string;
  is_valid?: boolean;
  missing_information?: string;
  ambiguities?: string;
  sql_query?: string;
  operation_type?: string;
  refresh_status?: string;
  success?: boolean;
  graph_id?: string;
  graph_name?: string;
}

// ==================== TOKEN MANAGEMENT RESPONSES ====================

export interface TokenListItem {
  token_id: string;
  created_at: number;
}

export interface TokenListResponse {
  tokens: TokenListItem[];
}

export interface GenerateTokenResponse {
  token_id: string;
  created_at: number;
}

export interface DeleteTokenResponse {
  message: string;
}

// ==================== DATABASE CONNECTION RESPONSES ====================

export interface DatabaseConnectionResponse {
  success?: boolean;
  message?: string;
  error?: string;
}

// ==================== ERROR RESPONSE ====================

export interface ApiError {
  error?: string;
  detail?: string;
  message?: string;
  status?: number;
}
