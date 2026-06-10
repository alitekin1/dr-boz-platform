import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Plus, CheckCircle2, XCircle, Database, Save, ShieldAlert } from 'lucide-react';
import { getEmbeddingConfigs, createEmbeddingConfig, updateEmbeddingConfig } from '../../lib/api';
import { EmbeddingConfig } from '../../lib/types';

const EmbeddingForm: React.FC = () => {
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [selectedConfig, setSelectedConfig] = React.useState<EmbeddingConfig | null>(null);
  
  const queryClient = useQueryClient();

  const { data: configs, isLoading, error } = useQuery<EmbeddingConfig[]>({
    queryKey: ['embedding-configs'],
    queryFn: getEmbeddingConfigs,
  });

  const handleEdit = (config: EmbeddingConfig) => {
    setSelectedConfig(config);
    setIsFormOpen(true);
  };

  const handleAdd = () => {
    setSelectedConfig(null);
    setIsFormOpen(true);
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading embedding configurations...</div>;
  if (error) return <div className="p-8 text-center text-destructive">Error loading embedding configurations</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Database className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Embedding Models</h3>
            <p className="text-sm text-muted-foreground">Configure models for RAG and vector searches</p>
          </div>
        </div>
        <button
          onClick={handleAdd}
          className="flex items-center space-x-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Add Config</span>
        </button>
      </div>

      <div className="grid gap-4">
        {configs?.map((config) => (
          <div
            key={config.id}
            className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl hover:border-primary/30 transition-all group"
          >
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold">{config.name}</span>
                <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded uppercase font-bold tracking-wider text-muted-foreground">
                  {config.provider}
                </span>
                {config.is_active ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              <p className="text-xs text-muted-foreground font-mono">{config.model}</p>
              {config.base_url && <p className="text-[10px] text-muted-foreground/60 truncate max-w-xs">{config.base_url}</p>}
            </div>

            <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => handleEdit(config)}
                className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                title="Edit"
              >
                <Edit2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {configs?.length === 0 && (
          <div className="p-8 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No embedding models configured. Add your first one for RAG support.
          </div>
        )}
      </div>

      {isFormOpen && (
        <EmbeddingModal
          config={selectedConfig}
          onClose={() => setIsFormOpen(false)}
        />
      )}
    </div>
  );
};

interface EmbeddingModalProps {
  config: EmbeddingConfig | null;
  onClose: () => void;
}

const EmbeddingModal: React.FC<EmbeddingModalProps> = ({ config, onClose }) => {
  const queryClient = useQueryClient();
  const [formData, setFormData] = React.useState({
    name: config?.name || '',
    provider: config?.provider || 'openai',
    model: config?.model || '',
    api_key: '',
    base_url: config?.base_url || '',
    pricing_input: config?.pricing_input || 0,
    is_active: config?.is_active ?? true,
  });

  const mutation = useMutation({
    mutationFn: (data: any) => {
      const payload = { ...data };
      if (!payload.api_key) delete payload.api_key;
      if (config) {
        return updateEmbeddingConfig(config.id, payload);
      }
      return createEmbeddingConfig(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['embedding-configs'] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(formData);
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border w-full max-w-lg rounded-2xl shadow-xl overflow-hidden">
        <div className="p-6 border-b border-border flex items-center justify-between bg-muted/30">
          <h3 className="text-xl font-bold">{config ? 'Edit Embedding' : 'Add Embedding'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg transition-colors">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Config Name</label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="e.g. Default Embeddings"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Provider</label>
              <select
                value={formData.provider}
                onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="google">Google</option>
                <option value="openai">OpenAI</option>
                <option value="openrouter">OpenRouter</option>
                <option value="anthropic">Anthropic</option>
                <option value="voyage">Voyage AI</option>
                <option value="cohere">Cohere</option>
                <option value="mistral">Mistral</option>
                <option value="local">Local/Ollama</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Model ID</label>
            <input
              type="text"
              required
              value={formData.model}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="e.g. text-embedding-3-small"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Base URL (Optional)</label>
            <input
              type="text"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center justify-between">
              <span>API Key</span>
              {config && (
                <span className="text-[10px] text-green-500 flex items-center">
                  <ShieldAlert className="w-3 h-3 mr-1" />
                  Key is set
                </span>
              )}
            </label>
            <input
              type="password"
              placeholder={config ? "••••••••••••••••" : "Enter API key"}
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Pricing (per 1M tokens)</label>
            <div className="relative">
              <span className="absolute left-3 top-2 text-muted-foreground text-sm">$</span>
              <input
                type="number"
                step="0.000001"
                value={formData.pricing_input}
                onChange={(e) => setFormData({ ...formData, pricing_input: parseFloat(e.target.value) })}
                className="w-full bg-muted/50 border border-border rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
          </div>

          <div className="flex items-center space-x-2 pt-2">
            <input
              type="checkbox"
              id="emb_active"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-muted/50"
            />
            <label htmlFor="emb_active" className="text-sm font-medium">Active</label>
          </div>

          <div className="flex items-center justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex items-center space-x-2 bg-primary text-primary-foreground px-6 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              <span>{mutation.isPending ? 'Saving...' : (config ? 'Update' : 'Create')}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EmbeddingForm;
