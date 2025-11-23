import { useState, useEffect } from "react";
import { ChevronDown, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface HeaderProps {
  onConnectDatabase: () => void;
  onUploadSchema: () => void;
}

const Header = ({ onConnectDatabase, onUploadSchema }: HeaderProps) => {
  const [githubStars, setGithubStars] = useState<string>('-');

  useEffect(() => {
    const controller = new AbortController();
    
    fetch('https://api.github.com/repos/FalkorDB/QueryWeaver', {
      signal: controller.signal,
    })
      .then(response => {
        if (!response.ok) {
          throw new Error(`GitHub API responded with status ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        if (typeof data.stargazers_count === "number") {
          setGithubStars(data.stargazers_count.toLocaleString());
        }
      })
      .catch(error => {
        if (error.name !== 'AbortError') {
          console.warn('Failed to fetch GitHub stars:', error);
        }
      });
    
    return () => controller.abort();
  }, []);

  return (
    <div className="flex items-center justify-between p-6 border-b border-border">
      <div className="flex items-center space-x-4">
        {/* Database Selector */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="min-w-[150px] justify-between">
              Select Database
              <ChevronDown className="w-4 h-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[200px]">
            <DropdownMenuItem disabled className="text-muted-foreground">
              No databases connected
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Upload Schema */}
        <div className="relative">
          <Button 
            variant="outline" 
            className="min-w-[140px] justify-between opacity-60 cursor-not-allowed" 
            disabled
            title="Upload schema feature coming soon"
            onClick={(e) => e.preventDefault()}
          >
            Upload Schema
            <ChevronDown className="w-4 h-4 opacity-50" />
          </Button>
        </div>

        {/* Connect Database Button */}
        <Button onClick={onConnectDatabase} className="bg-primary hover:bg-primary-dark">
          Connect Database
        </Button>
      </div>

      {/* GitHub Stars Link */}
      <a 
        href="https://github.com/FalkorDB/QueryWeaver" 
        target="_blank" 
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors text-gray-300 hover:text-white"
        title="View QueryWeaver on GitHub"
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
    </div>
  );
};

export default Header;