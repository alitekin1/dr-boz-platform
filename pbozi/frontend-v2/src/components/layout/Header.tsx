import React from 'react';
import { Sun, Moon, Monitor, Menu } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';

export const Header: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <header className="sticky top-0 z-40 flex items-center justify-between h-16 px-4 border-b bg-background/95 backdrop-blur border-border md:px-8">
      <div className="flex items-center">
        <button className="p-2 mr-2 text-muted-foreground md:hidden hover:bg-accent hover:text-accent-foreground rounded-md">
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-semibold text-foreground">Admin Panel</h1>
      </div>

      <div className="flex items-center space-x-2">
        <div className="flex items-center p-1 border rounded-lg bg-muted/50 border-border">
          <button
            onClick={() => setTheme('light')}
            className={`p-1.5 rounded-md transition-all ${theme === 'light' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            title="Light Mode"
          >
            <Sun className="w-4 h-4" />
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={`p-1.5 rounded-md transition-all ${theme === 'dark' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            title="Dark Mode"
          >
            <Moon className="w-4 h-4" />
          </button>
          <button
            onClick={() => setTheme('system')}
            className={`p-1.5 rounded-md transition-all ${theme === 'system' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            title="System Mode"
          >
            <Monitor className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
