import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { Data, FalkorDBCanvas, GraphNode, GraphLink } from '@falkordb/canvas';
import { X, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDatabase } from '@/contexts/DatabaseContext';
import { useQueryHighlight } from '@/contexts/QueryHighlightContext';
import { DatabaseService } from '@/services/database';
import { useToast } from '@/components/ui/use-toast';
import SchemaCanvasControls, { type SchemaTableOption } from './SchemaCanvasControls';

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

/** Accent used for tables/relations referenced by the selected SQL query. */
const HIGHLIGHT_COLOR = '#8b5cf6';
/** Opacity applied to schema elements the selected query does not touch. */
const DIMMED_OPACITY = 0.25;

// Geometry of a rendered table card, shared by the drawing code and the
// viewport framing below.
const NODE_WIDTH = 160;
const NODE_LINE_HEIGHT = 14;
const NODE_PADDING = 8;
const NODE_HEADER_HEIGHT = 20;

const tableNodeHeight = (columnCount: number): number =>
  NODE_HEADER_HEIGHT + columnCount * NODE_LINE_HEIGHT + NODE_PADDING * 2;

/** Gap in pixels kept between the framed tables and the canvas edges. */
const FIT_PADDING_PX = 32;
/** Upper bound on the framing zoom, so a single small table is not blown up. */
const FIT_MAX_ZOOM = 1.5;
const FIT_MIN_ZOOM = 0.05;
const FIT_ANIMATION_MS = 300;

/** Link endpoints are ids before the layout runs and node objects afterwards. */
const endpointId = (endpoint: unknown): string => {
  if (endpoint && typeof endpoint === 'object' && 'id' in endpoint) {
    return String((endpoint as { id: unknown }).id);
  }
  return String(endpoint);
};

/** Direction-agnostic key so a relation matches however the canvas orders it. */
const linkKey = (source: unknown, target: unknown): string =>
  [endpointId(source), endpointId(target)].sort().join('|');

// Must stay above the canvas' `interaction.zoomToFitDelay` (50ms default) so the
// highlight framing is applied after the canvas' own initial fit.
const HIGHLIGHT_ZOOM_DELAY_MS = 100;
/** How long to keep waiting for the layout to settle before framing anyway. */
const SETTLE_TIMEOUT_MS = 2000;
/** World-unit movement below which the layout counts as settled. */
const SETTLE_EPSILON = 0.5;

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

const boundsSettled = (a: Bounds, b: Bounds): boolean =>
  Math.abs(a.minX - b.minX) < SETTLE_EPSILON &&
  Math.abs(a.maxX - b.maxX) < SETTLE_EPSILON &&
  Math.abs(a.minY - b.minY) < SETTLE_EPSILON &&
  Math.abs(a.maxY - b.maxY) < SETTLE_EPSILON;

