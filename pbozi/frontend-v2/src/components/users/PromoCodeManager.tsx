import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit2, Gift, Plus, Power, PowerOff } from 'lucide-react';
import { createPromoCode, getPromoCodes, updatePromoCode } from '../../lib/api';
import { PromoCode, PromoCodePayload } from '../../lib/types';

type PromoFormState = {
  code: string;
  description: string;
  bonus_type: 'fixed' | 'percent';
  currency: 'USD' | 'TOMAN';
  bonus_value: string;
  minimum_charge: string;
  max_redemptions_total: string;
  max_redemptions_per_user: string;
  is_active: boolean;
  expires_at: string;
};

const emptyForm: PromoFormState = {
  code: '',
  description: '',
  bonus_type: 'fixed',
  currency: 'USD',
  bonus_value: '',
  minimum_charge: '0',
  max_redemptions_total: '',
  max_redemptions_per_user: '1',
  is_active: true,
  expires_at: '',
};

function toFormState(promoCode: PromoCode): PromoFormState {
  const isToman = promoCode.currency === 'TOMAN';
  return {
    code: promoCode.code,
    description: promoCode.description || '',
    bonus_type: promoCode.bonus_type,
    currency: promoCode.currency,
    bonus_value: isToman ? String(promoCode.bonus_value_toman) : String(promoCode.bonus_value_usd),
    minimum_charge: isToman ? String(promoCode.minimum_charge_toman) : String(promoCode.minimum_charge_usd),
    max_redemptions_total: promoCode.max_redemptions_total != null ? String(promoCode.max_redemptions_total) : '',
    max_redemptions_per_user: String(promoCode.max_redemptions_per_user),
    is_active: promoCode.is_active,
    expires_at: promoCode.expires_at ? new Date(promoCode.expires_at).toISOString().slice(0, 16) : '',
  };
}

function toPayload(state: PromoFormState): PromoCodePayload {
  const bonusValue = parseFloat(state.bonus_value);
  if (Number.isNaN(bonusValue) || bonusValue <= 0) {
    throw new Error('Bonus value must be greater than zero');
  }

  const minCharge = parseFloat(state.minimum_charge);
  if (Number.isNaN(minCharge) || minCharge < 0) {
    throw new Error('Minimum charge must be zero or greater');
  }

  const maxPerUser = parseInt(state.max_redemptions_per_user, 10);
  if (Number.isNaN(maxPerUser) || maxPerUser <= 0) {
    throw new Error('Max redemptions per user must be greater than zero');
  }

  const maxTotal = state.max_redemptions_total.trim()
    ? parseInt(state.max_redemptions_total, 10)
    : null;
  if (maxTotal != null && (Number.isNaN(maxTotal) || maxTotal <= 0)) {
    throw new Error('Max total redemptions must be greater than zero');
  }

  const expiresAt = state.expires_at.trim() ? new Date(state.expires_at).toISOString() : null;

  return {
    code: state.code.trim().toUpperCase(),
    description: state.description.trim() || null,
    bonus_type: state.bonus_type,
    currency: state.currency,
    bonus_value: bonusValue,
    minimum_charge: minCharge,
    max_redemptions_total: maxTotal,
    max_redemptions_per_user: maxPerUser,
    is_active: state.is_active,
    expires_at: expiresAt,
  };
}

