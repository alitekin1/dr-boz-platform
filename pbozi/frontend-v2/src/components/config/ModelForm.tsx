import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { X, Package, AlertCircle, CheckCircle2 } from 'lucide-react';
import { createModel, updateModel, getProviders, getModels, getSubscriptionConfig } from '../../lib/api';
import { Model, Provider, SubscriptionConfig } from '../../lib/types';

interface ModelFormProps {
  isOpen: boolean;
  onClose: () => void;
  model: Model | null; // null for create, non-null for update
}

const parseCapabilityFlag = (value: unknown): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return ['true', '1', 'yes', 'on'].includes(normalized);
  }
  return false;
};

const modelTypeOf = (model: Model | null): 'normal' | 'auto_router' => {
  return model?.capabilities?.model_type === 'auto_router' ? 'auto_router' : 'normal';
};

const numericIdOrNull = (value: string): number | null => {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

const TomanPreview: React.FC<{ usd: number; rate: number; label: string }> = ({ usd, rate, label }) => {
  const base = Math.round(usd * rate);
  const rounded = Math.round(base / 1000) * 1000;
  const suggestedUsd = rate > 0 ? parseFloat((rounded / rate).toFixed(6)) : 0;
  return (
    <div>
      <div className="text-muted-foreground">{label}:</div>
      <div className="font-bold text-foreground">{base.toLocaleString('fa-IR')} تومان</div>
      {rounded !== base && rounded > 0 && (
        <div className="text-[10px] text-green-600 mt-0.5">
          پیشنهاد رند: {rounded.toLocaleString('fa-IR')} تومان
          {suggestedUsd > 0 && (
            <span className="block text-[10px] text-muted-foreground">≈ ${suggestedUsd}/1M</span>
          )}
        </div>
      )}
    </div>
  );
};

const CODEX_MODEL_PRESETS = [
  {
    name: 'gpt-5.5',
    display_name: 'GPT-5.5 Codex',
    context_window: '272000',
    pricing_input: '0',
    pricing_output: '0',
  },
  {
    name: 'gpt-5.4',
    display_name: 'GPT-5.4 Codex',
    context_window: '272000',
    pricing_input: '0',
    pricing_output: '0',
  },
  {
    name: 'gpt-5.4-mini',
    display_name: 'GPT-5.4 Mini Codex',
    context_window: '272000',
    pricing_input: '0',
    pricing_output: '0',
  },
  {
    name: 'gpt-5.3-codex',
    display_name: 'GPT-5.3 Codex',
    context_window: '272000',
    pricing_input: '0',
    pricing_output: '0',
  },
  {
    name: 'gpt-5.3-codex-spark',
    display_name: 'GPT-5.3 Codex Spark',
    context_window: '272000',
    pricing_input: '0',
    pricing_output: '0',
  },
];

const ModelForm: React.FC<ModelFormProps> = ({ isOpen, onClose, model }) => {
  const [name, setName] = React.useState('');
  const [displayName, setDisplayName] = React.useState('');
  const [providerId, setProviderId] = React.useState<number>(0);
  const [pricingInput, setPricingInput] = React.useState('0');
  const [pricingOutput, setPricingOutput] = React.useState('0');
  const [contextWindow, setContextWindow] = React.useState('4096');
  const [isActive, setIsActive] = React.useState(true);
  const [isDefault, setIsDefault] = React.useState(false);
  const [supportsImageInput, setSupportsImageInput] = React.useState(false);
  const [modelType, setModelType] = React.useState<'normal' | 'auto_router'>('normal');
  const [routerModelId, setRouterModelId] = React.useState('');
  const [easyModelId, setEasyModelId] = React.useState('');
  const [mediumModelId, setMediumModelId] = React.useState('');
  const [hardModelId, setHardModelId] = React.useState('');
  const [visionModelId, setVisionModelId] = React.useState('');
  const [researchModelId, setResearchModelId] = React.useState('');
  const [fallbackModelId, setFallbackModelId] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: getProviders,
  });

  const { data: models } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: getModels,
  });

  const { data: subscriptionConfig } = useQuery<SubscriptionConfig>({
    queryKey: ['subscriptionConfig'],
    queryFn: getSubscriptionConfig,
  });

  const normalModelOptions = React.useMemo(() => {
    return (models || []).filter((item) => item.id !== model?.id && item.is_active && modelTypeOf(item) === 'normal');
  }, [models, model?.id]);

  const selectedProvider = React.useMemo(() => {
    return providers?.find((provider) => provider.id === providerId) || null;
  }, [providers, providerId]);

  const isCodexProvider = selectedProvider?.kind === 'codex_subscription';

  const applyCodexPreset = (modelName: string) => {
    const preset = CODEX_MODEL_PRESETS.find((item) => item.name === modelName);
    if (!preset) return;
    setName(preset.name);
    setDisplayName(preset.display_name);
    setContextWindow(preset.context_window);
    setPricingInput(preset.pricing_input);
    setPricingOutput(preset.pricing_output);
    setSupportsImageInput(false);
  };

  React.useEffect(() => {
    if (model) {
      const autoRouter = model.capabilities?.auto_router || {};
      setName(model.name);
      setDisplayName(model.display_name || '');
      setProviderId(model.provider_id || 0);
      setPricingInput(model.pricing_input.toString());
      setPricingOutput(model.pricing_output.toString());
      setContextWindow(model.context_window.toString());
      setIsActive(model.is_active);
      setIsDefault(model.is_default);
      setSupportsImageInput(parseCapabilityFlag(model.capabilities?.image_input));
      setModelType(modelTypeOf(model));
      setRouterModelId(autoRouter.router_model_id?.toString() || '');
      setEasyModelId(autoRouter.easy_model_id?.toString() || '');
      setMediumModelId(autoRouter.medium_model_id?.toString() || '');
      setHardModelId(autoRouter.hard_model_id?.toString() || '');
      setVisionModelId(autoRouter.vision_model_id?.toString() || '');
      setResearchModelId(autoRouter.research_model_id?.toString() || '');
      setFallbackModelId(autoRouter.fallback_model_id?.toString() || '');
    } else {
      setName('');
      setDisplayName('');
      setProviderId(providers?.[0]?.id || 0);
      setPricingInput('0');
      setPricingOutput('0');
      setContextWindow('4096');
      setIsActive(true);
      setIsDefault(false);
      setSupportsImageInput(false);
      setModelType('normal');
      setRouterModelId('');
      setEasyModelId('');
      setMediumModelId('');
      setHardModelId('');
      setVisionModelId('');
      setResearchModelId('');
      setFallbackModelId('');
    }
    setError(null);
  }, [model, isOpen, providers]);

  const mutation = useMutation({
    mutationFn: (data: any) => {
      if (model) {
        return updateModel(model.id, data);
      } else {
        return createModel(data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    },
  });

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (modelType === 'normal' && providerId === 0) {
      setError('Please select a provider');
      return;
    }
    if (modelType === 'auto_router' && (!routerModelId || !fallbackModelId)) {
      setError('Auto Router requires a router model and fallback model');
      return;
    }
    if (isDefault && !isActive) {
      setError('A default model must be active');
      return;
    }
    setError(null);
    const baseCapabilities = model?.capabilities && typeof model.capabilities === 'object'
      ? model.capabilities
      : {};
    const capabilities = modelType === 'auto_router'
      ? {
          ...baseCapabilities,
          model_type: 'auto_router',
          image_input: false,
          auto_router: {
            router_model_id: numericIdOrNull(routerModelId),
            easy_model_id: numericIdOrNull(easyModelId),
            medium_model_id: numericIdOrNull(mediumModelId),
            hard_model_id: numericIdOrNull(hardModelId),
            vision_model_id: numericIdOrNull(visionModelId),
            research_model_id: numericIdOrNull(researchModelId),
            fallback_model_id: numericIdOrNull(fallbackModelId),
          },
        }
      : {
          ...baseCapabilities,
          model_type: 'normal',
          image_input: supportsImageInput,
        };
    mutation.mutate({
      name,
      display_name: displayName || null,
      provider_id: modelType === 'auto_router' ? null : providerId,
      pricing_input: parseFloat(pricingInput),
      pricing_output: parseFloat(pricingOutput),
      context_window: parseInt(contextWindow),
      is_active: isActive,
      is_default: isDefault,
      capabilities,
    });
  };

  const renderModelSelect = (
    id: string,
    label: string,
    value: string,
    onChange: (value: string) => void,
    required = false
  ) => (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-muted-foreground mb-1">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
      >
        <option value="">Select model</option>
        {normalModelOptions.map((item) => (
          <option key={item.id} value={item.id}>
            {item.display_name || item.name}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Package className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">{model ? 'Edit Model' : 'Add Model'}</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[80vh] overflow-y-auto">
          <div>
            <label htmlFor="modelType" className="block text-sm font-medium text-muted-foreground mb-1">
              Model Type
            </label>
            <select
              id="modelType"
              value={modelType}
              onChange={(e) => setModelType(e.target.value as 'normal' | 'auto_router')}
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            >
              <option value="normal">Normal</option>
              <option value="auto_router">Auto Router</option>
            </select>
          </div>

          {modelType === 'normal' && (
            <div>
              <label htmlFor="provider" className="block text-sm font-medium text-muted-foreground mb-1">
                Provider
              </label>
              <select
                id="provider"
                value={providerId}
                onChange={(e) => setProviderId(parseInt(e.target.value))}
                required
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              >
                <option value={0} disabled>Select a provider</option>
                {providers?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.kind === 'codex_subscription' ? ' · Codex' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {modelType === 'normal' && isCodexProvider && (
            <div className="space-y-2">
              <label htmlFor="codexModelPreset" className="block text-sm font-medium text-muted-foreground mb-1">
                Codex Model
              </label>
              <select
                id="codexModelPreset"
                value={CODEX_MODEL_PRESETS.some((item) => item.name === name) ? name : ''}
                onChange={(e) => applyCodexPreset(e.target.value)}
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              >
                <option value="">Select a Codex model</option>
                {CODEX_MODEL_PRESETS.map((preset) => (
                  <option key={preset.name} value={preset.name}>
                    {preset.display_name} ({preset.name})
                  </option>
                ))}
              </select>
              <div className="grid gap-2 sm:grid-cols-2">
                {CODEX_MODEL_PRESETS.map((preset) => {
                  const isSelected = name === preset.name;
                  return (
                    <button
                      key={preset.name}
                      type="button"
                      onClick={() => applyCodexPreset(preset.name)}
                      aria-pressed={isSelected}
                      className={`flex min-h-12 items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                        isSelected
                          ? 'border-primary/50 bg-primary text-primary-foreground'
                          : 'border-border bg-muted/60 text-foreground hover:bg-muted'
                      }`}
                    >
                      <span>
                        <span className="block font-medium">{preset.display_name}</span>
                        <span className={isSelected ? 'text-primary-foreground/75' : 'text-muted-foreground'}>
                          {preset.name}
                        </span>
                      </span>
                      {isSelected && <CheckCircle2 className="h-4 w-4 shrink-0" />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <label htmlFor="modelName" className="block text-sm font-medium text-muted-foreground mb-1">
              Model Name (ID)
            </label>
            <input
              id="modelName"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="gpt-4, claude-3-opus..."
              required
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>

          <div>
            <label htmlFor="displayName" className="block text-sm font-medium text-muted-foreground mb-1">
              Display Name (Optional)
            </label>
            <input
              id="displayName"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="GPT-4 Turbo"
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>

          {modelType === 'normal' ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="pricingInput" className="block text-sm font-medium text-muted-foreground mb-1">
                    Pricing Input (USD/1M) — users see Toman
                  </label>
                  <input
                    id="pricingInput"
                    type="number"
                    step="0.000001"
                    value={pricingInput}
                    onChange={(e) => setPricingInput(e.target.value)}
                    required
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                  />
                </div>
                <div>
                  <label htmlFor="pricingOutput" className="block text-sm font-medium text-muted-foreground mb-1">
                    Pricing Output (USD/1M) — users see Toman
                  </label>
                  <input
                    id="pricingOutput"
                    type="number"
                    step="0.000001"
                    value={pricingOutput}
                    onChange={(e) => setPricingOutput(e.target.value)}
                    required
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                  />
                </div>
              </div>

              {subscriptionConfig && (
                <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg space-y-2">
                  <p className="text-xs font-bold text-amber-700">پیش‌نمایش قیمت برای کاربر (نرخ: {Number(subscriptionConfig.usd_to_toman_rate).toLocaleString('fa-IR')} تومان)</p>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <TomanPreview usd={parseFloat(pricingInput || '0')} rate={subscriptionConfig.usd_to_toman_rate} label="ورودی" />
                    <TomanPreview usd={parseFloat(pricingOutput || '0')} rate={subscriptionConfig.usd_to_toman_rate} label="خروجی" />
                  </div>
                </div>
              )}

              <div>
                <label htmlFor="contextWindow" className="block text-sm font-medium text-muted-foreground mb-1">
                  Context Window (tokens)
                </label>
                <input
                  id="contextWindow"
                  type="number"
                  value={contextWindow}
                  onChange={(e) => setContextWindow(e.target.value)}
                  required
                  className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                />
              </div>
            </>
          ) : (
            <div className="grid grid-cols-1 gap-3 p-3 bg-muted/30 border border-border rounded-lg">
              {renderModelSelect('routerModel', 'Router Model', routerModelId, setRouterModelId, true)}
              {renderModelSelect('easyModel', 'Easy Model', easyModelId, setEasyModelId)}
              {renderModelSelect('mediumModel', 'Medium Model', mediumModelId, setMediumModelId)}
              {renderModelSelect('hardModel', 'Hard Model', hardModelId, setHardModelId)}
              {renderModelSelect('visionModel', 'Vision Model', visionModelId, setVisionModelId)}
              {renderModelSelect('researchModel', 'Research Model', researchModelId, setResearchModelId)}
              {renderModelSelect('fallbackModel', 'Fallback Model', fallbackModelId, setFallbackModelId, true)}
            </div>
          )}

          <div className="flex items-center space-x-2">
            <input
              id="modelIsActive"
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
            />
            <label htmlFor="modelIsActive" className="text-sm font-medium text-muted-foreground">
              Active
            </label>
          </div>

          <div className="flex items-center space-x-2">
            <input
              id="modelIsDefault"
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              disabled={!isActive}
              className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary disabled:opacity-50"
            />
            <label htmlFor="modelIsDefault" className={`text-sm font-medium ${isActive ? 'text-muted-foreground' : 'text-muted-foreground/50'}`}>
              Set as default model
            </label>
          </div>

          {modelType === 'normal' && (
            <div className="flex items-center space-x-2">
              <input
                id="supportsImageInput"
                type="checkbox"
                checked={supportsImageInput}
                onChange={(e) => setSupportsImageInput(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <label htmlFor="supportsImageInput" className="text-sm font-medium text-muted-foreground">
                Supports image input (vision)
              </label>
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
              {mutation.isPending ? 'Saving...' : (model ? 'Update' : 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ModelForm;
