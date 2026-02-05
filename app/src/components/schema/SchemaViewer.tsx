import { useEffect, useRef, useState, useCallback } from 'react';
import type { Data, FalkorDBCanvas, GraphNode } from '@falkordb/canvas';
import { ZoomIn, ZoomOut, Locate, X, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDatabase } from '@/contexts/DatabaseContext';
import { DatabaseService } from '@/services/database';
import { useToast } from '@/components/ui/use-toast';

interface SchemaNode {
  id: number;
  userId: string;
  name: string;
  columns: Array<string | { name: string; type?: string; dataType?: string }>;
}

interface SchemaLink {
  source: number;
  target: number;
}

interface SchemaData {
  nodes: SchemaNode[];
  links: SchemaLink[];
  nodesMap: Map<number, SchemaNode>
}

interface SchemaViewerProps {
  isOpen: boolean;
  onClose: () => void;
  onWidthChange?: (width: number) => void;
  sidebarWidth?: number;
}

const SchemaViewer = ({ isOpen, onClose, onWidthChange, sidebarWidth = 64 }: SchemaViewerProps) => {
  const canvasRef = useRef<FalkorDBCanvas>(null);
  const resizeRef = useRef<HTMLDivElement>(null);
  const [schemaData, setSchemaData] = useState<SchemaData | null>(null);
  const [loading, setLoading] = useState(false);
  const { selectedGraph } = useDatabase();
  const { toast } = useToast();

  // Track current theme for canvas colors
  const [theme, setTheme] = useState<string>(() => {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  });

  // Listen for theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'attributes' && mutation.attributeName === 'data-theme') {
          const newTheme = document.documentElement.getAttribute('data-theme') || 'dark';
          setTheme(newTheme);
        }
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });

    return () => observer.disconnect();
  }, []);

  const NODE_WIDTH = 160;
  const MIN_WIDTH = 300;
  const MAX_WIDTH_PERCENT = 0.6;
  const DEFAULT_WIDTH_PERCENT = 0.5;

  const [width, setWidth] = useState(() => {
    const initialWidth = Math.floor(window.innerWidth * DEFAULT_WIDTH_PERCENT);
    return initialWidth;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [canvasLoaded, setCanvasLoaded] = useState(false);

  // Notify parent of width changes
  useEffect(() => {
    if (onWidthChange) {
      onWidthChange(width);
    }
  }, [width, onWidthChange]);

  // Load falkordb-canvas dynamically
  useEffect(() => {
    import('@falkordb/canvas').then(() => {
      setCanvasLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (isOpen && selectedGraph) {
      loadSchemaData();
    }
  }, [isOpen, selectedGraph]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;

      const newWidth = e.clientX - sidebarWidth;
      const maxWidth = Math.floor(window.innerWidth * MAX_WIDTH_PERCENT);

      if (newWidth >= MIN_WIDTH && newWidth <= maxWidth) {
        setWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing, sidebarWidth]);

  const loadSchemaData = async () => {
    if (!selectedGraph) return;

    setLoading(true);
    try {
      const data = await DatabaseService.getGraphData(selectedGraph.id);

      // Create a mapping from old IDs to new IDs
      const oldIdToNewId = new Map<string, number>();

      // Remap nodes with new sequential IDs
      data.nodes = data.nodes.map((node, index) => {
        const newId = index + 1;
        oldIdToNewId.set(node.id, newId);
        return {
          ...node,
          userId: node.id,
          id: newId,
        };
      });

      // Update links to use the new node IDs
      data.links = data.links.map((link) => ({
        ...link,
        source: oldIdToNewId.get(link.source) || link.source,
        target: oldIdToNewId.get(link.target) || link.target,
      }));

      const nodesMap = new Map<number, SchemaNode>(data.nodes.map((node) => [node.id, node]));

      setSchemaData({ ...data, nodesMap });
    } catch (error) {
      console.error('Failed to load schema:', error);
      toast({
        title: 'Failed to Load Schema',
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        variant: 'destructive',
      });
      setSchemaData({ nodes: [], links: [], nodesMap: new Map() });
    } finally {
      setLoading(false);
    }
  };

  const handleZoomIn = () => {
    const canvas = canvasRef.current

    if (canvas) {
      canvas.zoom(canvas.getZoom() * 1.1);
    }
  };

  const handleZoomOut = () => {
    const canvas = canvasRef.current;

    if (canvas) {
      canvas.zoom(canvas.getZoom() * 0.9);
    }
  };

  const handleCenter = useCallback(() => {
    console.log("Stop");

    const canvas = canvasRef.current;

    if (canvas) {
      canvas.zoomToFit();
    }
  }, []);

  // Convert schema data to canvas format
  const convertToCanvasData = useCallback((data: SchemaData): Data => {
    const nodes = data.nodes.map((node) => {
      // Calculate node size based on height (same calculation as in nodeCanvasObject)
      const columns = node.columns || [];
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;

      // Use the larger dimension as collision radius (in pixels)
      const size = Math.max(NODE_WIDTH / 2, nodeHeight / 2);

      return {
        id: node.id,
        labels: ['Table'],
        color: theme === 'light' ? '#60a5fa' : '#3b82f6',
        visible: true,
        size,
        data: {
          name: node.name,
          columns: node.columns
        }
      };
    });

    const links = data.links.map((link, index) => {
      return {
        id: index + 1,
        relationship: 'REFERENCES',
        color: theme === 'light' ? '#9ca3af' : '#4b5563',
        visible: true,
        source: link.source,
        target: link.target,
        data: {}
      };
    });

    return { nodes, links };
  }, [theme]);

  // Set up canvas configuration and data - MUST be in single effect to ensure proper order
  useEffect(() => {
    const canvas = canvasRef.current;

    if (!canvas || !canvasLoaded || !schemaData) return;

    const nodeCanvasObject = (node: GraphNode, ctx: CanvasRenderingContext2D) => {
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const fontSize = 12;

      // Theme-aware colors
      const isLight = theme === 'light';
      const textColor = isLight ? '#111' : '#f5f5f5';
      const fillColor = isLight ? '#ffffff' : '#191919';
      const strokeColor = isLight ? '#d1d5db' : '#374151';
      const columnTextColor = isLight ? '#111' : '#e5e7eb';
      const typeTextColor = isLight ? '#6b7280' : '#9ca3af';

      // Find the original schema node to get columns
      const schemaNode = schemaData.nodesMap.get(node.id);

      if (!schemaNode) return;

      const columns = schemaNode.columns || [];

      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;

      ctx.fillStyle = fillColor;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.fillRect(
        (node.x || 0) - NODE_WIDTH / 2,
        (node.y || 0) - nodeHeight / 2,
        NODE_WIDTH,
        nodeHeight
      );
      ctx.strokeRect(
        (node.x || 0) - NODE_WIDTH / 2,
        (node.y || 0) - nodeHeight / 2,
        NODE_WIDTH,
        nodeHeight
      );

      ctx.fillStyle = textColor;
      ctx.font = `bold ${fontSize}px Arial`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(
        node.displayName[1],
        node.x || 0,
        (node.y || 0) - nodeHeight / 2 + headerHeight / 2 + padding / 2
      );

      ctx.font = `${fontSize - 2}px Arial`;
      ctx.textAlign = 'left';
      const startX = (node.x || 0) - NODE_WIDTH / 2 + padding;
      let colY = (node.y || 0) - nodeHeight / 2 + headerHeight + padding;

      columns.forEach((col: any) => {
        let name = col;
        let type = null;
        if (typeof col === 'object') {
          name = col.name || '';
          type = col.type || col.dataType || null;
        }

        ctx.textAlign = 'left';
        ctx.fillStyle = columnTextColor;
        ctx.fillText(name, startX, colY);

        if (type) {
          ctx.fillStyle = typeTextColor;
          const nameWidth = ctx.measureText(name).width;
          const available = NODE_WIDTH - padding * 2 - nameWidth - 8;
          let typeText = String(type);
          if (available > 0) {
            if (ctx.measureText(typeText).width > available) {
              while (
                typeText.length > 0 &&
                ctx.measureText(typeText + '…').width > available
              ) {
                typeText = typeText.slice(0, -1);
              }
              typeText = typeText + '…';
            }
            ctx.textAlign = 'right';
            ctx.fillText(typeText, (node.x || 0) + NODE_WIDTH / 2 - padding, colY);
          }
          ctx.fillStyle = columnTextColor;
          ctx.textAlign = 'left';
        }

        colY += lineHeight;
      });
    };

    const nodePointerAreaPaint = (node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
      const schemaNode = schemaData.nodesMap.get(node.id);

      if (!schemaNode) return;

      const columns = schemaNode.columns || [];
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;

      ctx.fillStyle = color;
      const areaPadding = 5;
      ctx.fillRect(
        (node.x || 0) - NODE_WIDTH / 2 - areaPadding,
        (node.y || 0) - nodeHeight / 2 - areaPadding,
        NODE_WIDTH + areaPadding * 2,
        nodeHeight + areaPadding * 2
      );
    };


    const canvasData = convertToCanvasData(schemaData);

    canvas.setConfig({
      autoStopOnSettle: false,
      node: {
        nodeCanvasObject,
        nodePointerAreaPaint,
      }
    });
    
    canvas.setBackgroundColor(theme === 'light' ? '#ffffff' : '#191919');
    canvas.setForegroundColor(theme === 'light' ? '#111' : '#f5f5f5');
    canvas.setData(canvasData);
  }, [schemaData, theme, canvasLoaded, convertToCanvasData]);

  if (!isOpen) return null;

  return (
    <>
      {/* Mobile overlay backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 md:hidden"
        onClick={onClose}
      />

      {/* Schema Viewer */}
      <div
        data-testid="schema-panel"
        className={`fixed top-0 h-full bg-background border-r border-border flex flex-col transition-all duration-300
          ${isOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'}
          md:z-30 z-50
          w-[80vw] max-w-[400px] md:max-w-none
        `}
        style={{
          ...(window.innerWidth >= 768 ? {
            left: `${sidebarWidth}px`,
            width: `${width}px`
          } : {})
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">Database Schema</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Controls */}
        <div className="flex gap-2 p-2 border-b border-border">
          <Button
            variant="outline"
            size="sm"
            onClick={handleZoomIn}
            className="h-8 w-8 p-0 bg-card border-border text-muted-foreground hover:bg-foreground"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleZoomOut}
            className="h-8 w-8 p-0 bg-card border-border text-muted-foreground hover:bg-foreground"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleCenter}
            className="h-8 w-8 p-0 bg-card border-border text-muted-foreground hover:bg-foreground"
            title="Center"
          >
            <Locate className="h-4 w-4" />
          </Button>
        </div>

        {/* Graph Container */}
        <div className="h-[calc(100%-8rem)] w-full bg-background relative">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-muted-foreground">Loading schema...</div>
            </div>
          )}
          {!loading && canvasLoaded && schemaData && schemaData.nodes.length > 0 && (
            <falkordb-canvas ref={canvasRef} node-mode='replace' />
          )}
          {!loading && (!schemaData || schemaData.nodes.length === 0) && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-muted-foreground">
                <p>No schema data available</p>
                <p className="text-sm mt-2">
                  {!selectedGraph ? 'Select a database first' : 'This database has no schema data'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Resize Handle */}
        <div
          ref={resizeRef}
          className="absolute right-0 top-0 w-1 h-full cursor-ew-resize hover:bg-purple-500 transition-colors z-50"
          onMouseDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsResizing(true);
          }}
        >
          <div className="absolute right-0 top-1/2 -translate-y-1/2 -translate-x-1/2">
            <GripVertical className="h-4 w-4 text-border" />
          </div>
        </div>
      </div>
    </>
  );
};

export default SchemaViewer;
