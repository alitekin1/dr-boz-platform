import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Mic, Save, ShieldAlert } from 'lucide-react';
import { getTranscriptionConfig, updateTranscriptionConfig } from '../../lib/api';
import { TranscriptionConfig } from '../../lib/types';

const TranscriptionForm: React.FC = () => {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery<TranscriptionConfig>({
    queryKey: ['transcription-config'],
    queryFn: getTranscriptionConfig,
  });

  const [formData, setFormData] = React.useState<any>(null);

  React.useEffect(() => {
    if (config) {
      setFormData({
        name: config.name,
        provider: config.provider,
        model: config.model,
        base_url: config.base_url,
        api_key: '',
        pricing_input: config.pricing_input,
        pricing_output: config.pricing_output,
        is_active: config.is_active,
      });
    }
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: any) => {
      const payload = {
        ...data,
        pricing_input: parseFloat(data.pricing_input),
        pricing_output: parseFloat(data.pricing_output),
      };
      if (!payload.api_key) delete payload.api_key;
      return updateTranscriptionConfig(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcription-config'] });
      alert('Transcription configuration updated');
    },
  });

  if (isLoading || !formData) return <div className="p-8 text-center text-muted-foreground">Loading configuration...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Mic className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Voice Transcription</h3>
            <p className="text-sm text-muted-foreground">Configure Gemini model, billing rate, and credentials for Telegram voice-to-text</p>
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-medium ${formData.is_active ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
          {formData.is_active ? 'Enabled' : 'Disabled'}
        </div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-4 bg-muted/30 p-6 rounded-2xl border border-border">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Config Name</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Provider</label>
            <select
              value={formData.provider}
              onChange={(e) => {
                const provider = e.target.value;
                if (provider === 'openrouter') {
                  setFormData({
                    ...formData,
                    provider,
                    model: 'google/chirp-3',
                    base_url: 'https://openrouter.ai/api/v1',
                  });
                  return;
                }
                setFormData({
                  ...formData,
                  provider,
                  model: 'gemini-1.5-flash',
                  base_url: 'https://generativelanguage.googleapis.com/v1beta',
                });
              }}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="google">Google Gemini</option>
              <option value="openrouter">OpenRouter (Chirp 3)</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Model ID</label>
          <input
            type="text"
            value={formData.model}
            onChange={(e) => setFormData({ ...formData, model: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
            placeholder="gemini-3.1-flash-lite-preview"
          />
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
            <label className="text-sm font-medium">Input Pricing (USD / 1M tokens)</label>
            <div className="relative">
              <span className="absolute left-3 top-2 text-muted-foreground text-sm">$</span>
              <input
                type="number"
                min="0"
                step="0.000001"
                value={formData.pricing_input}
                onChange={(e) => setFormData({ ...formData, pricing_input: e.target.value })}
                className="w-full bg-background border border-border rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Output Pricing (USD / 1M tokens)</label>
            <div className="relative">
              <span className="absolute left-3 top-2 text-muted-foreground text-sm">$</span>
              <input
                type="number"
                min="0"
                step="0.000001"
                value={formData.pricing_output}
                onChange={(e) => setFormData({ ...formData, pricing_output: e.target.value })}
                className="w-full bg-background border border-border rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2 pt-2">
          <input
            type="checkbox"
            id="transcription_active"
            checked={formData.is_active}
            onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
            className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background"
          />
          <label htmlFor="transcription_active" className="text-sm font-medium">Enable voice transcription in Telegram bot</label>
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
        <Mic className="w-5 h-5 text-primary mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          Pricing values are used for credit estimation and charging after transcription usage is collected from the provider response.
        </p>
      </div>
    </div>
  );
};

export default TranscriptionForm;
