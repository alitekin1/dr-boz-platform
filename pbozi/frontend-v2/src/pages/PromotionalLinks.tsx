import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPromotionalLinks,
  createPromotionalLink,
  updatePromotionalLink,
  deactivatePromotionalLink,
  getPromotionalLinkStats,
  getSubscriptionPlans,
} from '../lib/api';
import {
  PromotionalLink,
  PromotionalLinkCreate,
  PromotionalLinkStats,
  SubscriptionPlan,
} from '../lib/types';
import {
  Link as LinkIcon,
  Plus,
  RefreshCcw,
  Copy,
  BarChart3,
  TrendingUp,
  Users,
  X,
  Edit,
  Trash2,
  Gift,
  Clock,
  Percent,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from 'lucide-react';

const OFFER_TYPE_LABELS: Record<string, string> = {
  credit_grant: 'اعتبار هدیه',
  free_subscription: 'اشتراک رایگان',
  topup_discount: 'تخفیف شارژ',
};

const OFFER_TYPE_ICONS: Record<string, React.ElementType> = {
  credit_grant: Gift,
  free_subscription: Clock,
  topup_discount: Percent,
};

const toTehranTime = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('fa-IR', { timeZone: 'Asia/Tehran' });
};

const PromotionalLinks = () => {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingLink, setEditingLink] = useState<PromotionalLink | null>(null);
  const [statsLink, setStatsLink] = useState<PromotionalLink | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const { data: links, isLoading } = useQuery<PromotionalLink[]>({
    queryKey: ['promotional-links'],
    queryFn: getPromotionalLinks,
  });

  const createMutation = useMutation({
    mutationFn: createPromotionalLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotional-links'] });
      setShowCreateModal(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<PromotionalLinkCreate> }) =>
      updatePromotionalLink(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotional-links'] });
      setEditingLink(null);
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: deactivatePromotionalLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotional-links'] });
    },
  });

  const handleCreate = (data: PromotionalLinkCreate) => {
    createMutation.mutate(data);
  };

  const handleUpdate = (id: number, data: Partial<PromotionalLinkCreate>) => {
    updateMutation.mutate({ id, data });
  };

  const handleDeactivate = (id: number) => {
    if (confirm('Are you sure you want to deactivate this link?')) {
      deactivateMutation.mutate(id);
    }
  };

  const copyToClipboard = (code: string) => {
    const botUsername = 'drbozai_bot';
    const link = `https://ble.ir/${botUsername}?start=offer_${code}`;

    const textArea = document.createElement('textarea');
    textArea.value = link;
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch (err) {
      console.error('Copy failed', err);
    }
    document.body.removeChild(textArea);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Promotional Links</h1>
          <p className="text-muted-foreground">
            Create and track promotional links for Telegram bot users.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['promotional-links'] })}
            className="flex items-center px-4 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
          >
            <RefreshCcw className="w-4 h-4 mr-2" />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4 mr-2" />
            Create Link
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
          <table className="w-full">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Title</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Clicks</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Redemptions</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Rate</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">Status</th>
                <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {links?.map((link) => {
                const rate = link.total_clicks > 0
                  ? ((link.total_redemptions / link.total_clicks) * 100).toFixed(1)
                  : '0.0';
                const Icon = OFFER_TYPE_ICONS[link.offer_type] || Gift;
                return (
                  <tr key={link.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium">{link.title}</div>
                      {link.description && (
                        <div className="text-sm text-muted-foreground truncate max-w-xs">
                          {link.description}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Icon className="w-4 h-4 text-primary" />
                        <span>{OFFER_TYPE_LABELS[link.offer_type]}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm">{link.total_clicks}</td>
                    <td className="px-4 py-3 text-sm">{link.total_redemptions}</td>
                    <td className="px-4 py-3 text-sm">{rate}%</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                          link.is_active
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                      >
                        {link.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => copyToClipboard(link.code)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                          title="Copy link"
                        >
                          {copiedCode === link.code ? (
                            <CheckCircle2 className="w-4 h-4 text-green-600" />
                          ) : (
                            <Copy className="w-4 h-4" />
                          )}
                        </button>
                        <button
                          onClick={() => setStatsLink(link)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                          title="View stats"
                        >
                          <BarChart3 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setEditingLink(link)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                          title="Edit"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeactivate(link.id)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors text-destructive"
                          title="Deactivate"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {links?.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                    No promotional links yet. Create one to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <CreateEditModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
          isPending={createMutation.isPending}
        />
      )}

      {editingLink && (
        <CreateEditModal
          link={editingLink}
          onClose={() => setEditingLink(null)}
          onSubmit={(data) => handleUpdate(editingLink.id, data)}
          isPending={updateMutation.isPending}
        />
      )}

      {statsLink && (
        <StatsModal link={statsLink} onClose={() => setStatsLink(null)} />
      )}
    </div>
  );
};

interface CreateEditModalProps {
  link?: PromotionalLink | null;
  onClose: () => void;
  onSubmit: (data: PromotionalLinkCreate) => void;
  isPending: boolean;
}

const CreateEditModal: React.FC<CreateEditModalProps> = ({ link, onClose, onSubmit, isPending }) => {
  const [title, setTitle] = useState(link?.title || '');
  const [description, setDescription] = useState(link?.description || '');
  const [offerType, setOfferType] = useState<PromotionalLinkCreate['offer_type']>(
    link?.offer_type || 'credit_grant'
  );
  const [offerValueToman, setOfferValueToman] = useState(link?.offer_value_toman || 0);
  const [offerDurationHours, setOfferDurationHours] = useState(link?.offer_duration_hours || 48);
  const [planId, setPlanId] = useState<number | ''>(link?.plan_id || '');
  const [discountPercent, setDiscountPercent] = useState(link?.discount_percent || 0);
  const [maxRedemptions, setMaxRedemptions] = useState<number | ''>(link?.max_redemptions || '');
  const [expiresAt, setExpiresAt] = useState(link?.expires_at ? link.expires_at.slice(0, 16) : '');

  const { data: plans } = useQuery<SubscriptionPlan[]>({
    queryKey: ['subscription-plans'],
    queryFn: getSubscriptionPlans,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      description: description || null,
      offer_type: offerType,
      offer_value_toman: offerType === 'credit_grant' ? offerValueToman : 0,
      offer_duration_hours: offerType === 'free_subscription' ? offerDurationHours : 0,
      plan_id: offerType === 'free_subscription' ? (planId === '' ? null : Number(planId)) : null,
      discount_percent: offerType === 'topup_discount' ? discountPercent : 0,
      max_redemptions: maxRedemptions === '' ? null : Number(maxRedemptions),
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg mx-4 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold">{link ? 'Edit Link' : 'Create Promotional Link'}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-muted transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. 100K Credit Giveaway"
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the offer..."
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
              rows={2}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Offer Type</label>
            <select
              value={offerType}
              onChange={(e) => setOfferType(e.target.value as PromotionalLinkCreate['offer_type'])}
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="credit_grant">اعتبار هدیه (Credit Grant)</option>
              <option value="free_subscription">اشتراک رایگان (Free Subscription)</option>
              <option value="topup_discount">تخفیف شارژ (Topup Discount)</option>
            </select>
          </div>

          {offerType === 'credit_grant' && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Credit Amount (Toman)</label>
              <input
                type="number"
                value={offerValueToman}
                onChange={(e) => setOfferValueToman(Number(e.target.value))}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                min={1}
                required
              />
            </div>
          )}

          {offerType === 'free_subscription' && (
            <>
              <div className="space-y-2">
                <label className="text-sm font-medium">Subscription Plan</label>
                <select
                  value={planId}
                  onChange={(e) => setPlanId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  required
                >
                  <option value="">Select a plan...</option>
                  {plans?.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Duration (hours)</label>
                <input
                  type="number"
                  value={offerDurationHours}
                  onChange={(e) => setOfferDurationHours(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  min={1}
                  required
                />
              </div>
            </>
          )}

          {offerType === 'topup_discount' && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Discount Percentage</label>
              <input
                type="number"
                value={discountPercent}
                onChange={(e) => setDiscountPercent(Number(e.target.value))}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                min={1}
                max={100}
                required
              />
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium">Max Redemptions (optional)</label>
            <input
              type="number"
              value={maxRedemptions}
              onChange={(e) => setMaxRedemptions(e.target.value === '' ? '' : Number(e.target.value))}
              placeholder="Leave empty for unlimited"
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              min={1}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Expiration (optional)</label>
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !title || (offerType === 'free_subscription' && planId === '')}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isPending ? 'Saving...' : link ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

interface StatsModalProps {
  link: PromotionalLink;
  onClose: () => void;
}

const StatsModal: React.FC<StatsModalProps> = ({ link, onClose }) => {
  const { data: stats, isLoading } = useQuery<PromotionalLinkStats>({
    queryKey: ['promotional-link-stats', link.id],
    queryFn: () => getPromotionalLinkStats(link.id),
  });

  const botUsername = 'drbozai_bot';
  const fullLink = `https://ble.ir/${botUsername}?start=offer_${link.code}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl mx-4 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold">Stats: {link.title}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-muted transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-6">
          <div className="bg-muted/50 rounded-lg p-3">
            <div className="text-sm text-muted-foreground mb-1">Link URL</div>
            <div className="font-mono text-sm break-all">{fullLink}</div>
          </div>

          {link.expires_at && (
            <div className="bg-muted/50 rounded-lg p-3">
              <div className="text-sm text-muted-foreground mb-1">انقضا (Tehran time)</div>
              <div className="font-semibold">{toTehranTime(link.expires_at)}</div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={Users} label="Total Clicks" value={stats?.total_clicks ?? 0} />
            <StatCard icon={CheckCircle2} label="Redemptions" value={stats?.total_redemptions ?? 0} color="green" />
            <StatCard icon={XCircle} label="Failed" value={stats?.total_failed ?? 0} color="red" />
            <StatCard icon={AlertCircle} label="Already Used" value={stats?.total_already_used ?? 0} color="yellow" />
          </div>

          <div className="bg-primary/10 rounded-xl p-4 flex items-center gap-4">
            <TrendingUp className="w-8 h-8 text-primary" />
            <div>
              <div className="text-sm text-muted-foreground">Conversion Rate</div>
              <div className="text-2xl font-bold">{stats?.conversion_rate ?? 0}%</div>
            </div>
          </div>

          {isLoading ? (
            <p className="text-muted-foreground text-center py-4">Loading click details...</p>
          ) : stats?.clicks && stats.clicks.length > 0 ? (
            <div>
              <h3 className="text-sm font-medium mb-2">Recent Clicks</h3>
              <div className="bg-muted/30 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">User ID</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Clicked</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {stats.clicks.slice(0, 20).map((click) => (
                      <tr key={click.id}>
                        <td className="px-3 py-2 font-mono">{click.user_id}</td>
                        <td className="px-3 py-2">{toTehranTime(click.clicked_at)}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                              click.redemption_status === 'redeemed'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : click.redemption_status === 'failed'
                                ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                                : click.redemption_status === 'already_used'
                                ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                                : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                            }`}
                          >
                            {click.redemption_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-4">No clicks yet.</p>
          )}
        </div>
      </div>
    </div>
  );
};

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: number;
  color?: string;
}

const StatCard: React.FC<StatCardProps> = ({ icon: Icon, label, value, color }) => {
  const colorClasses: Record<string, string> = {
    green: 'text-green-600 dark:text-green-400',
    red: 'text-red-600 dark:text-red-400',
    yellow: 'text-yellow-600 dark:text-yellow-400',
  };
  const iconColor = color ? colorClasses[color] : 'text-primary';

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <Icon className={`w-5 h-5 mb-2 ${iconColor}`} />
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm text-muted-foreground">{label}</div>
    </div>
  );
};

export default PromotionalLinks;