const SchemaViewer = ({ isOpen, onClose, onWidthChange, sidebarWidth = 64 }: SchemaViewerProps) => {
  const canvasRef = useRef<FalkorDBCanvas>(null);
  const resizeRef = useRef<HTMLDivElement>(null);
  // Handle of the in-flight "wait for the layout to settle" loop, so a new
  // framing request cancels the previous one instead of racing it.
  const settleFrameRef = useRef(0);
  // Schema snapshot currently seeded into the canvas, used to avoid re-seeding
  // (and losing node positions) when only the highlight changed.
  const renderedSchemaRef = useRef<SchemaData | null>(null);
  const [schemaData, setSchemaData] = useState<SchemaData | null>(null);
  const [loading, setLoading] = useState(false);
  // Focus mode dims everything that is not connected to the hovered/selected table.
  const [focusMode, setFocusMode] = useState(false);
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const { selectedGraph } = useDatabase();
  const { highlightedTables, clearQueryHighlight } = useQueryHighlight();
  const { toast } = useToast();

  // Tables referenced by the currently selected SQL query, and the relations
  // between them. Empty sets mean "no highlight" — everything renders normally.
  const { highlightedNodeIds, highlightedLinkKeys } = useMemo(() => {
    const nodeIds = new Set<number>();
    const linkKeys = new Set<string>();

    if (!schemaData || highlightedTables.length === 0) {
      return { highlightedNodeIds: nodeIds, highlightedLinkKeys: linkKeys };
    }

    const wanted = new Set(highlightedTables.map((table) => table.toLowerCase()));
    schemaData.nodes.forEach((node) => {
      if (node.name && wanted.has(String(node.name).toLowerCase())) {
        nodeIds.add(node.id);
      }
    });

    schemaData.links.forEach((link) => {
      if (nodeIds.has(link.source) && nodeIds.has(link.target)) {
        linkKeys.add(linkKey(link.source, link.target));
      }
    });

    return { highlightedNodeIds: nodeIds, highlightedLinkKeys: linkKeys };
  }, [schemaData, highlightedTables]);

  const hasHighlight = highlightedNodeIds.size > 0;

  // Table the user is pointing at (hover wins over the searched/clicked table).
  const focusTargetId = hoveredNodeId ?? selectedTableId;

  // Elements rendered with the accent colour. A selected SQL query wins; otherwise
  // the hovered/selected table together with its direct relations is emphasised.
  const { emphasisNodeIds, emphasisLinkKeys } = useMemo(() => {
    if (hasHighlight) {
      return { emphasisNodeIds: highlightedNodeIds, emphasisLinkKeys: highlightedLinkKeys };
    }

    const nodeIds = new Set<number>();
    const linkKeys = new Set<string>();

    if (schemaData && focusTargetId !== null) {
      nodeIds.add(focusTargetId);
      schemaData.links.forEach((link) => {
        if (link.source === focusTargetId || link.target === focusTargetId) {
          nodeIds.add(link.source);
          nodeIds.add(link.target);
          linkKeys.add(linkKey(link.source, link.target));
        }
      });
    }

    return { emphasisNodeIds: nodeIds, emphasisLinkKeys: linkKeys };
  }, [hasHighlight, highlightedNodeIds, highlightedLinkKeys, schemaData, focusTargetId]);

  // A query highlight always dims the rest; hover only dims in focus mode.
  const dimInactive = hasHighlight || (focusMode && emphasisNodeIds.size > 0);

  // Hover/selection emphasis is hidden while a query highlight is active, so
  // drop it when the highlight clears instead of letting it reappear.
  const hadHighlightRef = useRef(false);
  useEffect(() => {
    if (hadHighlightRef.current && !hasHighlight) {
      setHoveredNodeId(null);
      setSelectedTableId(null);
    }
    hadHighlightRef.current = hasHighlight;
  }, [hasHighlight]);

  // Search options for the canvas controls.
  const tableOptions = useMemo<SchemaTableOption[]>(() => {
    if (!schemaData) return [];

    return schemaData.nodes.map((node) => ({
      id: node.id,
      name: String(node.name ?? ''),
      columns: (node.columns || []).map((column) =>
        typeof column === 'object' ? String(column.name ?? '') : String(column)
      ),
    }));
  }, [schemaData]);

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

      setHoveredNodeId(null);
      setSelectedTableId(null);
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

  const linkColorFor = useCallback((sourceId: number, targetId: number) => {
    if (hasHighlight && highlightedLinkKeys.has(linkKey(sourceId, targetId))) return HIGHLIGHT_COLOR;
    return theme === 'light' ? '#9ca3af' : '#4b5563';
  }, [theme, hasHighlight, highlightedLinkKeys]);

  // Bounding box of the matching table cards in world units, or null when the
  // layout has not produced coordinates for any of them yet.
  const nodeBounds = useCallback((match?: (nodeId: number) => boolean): Bounds | null => {
    const canvas = canvasRef.current;

    if (!canvas || !schemaData) return null;

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    canvas.getGraphData()?.nodes.forEach((node) => {
      if (node.x === undefined || node.y === undefined) return;
      if (match && !match(Number(node.id))) return;

      const columns = schemaData.nodesMap.get(Number(node.id))?.columns ?? [];
      const halfHeight = tableNodeHeight(columns.length) / 2;

      minX = Math.min(minX, node.x - NODE_WIDTH / 2);
      maxX = Math.max(maxX, node.x + NODE_WIDTH / 2);
      minY = Math.min(minY, node.y - halfHeight);
      maxY = Math.max(maxY, node.y + halfHeight);
    });

    // Nothing matched, or the layout has not produced coordinates yet.
    if (!Number.isFinite(minX)) return null;

    return { minX, maxX, minY, maxY };
  }, [schemaData]);

  // The canvas' own zoomToFit frames node centres, so a tall table gets clipped
  // and a single table is zoomed to the configured maximum whatever its size.
  // Frame the rendered cards instead.
  const frameNodes = useCallback((match?: (nodeId: number) => boolean): boolean => {
    const canvas = canvasRef.current;

    if (!canvas) return false;

    const rect = canvas.getBoundingClientRect();

    if (!rect.width || !rect.height) return false;

    const bounds = nodeBounds(match);

    if (!bounds) return false;

    const { minX, maxX, minY, maxY } = bounds;

    // A panel narrower than the padding would otherwise ask for a negative area.
    const fitZoom = Math.min(
      Math.max(rect.width - FIT_PADDING_PX * 2, 1) / (maxX - minX),
      Math.max(rect.height - FIT_PADDING_PX * 2, 1) / (maxY - minY)
    );

    canvas.centerAt((minX + maxX) / 2, (minY + maxY) / 2, FIT_ANIMATION_MS);

    const zoom = Math.min(Math.max(fitZoom, FIT_MIN_ZOOM), FIT_MAX_ZOOM);
    // The canvas' own zoom() is instant, so go through force-graph to keep the
    // pan and the zoom on the same animation.
    const graph = canvas.getGraph();

    if (graph) {
      graph.zoom(zoom, FIT_ANIMATION_MS);
    } else {
      canvas.zoom(zoom);
    }

    return true;
  }, [nodeBounds]);

  // A running layout keeps moving after it has produced its first coordinates,
  // so framing them aims at an already-stale target. Wait for the bounds to stop
  // changing. Only one wait runs at a time: a later request supersedes an
  // earlier one rather than racing it.
  const frameWhenSettled = useCallback((match?: (nodeId: number) => boolean) => {
    cancelAnimationFrame(settleFrameRef.current);

    const deadline = Date.now() + SETTLE_TIMEOUT_MS;
    let previous: Bounds | null = null;

    const attempt = () => {
      const bounds = nodeBounds(match);

      if ((bounds && previous && boundsSettled(bounds, previous)) || Date.now() >= deadline) {
        frameNodes(match);
        return;
      }

      previous = bounds;
      settleFrameRef.current = requestAnimationFrame(attempt);
    };

    settleFrameRef.current = requestAnimationFrame(attempt);
  }, [nodeBounds, frameNodes]);

  // Switching layout or direction re-runs the canvas' own centre-based fit,
  // which clips tall cards and discards any highlight framing.
  const frameCurrentTarget = useCallback(() => {
    frameWhenSettled(
      hasHighlight ? (nodeId: number) => highlightedNodeIds.has(nodeId) : undefined
    );
  }, [frameWhenSettled, hasHighlight, highlightedNodeIds]);

  // Convert schema data to canvas format
  const convertToCanvasData = useCallback((data: SchemaData): Data => {
    const nodes = data.nodes.map((node) => {
      const nodeHeight = tableNodeHeight((node.columns || []).length);

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
        color: linkColorFor(link.source, link.target),
        visible: true,
        source: link.source,
        target: link.target,
        data: {}
      };
    });

    return { nodes, links };
  }, [theme, linkColorFor]);

  // Canvas configuration: custom table rendering, focus/dim predicates and
  // interaction handlers. Kept separate from the data effect so hovering never
  // re-seeds the graph.
  useEffect(() => {
    const canvas = canvasRef.current;

    if (!canvas || !canvasLoaded || !schemaData) return;

    const nodeCanvasObject = (node: GraphNode, ctx: CanvasRenderingContext2D) => {
      const lineHeight = NODE_LINE_HEIGHT;
      const padding = NODE_PADDING;
      const headerHeight = NODE_HEADER_HEIGHT;
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

      const isEmphasized = emphasisNodeIds.has(node.id);
      const isDimmed = dimInactive && !isEmphasized;
      const isActive = node.id === hoveredNodeId || node.id === selectedTableId;

      const columns = schemaNode.columns || [];

      const nodeHeight = tableNodeHeight(columns.length);

      const previousAlpha = ctx.globalAlpha;
      if (isDimmed) {
        ctx.globalAlpha = previousAlpha * DIMMED_OPACITY;
      }

      ctx.fillStyle = fillColor;
      ctx.strokeStyle = isEmphasized || isActive ? HIGHLIGHT_COLOR : strokeColor;
      ctx.lineWidth = isActive ? 3 : isEmphasized ? 2.5 : 1;
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

      ctx.fillStyle = isEmphasized || isActive ? HIGHLIGHT_COLOR : textColor;
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

      ctx.globalAlpha = previousAlpha;
    };

    const nodePointerAreaPaint = (node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
      const schemaNode = schemaData.nodesMap.get(node.id);

      if (!schemaNode) return;

      const columns = schemaNode.columns || [];
      const nodeHeight = tableNodeHeight(columns.length);

      ctx.fillStyle = color;
      const areaPadding = 5;
      ctx.fillRect(
        (node.x || 0) - NODE_WIDTH / 2 - areaPadding,
        (node.y || 0) - nodeHeight / 2 - areaPadding,
        NODE_WIDTH + areaPadding * 2,
        nodeHeight + areaPadding * 2
      );
    };


    const linkKeyOf = (link: GraphLink) => linkKey(link.source, link.target);

    canvas.setConfig({
      dimmed: dimInactive,
      dimOpacity: DIMMED_OPACITY,
      // Nodes are drawn by `nodeCanvasObject`, which replaces the canvas' own
      // node renderer — so node dimming is applied manually there and this
      // predicate only keeps the config coherent. Links still dim natively.
      isNodeDimmed: (node: GraphNode) => !emphasisNodeIds.has(node.id),
      isLinkDimmed: (link: GraphLink) => !emphasisLinkKeys.has(linkKeyOf(link)),
      isNodeSelected: (node: GraphNode) =>
        node.id === hoveredNodeId || node.id === selectedTableId,
      isLinkSelected: (link: GraphLink) => emphasisLinkKeys.has(linkKeyOf(link)),
      node: {
        nodeCanvasObject,
        nodePointerAreaPaint,
      },
      eventHandlers: {
        onNodeHover: (node: GraphNode | null) => setHoveredNodeId(node ? node.id : null),
        onNodeClick: (node: GraphNode) =>
          setSelectedTableId((current) => (current === node.id ? null : node.id)),
        onBackgroundClick: () => setSelectedTableId(null),
      },
    });

    canvas.setBackgroundColor(theme === 'light' ? '#ffffff' : '#191919');
    canvas.setForegroundColor(theme === 'light' ? '#111' : '#f5f5f5');
  }, [
    schemaData,
    theme,
    canvasLoaded,
    dimInactive,
    emphasisNodeIds,
    emphasisLinkKeys,
    hoveredNodeId,
    selectedTableId,
  ]);

  // Seed the canvas with the schema. `setData` recomputes the layout, so it only
  // runs for a new schema; later updates reuse the existing node positions.
  useEffect(() => {
    const canvas = canvasRef.current;

    if (!canvas || !canvasLoaded || !schemaData) return;

    const canvasData = convertToCanvasData(schemaData);

    if (renderedSchemaRef.current !== schemaData) {
      renderedSchemaRef.current = schemaData;
      canvas.setData(canvasData);
      return;
    }

    canvas.setGraphData(canvasData);
  }, [schemaData, canvasLoaded, convertToCanvasData]);

  // Bring the highlighted tables into view when a query is selected. The layout
  // may still be moving, so frame it once it has stopped.
  // Reopening the viewer re-runs this, since the canvas is unmounted while closed.
  useEffect(() => {
    if (!isOpen || !canvasLoaded || !hasHighlight) return;

    const timer = setTimeout(() => {
      frameWhenSettled((nodeId) => highlightedNodeIds.has(nodeId));
    }, HIGHLIGHT_ZOOM_DELAY_MS);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(settleFrameRef.current);
    };
  }, [isOpen, canvasLoaded, hasHighlight, highlightedNodeIds, frameWhenSettled]);

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
          translate-x-0
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
        <SchemaCanvasControls
          canvasRef={canvasRef}
          tables={tableOptions}
          disabled={loading || tableOptions.length === 0}
          focusMode={focusMode}
          onFocusModeChange={setFocusMode}
          selectedTableId={selectedTableId}
          onSelectTable={setSelectedTableId}
          onFrameNodes={frameNodes}
          onLayoutChanged={frameCurrentTarget}
        />

        {/* Highlight status */}
        {hasHighlight && (
          <div
            className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-primary/5"
            data-testid="schema-highlight-bar"
          >
            <span className="text-xs text-muted-foreground truncate">
              Highlighting {highlightedNodeIds.size} table{highlightedNodeIds.size === 1 ? '' : 's'} used by the selected query
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearQueryHighlight}
              className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </Button>
          </div>
        )}

        {/* Graph Container */}
        <div className="flex-1 min-h-0 w-full bg-background relative">
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
