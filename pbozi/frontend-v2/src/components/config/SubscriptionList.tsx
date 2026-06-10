import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, Shield, Settings, X, Save, UserCheck, RotateCw, Pencil, Package } from 'lucide-react';
import { 
  getSubscriptionPlans, 
  createSubscriptionPlan, 
  updateSubscriptionPlan,
  deleteSubscriptionPlan,
  getSubscriptionPlanRules, 
  createSubscriptionPlanRule, 
  deleteSubscriptionPlanRule,
  getModels,
  getTools,
  getSkills,
  getSubscriptionConfig,
  updateSubscriptionConfig,
  getUserSubscriptions,
  cancelUserSubscription,
  reactivateUserSubscription
} from '../../lib/api';
import { AdminUserSubscription, SubscriptionConfig, SubscriptionPlan, SubscriptionPlanRule, Model, Tool, Skill } from '../../lib/types';
import { TrialSettings } from './TrialSettings';

const formatToman = (value: number | undefined | null) => `${Number(value || 0).toLocaleString('fa-IR')} تومان`;
const formatDate = (value: string | undefined | null) => value ? new Date(value).toLocaleString('fa-IR') : '-';

export function SubscriptionList() {
  const [activeTab, setActiveTab] = useState<'plans' | 'config' | 'users' | 'trial'>('plans');
  const [isPlanFormOpen, setIsPlanFormOpen] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [isRuleFormOpen, setIsRuleFormOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<SubscriptionPlan | null>(null);

  const queryClient = useQueryClient();

  const { data: plans, isLoading: plansLoading } = useQuery({
    queryKey: ['subscriptionPlans'],
    queryFn: getSubscriptionPlans,
  });

  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: getModels,
  });

  const { data: tools } = useQuery({
    queryKey: ['tools'],
    queryFn: getTools,
  });

  const { data: skills } = useQuery({
    queryKey: ['skills'],
    queryFn: getSkills,
  });

  const { data: config } = useQuery({
    queryKey: ['subscriptionConfig'],
    queryFn: getSubscriptionConfig,
  });

  const toggleMutation = useMutation({
    mutationFn: (is_enabled: boolean) => updateSubscriptionConfig({ is_enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subscriptionConfig'] })
  });

  const deletePlanMutation = useMutation({
    mutationFn: deleteSubscriptionPlan,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subscriptionPlans'] })
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl">
        <div>
          <h3 className="text-sm font-bold">وضعیت نهایی سیستم اشتراک</h3>
          <p className="text-xs text-muted-foreground">با غیرفعال کردن این گزینه، تمامی بخش‌های مربوط به اشتراک در بات و پنل غیرفعال می‌شوند.</p>
        </div>
        <button
          onClick={() => toggleMutation.mutate(!config?.is_enabled)}
          disabled={toggleMutation.isPending}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            config?.is_enabled 
              ? 'bg-green-500 text-white shadow-lg shadow-green-500/20' 
              : 'bg-destructive text-white shadow-lg shadow-red-500/20'
          }`}
        >
          {toggleMutation.isPending ? 'در حال تغییر...' : (config?.is_enabled ? 'فعال (Enabled)' : 'غیرفعال (Disabled)')}
        </button>
      </div>

      <div className="flex items-center space-x-1 p-1 bg-muted/50 rounded-xl w-fit">
        <button
          onClick={() => setActiveTab('plans')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === 'plans' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          مدیریت پلن‌ها
        </button>
        <button
          onClick={() => setActiveTab('config')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === 'config' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          تنظیمات مالی
        </button>
        <button
          onClick={() => setActiveTab('users')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === 'users' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          اشتراک کاربران
        </button>
        <button
          onClick={() => setActiveTab('trial')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === 'trial' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          دوره آزمایشی (Trial)
        </button>
      </div>

      {activeTab === 'plans' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold">مدیریت اشتراک‌ها</h2>
              <p className="text-sm text-muted-foreground">تعریف پلن‌های اشتراک ماهیانه و قوانین مصرف آن‌ها</p>
            </div>
            <button
              onClick={() => { setEditingPlan(null); setIsPlanFormOpen(true); }}
              className="flex items-center space-x-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-all"
            >
              <Plus className="w-4 h-4 ml-2" />
              <span>افزودن اشتراک جدید</span>
            </button>
          </div>

          {plansLoading ? (
            <div className="flex justify-center p-8">در حال بارگذاری...</div>
          ) : (
            <div className="grid gap-6">
              {plans?.map((plan) => (
                <PlanCard 
                  key={plan.id} 
                  plan={plan} 
                  models={models || []}
                  tools={tools || []}
                  skills={skills || []}
                  onManageRules={() => {
                    setSelectedPlanId(plan.id);
                    setIsRuleFormOpen(true);
                  }}
                  onEdit={() => {
                    setEditingPlan(plan);
                    setIsPlanFormOpen(true);
                  }}
                  onDelete={() => {
                    if (window.confirm(`آیا از حذف پلن "${plan.name}" اطمینان دارید؟`)) {
                      deletePlanMutation.mutate(plan.id);
                    }
                  }}
                />
              ))}
              {plans?.length === 0 && (
                <div className="text-center p-12 border-2 border-dashed border-border rounded-xl">
                  <Shield className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-20" />
                  <p className="text-muted-foreground">هیچ اشتراکی تعریف نشده است.</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'config' && config && (
        <BillingConfigForm
          config={config}
          onSave={(payload) => updateSubscriptionConfig(payload)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['subscriptionConfig'] })}
        />
      )}

      {activeTab === 'users' && <UserSubscriptionsPanel />}

      {activeTab === 'trial' && <TrialSettings />}

      {isPlanFormOpen && (
        <PlanFormDialog 
          plan={editingPlan}
          models={models || []}
          tools={tools || []}
          skills={skills || []}
          onClose={() => { setIsPlanFormOpen(false); setEditingPlan(null); }}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ['subscriptionPlans'] });
            queryClient.invalidateQueries({ queryKey: ['subscriptionPlanRules'] });
            setIsPlanFormOpen(false);
            setEditingPlan(null);
          }}
        />
      )}

      {isRuleFormOpen && selectedPlanId && (
        <RuleManagerDialog 
          planId={selectedPlanId}
          models={models || []}
          onClose={() => {
            setIsRuleFormOpen(false);
            setSelectedPlanId(null);
          }}
        />
      )}
    </div>
  );
}

function BillingConfigForm({
  config,
  onSave,
  onSaved
}: {
  config: SubscriptionConfig;
  onSave: (payload: Partial<Omit<SubscriptionConfig, 'id'>>) => Promise<SubscriptionConfig>;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    monthly_price_toman: String(config.monthly_price_toman),
    gift_credit_toman: String(config.gift_credit_toman),
    api_markup_percent: String(config.api_markup_percent),
    first_topup_discount_percent: String(config.first_topup_discount_percent),
    first_topup_discount_cap_toman: String(config.first_topup_discount_cap_toman),
    usd_to_toman_rate: String(config.usd_to_toman_rate),
  });

  useEffect(() => {
    setForm({
      monthly_price_toman: String(config.monthly_price_toman),
      gift_credit_toman: String(config.gift_credit_toman),
      api_markup_percent: String(config.api_markup_percent),
      first_topup_discount_percent: String(config.first_topup_discount_percent),
      first_topup_discount_cap_toman: String(config.first_topup_discount_cap_toman),
      usd_to_toman_rate: String(config.usd_to_toman_rate),
    });
  }, [config]);

  const mutation = useMutation({
    mutationFn: () => onSave({
      is_enabled: config.is_enabled,
      monthly_price_toman: parseInt(form.monthly_price_toman, 10) || 0,
      gift_credit_toman: parseInt(form.gift_credit_toman, 10) || 0,
      api_markup_percent: parseFloat(form.api_markup_percent) || 0,
      first_topup_discount_percent: parseFloat(form.first_topup_discount_percent) || 0,
      first_topup_discount_cap_toman: parseInt(form.first_topup_discount_cap_toman, 10) || 0,
      usd_to_toman_rate: parseInt(form.usd_to_toman_rate, 10) || 0,
    }),
    onSuccess: onSaved
  });

  const updateField = (key: keyof typeof form, value: string) => {
    setForm(current => ({ ...current, [key]: value }));
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
      className="p-4 bg-card border border-border rounded-xl space-y-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold">تنظیمات مالی پیش‌فرض (Fallback)</h3>
          <p className="text-xs text-muted-foreground">این مقادیر فقط برای پلن‌هایی استفاده می‌شود که قیمت/اعتبار اختصاصی خود را نداشته باشند. هر پلن می‌تواند قیمت مستقل خود را در بخش «مدیریت اشتراک‌ها» تنظیم کند.</p>
        </div>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-xs font-bold hover:bg-primary/90 disabled:opacity-60 transition-all"
        >
          <Save className="w-4 h-4" />
          <span>{mutation.isPending ? 'در حال ذخیره...' : 'ذخیره'}</span>
        </button>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <NumberField label="قیمت پیش‌فرض (fallback)" value={form.monthly_price_toman} onChange={(value) => updateField('monthly_price_toman', value)} suffix="تومان" />
        <NumberField label="اعتبار هدیه پیش‌فرض (fallback)" value={form.gift_credit_toman} onChange={(value) => updateField('gift_credit_toman', value)} suffix="تومان" />
        <NumberField label="نرخ هر دلار API" value={form.usd_to_toman_rate} onChange={(value) => updateField('usd_to_toman_rate', value)} suffix="تومان" />
        <NumberField label="Markup مصرف API" value={form.api_markup_percent} onChange={(value) => updateField('api_markup_percent', value)} suffix="%" step="0.01" />
        <NumberField label="تخفیف اولین شارژ" value={form.first_topup_discount_percent} onChange={(value) => updateField('first_topup_discount_percent', value)} suffix="%" step="0.01" />
        <NumberField label="سقف شارژ تخفیفی اول" value={form.first_topup_discount_cap_toman} onChange={(value) => updateField('first_topup_discount_cap_toman', value)} suffix="تومان" />
      </div>

      <div className="text-xs text-muted-foreground">
        نمونه شارژ اول ۳۰۰٬۰۰۰ تومانی: پرداخت {formatToman(Math.round(300000 * (1 + (parseFloat(form.api_markup_percent) || 0) / 100) * (1 - (parseFloat(form.first_topup_discount_percent) || 0) / 100)))}
      </div>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange,
  suffix,
  step = '1'
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  suffix: string;
  step?: string;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium mb-1">{label}</span>
      <div className="flex items-center bg-muted border border-border rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-primary/50 transition-all">
        <input
          type="number"
          min="0"
          step={step}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full bg-transparent py-2 px-3 text-sm focus:outline-none"
        />
        <span className="px-3 text-[11px] text-muted-foreground whitespace-nowrap border-r border-border bg-muted/50">{suffix}</span>
      </div>
    </label>
  );
}

function UserSubscriptionsPanel() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState('all');
  const { data: subscriptions = [], isLoading } = useQuery({
    queryKey: ['userSubscriptions', status],
    queryFn: () => getUserSubscriptions(status),
  });

  const cancelMutation = useMutation({
    mutationFn: cancelUserSubscription,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['userSubscriptions'] })
  });

  const reactivateMutation = useMutation({
    mutationFn: reactivateUserSubscription,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['userSubscriptions'] })
  });

  const isMutating = cancelMutation.isPending || reactivateMutation.isPending;

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-border flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-muted/20">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <UserCheck className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold">کاربران دارای اشتراک</h3>
            <p className="text-xs text-muted-foreground">مشاهده و مدیریت اشتراک‌های خریداری‌شده</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="bg-muted border border-border rounded-lg py-2 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="all">همه</option>
            <option value="active">فعال</option>
            <option value="cancelled">لغوشده</option>
          </select>
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['userSubscriptions'] })}
            className="p-2 rounded-lg border border-border hover:bg-muted transition-colors"
            title="بروزرسانی"
          >
            <RotateCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="text-right p-3 font-medium border-b border-border">کاربر</th>
              <th className="text-right p-3 font-medium border-b border-border">پلن</th>
              <th className="text-right p-3 font-medium border-b border-border">Pool</th>
              <th className="text-right p-3 font-medium border-b border-border">وضعیت</th>
              <th className="text-right p-3 font-medium border-b border-border">خرید</th>
              <th className="text-right p-3 font-medium border-b border-border">انقضا</th>
              <th className="text-right p-3 font-medium border-b border-border">اعتبار تومانی</th>
              <th className="text-right p-3 font-medium border-b border-border">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-muted-foreground">در حال بارگذاری...</td>
              </tr>
            ) : subscriptions.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-muted-foreground italic">اشتراکی ثبت نشده است.</td>
              </tr>
            ) : subscriptions.map((subscription: AdminUserSubscription) => (
              <tr key={subscription.id} className="border-t border-border hover:bg-muted/10 transition-colors">
                <td className="p-3">
                  <div className="font-medium">{subscription.first_name || 'بدون نام'}</div>
                  <div className="text-xs text-muted-foreground">
                    {subscription.username ? `@${subscription.username}` : `تلگرام: ${subscription.telegram_user_id || '-'}`}
                  </div>
                  {subscription.phone_number && <div className="text-[11px] text-muted-foreground">{subscription.phone_number}</div>}
                </td>
                <td className="p-3">{subscription.plan_name || `#${subscription.plan_id}`}</td>
                <td className="p-3 text-xs text-muted-foreground">{subscription.pool_name || (subscription.pool_id ? `#${subscription.pool_id}` : '-')}</td>
                <td className="p-3">
                  <span className={`px-2 py-1 rounded text-[10px] font-bold ${subscription.is_active_now ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
                    {subscription.is_active_now ? 'فعال' : subscription.status}
                  </span>
                </td>
                <td className="p-3 text-[10px] text-muted-foreground">{formatDate(subscription.purchased_at)}</td>
                <td className="p-3 text-[10px] text-muted-foreground">{formatDate(subscription.expires_at)}</td>
                <td className="p-3 font-medium">{formatToman(subscription.total_balance_toman)}</td>
                <td className="p-3">
                  {subscription.is_active_now ? (
                    <button
                      type="button"
                      disabled={isMutating}
                      onClick={() => cancelMutation.mutate(subscription.id)}
                      className="px-3 py-1.5 rounded-lg bg-destructive/10 text-destructive text-[10px] font-bold hover:bg-destructive/20 disabled:opacity-60 transition-all"
                    >
                      لغو اشتراک
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={isMutating}
                      onClick={() => reactivateMutation.mutate(subscription.id)}
                      className="px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-[10px] font-bold hover:bg-primary/20 disabled:opacity-60 transition-all"
                    >
                      فعال‌سازی
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanCard({ plan, models, tools, skills, onManageRules, onEdit, onDelete }: { plan: SubscriptionPlan, models: Model[], tools: Tool[], skills: Skill[], onManageRules: () => void, onEdit: () => void, onDelete: () => void }) {
  const { data: rules, isLoading } = useQuery({
    queryKey: ['subscriptionPlanRules', plan.id],
    queryFn: () => getSubscriptionPlanRules(plan.id),
  });

  const restrictionTags = (items: string[] | null | undefined, sourceList: {name: string, display_name?: string | null}[]) => {
    if (items == null) return <span className="text-xs text-muted-foreground">همه مجاز</span>;
    if (items.length === 0) return <span className="text-xs text-red-500">بدون مجوز</span>;
    return (
      <div className="flex flex-wrap gap-1 mt-1">
        {items.map(itemName => {
          const item = sourceList.find(t => t.name === itemName);
          return (
            <span key={itemName} className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium border border-primary/20">
              {item?.display_name || itemName}
            </span>
          );
        })}
      </div>
    );
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow animate-in slide-in-from-bottom-2 duration-300">
      <div className="p-5 border-b border-border bg-muted/30 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="font-bold text-lg">{plan.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-sm font-bold text-primary">{formatToman(plan.monthly_price_toman)}</span>
              <span className="text-[10px] text-muted-foreground">ماهانه</span>
              <span className="text-muted-foreground text-xs mx-1">|</span>
              <span className="text-xs text-muted-foreground">اعتبار هدیه: {formatToman(plan.gift_credit_toman)}</span>
            </div>
            {plan.plan_type === 'tiered_cooldown' && (
              <div className="mt-2 text-[10px] text-amber-500 bg-amber-500/5 p-2 rounded-lg border border-amber-500/20 max-w-xs">
                <span className="font-bold block mb-0.5">محدودیت زمانی (Tiered)</span>
                ساعتی: {formatToman(plan.cooldown_limit_toman)} / {plan.cooldown_hours}h | هفتگی: {formatToman(plan.weekly_limit_toman)}
              </div>
            )}
            <div className="mt-2 flex flex-col gap-1.5">
              <div className="flex items-baseline gap-2">
                <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">ابزارهای مجاز:</span>
                {!plan.is_agentic
                  ? <span className="text-[10px] text-muted-foreground italic">غیرفعال (حالت معمولی)</span>
                  : restrictionTags(plan.allowed_tools_json, tools)}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">مهارت‌های مجاز:</span>
                {restrictionTags(plan.allowed_skills_json, skills)}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex flex-col items-end gap-1 mb-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${plan.is_active ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
              {plan.is_active ? 'فعال' : 'غیرفعال'}
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${plan.is_agentic ? 'bg-blue-500/10 text-blue-500' : 'bg-gray-500/10 text-gray-500'}`}>
              {plan.is_agentic ? 'ایجنتیک' : 'معمولی'}
            </span>
          </div>
          <div className="flex items-center border border-border rounded-lg bg-background overflow-hidden">
            <button 
              onClick={onEdit}
              className="p-2 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground border-l border-border"
              title="ویرایش"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button 
              onClick={onManageRules}
              className="p-2 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground border-l border-border"
              title="مدیریت قوانین"
            >
              <Settings className="w-4 h-4" />
            </button>
            <button 
              onClick={onDelete}
              className="p-2 hover:bg-muted transition-colors text-destructive hover:text-destructive"
              title="حذف"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
      <div className="p-5">
        <h4 className="text-xs font-bold mb-3 text-muted-foreground flex items-center gap-2 uppercase tracking-wider">
          <Package className="w-3.5 h-3.5" />
          قوانین مدل‌ها
        </h4>
        {isLoading ? (
          <p className="text-xs">در حال بارگذاری قوانین...</p>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3">
            {rules?.map(rule => {
              const model = models.find(m => m.id === rule.model_id);
              return (
                <div key={rule.id} className="flex items-center justify-between text-sm p-3 rounded-xl bg-muted/40 border border-border/50">
                  <div className="flex flex-col">
                    <span className="font-bold text-xs">{model?.display_name || model?.name || 'مدل ناشناخته'}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-muted-foreground">{rule.free_chats_count} چت رایگان</span>
                      <span className="text-[10px] text-primary font-bold">{rule.discount_percent}% تخفیف</span>
                    </div>
                  </div>
                </div>
              );
            })}
            {rules?.length === 0 && (
              <p className="text-[11px] text-muted-foreground italic col-span-2">هیچ قانونی برای این پلن تعریف نشده است. تمام مدل‌ها با تعرفه عادی محاسبه می‌شوند.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PlanFormDialog({ plan, models, tools, skills, onClose, onSuccess }: { plan: SubscriptionPlan | null, models: Model[], tools: Tool[], skills: Skill[], onClose: () => void, onSuccess: () => void }) {
  const queryClient = useQueryClient();
  const isEdit = !!plan;
  const [name, setName] = useState(plan?.name ?? '');
  const [planType, setPlanType] = useState(plan?.plan_type ?? 'monthly_credit');
  const [priceToman, setPriceToman] = useState(String(plan?.monthly_price_toman ?? 80000));
  const [giftCreditToman, setGiftCreditToman] = useState(String(plan?.gift_credit_toman ?? 100000));
  const [cooldownLimitToman, setCooldownLimitToman] = useState(String(plan?.cooldown_limit_toman ?? 0));
  const [cooldownHours, setCooldownHours] = useState(String(plan?.cooldown_hours ?? 0));
  const [weeklyLimitToman, setWeeklyLimitToman] = useState(String(plan?.weekly_limit_toman ?? 0));
  const [isActive, setIsActive] = useState(plan?.is_active ?? true);
  const [isAgentic, setIsAgentic] = useState(plan?.is_agentic ?? true);
  const [restrictTools, setRestrictTools] = useState(plan?.allowed_tools_json != null);
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set(plan?.allowed_tools_json ?? []));
  const [restrictSkills, setRestrictSkills] = useState(plan?.allowed_skills_json != null);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set(plan?.allowed_skills_json ?? []));
  const [error, setError] = useState<string | null>(null);
  const [modelRules, setModelRules] = useState<Array<{ model_id: number; free_chats_count: number; free_tokens_per_chat: number; discount_percent: number }>>([]);
  const [selectedModelId, setSelectedModelId] = useState<number>(0);
  const [newRuleFreeChats, setNewRuleFreeChats] = useState('2');
  const [newRuleFreeTokens, setNewRuleFreeTokens] = useState('100000');
  const [newRuleDiscount, setNewRuleDiscount] = useState('75');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const activeTools = tools.filter(t => t.is_active);
  const activeSkills = skills.filter(s => s.is_active);
  const activeModels = models.filter(m => m.is_active);

  const toggleTool = (toolName: string) => {
    setSelectedTools(prev => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
  };

  const toggleSkill = (skillName: string) => {
    setSelectedSkills(prev => {
      const next = new Set(prev);
      if (next.has(skillName)) next.delete(skillName);
      else next.add(skillName);
      return next;
    });
  };

  const addModelRule = () => {
    if (selectedModelId === 0) return;
    if (modelRules.some(r => r.model_id === selectedModelId)) {
      setError('این مدل قبلاً اضافه شده است');
      return;
    }
    setModelRules(prev => [...prev, {
      model_id: selectedModelId,
      free_chats_count: parseInt(newRuleFreeChats) || 0,
      free_tokens_per_chat: parseInt(newRuleFreeTokens) || 0,
      discount_percent: parseFloat(newRuleDiscount) || 0,
    }]);
    setSelectedModelId(0);
  };

  const removeModelRule = (modelId: number) => {
    setModelRules(prev => prev.filter(r => r.model_id !== modelId));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const payload: any = {
        name,
        plan_type: planType,
        monthly_price_toman: parseInt(priceToman, 10) || 0,
        gift_credit_toman: parseInt(giftCreditToman, 10) || 0,
        cooldown_limit_toman: parseInt(cooldownLimitToman, 10) || 0,
        cooldown_hours: parseInt(cooldownHours, 10) || 0,
        weekly_limit_toman: parseInt(weeklyLimitToman, 10) || 0,
        is_active: isActive,
        is_agentic: isAgentic,
        allowed_tools_json: restrictTools ? Array.from(selectedTools) : null,
        allowed_skills_json: restrictSkills ? Array.from(selectedSkills) : null,
      };

      let planId: number;
      if (isEdit && plan) {
        await updateSubscriptionPlan(plan.id, payload);
        planId = plan.id;
        const existingRules = await getSubscriptionPlanRules(planId);
        for (const rule of existingRules) {
          await deleteSubscriptionPlanRule(rule.id);
        }
      } else {
        const createdPlan = await createSubscriptionPlan(payload);
        planId = createdPlan.id;
      }

      for (const rule of modelRules) {
        await createSubscriptionPlanRule(planId, { ...rule, is_active: true });
      }

      queryClient.invalidateQueries({ queryKey: ['subscriptionPlans'] });
      queryClient.invalidateQueries({ queryKey: ['subscriptionPlanRules'] });
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'خطایی رخ داد');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-2xl animate-in fade-in zoom-in duration-200 overflow-y-auto max-h-[90vh]">
        <div className="p-4 border-b border-border flex items-center justify-between sticky top-0 bg-background z-10">
          <h2 className="text-lg font-bold">{isEdit ? 'ویرایش پلن' : 'تعریف اشتراک جدید'}</h2>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">نام اشتراک</label>
            <input 
              type="text" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder="مثلاً: حرفه‌ای (Pro)"
              required
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">نوع پلن</label>
            <select
              value={planType}
              onChange={e => setPlanType(e.target.value)}
              className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            >
              <option value="monthly_credit">پایه / اعتبار ماهیانه</option>
              <option value="tiered_cooldown">زمانی با محدودیت ساعتی</option>
            </select>
          </div>
          {planType === 'tiered_cooldown' && (
            <div className="space-y-4 p-3 border border-primary/20 bg-primary/5 rounded-lg">
              <div>
                <label className="block text-sm font-medium mb-1">لیمیت پولی ساعتی (تومان)</label>
                <input 
                  type="number" 
                  value={cooldownLimitToman}
                  onChange={e => setCooldownLimitToman(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">زمان انتظار قفل (ساعت)</label>
                  <input 
                    type="number" 
                    value={cooldownHours}
                    onChange={e => setCooldownHours(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">لیمیت پولی هفتگی (تومان)</label>
                  <input 
                    type="number" 
                    value={weeklyLimitToman}
                    onChange={e => setWeeklyLimitToman(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm"
                  />
                </div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">قیمت ماهیانه (تومان)</label>
              <input 
                type="number" 
                value={priceToman}
                onChange={e => setPriceToman(e.target.value)}
                required
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">اعتبار هدیه (تومان)</label>
              <input
                type="number"
                value={giftCreditToman}
                onChange={e => setGiftCreditToman(e.target.value)}
                required
                className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
              />
            </div>
          </div>
          <div className="flex items-center gap-6 p-2 bg-muted/30 rounded-lg">
            <div className="flex items-center space-x-2">
              <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="ml-2" />
              <label className="text-sm font-medium">فعال باشد</label>
            </div>
            <div className="flex items-center space-x-2">
              <input type="checkbox" checked={isAgentic} onChange={e => setIsAgentic(e.target.checked)} className="ml-2" />
              <label className="text-sm font-medium">حالت ایجنتیک</label>
            </div>
          </div>

          <div className="border border-border rounded-lg p-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold">مدل‌های مجاز این پلن</span>
              <span className="text-xs text-muted-foreground">{modelRules.length} مدل</span>
            </div>
            <p className="text-[10px] text-muted-foreground italic">مدل‌هایی که کاربران این پلن می‌توانند استفاده کنند. اگر مدلی اضافه نکنید، همه مدل‌ها مجاز هستند.</p>
            <div className="flex gap-2">
              <select 
                value={selectedModelId} 
                onChange={e => setSelectedModelId(parseInt(e.target.value))} 
                className="flex-1 bg-muted border border-border rounded-lg py-2 px-3 text-xs focus:outline-none"
              >
                <option value={0}>انتخاب مدل...</option>
                {activeModels.map(m => (
                  <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
                ))}
              </select>
              <input type="number" value={newRuleFreeChats} onChange={e => setNewRuleFreeChats(e.target.value)} placeholder="چت" className="w-16 bg-muted border border-border rounded-lg py-2 px-2 text-xs" title="چت رایگان" />
              <input type="number" value={newRuleDiscount} onChange={e => setNewRuleDiscount(e.target.value)} placeholder="%" className="w-16 bg-muted border border-border rounded-lg py-2 px-2 text-xs" title="درصد تخفیف" />
              <button type="button" onClick={addModelRule} disabled={selectedModelId === 0} className="px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold disabled:opacity-50">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {modelRules.length > 0 && (
              <div className="space-y-1 mt-2 max-h-32 overflow-y-auto">
                {modelRules.map(rule => {
                  const model = models.find(m => m.id === rule.model_id);
                  return (
                    <div key={rule.model_id} className="flex items-center justify-between p-2 rounded bg-muted/50 text-xs border border-border/50">
                      <div>
                        <span className="font-bold">{model?.display_name || model?.name || 'مدل ناشناخته'}</span>
                        <span className="text-muted-foreground mr-2">{rule.free_chats_count} چت رایگان | {rule.discount_percent}% تخفیف</span>
                      </div>
                      <button type="button" onClick={() => removeModelRule(rule.model_id)} className="p-1 text-destructive hover:bg-destructive/10 rounded transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="border border-border rounded-lg p-3 space-y-3">
              <div className="flex items-center space-x-2">
                <input 
                  type="checkbox" 
                  checked={restrictTools} 
                  onChange={e => setRestrictTools(e.target.checked)} 
                  className="ml-2" 
                  id="restrict-tools"
                />
                <label htmlFor="restrict-tools" className="text-xs font-bold uppercase tracking-wider">محدود کردن ابزارها</label>
              </div>
              {restrictTools && (
                <div className="grid grid-cols-1 gap-1 max-h-32 overflow-y-auto pr-1">
                  {activeTools.map(tool => (
                    <label key={tool.name} className="flex items-center space-x-2 p-1.5 rounded hover:bg-muted cursor-pointer text-[10px]">
                      <input
                        type="checkbox"
                        checked={selectedTools.has(tool.name)}
                        onChange={() => toggleTool(tool.name)}
                        className="ml-2"
                      />
                      <span>{tool.display_name || tool.name}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="border border-border rounded-lg p-3 space-y-3">
              <div className="flex items-center space-x-2">
                <input 
                  type="checkbox" 
                  checked={restrictSkills} 
                  onChange={e => setRestrictSkills(e.target.checked)} 
                  className="ml-2" 
                  id="restrict-skills"
                />
                <label htmlFor="restrict-skills" className="text-xs font-bold uppercase tracking-wider">محدود کردن مهارت‌ها</label>
              </div>
              {restrictSkills && (
                <div className="grid grid-cols-1 gap-1 max-h-32 overflow-y-auto pr-1">
                  {activeSkills.map(skill => (
                    <label key={skill.name} className="flex items-center space-x-2 p-1.5 rounded hover:bg-muted cursor-pointer text-[10px]">
                      <input
                        type="checkbox"
                        checked={selectedSkills.has(skill.name)}
                        onChange={() => toggleSkill(skill.name)}
                        className="ml-2"
                      />
                      <span>{skill.name}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {error && <div className="text-xs text-red-500 bg-red-500/10 p-2 rounded flex items-center gap-2">
            <X className="w-3 h-3" />
            {error}
          </div>}

          <div className="flex space-x-3 pt-4 border-t border-border mt-4">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg text-sm bg-muted hover:bg-muted/80 transition-colors font-medium">انصراف</button>
            <button type="submit" disabled={isSubmitting} className="flex-1 py-2 rounded-lg text-sm bg-primary text-primary-foreground font-bold shadow-lg shadow-primary/20 hover:bg-primary/90 transition-all">
              {isSubmitting ? 'در حال ثبت...' : (isEdit ? 'ذخیره تغییرات' : 'ایجاد پلن')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RuleManagerDialog({ planId, models, onClose }: { planId: number, models: Model[], onClose: () => void }) {
  const queryClient = useQueryClient();
  const [modelId, setModelId] = useState<number>(0);
  const [freeChats, setFreeChats] = useState('2');
  const [freeTokens, setFreeTokens] = useState('100000');
  const [discount, setDiscount] = useState('75');

  const { data: rules, isLoading } = useQuery({
    queryKey: ['subscriptionPlanRules', planId],
    queryFn: () => getSubscriptionPlanRules(planId),
  });

  const addRuleMutation = useMutation({
    mutationFn: (data: any) => createSubscriptionPlanRule(planId, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subscriptionPlanRules', planId] })
  });

  const deleteRuleMutation = useMutation({
    mutationFn: deleteSubscriptionPlanRule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['subscriptionPlanRules', planId] })
  });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm text-right" dir="rtl">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-2xl animate-in fade-in zoom-in duration-200 overflow-hidden">
        <div className="p-4 border-b border-border flex items-center justify-between bg-muted/20">
          <h2 className="text-lg font-bold">مدیریت قوانین مصرف</h2>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded transition-colors"><X className="w-5 h-5" /></button>
        </div>
        
        <div className="p-6 grid md:grid-cols-2 gap-8 max-h-[70vh] overflow-y-auto text-right">
          <div className="space-y-6">
            <div className="space-y-1">
              <h3 className="font-bold text-sm">افزودن قانون جدید</h3>
              <p className="text-[10px] text-muted-foreground italic">تعریف چت رایگان و تخفیف برای یک مدل خاص</p>
            </div>
            <form onSubmit={e => {
              e.preventDefault();
              if (modelId === 0) return;
              addRuleMutation.mutate({
                model_id: modelId,
                free_chats_count: parseInt(freeChats),
                free_tokens_per_chat: parseInt(freeTokens),
                discount_percent: parseFloat(discount)
              });
            }} className="space-y-4">
              <div>
                <label className="block text-[11px] font-medium mb-1.5 opacity-70">انتخاب مدل</label>
                <select 
                  value={modelId} 
                  onChange={e => setModelId(parseInt(e.target.value))} 
                  required
                  className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                >
                  <option value={0}>انتخاب کنید...</option>
                  {models.filter(m => m.is_active).map(m => (
                    <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-medium mb-1.5 opacity-70">تعداد چت رایگان</label>
                  <input type="number" value={freeChats} onChange={e => setFreeChats(e.target.value)} className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" />
                </div>
                <div>
                  <label className="block text-[11px] font-medium mb-1.5 opacity-70">درصد تخفیف (%)</label>
                  <input type="number" value={discount} onChange={e => setDiscount(e.target.value)} className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" />
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-medium mb-1.5 opacity-70">سقف توکن هر چت رایگان</label>
                <input type="number" value={freeTokens} onChange={e => setFreeTokens(e.target.value)} className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" />
              </div>
              <button 
                type="submit" 
                disabled={addRuleMutation.isPending || modelId === 0}
                className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-bold flex items-center justify-center space-x-2 shadow-lg shadow-primary/20 hover:bg-primary/90 transition-all disabled:opacity-50"
              >
                <Plus className="w-4 h-4 ml-2" />
                <span>ثبت قانون</span>
              </button>
            </form>
          </div>

          <div className="space-y-6">
            <div className="space-y-1">
              <h3 className="font-bold text-sm">قوانین ثبت‌شده</h3>
              <p className="text-[10px] text-muted-foreground italic">لیست مدل‌هایی که برای این پلن دارای شرایط خاص هستند</p>
            </div>
            {isLoading ? (
              <p className="text-xs">در حال بارگذاری...</p>
            ) : (
              <div className="space-y-3">
                {rules?.map(rule => {
                  const model = models.find(m => m.id === rule.model_id);
                  return (
                    <div key={rule.id} className="p-3.5 border border-border rounded-xl bg-muted/30 flex items-center justify-between border-r-4 border-r-primary">
                      <div>
                        <div className="font-bold text-xs">{model?.display_name || model?.name}</div>
                        <div className="text-[10px] text-muted-foreground mt-1.5 flex flex-wrap gap-2">
                          <span className="bg-background px-1.5 py-0.5 rounded border border-border">{rule.free_chats_count} چت رایگان</span>
                          <span className="bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold">{rule.discount_percent}% تخفیف</span>
                        </div>
                      </div>
                      <button 
                        onClick={() => deleteRuleMutation.mutate(rule.id)}
                        disabled={deleteRuleMutation.isPending}
                        className="p-2 text-destructive hover:bg-destructive/10 rounded-lg transition-colors mr-2"
                        title="حذف قانون"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
                {rules?.length === 0 && (
                  <div className="text-center p-8 border-2 border-dashed border-border rounded-2xl opacity-40">
                    <Package className="w-8 h-8 mx-auto mb-2" />
                    <p className="text-[11px] font-medium">هیچ قانونی تعریف نشده.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
