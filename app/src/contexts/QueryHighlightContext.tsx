import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useDatabase } from '@/contexts/DatabaseContext';
import { extractTablesFromSQL } from '@/utils/sqlTables';

interface QueryHighlightContextType {
  /** Id of the chat message whose SQL query is currently selected. */
  selectedQueryId: string | null;
  /** Table names referenced by the selected query (empty when nothing is selected). */
  highlightedTables: string[];
  /** Selects the query, or unselects it when it is already selected. */
  toggleQueryHighlight: (messageId: string, sql: string) => void;
  clearQueryHighlight: () => void;
}

const QueryHighlightContext = createContext<QueryHighlightContextType | undefined>(undefined);

export const QueryHighlightProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { selectedGraph } = useDatabase();
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(null);
  const [highlightedTables, setHighlightedTables] = useState<string[]>([]);

  const clearQueryHighlight = useCallback(() => {
    setSelectedQueryId(null);
    setHighlightedTables([]);
  }, []);

  // The highlight refers to tables of the active schema — drop it on switch.
  useEffect(() => {
    clearQueryHighlight();
  }, [selectedGraph?.id, clearQueryHighlight]);

  const toggleQueryHighlight = useCallback((messageId: string, sql: string) => {
    if (selectedQueryId === messageId) {
      clearQueryHighlight();
      return;
    }

    setSelectedQueryId(messageId);
    setHighlightedTables(extractTablesFromSQL(sql));
  }, [selectedQueryId, clearQueryHighlight]);

  const value = useMemo(
    () => ({ selectedQueryId, highlightedTables, toggleQueryHighlight, clearQueryHighlight }),
    [selectedQueryId, highlightedTables, toggleQueryHighlight, clearQueryHighlight],
  );

  return (
    <QueryHighlightContext.Provider value={value}>
      {children}
    </QueryHighlightContext.Provider>
  );
};

export const useQueryHighlight = () => {
  const context = useContext(QueryHighlightContext);
  if (context === undefined) {
    throw new Error('useQueryHighlight must be used within a QueryHighlightProvider');
  }
  return context;
};
