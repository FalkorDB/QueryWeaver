import React, { createContext, useContext, useState, useEffect } from 'react';
import { DatabaseService } from '@/services/database';
import type { Graph } from '@/types/api';

interface DatabaseContextType {
  graphs: Graph[];
  selectedGraph: Graph | null;
  isLoading: boolean;
  selectGraph: (graphId: string) => void;
  refreshGraphs: () => Promise<void>;
  uploadSchema: (file: File, databaseName?: string) => Promise<void>;
  deleteGraph: (graphId: string) => Promise<void>;
}

const DatabaseContext = createContext<DatabaseContextType | undefined>(undefined);

export const DatabaseProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [graphs, setGraphs] = useState<Graph[]>([]);
  const [selectedGraph, setSelectedGraph] = useState<Graph | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchGraphs = async () => {
    try {
      setIsLoading(true);
      const fetchedGraphs = await DatabaseService.getGraphs();
      setGraphs(fetchedGraphs);

      // Auto-select first graph if none selected (using functional update to avoid stale closure)
      setSelectedGraph(current => {
        if (!current && fetchedGraphs.length > 0) {
          return fetchedGraphs[0];
        }
        return current;
      });
    } catch (error) {
      console.log('Backend not available - running in demo mode without saved databases');
      // Silently fail - this is expected when backend isn't running
      setGraphs([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount - fetchGraphs is stable

  const selectGraph = (graphId: string) => {
    const graph = graphs.find(g => g.id === graphId);
    if (graph) {
      setSelectedGraph(graph);
    }
  };

  const uploadSchema = async (file: File, databaseName?: string) => {
    try {
      setIsLoading(true);
      await DatabaseService.uploadSchema({
        file,
        database_name: databaseName,
      });
      await fetchGraphs();
    } catch (error) {
      console.error('Failed to upload schema:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const deleteGraph = async (graphId: string) => {
    try {
      setIsLoading(true);
      await DatabaseService.deleteGraph(graphId);
      
      // Clear selection if deleted graph was selected
      if (selectedGraph?.id === graphId) {
        setSelectedGraph(null);
      }
      
      await fetchGraphs();
    } catch (error) {
      console.error('Failed to delete graph:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const value: DatabaseContextType = {
    graphs,
    selectedGraph,
    isLoading,
    selectGraph,
    refreshGraphs: fetchGraphs,
    uploadSchema,
    deleteGraph,
  };

  return <DatabaseContext.Provider value={value}>{children}</DatabaseContext.Provider>;
};

export const useDatabase = () => {
  const context = useContext(DatabaseContext);
  if (context === undefined) {
    throw new Error('useDatabase must be used within a DatabaseProvider');
  }
  return context;
};