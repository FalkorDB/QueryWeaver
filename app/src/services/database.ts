import { API_CONFIG, buildApiUrl } from '@/config/api';
import type { Graph, GraphUploadResponse, SchemaUploadRequest } from '@/types/api';

/**
 * Database/Graph Management Service
 * Handles database schema uploads and graph management
 */

export class DatabaseService {
  /**
   * Get all graphs/databases for the current user
   */
  static async getGraphs(): Promise<Graph[]> {
    try {
      const url = buildApiUrl(API_CONFIG.ENDPOINTS.GRAPHS);
      console.log('Fetching graphs from:', url);
      
      const response = await fetch(url, {
        credentials: 'include',
      });

      console.log('Graphs response status:', response.status);

      // 401/403 = Not authenticated - this is normal if user hasn't signed in
      if (response.status === 401 || response.status === 403) {
        console.log('Not authenticated - sign in to access saved databases');
        return [];
      }

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Failed to fetch graphs:', response.status, errorText);
        throw new Error('Failed to fetch graphs');
      }

      const data = await response.json();
      console.log('Graphs data received:', data);
      
      // Backend returns array of strings like ["northwind", "chinook"]
      // Transform to Graph objects
      const graphNames = data.graphs || data || [];
      
      if (Array.isArray(graphNames) && graphNames.length > 0 && typeof graphNames[0] === 'string') {
        // Transform string array to Graph objects
        return graphNames.map((name: string) => ({
          id: name,
          name: name,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }));
      }
      
      // If already objects, return as is
      return graphNames;
    } catch (error) {
      // Backend not available - return empty array for demo mode
      console.log('Backend not available for graphs - using demo mode', error);
      return [];
    }
  }

  /**
   * Get a specific graph by ID
   */
  static async getGraph(id: string): Promise<Graph> {
    try {
      const response = await fetch(
        buildApiUrl(API_CONFIG.ENDPOINTS.GRAPH_BY_ID(id)),
        {
          credentials: 'include',
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch graph');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Failed to get graph:', error);
      throw error;
    }
  }

  /**
   * Get graph data (nodes and links) for schema visualization
   */
  static async getGraphData(id: string): Promise<{ nodes: any[]; links: any[] }> {
    try {
      const response = await fetch(
        buildApiUrl(`/graphs/${encodeURIComponent(id)}/data`),
        {
          credentials: 'include',
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch graph data');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Failed to get graph data:', error);
      throw error;
    }
  }

  /**
   * Upload database schema file
   * Accepts SQL files, CSV files, or JSON schema definitions
   */
  static async uploadSchema(request: SchemaUploadRequest): Promise<GraphUploadResponse> {
    try {
      const formData = new FormData();
      formData.append('file', request.file);
      
      if (request.database_name) {
        formData.append('database', request.database_name);
      }
      
      if (request.description) {
        formData.append('description', request.description);
      }

      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.UPLOAD_SCHEMA), {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to upload schema');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.log('Backend not available for schema upload - demo mode only');
      // Check if it's a network error (backend not running)
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please start the QueryWeaver backend to upload schemas.');
      }
      throw error;
    }
  }

  /**
   * Delete a graph/database
   */
  static async deleteGraph(id: string): Promise<void> {
    try {
      const response = await fetch(
        buildApiUrl(API_CONFIG.ENDPOINTS.DELETE_GRAPH(id)),
        {
          method: 'DELETE',
          credentials: 'include',
        }
      );

      if (!response.ok) {
        throw new Error('Failed to delete graph');
      }
    } catch (error) {
      console.error('Failed to delete graph:', error);
      throw error;
    }
  }

  /**
   * Connect to an external database using connection URL
   * Format: postgresql://user:pass@host:port/database or mysql://user:pass@host:port/database
   */
  static async connectDatabaseUrl(config: {
    type: string;
    connectionUrl: string;
  }): Promise<GraphUploadResponse> {
    try {
      const response = await fetch(buildApiUrl('/database'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: config.connectionUrl,
        }),
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to connect to database');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.log('Backend not available for database connection - demo mode only');
      // Check if it's a network error (backend not running)
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please start the QueryWeaver backend to connect to databases.');
      }
      throw error;
    }
  }

  /**
   * Connect to an external database using individual parameters
   * This would require backend implementation for direct database connections
   */
  static async connectDatabase(config: {
    type: string;
    host: string;
    port: number;
    database: string;
    username: string;
    password: string;
  }): Promise<GraphUploadResponse> {
    try {
      // Build connection URL from individual parameters
      const protocol = config.type === 'mysql' ? 'mysql' : 'postgresql';
      const connectionUrl = `${protocol}://${encodeURIComponent(config.username)}:${encodeURIComponent(config.password)}@${config.host}:${config.port}/${encodeURIComponent(config.database)}`;
      
      const response = await fetch(buildApiUrl('/database'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: connectionUrl,
        }),
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to connect to database');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.log('Backend not available for database connection - demo mode only');
      // Check if it's a network error (backend not running)
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please start the QueryWeaver backend to connect to databases.');
      }
      throw error;
    }
  }
}

