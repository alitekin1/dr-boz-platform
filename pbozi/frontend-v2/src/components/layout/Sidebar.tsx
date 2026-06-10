import React from 'react';
import { 
  LayoutDashboard, 
  Settings, 
  Users, 
  ChevronRight,
  LogOut,
  MessageSquare,
  Link as LinkIcon,
  DollarSign,
  CreditCard,
  Archive,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SidebarItemProps {
  icon: React.ElementType;
  label: string;
  active?: boolean;
  onClick?: () => void;
}

const SidebarItem: React.FC<SidebarItemProps> = ({ icon: Icon, label, active, onClick }) => {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center w-full px-4 py-3 mb-1 text-sm font-medium transition-colors rounded-lg group",
        active 
          ? "bg-primary text-primary-foreground shadow-sm" 
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
    >
      <Icon className={cn("w-5 h-5 mr-3 shrink-0", active ? "text-primary-foreground" : "text-muted-foreground group-hover:text-accent-foreground")} />
      <span>{label}</span>
      {active && <ChevronRight className="w-4 h-4 ml-auto" />}
    </button>
  );
};

interface SidebarProps {
  activeSection: string;
  onSectionChange: (section: string) => void;
  onLogout: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeSection, onSectionChange, onLogout }) => {
  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', id: 'Dashboard' },
    { icon: Users, label: 'User Management', id: 'User Management' },
    { icon: DollarSign, label: 'Financial', id: 'Financial' },
    { icon: CreditCard, label: 'Payments', id: 'Payments' },
    { icon: LinkIcon, label: 'Referrals', id: 'Referrals' },
    { icon: LinkIcon, label: 'Promotional Links', id: 'Promotional Links' },
    { icon: MessageSquare, label: 'Messaging', id: 'Messaging' },
    { icon: Settings, label: 'Configuration', id: 'Configuration' },
    { icon: Archive, label: 'Backups', id: 'Backups' },
  ];

  return (
    <aside dir="ltr" className="fixed inset-y-0 left-0 z-50 w-64 transition-transform -translate-x-full bg-background border-r border-border md:translate-x-0">
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-center h-16 border-b border-border">
          <span className="text-xl font-bold tracking-tight text-foreground">BozGPT Admin</span>
        </div>
        
        <nav className="flex-1 px-3 py-4 overflow-y-auto">
          {navItems.map((item) => (
            <SidebarItem
              key={item.id}
              icon={item.icon}
              label={item.label}
              active={activeSection === item.id}
              onClick={() => onSectionChange(item.id)}
            />
          ))}
        </nav>
        
        <div className="p-4 border-t border-border space-y-2">
          <div className="flex items-center px-2 py-3 rounded-lg bg-muted/50">
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center mr-3">
              <Users className="w-4 h-4 text-primary" />
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-medium text-foreground truncate">Admin User</p>
              <p className="text-xs text-muted-foreground truncate">BozGPT Control Panel</p>
            </div>
          </div>
          
          <button
            onClick={onLogout}
            className="flex items-center w-full px-4 py-2 text-xs font-medium text-red-500 hover:bg-red-500/10 rounded-lg transition-colors group"
          >
            <LogOut className="w-4 h-4 mr-3" />
            <span>Logout</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
