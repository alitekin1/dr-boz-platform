import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from './context/ThemeContext';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import Dashboard from './pages/Dashboard';
import UsersPage from './pages/Users';
import Configuration from './pages/Configuration';
import Messaging from './pages/Messaging';
import Referrals from './pages/Referrals';
import Financial from './pages/Financial';
import AdminPaymentsPage from './components/payments/AdminPaymentsPage';
import PromotionalLinks from './pages/PromotionalLinks';
import Backups from './pages/Backups';
import UserPortal from './pages/user/UserPortal';
import { ADMIN_PASSWORD_KEY } from './lib/config';
import { verifyAdminPassword } from './lib/api';
import { Key, Lock } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  const [activeSection, setActiveSection] = useState('Dashboard');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [isUserPortal, setIsUserPortal] = useState(false);

  useEffect(() => {
    const path = window.location.pathname;
    if (path === '/user' || path === '/user/') {
      setIsUserPortal(true);
      return;
    }

    const savedPassword = localStorage.getItem(ADMIN_PASSWORD_KEY);
    if (savedPassword) {
      verifyAdminPassword(savedPassword)
        .then(() => setIsAuthenticated(true))
        .catch(() => {
          localStorage.removeItem(ADMIN_PASSWORD_KEY);
          setIsAuthenticated(false);
        });
    }
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedPassword = password.trim();
    if (!trimmedPassword) return;

    setIsSubmittingLogin(true);
    setAuthError('');

    try {
      await verifyAdminPassword(trimmedPassword);
      localStorage.setItem(ADMIN_PASSWORD_KEY, trimmedPassword);
      setIsAuthenticated(true);
      setPassword('');
    } catch {
      setAuthError('Incorrect admin password.');
    } finally {
      setIsSubmittingLogin(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(ADMIN_PASSWORD_KEY);
    setIsAuthenticated(false);
    setPassword('');
    setAuthError('');
  };

  const renderContent = () => {
    switch (activeSection) {
      case 'Dashboard':
        return <Dashboard />;
      case 'Messaging':
        return <Messaging />;
      case 'Referrals':
        return <Referrals />;
      case 'Financial':
        return <Financial />;
      case 'Payments':
        return <AdminPaymentsPage />;
      case 'User Management':
        return <UsersPage />;
      case 'Configuration':
        return <Configuration />;
      case 'Promotional Links':
        return <PromotionalLinks />;
      case 'Backups':
        return <Backups />;
      default:
        return (
          <div className="flex items-center justify-center h-64">
            <p className="text-muted-foreground">Section "{activeSection}" is under construction.</p>
          </div>
        );
    }
  };

  if (isUserPortal) {
    return <UserPortal />;
  }

  if (!isAuthenticated) {
    return (
      <ThemeProvider>
        <div dir="ltr" className="min-h-screen flex items-center justify-center bg-background p-4">
          <div className="w-full max-w-md space-y-8 bg-card p-8 rounded-2xl border border-border shadow-xl">
            <div className="text-center space-y-2">
              <div className="mx-auto w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center text-primary mb-4">
                <Lock className="w-6 h-6" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">BozGPT Admin Settings</h1>
              <p className="text-muted-foreground">Enter admin password to access the panel.</p>
            </div>
            
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="password"
                    placeholder="Admin Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    required
                    autoFocus
                  />
                </div>
                {authError && (
                  <p className="text-sm text-destructive">{authError}</p>
                )}
              </div>
              <button
                type="submit"
                disabled={isSubmittingLogin}
                className="w-full py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors shadow-lg shadow-primary/20"
              >
                {isSubmittingLogin ? 'Verifying...' : 'Login to Dashboard'}
              </button>
            </form>
            
            <div className="pt-4 text-center">
              <p className="text-xs text-muted-foreground italic">
                Password will be securely stored in your browser session.
              </p>
            </div>
          </div>
        </div>
      </ThemeProvider>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <div dir="ltr" className="min-h-screen bg-background text-foreground">
          <Sidebar activeSection={activeSection} onSectionChange={setActiveSection} onLogout={handleLogout} />
          
          <div className="md:pl-64 flex flex-col min-h-screen">
            <Header />
            
            <main className="flex-1 p-4 md:p-8">
              <div className="max-w-7xl mx-auto">
                {renderContent()}
              </div>
            </main>
          </div>
        </div>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
