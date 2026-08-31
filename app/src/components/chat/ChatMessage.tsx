import React, { useState } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import { Database, Search, Code, MessageSquare, AlertTriangle, Copy, Check } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import type { User as UserType } from '@/types/api';

interface Step {
  icon: 'search' | 'database' | 'code' | 'message';
  text: string;
}

interface ChatMessageProps {
  type: 'user' | 'ai' | 'ai-steps' | 'sql-query' | 'query-result' | 'confirmation';
  content: string;
  steps?: Step[];
  queryData?: any[]; // For table data
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
  };
  progress?: number; // Progress percentage for AI steps
  user?: UserType | null; // User info for avatar
  isQueryHighlighted?: boolean; // Whether this query's tables are highlighted in the schema canvas
  onToggleQueryHighlight?: () => void; // Select/unselect this query to highlight it in the schema canvas
  onConfirm?: () => void;
  onCancel?: () => void;
}

// The model answers in markdown; render it with the app's typography instead of
// pulling in the Tailwind prose plugin.
const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 last:mb-0 list-disc pl-5 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 last:mb-0 list-decimal pl-5 space-y-1">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h1 className="mb-2 mt-4 first:mt-0 text-lg font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 first:mt-0 text-base font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 first:mt-0 text-base font-semibold">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 last:mb-0 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-sm">{children}</code>,
  // A fenced block brings its own frame, so cancel the inline chip styling inside it.
  pre: ({ children }) => (
    <pre className="mb-3 last:mb-0 overflow-x-auto rounded border border-border bg-background p-3 [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  // The answer is model output; rendering images would fetch arbitrary URLs.
  img: ({ alt }) => <span className="text-muted-foreground">{alt ? `[image: ${alt}]` : '[image]'}</span>,
  table: ({ children }) => (
    <div className="mb-3 last:mb-0 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-border px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
};

const ChatMessage = ({ type, content, steps, queryData, analysisInfo, confirmationData, progress, user, isQueryHighlighted, onToggleQueryHighlight, onConfirm, onCancel }: ChatMessageProps) => {
  const [copied, setCopied] = useState(false);

  const handleCopyQuery = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text:', err);
    }
  };

  // Clicking the query toggles the schema highlight, but a click that ends a
  // text selection must not steal the selection from the user.
  const handleQueryBlockClick = () => {
    if (window.getSelection()?.toString()) return;
    onToggleQueryHighlight?.();
  };

  if (type === 'confirmation') {
    const operationType = (confirmationData?.operationType ?? 'UNKNOWN').toUpperCase();
    const isHighRisk = ['DELETE', 'DROP', 'TRUNCATE'].includes(operationType);

    return (
      <div className="px-6" data-testid="confirmation-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
              QW
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <Card className={`${isHighRisk ? 'border-error/50 bg-error/5' : 'border-warning/50 bg-warning/5'}`}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className={`w-5 h-5 ${isHighRisk ? 'text-error' : 'text-warning'}`} />
                  <span className={`text-base font-semibold ${isHighRisk ? 'text-error' : 'text-warning'}`}>
                    Destructive Operation Detected
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <p className="text-foreground text-sm mb-2">
                      This operation will perform a <span className={`font-semibold ${isHighRisk ? 'text-error' : 'text-warning'}`}>{operationType}</span> query:
                    </p>
                    {confirmationData?.sqlQuery && (
                      <div className="bg-background border border-border rounded p-3 overflow-x-auto">
                        <pre className="text-sm font-mono text-foreground whitespace-pre-wrap break-words overflow-wrap-anywhere">
                          <code className="language-sql">{confirmationData.sqlQuery}</code>
                        </pre>
                      </div>
                    )}
                  </div>

                  <div className={`${isHighRisk ? 'bg-error/10 border-error/50' : 'bg-warning/10 border-warning/50'} border rounded p-3`}>
                    <p className="text-sm text-foreground">
                      {isHighRisk ? (
                        <>
                          <span className="font-semibold text-error">⚠️ WARNING:</span> This operation may be irreversible and will permanently modify your database.
                        </>
                      ) : (
                        <>This operation will make changes to your database. Please review carefully before confirming.</>
                      )}
                    </p>
                  </div>

                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="outline"
                      onClick={onCancel}
                      className="flex-1 bg-card border-border text-muted-foreground hover:bg-muted"
                      data-testid="confirmation-cancel-button"
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={onConfirm}
                      className={`flex-1 ${isHighRisk ? 'bg-error hover:bg-error/90' : 'bg-warning hover:bg-warning/90'} text-white font-semibold`}
                      data-testid="confirmation-confirm-button"
                    >
                      Confirm {operationType}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  if (type === 'user') {
    return (
      <div className="px-6" data-testid="user-message">
        <div className="flex justify-end gap-3 mb-6">
          <div className="flex-1 max-w-xl">
            <Card className="bg-muted border-border inline-block float-right">
              <CardContent className="p-3">
                <p className="text-foreground text-base leading-relaxed">{content}</p>
              </CardContent>
            </Card>
          </div>
          <Avatar className="h-10 w-10 border-2 border-primary flex-shrink-0">
            <AvatarImage src={user?.picture} alt={user?.name || user?.email} />
            <AvatarFallback className="bg-primary text-primary-foreground font-medium">
              {(user?.name || user?.email || 'U').charAt(0).toUpperCase()}
            </AvatarFallback>
          </Avatar>
        </div>
      </div>
    );
  }

  if (type === 'sql-query') {
    const hasSQL = content && content.trim().length > 0;
    const isValid = analysisInfo?.isValid !== false; // Default to true if not specified
    const isClickable = hasSQL && Boolean(onToggleQueryHighlight);

    return (
      <div className="px-6" data-testid="sql-query-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
              <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
          <Card className={`bg-card ${isValid ? 'border-primary/30' : 'border-warning/30'}`}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Code className={`w-4 h-4 ${isValid ? 'text-primary' : 'text-warning'}`} />
                <span className={`text-base font-semibold ${isValid ? 'text-primary' : 'text-warning'}`}>
                  {hasSQL ? 'Generated SQL Query' : 'Query Analysis'}
                </span>
                {isQueryHighlighted && (
                  <Badge variant="outline" className="ml-auto text-xs border-primary text-primary">
                    Shown in schema
                  </Badge>
                )}
                {isClickable && (
                  <Button
                    variant="ghost"
                    size="sm"
                    data-testid="sql-highlight-toggle"
                    aria-pressed={isQueryHighlighted}
                    onClick={onToggleQueryHighlight}
                    className={`h-7 px-2 text-xs ${isQueryHighlighted ? '' : 'ml-auto'}`}
                  >
                    {isQueryHighlighted ? 'Clear schema highlight' : 'Show in schema'}
                  </Button>
                )}
              </div>

              {hasSQL && (
                <div className="overflow-x-auto -mx-2 px-2">
                  <div className="relative">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleCopyQuery}
                      className="absolute top-2 right-2 z-10 h-8 w-8 p-0 hover:bg-muted"
                      title={copied ? "Copied!" : "Copy query"}
                    >
                      {copied ? (
                        <Check className="w-4 h-4 text-success" />
                      ) : (
                        <Copy className="w-4 h-4 text-muted-foreground" />
                      )}
                    </Button>
                    <pre
                      data-testid="sql-query-block"
                      onClick={isClickable ? handleQueryBlockClick : undefined}
                      className={`bg-background text-foreground p-3 pr-12 rounded text-sm mb-1 w-fit min-w-full font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere transition-colors ${
                        isClickable ? 'cursor-pointer hover:ring-1 hover:ring-primary/50' : ''
                      } ${isQueryHighlighted ? 'ring-2 ring-primary bg-primary/5' : ''}`}
                    >
                      <code className="language-sql">{content}</code>
                    </pre>
                    {isClickable && (
                      <p className="text-xs text-muted-foreground mb-3">
                        {isQueryHighlighted
                          ? 'Click the query again to clear the schema highlight.'
                          : 'Click the query to highlight its tables and relations in the schema.'}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {!isValid && (
                <div className="space-y-2 text-sm">
                  {analysisInfo?.explanation && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-warning">Explanation:</span>
                      <p className="text-foreground mt-1">{analysisInfo.explanation}</p>
                    </div>
                  )}
                  {analysisInfo?.missing && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-warning">Missing Information:</span>
                      <p className="text-foreground mt-1">{analysisInfo.missing}</p>
                    </div>
                  )}
                  {analysisInfo?.ambiguities && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-warning">Ambiguities:</span>
                      <p className="text-foreground mt-1">{analysisInfo.ambiguities}</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      </div>
    );
  }

  if (type === 'query-result') {
    return (
      <div className="px-6" data-testid="query-results-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
              QW
            </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0 max-w-full overflow-hidden">
          <Card className="bg-card border-success/30 max-w-full">
            <CardContent className="p-4 max-w-full overflow-hidden">
              <div className="flex items-center gap-2 mb-3">
                <Database className="w-4 h-4 text-success" />
                <span className="text-base font-semibold text-success">Query Results</span>
                <Badge variant="outline" className="ml-auto text-sm">
                  {queryData?.length || 0} rows
                </Badge>
              </div>
              {queryData && queryData.length > 0 && (
                <div className="max-w-full overflow-hidden -mx-4 px-4">
                  <div className="overflow-x-auto overflow-y-auto max-h-96 border border-border rounded scrollbar-visible" style={{ maxWidth: '100%' }}>
                    <table className="text-sm border-collapse" data-testid="results-table" style={{ width: '100%', maxWidth: '100%', tableLayout: 'auto', display: 'table' }}>
                      <thead className="sticky top-0 bg-card z-10">
                        <tr className="border-b border-border">
                          {Object.keys(queryData[0]).map((column) => (
                            <th key={column} className="text-left px-3 py-2 text-muted-foreground font-semibold bg-card break-words" style={{ maxWidth: '300px', minWidth: '100px' }}>
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryData.map((row, index) => (
                          <tr key={index} className="border-b border-border hover:bg-muted">
                            {Object.values(row).map((value: any, cellIndex) => (
                              <td key={cellIndex} className="px-3 py-2 text-foreground break-words" style={{ maxWidth: '300px', minWidth: '100px' }}>
                                {String(value)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        </div>
      </div>
    );
  }

  if (type === 'ai') {
    return (
      <div className="px-6" data-testid="ai-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
              <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="text-foreground text-base leading-relaxed break-words">
              <Markdown remarkPlugins={[remarkGfm, remarkBreaks]} components={markdownComponents}>
                {content}
              </Markdown>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (type === 'ai-steps') {
    return (
      <div className="px-6">
      <div className="flex gap-3 mb-6 items-start">
        <Avatar className="w-8 h-8 flex-shrink-0">
          <AvatarFallback className="bg-primary text-primary-foreground text-xs font-bold">
            QW
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <Card className="bg-card border-primary/30 max-w-md">
            <CardContent className="p-4">
              <div className="space-y-3">
                {steps?.map((step, index) => (
                  <div key={index} className="flex items-center gap-3 text-sm text-foreground">
                    <Badge variant="outline" className="p-1 w-6 h-6 flex items-center justify-center border-primary">
                      {step.icon === 'search' && <Search className="w-3 h-3 text-primary" />}
                      {step.icon === 'database' && <Database className="w-3 h-3 text-primary" />}
                      {step.icon === 'code' && <Code className="w-3 h-3 text-primary" />}
                      {step.icon === 'message' && <MessageSquare className="w-3 h-3 text-primary" />}
                    </Badge>
                    <span>{step.text}</span>
                  </div>
                ))}
                {progress !== undefined && (
                  <div className="mt-4">
                    <Progress value={progress} className="h-2" />
                    <p className="text-xs text-muted-foreground mt-1">{progress}% complete</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
      </div>
    );
  }

  return null;
};

export default ChatMessage;
