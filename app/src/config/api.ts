// API Configuration
export const API_CONFIG = {
  // Base URL for the QueryWeaver backend API
  // When served from backend (port 5000): use empty string (same origin)
  // When using Vite dev server (port 8080): use /api prefix for proxy
  // For production: use environment variable or empty string
  BASE_URL: import.meta.env.VITE_API_URL || (
    // If running on Vite dev server (port 8080), use /api proxy
    window.location.port === '8080' ? '/api' : ''
  ),
  
  // Streaming boundary marker used by QueryWeaver backend
  STREAM_BOUNDARY: '|||FALKORDB_MESSAGE_BOUNDARY|||',
  
  // Endpoints
  ENDPOINTS: {
    // Authentication
    AUTH_STATUS: '/auth-status',
    LOGIN_GOOGLE: '/login/google',
    LOGIN_GITHUB: '/login/github',
    LOGOUT: '/logout',
    
    // Graph/Database management
    GRAPHS: '/graphs',
    GRAPH_BY_ID: (id: string) => `/graphs/${id}`,
    UPLOAD_SCHEMA: '/upload',
    DELETE_GRAPH: (id: string) => `/graphs/${id}`,
    CONNECT_DATABASE: '/database',
    
    // Chat/Query
    CHAT: '/chat',
    CONFIRM: '/confirm',
    
    // User
    USER: '/user',
  },
};

// Helper to build full API URL
export const buildApiUrl = (endpoint: string): string => {
  return `${API_CONFIG.BASE_URL}${endpoint}`;
};