const PromoCodeManager: React.FC = () => {
  const queryClient = useQueryClient();
  const [form, setForm] = React.useState<PromoFormState>(emptyForm);
  const [editingCodeId, setEditingCodeId] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const { data: promoCodes = [], isLoading } = useQuery<PromoCode[]>({
    queryKey: ['promo-codes'],
    queryFn: getPromoCodes,
  });

  const createMutation = useMutation({
    mutationFn: (payload: PromoCodePayload) => createPromoCode(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promo-codes'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setForm(emptyForm);
      setError(null);
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'Failed to create promo code');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<PromoCodePayload> }) => updatePromoCode(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promo-codes'] });
      setEditingCodeId(null);
      setForm(emptyForm);
      setError(null);
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'Failed to update promo code');
    },
  });

  const isSaving = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const payload = toPayload(form);
      if (!payload.code) {
        throw new Error('Code is required');
      }
      if (editingCodeId == null) {
        createMutation.mutate(payload);
      } else {
        updateMutation.mutate({ id: editingCodeId, payload });
      }
    } catch (err: any) {
      setError(err.message || 'Invalid form values');
    }
  };

  const startEdit = (promoCode: PromoCode) => {
    setEditingCodeId(promoCode.id);
    setForm(toFormState(promoCode));
    setError(null);
  };

  const cancelEdit = () => {
    setEditingCodeId(null);
    setForm(emptyForm);
    setError(null);
  };

  const toggleActive = (promoCode: PromoCode) => {
    updateMutation.mutate({
      id: promoCode.id,
      payload: { is_active: !promoCode.is_active },
    });
  };

  const currencyLabel = form.currency === 'TOMAN' ? 'تومان' : 'USD';
  const currencySymbol = form.currency === 'TOMAN' ? '' : '$';

  return (
    <div className="space-y-4 border border-border rounded-xl p-4 bg-card/40">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2"><Gift className="w-5 h-5 text-primary" /> Gift / Discount Codes</h3>
          <p className="text-xs text-muted-foreground">Create configurable codes (fixed bonus or % bonus) in USD or Toman.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Code</label>
          <input
            value={form.code}
            onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
            placeholder="BONUS10"
            required
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm tracking-wide uppercase focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Currency</label>
          <select
            value={form.currency}
            onChange={(e) => setForm((prev) => ({ ...prev, currency: e.target.value as 'USD' | 'TOMAN' }))}
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="USD">USD ($)</option>
            <option value="TOMAN">Toman (تومان)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Type</label>
          <select
            value={form.bonus_type}
            onChange={(e) => setForm((prev) => ({ ...prev, bonus_type: e.target.value as 'fixed' | 'percent' }))}
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="fixed">Fixed bonus ({currencyLabel})</option>
            <option value="percent">Percent of charge (%)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Bonus Value</label>
          <div className="relative">
            {form.currency === 'USD' && form.bonus_type === 'fixed' && (
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
            )}
            <input
              type="number"
              min="0"
              step={form.bonus_type === 'percent' ? '1' : form.currency === 'TOMAN' ? '1000' : '0.01'}
              value={form.bonus_value}
              onChange={(e) => setForm((prev) => ({ ...prev, bonus_value: e.target.value }))}
              placeholder={form.bonus_type === 'fixed' ? (form.currency === 'TOMAN' ? '100000' : '2.00') : '20'}
              required
              className={`w-full bg-muted border border-border rounded-lg py-2 ${form.currency === 'USD' && form.bonus_type === 'fixed' ? 'pl-7' : 'pl-3'} pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50`}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Minimum Charge ({currencyLabel})</label>
          <div className="relative">
            {form.currency === 'USD' && (
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
            )}
            <input
              type="number"
              min="0"
              step={form.currency === 'TOMAN' ? '1000' : '0.01'}
              value={form.minimum_charge}
              onChange={(e) => setForm((prev) => ({ ...prev, minimum_charge: e.target.value }))}
              className={`w-full bg-muted border border-border rounded-lg py-2 ${form.currency === 'USD' ? 'pl-7' : 'pl-3'} pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50`}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Max Total Redemptions</label>
          <input
            type="number"
            min="1"
            step="1"
            value={form.max_redemptions_total}
            onChange={(e) => setForm((prev) => ({ ...prev, max_redemptions_total: e.target.value }))}
            placeholder="Unlimited"
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Max Per User</label>
          <input
            type="number"
            min="1"
            step="1"
            value={form.max_redemptions_per_user}
            onChange={(e) => setForm((prev) => ({ ...prev, max_redemptions_per_user: e.target.value }))}
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-xs font-medium text-muted-foreground mb-1">Description</label>
          <input
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
            placeholder={form.currency === 'TOMAN' ? 'e.g. Give 100,000 Toman free credit' : 'e.g. Give $2 extra on $10 top-up'}
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Expires At (optional)</label>
          <input
            type="datetime-local"
            value={form.expires_at}
            onChange={(e) => setForm((prev) => ({ ...prev, expires_at: e.target.value }))}
            className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div className="flex items-end">
          <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))}
            />
            Active
          </label>
        </div>

        {error && (
          <div className="md:col-span-2 p-2 text-xs rounded-lg bg-destructive/10 text-destructive">{error}</div>
        )}

        <div className="md:col-span-2 flex gap-2">
          <button
            type="submit"
            disabled={isSaving}
            className="inline-flex items-center gap-2 px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {editingCodeId == null ? <Plus className="w-4 h-4" /> : <Edit2 className="w-4 h-4" />}
            {isSaving ? 'Saving...' : editingCodeId == null ? 'Create Code' : 'Update Code'}
          </button>
          {editingCodeId != null && (
            <button
              type="button"
              onClick={cancelEdit}
              className="px-3 py-2 rounded-lg text-sm font-medium bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
            >
              Cancel Edit
            </button>
          )}
        </div>
      </form>

      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-muted/60 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Code</th>
              <th className="px-3 py-2 text-left font-medium">Rule</th>
              <th className="px-3 py-2 text-left font-medium">Limits</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">Loading promo codes...</td>
              </tr>
            )}
            {!isLoading && promoCodes.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">No promo codes yet.</td>
              </tr>
            )}
            {promoCodes.map((promoCode) => {
              const isToman = promoCode.currency === 'TOMAN';
              const ruleText = promoCode.bonus_type === 'fixed'
                ? (isToman ? `+${promoCode.bonus_value_toman.toLocaleString()} تومان` : `+$${promoCode.bonus_value_usd.toFixed(2)}`)
                : (isToman ? `+${promoCode.bonus_value_toman.toFixed(2)}% (تومان)` : `+${promoCode.bonus_value_usd.toFixed(2)}%`);
              const minText = isToman
                ? (promoCode.minimum_charge_toman > 0 ? `min ${promoCode.minimum_charge_toman.toLocaleString()} تومان` : 'no min')
                : (promoCode.minimum_charge_usd > 0 ? `min $${promoCode.minimum_charge_usd.toFixed(2)}` : 'no min');
              const currencyBadge = isToman
                ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] bg-blue-100 text-blue-800 ml-1">تومان</span>'
                : '<span class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] bg-gray-100 text-gray-800 ml-1">USD</span>';
              return (
                <tr key={promoCode.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono">{promoCode.code}</td>
                  <td className="px-3 py-2">
                    <span dangerouslySetInnerHTML={{ __html: ruleText }} />
                    <span dangerouslySetInnerHTML={{ __html: currencyBadge }} />
                    <span className="text-muted-foreground"> ({minText})</span>
                  </td>
                  <td className="px-3 py-2">
                    total: {promoCode.max_redemptions_total ?? 'unlimited'} / user: {promoCode.max_redemptions_per_user}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full ${promoCode.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {promoCode.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <button
                      onClick={() => startEdit(promoCode)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border hover:bg-muted"
                      title="Edit"
                    >
                      <Edit2 className="w-3 h-3" />
                      Edit
                    </button>
                    <button
                      onClick={() => toggleActive(promoCode)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border hover:bg-muted"
                      title={promoCode.is_active ? 'Deactivate' : 'Activate'}
                    >
                      {promoCode.is_active ? <PowerOff className="w-3 h-3" /> : <Power className="w-3 h-3" />}
                      {promoCode.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default PromoCodeManager;
