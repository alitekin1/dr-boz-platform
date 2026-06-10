import React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, CreditCard, AlertCircle } from 'lucide-react';
import { adjustUserCredit } from '../../lib/api';
import { User } from '../../lib/types';

interface CreditAdjustmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: User | null;
}

const CreditAdjustmentModal: React.FC<CreditAdjustmentModalProps> = ({ isOpen, onClose, user }) => {
  const [amount, setAmount] = React.useState<string>('');
  const [direction, setDirection] = React.useState<'credit' | 'debit'>('credit');
  const [reason, setReason] = React.useState<string>('');
  const [error, setError] = React.useState<string | null>(null);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => {
      if (!user) throw new Error('No user selected');
      const numAmount = parseFloat(amount);
      if (isNaN(numAmount) || numAmount <= 0) throw new Error('Invalid amount');
      return adjustUserCredit(user.id, numAmount, direction, reason);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      onClose();
      // Reset form
      setAmount('');
      setDirection('credit');
      setReason('');
      setError(null);
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    },
  });

  if (!isOpen || !user) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  };

  const displayName = user.preferred_name || user.first_name || user.username || `User ${user.id}`;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <CreditCard className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Adjust Credits</h2>
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
            <p className="text-xs text-muted-foreground mt-1">Current balance: ${user.credit_balance_usd?.toFixed(2) ?? '0.00'}</p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setDirection('credit')}
              className={`py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                direction === 'credit' 
                ? 'bg-green-500/10 text-green-600 border border-green-500/20 shadow-sm' 
                : 'bg-muted text-muted-foreground hover:bg-muted/80 border border-transparent'
              }`}
            >
              Add Credit
            </button>
            <button
              type="button"
              onClick={() => setDirection('debit')}
              className={`py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                direction === 'debit' 
                ? 'bg-red-500/10 text-red-600 border border-red-500/20 shadow-sm' 
                : 'bg-muted text-muted-foreground hover:bg-muted/80 border border-transparent'
              }`}
            >
              Subtract Debit
            </button>
          </div>

          <div>
            <label htmlFor="amount" className="block text-sm font-medium text-muted-foreground mb-1">
              Amount (Toman)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">T</span>
              <input
                id="amount"
                type="number"
                step="1"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
                required
                className="w-full bg-muted border border-border rounded-lg py-2 pl-7 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              />
            </div>
          </div>

          <div>
            <label htmlFor="reason" className="block text-sm font-medium text-muted-foreground mb-1">
              Reason
            </label>
            <textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Manual refund, Promotional credit..."
              required
              rows={3}
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all resize-none"
            />
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
              {mutation.isPending ? 'Processing...' : 'Confirm Adjustment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreditAdjustmentModal;
