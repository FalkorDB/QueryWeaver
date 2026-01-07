import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Trash2, Star, RefreshCw, PanelLeft } from "lucide-react";
import Sidebar from "@/components/layout/Sidebar";
import ChatInterface from "@/components/chat/ChatInterface";
import LoginModal from "@/components/modals/LoginModal";
import DatabaseModal from "@/components/modals/DatabaseModal";
import DeleteDatabaseModal from "@/components/modals/DeleteDatabaseModal";
import TokensModal from "@/components/modals/TokensModal";
import SchemaViewer from "@/components/schema";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { useAuth } from "@/contexts/AuthContext";
import { useDatabase } from "@/contexts/DatabaseContext";
import { DatabaseService } from "@/services/database";
import { useToast } from "@/components/ui/use-toast";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

const Index = () => {
  const { isAuthenticated, isLoading: authLoading, logout, user } = useAuth();
  const { selectedGraph, graphs, selectGraph, uploadSchema } = useDatabase();
  const { toast } = useToast();
  const [showDatabaseModal, setShowDatabaseModal] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showSchemaViewer, setShowSchemaViewer] = useState(false);
  const [showTokensModal, setShowTokensModal] = useState(false);
  const [isRefreshingSchema, setIsRefreshingSchema] = useState(false);
  const [isChatProcessing, setIsChatProcessing] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  );
  const [schemaViewerWidth, setSchemaViewerWidth] = useState(() =>
    typeof window !== "undefined" ? Math.floor(window.innerWidth * 0.4) : 0,
  );
  const [githubStars, setGithubStars] = useState<string>('-');
  const [databaseToDelete, setDatabaseToDelete] = useState<{ id: string; name: string; isDemo: boolean } | null>(null);
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Handle window resize to update layout
  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Auto-collapse sidebar when switching to mobile view
  useEffect(() => {
    const isMobile = windowWidth < 768;
    if (isMobile) {
      setSidebarCollapsed(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowWidth]); // Only run when windowWidth changes, not on manual toggle

  // Calculate sidebar width based on collapsed state
  // On desktop: sidebar is always visible (64px), on mobile: can be collapsed (0px)
  const getSidebarWidth = () => {
    const isMobile = windowWidth < 768;
    if (isMobile) {
      return sidebarCollapsed ? 0 : 64;
    }
    return 64; // Always visible on desktop
  };
  
  const sidebarWidth = getSidebarWidth();
  
  // Calculate main content margin and width
  // On mobile: ignore schema viewer (it's an overlay), only account for sidebar
  // On desktop: account for both sidebar and schema viewer
  const getMainContentStyles = () => {
    const isMobile = windowWidth < 768;

    if (isMobile) {
      return {
        marginLeft: `${sidebarWidth}px`,
        width: `calc(100% - ${sidebarWidth}px)`
      };
    }

    // Desktop
    const totalOffset = showSchemaViewer ? schemaViewerWidth + sidebarWidth : sidebarWidth;
    return {
      marginLeft: `${totalOffset}px`,
      width: `calc(100% - ${totalOffset}px)`
    };
  };

  // Fetch GitHub stars
  useEffect(() => {
    fetch('https://api.github.com/repos/FalkorDB/QueryWeaver')
      .then(response => response.json())
      .then(data => {
        if (typeof data.stargazers_count === 'number') {
          setGithubStars(data.stargazers_count.toLocaleString());
        }
      })
      .catch(error => {
        console.log('Failed to fetch GitHub stars:', error);
      });
  }, []);

  // Show login modal when not authenticated after loading completes
  useEffect(() => {
    // Only auto-open the login modal once per user/session to avoid locking
    // the SPA when the backend is down or in demo mode. Allow users to
    // dismiss it and remember that choice in sessionStorage.
    if (!authLoading && !isAuthenticated) {
      const dismissed = sessionStorage.getItem('loginModalDismissed');
      if (!dismissed) {
        setShowLoginModal(true);
      }
    }
  }, [authLoading, isAuthenticated]);

  const handleConnectDatabase = () => {
    if (isRefreshingSchema || isChatProcessing) return;
    setShowDatabaseModal(true);
  };

  const handleUploadSchema = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await uploadSchema(file, file.name.replace(/\.[^/.]+$/, ""));
      toast({
        title: "Schema Uploaded",
        description: "Database schema uploaded successfully!",
      });
    } catch (error) {
      toast({
        title: "Upload Failed",
        description: error instanceof Error ? error.message : "Failed to upload schema",
        variant: "destructive",
      });
    }
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDeleteGraph = async (graphId: string, graphName: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent dropdown from closing/selecting
    
    // Check if this is a demo database
    const isDemo = graphId.startsWith('general_');
    
    if (isRefreshingSchema) return;
    // Show the delete confirmation modal
    setDatabaseToDelete({ id: graphId, name: graphName, isDemo });
    setShowDeleteModal(true);
  };

  const confirmDeleteGraph = async () => {
    if (!databaseToDelete) return;

    try {
      await DatabaseService.deleteGraph(databaseToDelete.id);

      toast({
        title: "Database Deleted",
        description: `Successfully deleted "${databaseToDelete.name}"`,
      });

      // Close modal before refresh
      setShowDeleteModal(false);
      setDatabaseToDelete(null);

      // Refresh the graphs list (can be replaced with a context refresh later)
      window.location.reload();
    } catch (error) {
      toast({
        title: "Delete Failed",
        description: error instanceof Error ? error.message : "Failed to delete database",
        variant: "destructive",
      });
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      toast({
        title: "Logged Out",
        description: "You have been successfully logged out",
      });
      // Refresh to reset state
      window.location.reload();
    } catch (error) {
      toast({
        title: "Logout Failed",
        description: error instanceof Error ? error.message : "Failed to logout",
        variant: "destructive",
      });
    }
  };

  const handleRefreshSchema = async () => {
    if (!selectedGraph) {
      toast({
        title: "No Database Selected",
        description: "Please select a database first",
        variant: "destructive",
      });
      return;
    }

    if (isChatProcessing) {
      toast({
        title: "Chat is Processing",
        description: "Please wait for the current query to complete",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsRefreshingSchema(true);
      const response = await fetch(`/graphs/${selectedGraph.id}/refresh`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Failed to refresh schema' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      // Process streaming response
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let hasError = false;
      const delimiter = '|||FALKORDB_MESSAGE_BOUNDARY|||';

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Process complete messages
        const parts = buffer.split(delimiter);
        buffer = parts.pop() || ''; // Keep incomplete part in buffer

        for (const part of parts) {
          const trimmed = part.trim();
          if (!trimmed) continue;

          try {
            const message = JSON.parse(trimmed);
            if (message.type === 'error') {
              hasError = true;
              throw new Error(message.message || 'Schema refresh failed');
            }
          } catch (e) {
            if (e instanceof SyntaxError) {
              console.error('Failed to parse message:', trimmed);
            } else {
              throw e;
            }
          }
        }
      }

      if (hasError) {
        return; // Error already thrown and caught
      }

      toast({
        title: "Schema Refreshed",
        description: "Database schema refreshed successfully!",
      });

      // Reload to show updated schema
      window.location.reload();
    } catch (error) {
      console.error('Refresh error:', error);
      toast({
        title: "Refresh Failed",
        description: error instanceof Error ? error.message : "Failed to refresh schema",
        variant: "destructive",
      });
    }
    finally {
      setIsRefreshingSchema(false);
    }
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Hidden file input for schema upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".sql,.csv,.json"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
        data-testid="schema-upload-input"
      />
      
      {/* Left Sidebar */}
      <Sidebar 
        onSchemaClick={() => { if (!isRefreshingSchema) setShowSchemaViewer(!showSchemaViewer); }}
        isSchemaOpen={showSchemaViewer}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
      
      {/* Schema Viewer */}
      <SchemaViewer 
        isOpen={showSchemaViewer}
        onClose={() => setShowSchemaViewer(false)}
        onWidthChange={setSchemaViewerWidth}
        sidebarWidth={sidebarWidth}
      />
      
      {/* Main Content */}
      <div className="flex flex-1 flex-col transition-all duration-300" style={getMainContentStyles()}>
        {/* Header */}
        <header className="border-b border-border">
          {/* Desktop Header */}
          <div className="hidden md:flex items-center justify-between p-6">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                <img src="/icons/queryweaver.svg" alt="QueryWeaver" style={{ height: '3rem', width: 'auto' }} data-testid="logo" />
                <span className="text-muted-foreground">|</span>
                <p className="text-sm text-muted-foreground">Graph-Powered Text-to-SQL</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {selectedGraph ? (
                <Badge variant="default" className="bg-green-600 hover:bg-green-700" data-testid="database-status-badge">
                  Connected: {selectedGraph.name}
                </Badge>
              ) : (
                <Badge variant="secondary" className="bg-yellow-600 hover:bg-yellow-700" data-testid="database-status-badge">
                  No Database Selected
                </Badge>
              )}
              {/* GitHub Stars Link */}
              <a
                href="https://github.com/FalkorDB/QueryWeaver"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-card hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                title="View QueryWeaver on GitHub"
                data-testid="github-repo-link"
              >
                <svg 
                  width="16" 
                  height="16" 
                  viewBox="0 0 24 24" 
                  fill="currentColor" 
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path d="M12 0C5.374 0 0 5.373 0 12 0 17.302 3.438 21.8 8.207 23.387c.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                </svg>
                <Star className="w-3 h-3" fill="currentColor" />
                <span className="text-sm font-medium">{githubStars}</span>
              </a>
              {isAuthenticated ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="p-0 h-auto rounded-full hover:opacity-80 transition-opacity"
                      title={user?.name || user?.email}
                      data-testid="user-menu-trigger"
                    >
                      <Avatar className="h-10 w-10 border-2 border-purple-500">
                        <AvatarImage src={user?.picture} alt={user?.name || user?.email} />
                        <AvatarFallback className="bg-purple-600 text-white font-medium">
                          {(user?.name || user?.email || 'U').charAt(0).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="bg-card border-border text-foreground" align="end">
                    <div className="px-3 py-2 border-b border-border" data-testid="user-info-section">
                      <p className="text-sm font-medium text-foreground" data-testid="user-name-display">{user?.name}</p>
                      <p className="text-xs text-muted-foreground" data-testid="user-email-display">{user?.email}</p>
                    </div>
                    <DropdownMenuItem className="hover:!bg-muted cursor-pointer" onClick={() => setShowTokensModal(true)} data-testid="api-tokens-menu-item">
                      API Tokens
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-border" />
                    <DropdownMenuItem className="hover:!bg-muted cursor-pointer" onClick={handleLogout} data-testid="logout-menu-item">
                      Logout
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Button
                  variant="outline"
                  className="bg-purple-600 border-purple-500 text-white hover:bg-purple-700"
                  onClick={() => setShowLoginModal(true)}
                  data-testid="sign-in-btn"
                >
                  Sign In
                </Button>
              )}
            </div>
          </div>

          {/* Mobile Header */}
          <div className="md:hidden p-4 space-y-3">
            {/* Row 1: Hamburger (if collapsed) + Logo + User */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {sidebarCollapsed && (
                  <button
                    onClick={() => setSidebarCollapsed(false)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600 text-white hover:bg-purple-700 transition-all"
                    data-testid="sidebar-toggle"
                  >
                    <PanelLeft className="h-5 w-5" />
                  </button>
                )}
                <img src="/icons/queryweaver.svg" alt="QueryWeaver" className="h-8" data-testid="logo" />
              </div>
              <div className="flex items-center gap-2">
                <a
                  href="https://github.com/FalkorDB/QueryWeaver"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 px-2 py-1 rounded bg-card hover:bg-muted transition-colors text-muted-foreground"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path d="M12 0C5.374 0 0 5.373 0 12 0 17.302 3.438 21.8 8.207 23.387c.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                  </svg>
                  <Star className="w-3 h-3" fill="currentColor" />
                  <span className="text-xs font-medium">{githubStars}</span>
                </a>
                {isAuthenticated ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        className="p-0 h-auto rounded-full hover:opacity-80 transition-opacity"
                      >
                        <Avatar className="h-8 w-8 border-2 border-purple-500">
                          <AvatarImage src={user?.picture} alt={user?.name || user?.email} />
                          <AvatarFallback className="bg-purple-600 text-white font-medium text-xs">
                            {(user?.name || user?.email || 'U').charAt(0).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-card border-border text-foreground" align="end">
                      <div className="px-3 py-2 border-b border-border" data-testid="user-info-section">
                        <p className="text-sm font-medium text-foreground" data-testid="user-name-display">{user?.name}</p>
                        <p className="text-xs text-muted-foreground" data-testid="user-email-display">{user?.email}</p>
                      </div>
                      <DropdownMenuItem className="hover:!bg-muted cursor-pointer" onClick={() => setShowTokensModal(true)} data-testid="api-tokens-menu-item">
                        API Tokens
                      </DropdownMenuItem>
                      <DropdownMenuSeparator className="bg-border" />
                      <DropdownMenuItem className="hover:!bg-muted cursor-pointer" onClick={handleLogout} data-testid="logout-menu-item">
                        Logout
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="bg-purple-600 border-purple-500 text-white hover:bg-purple-700"
                    onClick={() => setShowLoginModal(true)}
                  >
                    Sign In
                  </Button>
                )}
              </div>
            </div>
            
            {/* Row 2: Tagline + Database Status */}
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">Graph-Powered Text-to-SQL</p>
              {selectedGraph ? (
                <Badge variant="default" className="bg-green-600 hover:bg-green-700 text-xs px-2 py-0.5 flex-shrink-0">
                  {selectedGraph.name === 'DEMO_CRM' ? 'CRM' : selectedGraph.name}
                </Badge>
              ) : (
                <Badge variant="secondary" className="bg-yellow-600 hover:bg-yellow-700 text-xs px-2 py-0.5 flex-shrink-0">
                  No DB
                </Badge>
              )}
            </div>
          </div>
        </header>

        {/* Sub-header for controls */}
        <div className="px-6 py-4 border-b border-border">
          <div className="flex gap-3 flex-wrap md:flex-nowrap">
              <Button
                variant="outline"
                className="bg-card border-border text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed p-2"
                onClick={handleRefreshSchema}
                disabled={!selectedGraph || isRefreshingSchema || isChatProcessing}
                title={selectedGraph ? (isRefreshingSchema ? 'Refreshing schema...' : isChatProcessing ? 'Wait for query to complete' : 'Refresh Schema') : "Select a database first"}
                data-testid="refresh-schema-btn"
              >
                {isRefreshingSchema ? <LoadingSpinner size="sm" /> : <RefreshCw className="w-4 h-4" />}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    className="bg-card border-border text-muted-foreground hover:bg-muted flex-1 md:flex-initial"
                    disabled={isRefreshingSchema || isChatProcessing}
                    title={isRefreshingSchema ? 'Refreshing schema...' : isChatProcessing ? 'Wait for query to complete' : undefined}
                    data-testid="database-selector-trigger"
                  >
                    <span className="truncate">{selectedGraph?.name || 'Select Database'}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="bg-card border-border text-foreground">
                  {graphs.map((graph) => {
                    const isDemo = graph.id.startsWith('general_');
                    return (
                      <DropdownMenuItem
                        key={graph.id}
                        className="hover:!bg-muted flex items-center justify-between group"
                        onClick={() => { if (!isRefreshingSchema && !isChatProcessing) selectGraph(graph.id); }}
                        disabled={isRefreshingSchema || isChatProcessing}
                        data-testid={`database-option-${graph.id}`}
                      >
                        <span>{graph.name}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className={`h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity ${
                            isDemo || isRefreshingSchema || isChatProcessing ? 'cursor-not-allowed opacity-40' : 'hover:bg-red-600 hover:text-white'
                          }`}
                          onClick={(e) => { if (isDemo || isRefreshingSchema || isChatProcessing) return; handleDeleteGraph(graph.id, graph.name, e); }}
                          disabled={isDemo || isRefreshingSchema}
                          title={isDemo ? 'Demo databases cannot be deleted' : (isRefreshingSchema ? 'Refreshing schema...' : `Delete ${graph.name}`)}
                          data-testid={`delete-graph-btn-${graph.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </DropdownMenuItem>
                    );
                  })}
                  {graphs.length === 0 && (
                    <DropdownMenuItem disabled className="text-muted-foreground">
                      No databases available
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
              <Button
                variant="outline"
                className="bg-purple-600 border-purple-500 text-white hover:bg-purple-700 hover:border-purple-600 hover:text-white flex-1 md:flex-initial shadow-sm hover:shadow-md transition-all"
                onClick={handleConnectDatabase}
                disabled={isRefreshingSchema || isChatProcessing}
                title={isRefreshingSchema ? 'Refreshing schema...' : isChatProcessing ? 'Wait for query to complete' : undefined}
                data-testid="connect-database-btn"
              >
                  <span className="hidden sm:inline">Connect to Database</span>
                  <span className="sm:hidden">Connect DB</span>
              </Button>
              <Button
                variant="outline"
                className="bg-card border-border text-muted-foreground opacity-60 cursor-not-allowed hidden md:flex"
                disabled
                title="Upload schema feature coming soon"
                onClick={(e) => e.preventDefault()}
                data-testid="upload-schema-btn"
              >
                  Upload Schema
              </Button>
          </div>
        </div>
        
        {/* Chat Interface - Full remaining height */}
        <div className="flex-1 overflow-hidden flex justify-center">
          <div className="h-full w-full max-w-7xl md:px-[15px]">
            <ChatInterface
              disabled={isRefreshingSchema}
              onProcessingChange={setIsChatProcessing}
            />
          </div>
        </div>
      </div>

      {/* Modals */}
      <LoginModal 
        open={showLoginModal} 
        onOpenChange={(open) => {
          setShowLoginModal(open);
          if (!open) {
            // Remember dismissal for this session to avoid pinning the modal
            sessionStorage.setItem('loginModalDismissed', '1');
          }
        }}
        canClose={true}
      />
      <DatabaseModal open={showDatabaseModal} onOpenChange={setShowDatabaseModal} />
      <DeleteDatabaseModal 
        open={showDeleteModal} 
        onOpenChange={setShowDeleteModal}
        databaseName={databaseToDelete?.name || ''}
        onConfirm={confirmDeleteGraph}
        isDemo={databaseToDelete?.isDemo || false}
      />
      <TokensModal open={showTokensModal} onOpenChange={setShowTokensModal} />
    </div>
  );
};

export default Index;
