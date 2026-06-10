import React from 'react';
import { Server, Package, Settings, MessageSquare, DollarSign } from 'lucide-react';
import ProviderList from '../components/config/ProviderList';
import ModelList from '../components/config/ModelList';
import StarterCreditForm from '../components/config/StarterCreditForm';
import SystemPromptEditor from '../components/config/SystemPromptEditor';
import { SubscriptionList } from '../components/config/SubscriptionList';

const Configuration: React.FC = () => {
  const [activeTab, setActiveTab] = React.useState<'general' | 'providers' | 'models' | 'prompts' | 'subscriptions'>('general');

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Configuration</h1>
          <p className="text-muted-foreground">Manage system settings.</p>
        </div>
      </div>

      <div className="flex items-center space-x-1 p-1 bg-muted/50 rounded-xl w-fit overflow-x-auto max-w-full">
        <button
          onClick={() => setActiveTab('general')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'general'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
          }`}
        >
          <Settings className="w-4 h-4" />
          <span>General</span>
        </button>
        <button
          onClick={() => setActiveTab('prompts')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'prompts'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>System Prompt</span>
        </button>
        <button
          onClick={() => setActiveTab('providers')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'providers'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
          }`}
        >
          <Server className="w-4 h-4" />
          <span>Providers</span>
        </button>
        <button
          onClick={() => setActiveTab('models')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'models'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
          }`}
        >
          <Package className="w-4 h-4" />
          <span>Models</span>
        </button>
        <button
          onClick={() => setActiveTab('subscriptions')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'subscriptions'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
          }`}
        >
          <DollarSign className="w-4 h-4" />
          <span>اشتراک و نرخ ارز</span>
        </button>
        </div>

      <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
        {activeTab === 'general' && <StarterCreditForm />}
        {activeTab === 'prompts' && <SystemPromptEditor />}
        {activeTab === 'providers' && <ProviderList />}
        {activeTab === 'models' && <ModelList />}
        {activeTab === 'subscriptions' && <SubscriptionList />}
      </div>
    </div>
  );
};

export default Configuration;
