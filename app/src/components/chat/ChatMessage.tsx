import React, { useState } from 'react';
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
  onConfirm?: () => void;
  onCancel?: () => void;
}

const ChatMessage = ({ type, content, steps, queryData, analysisInfo, confirmationData, progress, user, onConfirm, onCancel }: ChatMessageProps) => {
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

  if (type === 'confirmation') {
    const operationType = (confirmationData?.operationType ?? 'UNKNOWN').toUpperCase();
    const isHighRisk = ['DELETE', 'DROP', 'TRUNCATE'].includes(operationType);

    return (
      <div className="px-6" data-testid="confirmation-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
            <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
              QW
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <Card className={`${isHighRisk ? 'border-red-500/50 bg-red-950/20' : 'border-yellow-500/50 bg-yellow-950/20'}`}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className={`w-5 h-5 ${isHighRisk ? 'text-red-400' : 'text-yellow-400'}`} />
                  <span className={`text-base font-semibold ${isHighRisk ? 'text-red-400' : 'text-yellow-400'}`}>
                    Destructive Operation Detected
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <p className="text-foreground text-sm mb-2">
                      This operation will perform a <span className={`font-semibold ${isHighRisk ? 'text-red-400' : 'text-yellow-400'}`}>{operationType}</span> query:
                    </p>
                    {confirmationData?.sqlQuery && (
                      <div className="bg-background border border-border rounded p-3 overflow-x-auto">
                        <pre className="text-sm font-mono text-foreground whitespace-pre-wrap break-words overflow-wrap-anywhere">
                          <code className="language-sql">{confirmationData.sqlQuery}</code>
                        </pre>
                      </div>
                    )}
                  </div>

                  <div className={`${isHighRisk ? 'bg-red-950/40 border-red-700/50' : 'bg-yellow-950/40 border-yellow-700/50'} border rounded p-3`}>
                    <p className="text-sm text-foreground">
                      {isHighRisk ? (
                        <>
                          <span className="font-semibold text-red-400">⚠️ WARNING:</span> This operation may be irreversible and will permanently modify your database.
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
                      className={`flex-1 ${isHighRisk ? 'bg-red-600 hover:bg-red-700' : 'bg-yellow-600 hover:bg-yellow-700'} text-white font-semibold`}
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
          <Avatar className="h-10 w-10 border-2 border-purple-500 flex-shrink-0">
            <AvatarImage src={user?.picture} alt={user?.name || user?.email} />
            <AvatarFallback className="bg-purple-600 text-white font-medium">
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

    return (
      <div className="px-6" data-testid="sql-query-message">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
              <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
          <Card className={`bg-card ${isValid ? 'border-purple-500/30' : 'border-yellow-500/30'}`}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Code className={`w-4 h-4 ${isValid ? 'text-purple-400' : 'text-yellow-400'}`} />
                <span className={`text-base font-semibold ${isValid ? 'text-purple-400' : 'text-yellow-400'}`}>
                  {hasSQL ? 'Generated SQL Query' : 'Query Analysis'}
                </span>
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
                        <Check className="w-4 h-4 text-green-400" />
                      ) : (
                        <Copy className="w-4 h-4 text-muted-foreground" />
                      )}
                    </Button>
                    <pre className="bg-background text-foreground p-3 rounded text-sm mb-3 w-fit min-w-full font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">
                      <code className="language-sql">{content}</code>
                    </pre>
                  </div>
                </div>
              )}

              {!isValid && (
                <div className="space-y-2 text-sm">
                  {analysisInfo?.explanation && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-yellow-400">Explanation:</span>
                      <p className="text-foreground mt-1">{analysisInfo.explanation}</p>
                    </div>
                  )}
                  {analysisInfo?.missing && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-orange-400">Missing Information:</span>
                      <p className="text-foreground mt-1">{analysisInfo.missing}</p>
                    </div>
                  )}
                  {analysisInfo?.ambiguities && (
                    <div className="bg-background/50 p-2 rounded">
                      <span className="font-semibold text-orange-400">Ambiguities:</span>
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
            <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
              QW
            </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0 max-w-full overflow-hidden">
          <Card className="bg-card border-green-500/30 max-w-full">
            <CardContent className="p-4 max-w-full overflow-hidden">
              <div className="flex items-center gap-2 mb-3">
                <Database className="w-4 h-4 text-green-400" />
                <span className="text-base font-semibold text-green-400">Query Results</span>
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
              <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="text-foreground text-base leading-relaxed whitespace-pre-line">
              {content}
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
          <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
            QW
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <Card className="bg-card border-purple-500/30 max-w-md">
            <CardContent className="p-4">
              <div className="space-y-3">
                {steps?.map((step, index) => (
                  <div key={index} className="flex items-center gap-3 text-sm text-foreground">
                    <Badge variant="outline" className="p-1 w-6 h-6 flex items-center justify-center border-purple-400">
                      {step.icon === 'search' && <Search className="w-3 h-3 text-purple-400" />}
                      {step.icon === 'database' && <Database className="w-3 h-3 text-purple-400" />}
                      {step.icon === 'code' && <Code className="w-3 h-3 text-purple-400" />}
                      {step.icon === 'message' && <MessageSquare className="w-3 h-3 text-purple-400" />}
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
