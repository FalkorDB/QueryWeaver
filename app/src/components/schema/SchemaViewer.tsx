import { useEffect, useRef, useState, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { forceCollide, forceCenter, forceManyBody } from 'd3-force';
import { ZoomIn, ZoomOut, Locate, X, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDatabase } from '@/contexts/DatabaseContext';
import { DatabaseService } from '@/services/database';
import { useToast } from '@/components/ui/use-toast';

interface SchemaNode {
  id?: string;
  name: string;
  columns: Array<string | { name: string; type?: string; dataType?: string }>;
  height?: number;
  x?: number;
  y?: number;
}

interface SchemaLink {
  source: string | SchemaNode;
  target: string | SchemaNode;
}

interface SchemaData {
  nodes: SchemaNode[];
  links: SchemaLink[];
}

interface SchemaViewerProps {
  isOpen: boolean;
  onClose: () => void;
  onWidthChange?: (width: number) => void;
  sidebarWidth?: number;
}

const SchemaViewer = ({ isOpen, onClose, onWidthChange, sidebarWidth = 64 }: SchemaViewerProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const resizeRef = useRef<HTMLDivElement>(null);
  const [schemaData, setSchemaData] = useState<SchemaData | null>(null);
  const [loading, setLoading] = useState(false);
  const { selectedGraph } = useDatabase();
  const { toast } = useToast();
  
  // Track if forces have been configured to prevent reconfiguration on resize
  const forcesConfiguredRef = useRef(false);
  
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
          // Force graph redraw when theme changes
          if (graphRef.current) {
            graphRef.current.refresh();
          }
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
  const NODE_SIZE = 6; // For collision detection
  const MIN_WIDTH = 300;
  const MAX_WIDTH_PERCENT = 0.6;
  const DEFAULT_WIDTH_PERCENT = 0.5;
  
  // Force configuration constants (from FalkorDB browser, adjusted for smaller graphs)
  const REFERENCE_NODE_COUNT = 2000;
  const BASE_LINK_DISTANCE = 20;
  const BASE_LINK_STRENGTH = 0.5;
  const BASE_CHARGE_STRENGTH = -1;
  const BASE_CENTER_STRENGTH = 0.1;
  
  // Scaling factors for small graphs (inverse scaling)
  const MIN_LINK_DISTANCE = 80;  // Minimum distance for small graphs
  const MAX_LINK_DISTANCE = 300; // Maximum distance for very small graphs
  const MIN_CHARGE_STRENGTH = -50;  // Minimum charge for small graphs
  const MAX_CHARGE_STRENGTH = -800; // Maximum charge for very small graphs
  
  const [width, setWidth] = useState(() => {
    const initialWidth = Math.floor(window.innerWidth * DEFAULT_WIDTH_PERCENT);
    return initialWidth;
  });
  const [isResizing, setIsResizing] = useState(false);
  
  // Notify parent of width changes
  useEffect(() => {
    if (onWidthChange) {
      onWidthChange(width);
    }
  }, [width, onWidthChange]);

  useEffect(() => {
    if (isOpen && selectedGraph) {
      loadSchemaData();
      // Reset forces configured flag when loading new data
      forcesConfiguredRef.current = false;
    }
  }, [isOpen, selectedGraph]);

  // Configure forces when schema data changes
  useEffect(() => {
    if (!schemaData?.nodes?.length || !graphRef.current) return;
    
    // Skip if forces already configured (prevents reconfiguration on resize)
    if (forcesConfiguredRef.current) {
      console.log('Forces already configured, skipping reconfiguration');
      return;
    }

    const graph = graphRef.current;
    
    // Wait for d3 to be available - it's not immediately accessible on mount
    const configureForces = () => {
      const d3 = graph.d3Force;
      
      if (!d3) {
        console.log('d3 not yet available, retrying...');
        setTimeout(configureForces, 100);
        return;
      }

      const nodeCount = schemaData.nodes.length;
      
      console.log(`Configuring forces for ${nodeCount} nodes`);
      
      // For small graphs, we need STRONGER forces, not weaker
      // Inverse scaling: fewer nodes = stronger repulsion and larger distances
      let linkDistance: number;
      let chargeStrength: number;
      
      if (nodeCount < 50) {
        // Small graphs: use strong forces with inverse scaling
        const smallGraphScale = Math.max(0.1, Math.min(1, nodeCount / 50));
        linkDistance = MAX_LINK_DISTANCE - (MAX_LINK_DISTANCE - MIN_LINK_DISTANCE) * smallGraphScale;
        chargeStrength = MAX_CHARGE_STRENGTH - (MAX_CHARGE_STRENGTH - MIN_CHARGE_STRENGTH) * smallGraphScale;
      } else {
        // Large graphs: use the original FalkorDB scaling
        const scale = Math.sqrt(nodeCount / REFERENCE_NODE_COUNT);
        linkDistance = Math.max(
          Math.min(BASE_LINK_DISTANCE * scale, 120),
          BASE_LINK_DISTANCE
        );
        chargeStrength = Math.min(
          Math.max(BASE_CHARGE_STRENGTH * scale, -80),
          BASE_CHARGE_STRENGTH
        );
      }
      
      console.log(`Link distance: ${linkDistance}`);
      console.log(`Charge strength: ${chargeStrength}`);

      // Configure all forces
      d3('link')
        ?.id((d: SchemaNode) => d.name)
        .distance(linkDistance)
        .strength(BASE_LINK_STRENGTH);
      
      // Use actual node width for collision detection to prevent overlap
      d3('collision', forceCollide(NODE_WIDTH / 2 + 20).strength(1.0).iterations(2));
      d3('center', forceCenter(0, 0).strength(BASE_CENTER_STRENGTH));
      d3('charge', forceManyBody().strength(chargeStrength));

      console.log('Forces configured, reheating simulation');
      graph.d3ReheatSimulation();
      
      // Mark forces as configured to prevent reconfiguration
      forcesConfiguredRef.current = true;
    };

    configureForces();
  }, [schemaData]);  // Handle resize
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
      console.log('Schema data received:', data);
      console.log('Nodes:', data.nodes);
      console.log('Links:', data.links);
      
      setSchemaData(data);
    } catch (error) {
      console.error('Failed to load schema:', error);
      toast({
        title: 'Failed to Load Schema',
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        variant: 'destructive',
      });
      setSchemaData({ nodes: [], links: [] });
    } finally {
      setLoading(false);
    }
  };

  const handleZoomIn = () => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom();
      graphRef.current.zoom(currentZoom * 1.1, 200);
    }
  };

  const handleZoomOut = () => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom();
      graphRef.current.zoom(currentZoom * 0.9, 200);
    }
  };

  const handleCenter = () => {
    if (graphRef.current && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const minDimension = Math.min(rect.width, rect.height);
      const padding = minDimension * 0.1;
      graphRef.current.zoomToFit(500, padding);
    }
  };

  const nodeCanvasObject = (node: any, ctx: CanvasRenderingContext2D) => {
    const lineHeight = 14;
    const padding = 8;
    const headerHeight = 20;
    const fontSize = 12;
    
    // Theme-aware colors
    const isLight = theme === 'light';
    const textColor = isLight ? '#111' : '#f5f5f5';
    const fillColor = isLight ? '#ffffff' : '#1f2937';
    const strokeColor = isLight ? '#d1d5db' : '#374151';
    const columnTextColor = isLight ? '#111' : '#e5e7eb';
    const typeTextColor = isLight ? '#6b7280' : '#9ca3af';

    if (!node.height) {
      node.height = headerHeight + (node.columns?.length || 0) * lineHeight + padding * 2;
    }

    ctx.fillStyle = fillColor;
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1;
    ctx.fillRect(
      node.x - NODE_WIDTH / 2,
      node.y - node.height / 2,
      NODE_WIDTH,
      node.height
    );
    ctx.strokeRect(
      node.x - NODE_WIDTH / 2,
      node.y - node.height / 2,
      NODE_WIDTH,
      node.height
    );

    ctx.fillStyle = textColor;
    ctx.font = `bold ${fontSize}px Arial`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(
      node.name,
      node.x,
      node.y - node.height / 2 + headerHeight / 2 + padding / 2
    );

    ctx.font = `${fontSize - 2}px Arial`;
    ctx.textAlign = 'left';
    const startX = node.x - NODE_WIDTH / 2 + padding;
    let colY = node.y - node.height / 2 + headerHeight + padding;
    (node.columns || []).forEach((col: any) => {
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
          ctx.fillText(typeText, node.x + NODE_WIDTH / 2 - padding, colY);
        }
        ctx.fillStyle = columnTextColor;
        ctx.textAlign = 'left';
      }

      colY += lineHeight;
    });
  };

  const nodePointerAreaPaint = (node: any, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = color;
    const padding = 5;
    ctx.fillRect(
      node.x - NODE_WIDTH / 2 - padding,
      node.y - node.height / 2 - padding,
      NODE_WIDTH + padding * 2,
      node.height + padding * 2
    );
  };

  // Memoize graphData to prevent recreation on every render (especially during resize)
  const memoizedGraphData = useMemo(() => {
    if (!schemaData) return { nodes: [], links: [] };
    
    console.log('Schema data received:', schemaData);
    console.log('Nodes:', schemaData.nodes);
    console.log('Links:', schemaData.links);
    
    schemaData.nodes.forEach(node => {
      console.log('Node:', node.name, 'id:', node.id, 'columns:', node.columns?.length);
    });
    
    schemaData.links.forEach(link => {
      console.log('Link:', link.source, '->', link.target);
    });
    
    return {
      nodes: schemaData.nodes,
      links: schemaData.links
    };
  }, [schemaData]);

  // Get theme-aware colors
  const getBackgroundColor = () => {
    return theme === 'light' ? '#ffffff' : '#030712';
  };

  const getLinkColor = () => {
    return theme === 'light' ? '#9ca3af' : '#4b5563';
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Mobile overlay backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onClose}
        />
      )}
      
      {/* Schema Viewer */}
      <div
        data-testid="schema-panel"
        className={`fixed top-0 h-full bg-gray-900 border-r border-gray-700 flex flex-col transition-all duration-300
          ${isOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'}
          md:z-30 z-50
          w-[80vw] max-w-[400px] md:max-w-none
        `}
        style={{
          ...(isOpen && window.innerWidth >= 768 ? {
            left: `${sidebarWidth}px`,
            width: `${width}px`
          } : {})
        }}
      >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-gray-100">Database Schema</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          className="h-8 w-8 p-0 text-gray-400 hover:text-gray-100"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Controls */}
      <div className="flex gap-2 p-2 border-b border-gray-700">
        <Button
          variant="outline"
          size="sm"
          onClick={handleZoomIn}
          className="h-8 w-8 p-0 bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
          title="Zoom In"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleZoomOut}
          className="h-8 w-8 p-0 bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
          title="Zoom Out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleCenter}
          className="h-8 w-8 p-0 bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
          title="Center"
        >
          <Locate className="h-4 w-4" />
        </Button>
      </div>

      {/* Graph Container */}
      <div ref={containerRef} className="h-[calc(100%-8rem)] w-full bg-gray-950 relative">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-gray-400">Loading schema...</div>
          </div>
        )}
        {!loading && schemaData && schemaData.nodes && schemaData.nodes.length > 0 && (
          <div className="w-full h-full">
            <ForceGraph2D
              ref={graphRef}
              graphData={memoizedGraphData}
              width={containerRef.current?.clientWidth || width}
              height={containerRef.current?.clientHeight || 600}
              nodeId="name"
              nodeLabel="name"
              linkSource="source"
              linkTarget="target"
              nodeCanvasObject={nodeCanvasObject}
              nodePointerAreaPaint={nodePointerAreaPaint}
              nodeRelSize={1}
              nodeVal={1}
              linkColor={getLinkColor}
              linkWidth={1.5}
              linkDirectionalArrowLength={6}
              linkDirectionalArrowRelPos={1}
              warmupTicks={0}
              cooldownTime={1000}
              cooldownTicks={Infinity}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
              onEngineStop={handleCenter}
              backgroundColor={getBackgroundColor()}
              enableNodeDrag={true}
              enableZoomInteraction={true}
              enablePanInteraction={true}
            />
          </div>
        )}
        {!loading && (!schemaData || !schemaData.nodes || schemaData.nodes.length === 0) && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
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
          <GripVertical className="h-4 w-4 text-gray-600" />
        </div>
      </div>
    </div>
    </>
  );
};

export default SchemaViewer;
