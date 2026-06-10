import React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Server, AlertCircle, RefreshCw, Search, CheckCircle2 } from 'lucide-react';
import { createProvider, discoverProviderModels, updateProvider } from '../../lib/api';
import {
  ImportedProviderModelConfigInput,
  Provider,
  ProviderModelDiscoverResponse,
  ProviderUpsertInput,
} from '../../lib/types';

interface ProviderFormProps {
  isOpen: boolean;
  onClose: () => void;
  provider: Provider | null;
}

interface DiscoveredModelDraft {
  name: string;
  display_name: string;
  pricing_input: string;
  pricing_output: string;
  context_window: string;
  is_active: boolean;
  enabled: boolean;
}

const DEFAULT_CONTEXT_WINDOW = '128000';

const parseErrorMessage = (err: unknown, fallback: string): string => {
  const maybeAxios = err as { response?: { data?: { detail?: string } }; message?: string };
  if (maybeAxios.response?.data?.detail) {
    return maybeAxios.response.data.detail;
  }
  return maybeAxios.message || fallback;
};

const mergeDiscoveredModels = (
  names: string[],
  previous: DiscoveredModelDraft[]
): DiscoveredModelDraft[] => {
  const previousByName = new Map(previous.map((item) => [item.name, item]));
  return names.map((name) => {
    const existing = previousByName.get(name);
    if (existing) {
      return existing;
    }
    return {
      name,
      display_name: name,
      pricing_input: '0',
      pricing_output: '0',
      context_window: DEFAULT_CONTEXT_WINDOW,
      is_active: true,
      enabled: false,
    };
  });
};

