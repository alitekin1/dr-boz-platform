import React, { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UserPlansPage from './UserPlansPage';
import UserBillingPage from './UserBillingPage';
import MySubscriptionPage from './MySubscriptionPage';
import { Wallet, Zap, CreditCard, LogOut } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const USER_TELEGRAM_ID_KEY = 'user_telegram_id';

export default function UserPortal() {
  const [telegramUserId, setTelegramUserId] = useState<number | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [activePage, setActivePage] = useState('my-subscription');

  useEffect(() => {
    const saved = localStorage.getItem(USER_TELEGRAM_ID_KEY);
    if (saved) {
      const id = parseInt(saved);
      if (!isNaN(id)) {
        setTelegramUserId(id);
      }
    }
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(inputValue);
    if (!isNaN(id) && id > 0) {
      setTelegramUserId(id);
      localStorage.setItem(USER_TELEGRAM_ID_KEY, String(id));
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(USER_TELEGRAM_ID_KEY);
    setTelegramUserId(null);
    setInputValue('');
  };

  if (!telegramUserId) {
    return (
      <div dir="rtl" className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="w-full max-w-md space-y-8 bg-card p-8 rounded-2xl border border-border shadow-xl">
          <div className="text-center space-y-2">
            <div className="mx-auto w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center text-primary mb-4">
              <Zap className="w-6 h-6" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">دکتر بز</h1>
            <p className="text-muted-foreground">برای مدیریت اشتراک وارد شوید</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-sm text-muted-foreground">شناسه تلگرام</label>
              <input
                type="number"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Telegram User ID"
                className="w-full px-4 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                required
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                این شناسه را می‌توانید از ربات تلگرام دریافت کنید
              </p>
            </div>
            <button
              type="submit"
              className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors"
            >
              ورود
            </button>
          </form>
        </div>
      </div>
    );
  }

  const navItems = [
    { id: 'my-subscription', label: 'اشتراک من', icon: Zap },
    { id: 'plans', label: 'پلن‌ها', icon: CreditCard },
    { id: 'billing', label: 'کیف پول', icon: Wallet },
  ];

  const renderPage = () => {
    switch (activePage) {
      case 'plans':
        return <UserPlansPage telegramUserId={telegramUserId} onNavigate={setActivePage} />;
      case 'billing':
        return <UserBillingPage telegramUserId={telegramUserId} />;
      case 'my-subscription':
      default:
        return <MySubscriptionPage telegramUserId={telegramUserId} onNavigate={setActivePage} />;
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div dir="rtl" className="min-h-screen bg-background">
        <header className="border-b border-border bg-card sticky top-0 z-10">
          <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-primary" />
              <span className="font-semibold">دکتر بز</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground">
                ID: {telegramUserId}
              </span>
              <button
                onClick={handleLogout}
                className="p-2 hover:bg-muted rounded-lg transition-colors"
                title="خروج"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </header>

        <nav className="border-b border-border bg-card">
          <div className="max-w-4xl mx-auto px-4">
            <div className="flex gap-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActivePage(item.id)}
                    className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                      activePage === item.id
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        </nav>

        <main className="max-w-4xl mx-auto p-4 md:p-8">
          {renderPage()}
        </main>
      </div>
    </QueryClientProvider>
  );
}
