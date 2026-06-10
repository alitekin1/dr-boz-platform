import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Coins, Info } from 'lucide-react';
import { getStarterCreditConfig, updateStarterCreditConfig } from '../../lib/api';
import { StarterCreditConfig } from '../../lib/types';

const StarterCreditForm: React.FC = () => {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery<StarterCreditConfig>({
    queryKey: ['starter-credit-config'],
    queryFn: getStarterCreditConfig,
  });

  const [formData, setFormData] = React.useState<any>(null);

  React.useEffect(() => {
    if (config) {
      setFormData({
        amount_usd: config.amount_usd,
        amount_toman: config.amount_toman,
        welcome_message: config.welcome_message || '',
        is_active: config.is_active,
      });
    }
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: any) => {
      return updateStarterCreditConfig({
        amount_usd: parseFloat(data.amount_usd) || 0,
        amount_toman: parseInt(data.amount_toman) || 0,
        welcome_message: data.welcome_message,
        is_active: data.is_active,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['starter-credit-config'] });
      alert('Starter Credit configuration updated');
    },
  });

  if (isLoading || !formData) return <div className="p-8 text-center text-muted-foreground">Loading configuration...</div>;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Coins className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Starter Credit</h3>
            <p className="text-sm text-muted-foreground">Automatically give free credit to new users upon registration.</p>
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-medium ${formData.is_active ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
          {formData.is_active ? 'Active' : 'Inactive'}
        </div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-4 bg-muted/30 p-6 rounded-2xl border border-border">
        <div className="space-y-2">
          <label className="text-sm font-medium">Starter Amount (USD)</label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={formData.amount_usd}
              onChange={(e) => setFormData({ ...formData, amount_usd: e.target.value })}
              className="w-full bg-background border border-border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="0.00"
            />
          </div>
          <p className="text-[10px] text-muted-foreground">USD credit added to user's wallet. Set to 0 to disable.</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Starter Amount (Toman)</label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">﷼</span>
            <input
              type="number"
              step="1000"
              min="0"
              value={formData.amount_toman}
              onChange={(e) => setFormData({ ...formData, amount_toman: e.target.value })}
              className="w-full bg-background border border-border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="0"
            />
          </div>
          <p className="text-[10px] text-muted-foreground">Toman gift credit for chat usage. This is what users actually spend when chatting. Set to 0 to disable.</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Welcome Message (Persian recommended)</label>
          <textarea
            value={formData.welcome_message}
            onChange={(e) => setFormData({ ...formData, welcome_message: e.target.value })}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            rows={3}
            placeholder="e.g. Welcome gift: {amount} USD has been added to your wallet!"
          />
          <p className="text-[10px] text-muted-foreground">Use <code>{'{amount}'}</code> as a placeholder for the USD amount. This message is shown when onboarding is complete.</p>
        </div>

        <div className="flex items-center space-x-2 pt-2">
          <input
            type="checkbox"
            id="starter_active"
            checked={formData.is_active}
            onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
            className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background"
          />
          <label htmlFor="starter_active" className="text-sm font-medium">Enable automatic starter credit</label>
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
        <Info className="w-5 h-5 text-primary mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          The starter credit is a one-time grant for each new user. Existing users will not be affected when you change this value. 
          Use Toman credit for chat usage (users spend this when chatting). USD credit is stored in the wallet but not used for chat billing.
        </p>
      </div>
    </div>
  );
};

export default StarterCreditForm;
