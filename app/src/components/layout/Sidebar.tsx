import React from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  BookOpen,
  LifeBuoy,
  Waypoints,
  Sliders,
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
  onSettingsClick?: () => void;
}

const SidebarIcon = ({ icon: Icon, label, active, onClick, href, testId }: {
  icon: React.ElementType,
  label: string,
  active?: boolean,
  onClick?: () => void,
  href?: string,
  testId?: string
}) => {
  // An icon with neither a handler nor a destination used to fall through to a
  // `<Link to="#">`, which looks clickable but does nothing (issue #239).
  // Render nothing instead, so a button only exists once it is wired up.
  if (!onClick && !href) return null;

  const iconClasses = `flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
    active
      ? 'bg-purple-600 text-white'
      : 'text-muted-foreground hover:bg-card hover:text-foreground'
  }`;

  return (
    <TooltipProvider delayDuration={300} skipDelayDuration={0}>
      <Tooltip delayDuration={0}>
        <TooltipTrigger asChild>
          {onClick ? (
            <button
              onClick={onClick}
              className={iconClasses}
              data-testid={testId}
            >
              <Icon className="h-5 w-5" />
              <span className="sr-only">{label}</span>
            </button>
          ) : (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className={iconClasses}
              data-testid={testId}
            >
              <Icon className="h-5 w-5" />
              <span className="sr-only">{label}</span>
            </a>
          )}
        </TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};


const Sidebar = ({ className, onSchemaClick, isSchemaOpen, isCollapsed = false, onSettingsClick }: SidebarProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const isSettingsOpen = location.pathname === '/settings';
  
  const handleSettingsClick = () => {
    if (onSettingsClick) {
      onSettingsClick();
    }
    if (isSettingsOpen) {
      navigate('/');
    } else {
      navigate('/settings');
    }
  };
  
  return (
    <>
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-background transition-all duration-300",
        // Only collapse on mobile (md:w-16 keeps it visible on desktop)
        isCollapsed ? "w-0 -translate-x-full overflow-hidden md:w-16 md:translate-x-0" : "w-16",
        className
      )}>
        <nav className="flex flex-col items-center gap-4 px-2 py-4">
          <ThemeToggle />
          <SidebarIcon
            icon={Waypoints}
            label="Schema"
            active={isSchemaOpen}
            onClick={onSchemaClick}
            testId="schema-button"
          />
        </nav>
      
      <div className="flex-1 flex items-center justify-center">
        <Separator orientation="horizontal" className="bg-border w-8" />
      </div>
      
      <nav className="flex flex-col items-center gap-4 px-2 py-4">
        <SidebarIcon icon={Sliders} label="Settings" active={isSettingsOpen} onClick={handleSettingsClick} testId="settings-button" />
        <SidebarIcon icon={BookOpen} label="Documentation" href="https://docs.falkordb.com/" testId="documentation-link" />
        <SidebarIcon icon={LifeBuoy} label="Support" href="https://discord.com/invite/jyUgBweNQz" testId="support-link" />
      </nav>
    </aside>
    </>
  );
};

export default Sidebar;