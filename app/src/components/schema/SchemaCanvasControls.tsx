import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, RefObject } from 'react';
import type {
  FalkorDBCanvas,
  HierarchyDirection,
  LayoutMode,
  RadialDirection,
} from '@falkordb/canvas';
import {
  ChevronDown,
  Circle,
  Pause,
  Pin,
  PinOff,
  Play,
  Search,
  Shrink,
  Telescope,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const LAYOUTS: { value: LayoutMode; label: string }[] = [
  { value: 'force', label: 'Force' },
  { value: 'tree', label: 'Tree' },
  { value: 'radial', label: 'Radial' },
];

const HIERARCHY_DIRECTIONS: { value: HierarchyDirection; label: string }[] = [
  { value: 'td', label: 'Top → Down' },
  { value: 'bu', label: 'Bottom → Up' },
  { value: 'lr', label: 'Left → Right' },
  { value: 'rl', label: 'Right → Left' },
];

const RADIAL_DIRECTIONS: { value: RadialDirection; label: string }[] = [
  { value: 'out', label: 'Outward' },
  { value: 'in', label: 'Inward' },
];

const MAX_SUGGESTIONS = 8;

const getDefaultDirection = (mode: LayoutMode) => {
  if (mode === 'tree') return 'td';
  if (mode === 'radial') return 'out';
  return '';
};

export interface SchemaTableOption {
  id: number;
  name: string;
  columns: string[];
}

interface SchemaCanvasControlsProps {
  canvasRef: RefObject<FalkorDBCanvas | null>;
  tables: SchemaTableOption[];
  disabled?: boolean;
  focusMode: boolean;
  onFocusModeChange: (enabled: boolean) => void;
  selectedTableId: number | null;
  onSelectTable: (tableId: number | null) => void;
  /** Frames the matching tables (all of them when no predicate is given). */
  onFrameNodes: (match?: (nodeId: number) => boolean) => void;
  /**
   * Re-frames the current view once the new layout has settled. The canvas runs
   * its own centre-based fit after a layout change, which clips tall cards and
   * discards any highlight framing.
   */
  onLayoutChanged: () => void;
}

const SchemaCanvasControls = ({
  canvasRef,
  tables,
  disabled = false,
  focusMode,
  onFocusModeChange,
  selectedTableId,
  onSelectTable,
  onFrameNodes,
  onLayoutChanged,
}: SchemaCanvasControlsProps) => {
  const [layout, setLayout] = useState<LayoutMode>('force');
  const [direction, setDirection] = useState<string>('');
  const [animation, setAnimation] = useState(true);
  const [pinned, setPinned] = useState(false);
  const [search, setSearch] = useState('');
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(0);

  // Remembers the last direction picked per layout so switching back restores it.
  const directionsRef = useRef<Record<string, string>>({ tree: 'td', radial: 'out' });

  // A new schema invalidates the search term and its suggestions.
  useEffect(() => {
    setSearch('');
    setSuggestionsOpen(false);
    setActiveSuggestion(0);
  }, [tables]);

  const suggestions = useMemo(() => {
    const term = search.trim().toLowerCase();

    if (!term) return [];

    return tables
      .filter(
        (table) =>
          table.name.toLowerCase().includes(term) ||
          table.columns.some((column) => column.toLowerCase().includes(term))
      )
      .slice(0, MAX_SUGGESTIONS);
  }, [tables, search]);

  const focusTable = useCallback(
    (table: SchemaTableOption) => {
      onSelectTable(table.id);
      setSearch(table.name);
      setSuggestionsOpen(false);
      onFrameNodes((nodeId) => nodeId === table.id);
    },
    [onFrameNodes, onSelectTable]
  );

  const clearSearch = useCallback(() => {
    setSearch('');
    setSuggestionsOpen(false);
    onSelectTable(null);
  }, [onSelectTable]);

  const handleSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setSuggestionsOpen(false);
      return;
    }

    if (suggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSuggestionsOpen(true);
      setActiveSuggestion((index) => (index + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSuggestionsOpen(true);
      setActiveSuggestion((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      focusTable(suggestions[Math.min(activeSuggestion, suggestions.length - 1)]);
    }
  };

  const handleZoom = (factor: number) => {
    const canvas = canvasRef.current;

    if (!canvas) return;

    if (selectedTableId !== null) {
      // Canvas node ids may be normalised to strings, so compare loosely.
      const node = canvas
        .getGraphData()
        ?.nodes.find((n) => String(n.id) === String(selectedTableId));

      if (node) {
        canvas.centerAt(node.x ?? 0, node.y ?? 0, 300);
      }
    }

    canvas.zoom(canvas.getZoom() * factor);
  };

  const handleCenter = () => {
    onFrameNodes();
  };

  const applyDirection = (mode: LayoutMode, value: string) => {
    if (mode === 'tree') {
      canvasRef.current?.setLayoutOptions({ tree: { direction: value as HierarchyDirection } });
    } else if (mode === 'radial') {
      canvasRef.current?.setLayoutOptions({ radial: { direction: value as RadialDirection } });
    }
  };

  const handleLayoutChange = (value: string, directionOverride?: string) => {
    const mode = value as LayoutMode;
    const dir =
      mode === 'force'
        ? ''
        : (directionOverride ?? (directionsRef.current[mode] || getDefaultDirection(mode)));

    if (mode !== 'force') {
      directionsRef.current = { ...directionsRef.current, [mode]: dir };
    }

    // Direction options must be applied before setLayout so the layout engine uses them.
    applyDirection(mode, dir);
    canvasRef.current?.setLayout(mode);

    setLayout(mode);
    setDirection(dir);
    // Tree and radial layouts are deterministic, so the canvas pins their nodes.
    const nextPinned = mode !== 'force';
    setPinned(nextPinned);
    canvasRef.current?.setPinOnDragEnd(nextPinned);

    if (nextPinned) {
      setAnimation(false);
      canvasRef.current?.setAnimation(false);
    }

    onLayoutChanged();
  };

  const handleDirectionChange = (value: string, targetLayout: LayoutMode) => {
    directionsRef.current = { ...directionsRef.current, [targetLayout]: value };
    setDirection(value);
    applyDirection(targetLayout, value);
    onLayoutChanged();
  };

  const handleAnimationToggle = (checked: boolean) => {
    setAnimation(checked);
    canvasRef.current?.setAnimation(checked);
  };

  const handleFocusToggle = (checked: boolean) => {
    onFocusModeChange(checked);
  };

  const handlePinToggle = () => {
    const next = !pinned;
    setPinned(next);
    canvasRef.current?.setPinOnDragEnd(next);

    if (next) {
      setAnimation(false);
      canvasRef.current?.setAnimation(false);
    }
  };

  const animationDisabled = disabled || pinned || layout !== 'force';

  return (
    <div
      data-testid="schema-canvas-controls"
      className="flex flex-wrap items-center gap-2 p-2 border-b border-border"
    >
      {/* Search */}
      <div className="relative flex-1 min-w-[140px]">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          data-testid="schema-search"
          value={search}
          disabled={disabled}
          placeholder="Search tables or columns"
          aria-label="Search tables or columns"
          className="h-8 pl-7 pr-7 text-xs"
          onChange={(e) => {
            setSearch(e.target.value);
            setSuggestionsOpen(true);
            setActiveSuggestion(0);
          }}
          onFocus={() => setSuggestionsOpen(true)}
          onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 120)}
          onKeyDown={handleSearchKeyDown}
        />
        {search && (
          <button
            type="button"
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            onClick={clearSearch}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        {suggestionsOpen && suggestions.length > 0 && (
          <ul
            data-testid="schema-search-suggestions"
            className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-md border border-border bg-popover shadow-md"
          >
            {suggestions.map((table, index) => (
              <li key={table.id}>
                <button
                  type="button"
                  className={`w-full px-2 py-1.5 text-left text-xs hover:bg-accent ${index === activeSuggestion ? 'bg-accent' : ''}`}
                  onMouseEnter={() => setActiveSuggestion(index)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => focusTable(table)}
                >
                  <span className="text-foreground">{table.name}</span>
                  <span className="ml-2 text-muted-foreground">
                    {table.columns.length} column{table.columns.length === 1 ? '' : 's'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Layout */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            data-testid="schema-layout-control"
            aria-label="Select graph layout"
            disabled={disabled}
            className="flex items-center gap-1 h-8 rounded-md border border-border bg-card px-2 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
          >
            {LAYOUTS.find((l) => l.value === layout)?.label}
            <ChevronDown className="h-3 w-3" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuRadioGroup value={layout} onValueChange={handleLayoutChange}>
            <DropdownMenuRadioItem value="force">Force</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger className="pl-8 relative">
              {layout === 'tree' && (
                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                  <Circle className="h-2 w-2 fill-current" />
                </span>
              )}
              Tree
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {HIERARCHY_DIRECTIONS.map((d) => (
                <DropdownMenuItem
                  key={d.value}
                  className={`pl-8 relative ${layout === 'tree' && direction === d.value ? 'bg-accent' : ''}`}
                  onSelect={() => {
                    // Switching layout already applies the picked direction first.
                    if (layout !== 'tree') handleLayoutChange('tree', d.value);
                    else handleDirectionChange(d.value, 'tree');
                  }}
                >
                  {layout === 'tree' && direction === d.value && (
                    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                      <Circle className="h-2 w-2 fill-current" />
                    </span>
                  )}
                  {d.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger className="pl-8 relative">
              {layout === 'radial' && (
                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                  <Circle className="h-2 w-2 fill-current" />
                </span>
              )}
              Radial
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {RADIAL_DIRECTIONS.map((d) => (
                <DropdownMenuItem
                  key={d.value}
                  className={`pl-8 relative ${layout === 'radial' && direction === d.value ? 'bg-accent' : ''}`}
                  onSelect={() => {
                    // Switching layout already applies the picked direction first.
                    if (layout !== 'radial') handleLayoutChange('radial', d.value);
                    else handleDirectionChange(d.value, 'radial');
                  }}
                >
                  {layout === 'radial' && direction === d.value && (
                    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                      <Circle className="h-2 w-2 fill-current" />
                    </span>
                  )}
                  {d.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Animation */}
      <div
        className="flex items-center gap-1.5"
        title={animation ? 'Pause animation' : 'Resume animation'}
      >
        {animation ? (
          <Pause className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <Play className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <Switch
          data-testid="schema-animation-control"
          aria-label={animation ? 'Pause animation' : 'Resume animation'}
          checked={animation}
          disabled={animationDisabled}
          onCheckedChange={handleAnimationToggle}
        />
      </div>

      {/* Focus mode */}
      <div
        className="flex items-center gap-1.5"
        title={focusMode ? 'Disable focus mode' : 'Enable focus mode'}
      >
        <Telescope className="h-3.5 w-3.5 text-muted-foreground" />
        <Switch
          data-testid="schema-focus-control"
          aria-label={focusMode ? 'Disable focus mode' : 'Enable focus mode'}
          checked={focusMode}
          disabled={disabled}
          onCheckedChange={handleFocusToggle}
        />
      </div>

      {/* Pin / zoom */}
      <div className="flex items-center gap-1">
        <Button
          data-testid="schema-pin-control"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={handlePinToggle}
          className="h-8 w-8 p-0 bg-card border-border text-muted-foreground"
          title={pinned ? 'Unpin nodes' : 'Pin nodes on drag'}
        >
          {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
        </Button>
        <Button
          data-testid="schema-zoom-in-control"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => handleZoom(1.1)}
          className="h-8 w-8 p-0 bg-card border-border text-muted-foreground"
          title="Zoom in"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          data-testid="schema-zoom-out-control"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => handleZoom(0.9)}
          className="h-8 w-8 p-0 bg-card border-border text-muted-foreground"
          title="Zoom out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          data-testid="schema-center-control"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={handleCenter}
          className="h-8 w-8 p-0 bg-card border-border text-muted-foreground"
          title="Fit graph to screen"
        >
          <Shrink className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
};

export default SchemaCanvasControls;
