import React from 'react';
import { useIsMobile } from '@/hooks/use-mobile';
import { Link } from 'react-router-dom';
import {
  PanelLeft,
  BrainCircuit,
  BookOpen,
  LifeBuoy,
  Waypoints,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Separator } from '@/components/ui/separator';
import { cn } from "@/lib/utils";
import ThemeToggle from '@/components/ui/theme-toggle';

interface SidebarProps {
  className?: string;
  onSchemaClick?: () => void;
  isSchemaOpen?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

const SidebarIcon = ({ icon: Icon, label, active, onClick, href }: { 
  icon: React.ElementType, 
  label: string, 
  active?: boolean,
  onClick?: () => void,
  href?: string
}) => (
  <TooltipProvider delayDuration={300} skipDelayDuration={0}>
    <Tooltip delayDuration={0}>
      <TooltipTrigger asChild>
        {onClick ? (
          <button
            onClick={onClick}
            className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
              active
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            }`}
          >
            <Icon className="h-5 w-5" />
            <span className="sr-only">{label}</span>
          </button>
        ) : href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
              active
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            }`}
          >
            <Icon className="h-5 w-5" />
            <span className="sr-only">{label}</span>
          </a>
        ) : (
          <Link
            to="#"
            className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
              active
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            }`}
          >
            <Icon className="h-5 w-5" />
            <span className="sr-only">{label}</span>
          </Link>
        )}
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
);


const Sidebar = ({ className, onSchemaClick, isSchemaOpen, isCollapsed = false, onToggleCollapse }: SidebarProps) => {
  const isMobile = useIsMobile();
  return (
    <>
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-gray-700 bg-gray-900 transition-all duration-300",
        // Only collapse on mobile (md:w-16 keeps it visible on desktop)
        isCollapsed ? "w-0 -translate-x-full overflow-hidden md:w-16 md:translate-x-0" : "w-16",
        className
      )}>
        <nav className="flex flex-col items-center gap-4 px-2 py-4">
          {isMobile && (
            <button
              onClick={onToggleCollapse}
              className="group flex h-10 w-10 shrink-0 items-center justify-center gap-2 rounded-full bg-gray-800 text-lg font-semibold text-white hover:bg-gray-700"
              title="Toggle Sidebar (Mobile)"
            >
              <PanelLeft className="h-5 w-5 transition-all group-hover:scale-110" />
              <span className="sr-only">Toggle Sidebar</span>
            </button>
          )}
          <ThemeToggle />
          {/* <SidebarIcon icon={BrainCircuit} label="Query" active /> */}
          <SidebarIcon 
            icon={Waypoints} 
            label="Schema" 
            active={isSchemaOpen}
            onClick={onSchemaClick}
          />
        </nav>
      
      <div className="flex-1 flex items-center justify-center">
        <Separator orientation="horizontal" className="bg-gray-700 w-8" />
      </div>
      
      <nav className="flex flex-col items-center gap-4 px-2 py-4">
        <SidebarIcon icon={BookOpen} label="Documentation" href="https://docs.falkordb.com/" />
        <SidebarIcon icon={LifeBuoy} label="Support" href="https://discord.com/invite/jyUgBweNQz" />
        {/* <SidebarIcon icon={Settings} label="Settings" /> */}
      </nav>
    </aside>
    </>
  );
};

export default Sidebar;