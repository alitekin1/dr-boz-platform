import React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Gift, X } from 'lucide-react';
import { redeemPromoCodeForUser } from '../../lib/api';

interface UserLite {
  id: number;
  telegram_user_id?: number | null;
  first_name?: string | null;
  username?: string | null;
  preferred_name?: string | null;
}

interface PromoCodeRedeemModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: UserLite | null;
}

const PromoCodeRedeemModal: React.FC<PromoCodeRedeemModalProps> = ({ isOpen, onClose, user }) => {
  const [code, setCode] = React.useState('');
  const [currency, setCurrency] = React.useState<'USD' | 'TOMAN'>('USD');
  const [chargeAmount, setChargeAmount] = React.useState('0');
  const [error, setError] = React.useState<string | null>(null);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => {
      if (!user) throw new Error('No user selected');
      if (!code.trim()) {
        throw new Error('Code is required');
      }
      return redeemPromoCodeForUser(user.id, {
        code: code.trim(),
        charge_amount: currency === 'USD' ? parseFloat(chargeAmount) : 0,
        charge_amount_toman: currency === 'TOMAN' ? parseInt(chargeAmount, 10) : 0,
        currency,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['promo-codes'] });
      queryClient.invalidateQueries({ queryKey: ['promo-code-redemptions'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setCode('');
      setChargeAmount('0');
      setCurrency('USD');
      setError(null);
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'Failed to redeem promo code');
    },
  });

  if (!isOpen || !user) return null;

  const displayName = user.preferred_name || user.first_name || user.username || `User ${user.id}`;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Gift className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Apply Gift / Discount Code</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <p className="text-sm text-muted-foreground mb-1">User</p>
            <p className="font-medium">{displayName} <span className="text-xs text-muted-foreground font-normal">({user.telegram_user_id || 'No TG ID'})</span></p>
          </div>

          <div>
            <label htmlFor="promo-code" className="block text-sm font-medium text-muted-foreground mb-1">
              Promo Code
            </label>
            <input
              id="promo-code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="SPRING2026"
              required
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm tracking-wide uppercase focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>

          <div>
            <label htmlFor="currency" className="block text-sm font-medium text-muted-foreground mb-1">
              Charge Currency
            </label>
            <select
              id="currency"
              value={currency}
              onChange={(e) => {
                setCurrency(e.target.value as 'USD' | 'TOMAN');
                setChargeAmount('0');
              }}
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            >
              <option value="USD">USD ($)</option>
              <option value="TOMAN">Toman (تومان)</option>
            </select>
          </div>

          <div>
            <label htmlFor="charge-amount" className="block text-sm font-medium text-muted-foreground mb-1">
              Charge Amount ({currency === 'TOMAN' ? 'تومان' : 'USD'})
            </label>
            <div className="relative">
              {currency === 'USD' && (
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
              )}
              <input
                id="charge-amount"
                type="number"
                min="0"
                step={currency === 'TOMAN' ? '1000' : '0.01'}
                value={chargeAmount}
                onChange={(e) => setChargeAmount(e.target.value)}
                className={`w-full bg-muted border border-border rounded-lg py-2 ${currency === 'USD' ? 'pl-7' : 'pl-3'} pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all`}
              />
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {currency === 'TOMAN'
                ? 'Set to 0 for pure gift codes. Enter the Toman amount paid for charge bonuses.'
                : 'Set to 0 for pure gift codes. For charge bonuses, enter the amount paid.'}
            </p>
          </div>

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
              {mutation.isPending ? 'Applying...' : 'Apply Code'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PromoCodeRedeemModal;
