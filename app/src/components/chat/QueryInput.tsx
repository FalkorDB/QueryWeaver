import React, { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send } from "lucide-react";

interface QueryInputProps {
  onSubmit: (query: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

const QueryInput = ({ onSubmit, placeholder = "Ask me anything about your database...", disabled = false }: QueryInputProps) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !disabled) {
      onSubmit(query.trim());
      setQuery('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="relative" data-testid="query-input-form">
      <Textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="min-h-[60px] bg-card border-border text-foreground placeholder-muted-foreground resize-none pr-12 focus-visible:border-purple-500 focus-visible:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !disabled) {
            e.preventDefault();
            handleSubmit(e);
          }
        }}
        data-testid="query-textarea"
      />
      <Button
        type="submit"
        size="icon"
        className="absolute right-2 bottom-2 bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={!query.trim() || disabled}
        aria-label="Send query"
        data-testid="send-query-btn"
      >
        <Send className="w-4 h-4" />
      </Button>
    </form>
  );
};

export default QueryInput;