const ProviderForm: React.FC<ProviderFormProps> = ({ isOpen, onClose, provider }) => {
  const [name, setName] = React.useState('');
  const [providerKind, setProviderKind] = React.useState<'openai_compatible' | 'codex_subscription'>('openai_compatible');
  const [baseUrl, setBaseUrl] = React.useState('');
  const [apiKey, setApiKey] = React.useState('');
  const [isActive, setIsActive] = React.useState(true);
  const [discoveredModels, setDiscoveredModels] = React.useState<DiscoveredModelDraft[]>([]);
  const [modelSearch, setModelSearch] = React.useState('');
  const [discoveryError, setDiscoveryError] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const lastDiscoveryKeyRef = React.useRef('');

  const queryClient = useQueryClient();

  React.useEffect(() => {
    if (provider) {
      const kind = provider.kind === 'codex_subscription' ? 'codex_subscription' : 'openai_compatible';
      setName(provider.name);
      setProviderKind(kind);
      setBaseUrl(kind === 'codex_subscription' ? provider.base_url || 'codex://subscription' : provider.base_url);
      setApiKey(provider.api_key || '');
      setIsActive(provider.is_active);
    } else {
      setName('');
      setProviderKind('openai_compatible');
      setBaseUrl('');
      setApiKey('');
      setIsActive(true);
    }
    setDiscoveredModels([]);
    setModelSearch('');
    setDiscoveryError(null);
    lastDiscoveryKeyRef.current = '';
    setError(null);
  }, [provider, isOpen]);

  const discoverMutation = useMutation({
    mutationFn: (data: { base_url: string; api_key?: string }) => discoverProviderModels(data),
    onSuccess: (response: ProviderModelDiscoverResponse) => {
      setDiscoveredModels((previous) => mergeDiscoveredModels(response.models, previous));
      setDiscoveryError(null);
    },
    onError: (err: unknown) => {
      setDiscoveryError(parseErrorMessage(err, 'Model discovery failed'));
    },
  });

  const triggerDiscovery = React.useCallback(
    (force = false) => {
      if (providerKind === 'codex_subscription') {
        setDiscoveredModels([]);
        setDiscoveryError(null);
        lastDiscoveryKeyRef.current = '';
        return;
      }

      const trimmedBaseUrl = baseUrl.trim();
      const trimmedApiKey = apiKey.trim();
      if (!trimmedBaseUrl) {
        setDiscoveredModels([]);
        setDiscoveryError(null);
        lastDiscoveryKeyRef.current = '';
        return;
      }

      const discoveryKey = `${trimmedBaseUrl}::${trimmedApiKey}`;
      if (!force && discoveryKey === lastDiscoveryKeyRef.current) {
        return;
      }

      lastDiscoveryKeyRef.current = discoveryKey;
      discoverMutation.mutate({
        base_url: trimmedBaseUrl,
        api_key: trimmedApiKey || undefined,
      });
    },
    [apiKey, baseUrl, discoverMutation, providerKind]
  );

  React.useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (providerKind === 'codex_subscription') {
      setBaseUrl((current) => current || 'codex://subscription');
      setApiKey('');
      setDiscoveredModels([]);
      setDiscoveryError(null);
      return;
    }
    if (!baseUrl.trim()) {
      return;
    }
    const timer = setTimeout(() => {
      triggerDiscovery();
    }, 700);
    return () => clearTimeout(timer);
  }, [apiKey, baseUrl, isOpen, providerKind, triggerDiscovery]);

  const mutation = useMutation({
    mutationFn: (data: ProviderUpsertInput) => {
      if (provider) {
        return updateProvider(provider.id, data);
      }
      return createProvider(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      onClose();
    },
    onError: (err: unknown) => {
      setError(parseErrorMessage(err, 'An error occurred'));
    },
  });

  const updateDiscoveredModel = (nameValue: string, patch: Partial<DiscoveredModelDraft>) => {
    setDiscoveredModels((previous) =>
      previous.map((item) => (item.name === nameValue ? { ...item, ...patch } : item))
    );
  };

  const setDiscoveredModelImportState = (nameValue: string, enabled: boolean) => {
    setDiscoveredModels((previous) =>
      previous.map((item) =>
        item.name === nameValue
          ? { ...item, enabled, is_active: enabled ? true : item.is_active }
          : item
      )
    );
  };

  const toggleDiscoveredModel = (nameValue: string) => {
    setDiscoveredModels((previous) =>
      previous.map((item) =>
        item.name === nameValue
          ? { ...item, enabled: !item.enabled, is_active: !item.enabled ? true : item.is_active }
          : item
      )
    );
  };

  const handleDiscoveredModelRowClick = (event: React.MouseEvent<HTMLTableRowElement>, nameValue: string) => {
    const target = event.target as HTMLElement | null;
    if (target?.closest('input, button, select, textarea, a')) {
      return;
    }
    toggleDiscoveredModel(nameValue);
  };

  const normalizedSearch = modelSearch.trim().toLowerCase();
  const filteredDiscoveredModels = React.useMemo(() => {
    if (!normalizedSearch) {
      return discoveredModels;
    }
    return discoveredModels.filter((item) => {
      const modelName = item.name.toLowerCase();
      const displayName = (item.display_name || '').toLowerCase();
      return modelName.includes(normalizedSearch) || displayName.includes(normalizedSearch);
    });
  }, [discoveredModels, normalizedSearch]);

  const setAllImportState = (enabled: boolean) => {
    setDiscoveredModels((previous) =>
      previous.map((item) => ({ ...item, enabled, is_active: enabled ? true : item.is_active }))
    );
  };

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const selectedModels = providerKind === 'codex_subscription' ? [] : discoveredModels.filter((item) => item.enabled);
    const importedModels: ImportedProviderModelConfigInput[] = [];

    for (const item of selectedModels) {
      const pricingInputValue = Number.parseFloat(item.pricing_input);
      const pricingOutputValue = Number.parseFloat(item.pricing_output);
      const contextWindowValue = Number.parseInt(item.context_window, 10);

      if (!Number.isFinite(pricingInputValue) || pricingInputValue < 0) {
        setError(`Invalid input pricing for model ${item.name}`);
        return;
      }
      if (!Number.isFinite(pricingOutputValue) || pricingOutputValue < 0) {
        setError(`Invalid output pricing for model ${item.name}`);
        return;
      }
      if (!Number.isInteger(contextWindowValue) || contextWindowValue < 1) {
        setError(`Invalid context window for model ${item.name}`);
        return;
      }

      importedModels.push({
        name: item.name,
        display_name: item.display_name.trim() || item.name,
        pricing_input: pricingInputValue,
        pricing_output: pricingOutputValue,
        context_window: contextWindowValue,
        is_active: item.is_active,
      });
    }

    const payload: ProviderUpsertInput = {
      name: name.trim(),
      base_url: providerKind === 'codex_subscription' ? 'codex://subscription' : baseUrl.trim(),
      api_key: providerKind === 'codex_subscription' ? '' : apiKey.trim(),
      kind: providerKind,
      is_active: isActive,
    };

    if (importedModels.length > 0) {
      payload.sync_models = true;
      payload.model_names = importedModels.map((item) => item.name);
      payload.imported_models = importedModels;
      payload.activate_imported_models = false;
    }

    mutation.mutate(payload);
  };

  const selectedCount = discoveredModels.filter((item) => item.enabled).length;
  const isCodexProvider = providerKind === 'codex_subscription';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-4xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Server className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">{provider ? 'Edit Provider' : 'Add Provider'}</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[85vh] overflow-y-auto">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-muted-foreground mb-1">
                Provider Name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="openai, anthropic, ollama..."
                required
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              />
            </div>

            <div>
              <label htmlFor="providerKind" className="block text-sm font-medium text-muted-foreground mb-1">
                Provider Type
              </label>
              <select
                id="providerKind"
                value={providerKind}
                onChange={(e) => setProviderKind(e.target.value as 'openai_compatible' | 'codex_subscription')}
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              >
                <option value="openai_compatible">OpenAI-compatible</option>
                <option value="codex_subscription">Codex subscription</option>
              </select>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex items-end">
              <div className="flex items-center space-x-2">
                <input
                  id="isActive"
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                />
                <label htmlFor="isActive" className="text-sm font-medium text-muted-foreground">
                  Provider Active
                </label>
              </div>
            </div>

            <div>
              <label htmlFor="baseUrl" className="block text-sm font-medium text-muted-foreground mb-1">
                {isCodexProvider ? 'Codex Runtime URL' : 'OpenAI-Compatible Base URL'}
              </label>
              <input
                id="baseUrl"
                type="text"
                value={isCodexProvider ? 'codex://subscription' : baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                disabled={isCodexProvider}
                required
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-70"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="apiKey" className="block text-sm font-medium text-muted-foreground mb-1">
                API Key (optional for open providers)
              </label>
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                disabled={isCodexProvider}
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-70"
              />
            </div>
          </div>

          {!isCodexProvider && (
          <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Detected Models</p>
                <p className="text-xs text-muted-foreground">
                  Auto-fetched from provider `/models`. Configure price and bot availability before save.
                </p>
              </div>
              <button
                type="button"
                onClick={() => triggerDiscovery(true)}
                disabled={discoverMutation.isPending || !baseUrl.trim()}
                className="inline-flex items-center space-x-1 text-xs text-primary disabled:text-muted-foreground"
              >
                <RefreshCw className={`w-3 h-3 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />
                <span>{discoverMutation.isPending ? 'Checking...' : 'Refresh'}</span>
              </button>
            </div>

            {discoveredModels.length > 0 ? (
              <>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{discoveredModels.length} models detected</span>
                  <span>{selectedCount} models selected for import</span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative min-w-[220px] flex-1">
                    <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                      placeholder="Search models..."
                      className="w-full bg-background border border-border rounded-md py-1.5 pl-7 pr-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setAllImportState(true)}
                    disabled={discoveredModels.length === 0}
                    className="px-2.5 py-1.5 rounded-md text-xs font-medium bg-muted text-foreground hover:bg-muted/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    onClick={() => setAllImportState(false)}
                    disabled={discoveredModels.length === 0 || selectedCount === 0}
                    className="px-2.5 py-1.5 rounded-md text-xs font-medium bg-muted text-foreground hover:bg-muted/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Deselect all
                  </button>
                </div>

                <div className="max-h-80 overflow-auto rounded border border-border/80 bg-background">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/40 border-b border-border">
                      <tr>
                        <th className="text-left p-2 font-medium">Import</th>
                        <th className="text-left p-2 font-medium">Model</th>
                        <th className="text-left p-2 font-medium">Display Name</th>
                        <th className="text-left p-2 font-medium">Input $/1M</th>
                        <th className="text-left p-2 font-medium">Output $/1M</th>
                        <th className="text-left p-2 font-medium">Context</th>
                        <th className="text-left p-2 font-medium">Bot Active</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDiscoveredModels.map((model) => (
                        <tr
                          key={model.name}
                          onClick={(event) => handleDiscoveredModelRowClick(event, model.name)}
                          className={`border-b border-border/50 last:border-0 align-top cursor-pointer transition-colors ${
                            model.enabled ? 'bg-primary/5 hover:bg-primary/10' : 'hover:bg-muted/40'
                          }`}
                        >
                          <td className="p-2">
                            <button
                              type="button"
                              onClick={() => setDiscoveredModelImportState(model.name, !model.enabled)}
                              aria-pressed={model.enabled}
                              className={`inline-flex min-w-[84px] items-center justify-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
                                model.enabled
                                  ? 'border-primary/40 bg-primary text-primary-foreground'
                                  : 'border-border bg-muted text-muted-foreground hover:text-foreground'
                              }`}
                            >
                              {model.enabled && <CheckCircle2 className="h-3 w-3" />}
                              <span>{model.enabled ? 'Selected' : 'Select'}</span>
                            </button>
                          </td>
                          <td className="p-2">
                            <code className={`text-[11px] ${model.enabled ? 'text-primary' : 'text-muted-foreground'}`}>
                              {model.name}
                            </code>
                          </td>
                          <td className="p-2">
                            <input
                              type="text"
                              value={model.display_name}
                              onChange={(e) => updateDiscoveredModel(model.name, { display_name: e.target.value })}
                              className="w-36 bg-muted border border-border rounded py-1 px-2"
                              disabled={!model.enabled}
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              step="0.000001"
                              min="0"
                              value={model.pricing_input}
                              onChange={(e) => updateDiscoveredModel(model.name, { pricing_input: e.target.value })}
                              className="w-24 bg-muted border border-border rounded py-1 px-2"
                              disabled={!model.enabled}
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              step="0.000001"
                              min="0"
                              value={model.pricing_output}
                              onChange={(e) => updateDiscoveredModel(model.name, { pricing_output: e.target.value })}
                              className="w-24 bg-muted border border-border rounded py-1 px-2"
                              disabled={!model.enabled}
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              min="1"
                              value={model.context_window}
                              onChange={(e) => updateDiscoveredModel(model.name, { context_window: e.target.value })}
                              className="w-24 bg-muted border border-border rounded py-1 px-2"
                              disabled={!model.enabled}
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="checkbox"
                              checked={model.is_active}
                              onChange={(e) => updateDiscoveredModel(model.name, { is_active: e.target.checked })}
                              className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                              disabled={!model.enabled}
                            />
                          </td>
                        </tr>
                      ))}
                      {filteredDiscoveredModels.length === 0 && (
                        <tr>
                          <td colSpan={7} className="p-3 text-center text-muted-foreground">
                            No models match your search.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                {discoverMutation.isPending
                  ? 'Loading model list from provider...'
                  : 'Enter base URL to auto-load models. Add API key if provider requires authentication.'}
              </p>
            )}

            {discoveryError && <p className="text-xs text-destructive">{discoveryError}</p>}
          </div>
          )}

          {error && (
            <div className="p-3 bg-destructive/10 text-destructive text-xs rounded-lg flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex space-x-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-lg text-sm font-medium bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex-1 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving...' : provider ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ProviderForm;
