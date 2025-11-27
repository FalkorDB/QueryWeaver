import React from 'react';
import { User, Bot, ArrowRight, Database, Search, Code, MessageSquare } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { User as UserType } from '@/types/api';

interface Step {
  icon: 'search' | 'database' | 'code' | 'message';
  text: string;
}

interface ChatMessageProps {
  type: 'user' | 'ai' | 'ai-steps' | 'sql-query' | 'query-result';
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
  progress?: number; // Progress percentage for AI steps
  user?: UserType | null; // User info for avatar
}

const ChatMessage = ({ type, content, steps, queryData, analysisInfo, progress, user }: ChatMessageProps) => {
  if (type === 'user') {
    return (
      <div className="px-6">
        <div className="flex justify-end gap-3 mb-6">
          <div className="flex-1 max-w-xl">
            <Card className="bg-gray-700 border-gray-600 inline-block float-right">
              <CardContent className="p-3">
                <p className="text-gray-200 text-base leading-relaxed">{content}</p>
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
      <div className="px-6">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
              <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
          <Card className={`bg-gray-800 ${isValid ? 'border-purple-500/30' : 'border-yellow-500/30'}`}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Code className={`w-4 h-4 ${isValid ? 'text-purple-400' : 'text-yellow-400'}`} />
                <span className={`text-base font-semibold ${isValid ? 'text-purple-400' : 'text-yellow-400'}`}>
                  {hasSQL ? 'Generated SQL Query' : 'Query Analysis'}
                </span>
              </div>

              {hasSQL && (
                <div className="overflow-x-auto -mx-2 px-2">
                  <pre className="bg-gray-900 text-gray-200 p-3 rounded text-sm mb-3 w-fit min-w-full font-mono">
                    <code className="language-sql">{content}</code>
                  </pre>
                </div>
              )}

              {!isValid && (
                <div className="space-y-2 text-sm">
                  {analysisInfo?.explanation && (
                    <div className="bg-gray-900/50 p-2 rounded">
                      <span className="font-semibold text-yellow-400">Explanation:</span>
                      <p className="text-gray-300 mt-1">{analysisInfo.explanation}</p>
                    </div>
                  )}
                  {analysisInfo?.missing && (
                    <div className="bg-gray-900/50 p-2 rounded">
                      <span className="font-semibold text-orange-400">Missing Information:</span>
                      <p className="text-gray-300 mt-1">{analysisInfo.missing}</p>
                    </div>
                  )}
                  {analysisInfo?.ambiguities && (
                    <div className="bg-gray-900/50 p-2 rounded">
                      <span className="font-semibold text-orange-400">Ambiguities:</span>
                      <p className="text-gray-300 mt-1">{analysisInfo.ambiguities}</p>
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
      <div className="px-6">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
            <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
              QW
            </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0 max-w-full overflow-hidden">
          <Card className="bg-gray-800 border-green-500/30 max-w-full">
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
                  <div className="overflow-x-auto overflow-y-auto max-h-96 border border-gray-700 rounded scrollbar-visible" style={{ maxWidth: '100%' }}>
                    <table className="text-sm border-collapse" style={{ width: '100%', maxWidth: '100%', tableLayout: 'auto', display: 'table' }}>
                      <thead className="sticky top-0 bg-gray-800 z-10">
                        <tr className="border-b border-gray-700">
                          {Object.keys(queryData[0]).map((column) => (
                            <th key={column} className="text-left px-3 py-2 text-gray-300 font-semibold bg-gray-800 whitespace-nowrap">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryData.map((row, index) => (
                          <tr key={index} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                            {Object.values(row).map((value: any, cellIndex) => (
                              <td key={cellIndex} className="px-3 py-2 text-gray-200 whitespace-nowrap">
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
      <div className="px-6">
        <div className="flex gap-3 mb-6 items-start">
          <Avatar className="w-8 h-8 flex-shrink-0">
              <AvatarFallback className="bg-purple-600 text-white text-xs font-bold">
                QW
              </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="text-gray-200 text-base leading-relaxed whitespace-pre-line">
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
          <Card className="bg-gray-800 border-purple-500/30 max-w-md">
            <CardContent className="p-4">
              <div className="space-y-3">
                {steps?.map((step, index) => (
                  <div key={index} className="flex items-center gap-3 text-sm text-gray-300">
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
                    <p className="text-xs text-gray-400 mt-1">{progress}% complete</p>
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
