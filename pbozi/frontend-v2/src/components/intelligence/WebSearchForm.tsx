import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Search, Globe, ShieldAlert } from 'lucide-react';
import { getWebSearchConfig, updateWebSearchConfig } from '../../lib/api';
import { WebSearchConfig } from '../../lib/types';

const WebSearchForm: React.FC = () => {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery<WebSearchConfig>({
    queryKey: ['web-search-config'],
    queryFn: getWebSearchConfig,
  });

  const [formData, setFormData] = React.useState<any>(null);

  React.useEffect(() => {
    if (config) {
      setFormData({
        name: config.name,
        provider: config.provider,
        base_url: config.base_url,
        api_key: '',
        search_type: config.search_type,
        max_results: config.max_results,
        include_domains: config.include_domains?.join(', ') || '',
        exclude_domains: config.exclude_domains?.join(', ') || '',
        is_active: config.is_active,
      });
    }
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: any) => {
      const payload = {
        ...data,
        include_domains: data.include_domains ? data.include_domains.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
        exclude_domains: data.exclude_domains ? data.exclude_domains.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
        max_results: parseInt(data.max_results),
      };
      if (!payload.api_key) delete payload.api_key;
      return updateWebSearchConfig(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['web-search-config'] });
      alert('Web Search configuration updated');
    },
  });

  if (isLoading || !formData) return <div className="p-8 text-center text-muted-foreground">Loading configuration...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Search className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Web Search Configuration</h3>
            <p className="text-sm text-muted-foreground">Configure the global web search provider (Exa.ai)</p>
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-medium ${formData.is_active ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
          {formData.is_active ? 'Enabled' : 'Disabled'}
        </div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-4 bg-muted/30 p-6 rounded-2xl border border-border">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Provider Name</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Provider Type</label>
            <select
              value={formData.provider}
              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="exa">Exa.ai</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">API Base URL</label>
          <input
            type="text"
            value={formData.base_url}
            onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium flex items-center justify-between">
            <span>API Key</span>
            {config?.api_key_set && (
              <span className="text-[10px] text-green-500 flex items-center">
                <ShieldAlert className="w-3 h-3 mr-1" />
                Key is already set
              </span>
            )}
          </label>
          <input
            type="password"
            placeholder={config?.api_key_set ? "••••••••••••••••" : "Enter API key"}
            value={formData.api_key}
            onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Search Type</label>
            <select
              value={formData.search_type}
              onChange={(e) => setFormData({ ...formData, search_type: e.target.value })}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="auto">Auto</option>
              <option value="neural">Neural</option>
              <option value="keyword">Keyword</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Max Results</label>
            <input
              type="number"
              min="1"
              max="10"
              value={formData.max_results}
              onChange={(e) => setFormData({ ...formData, max_results: e.target.value })}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Include Domains (comma-separated)</label>
          <input
            type="text"
            placeholder="e.g. stackoverflow.com, github.com"
            value={formData.include_domains}
            onChange={(e) => setFormData({ ...formData, include_domains: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Exclude Domains (comma-separated)</label>
          <input
            type="text"
            placeholder="e.g. facebook.com, pinterest.com"
            value={formData.exclude_domains}
            onChange={(e) => setFormData({ ...formData, exclude_domains: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="flex items-center space-x-2 pt-2">
          <input
            type="checkbox"
            id="search_active"
            checked={formData.is_active}
            onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
            className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background"
          />
          <label htmlFor="search_active" className="text-sm font-medium">Enable Web Search functionality</label>
        </div>

        <div className="pt-4">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full flex items-center justify-center space-x-2 bg-primary text-primary-foreground py-2.5 rounded-xl font-semibold hover:bg-primary/90 transition-all disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            <span>{mutation.isPending ? 'Saving Changes...' : 'Save Configuration'}</span>
          </button>
        </div>
      </form>

      <div className="p-4 bg-primary/5 rounded-xl border border-primary/10 flex items-start space-x-3">
        <Globe className="w-5 h-5 text-primary mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          Web search allows models to access real-time information from the internet. 
          When enabled and bound to a scope, models can trigger search queries to improve response accuracy.
        </p>
      </div>
    </div>
  );
};

export default WebSearchForm;
