import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DollarSign, Save, RotateCw, TrendingUp, Wallet, Percent, CreditCard } from 'lucide-react';
import { getSubscriptionConfig, updateSubscriptionConfig } from '../lib/api';
import { SubscriptionConfig } from '../lib/types';

const formatToman = (value: number | undefined | null) => `${Number(value || 0).toLocaleString('fa-IR')} تومان`;

function NumberField({
  label,
  value,
  onChange,
  suffix,
  step = '1',
  icon: Icon,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  suffix: string;
  step?: string;
  icon?: React.ElementType;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium mb-1 flex items-center gap-1.5">
        {Icon && <Icon className="w-3.5 h-3.5 text-muted-foreground" />}
        {label}
      </span>
      <div className="flex items-center bg-muted border border-border rounded-lg overflow-hidden">
        <input
          type="number"
          min="0"
          step={step}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full bg-transparent py-2 px-3 text-sm focus:outline-none"
        />
        <span className="px-3 text-[11px] text-muted-foreground whitespace-nowrap border-r border-border">{suffix}</span>
      </div>
    </label>
  );
}

export default function Financial() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    usd_to_toman_rate: '',
    monthly_price_toman: '',
    gift_credit_toman: '',
    api_markup_percent: '',
    first_topup_discount_percent: '',
    first_topup_discount_cap_toman: '',
  });
  const [savedMsg, setSavedMsg] = useState('');

  const { data: config, isLoading } = useQuery<SubscriptionConfig>({
    queryKey: ['subscriptionConfig'],
    queryFn: getSubscriptionConfig,
  });

  React.useEffect(() => {
    if (config) {
      setForm({
        usd_to_toman_rate: String(config.usd_to_toman_rate),
        monthly_price_toman: String(config.monthly_price_toman),
        gift_credit_toman: String(config.gift_credit_toman),
        api_markup_percent: String(config.api_markup_percent),
        first_topup_discount_percent: String(config.first_topup_discount_percent),
        first_topup_discount_cap_toman: String(config.first_topup_discount_cap_toman),
      });
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () => updateSubscriptionConfig({
      usd_to_toman_rate: parseInt(form.usd_to_toman_rate, 10) || 0,
      monthly_price_toman: parseInt(form.monthly_price_toman, 10) || 0,
      gift_credit_toman: parseInt(form.gift_credit_toman, 10) || 0,
      api_markup_percent: parseFloat(form.api_markup_percent) || 0,
      first_topup_discount_percent: parseFloat(form.first_topup_discount_percent) || 0,
      first_topup_discount_cap_toman: parseInt(form.first_topup_discount_cap_toman, 10) || 0,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptionConfig'] });
      setSavedMsg('تنظیمات ذخیره شد');
      setTimeout(() => setSavedMsg(''), 3000);
    },
  });

  const updateField = (key: keyof typeof form, value: string) => {
    setForm(current => ({ ...current, [key]: value }));
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">در حال بارگذاری...</div>;

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">تنظیمات مالی</h1>
          <p className="text-sm text-muted-foreground">نرخ دلار، قیمت‌های پایه و تخفیف‌ها</p>
        </div>
        <div className="flex items-center gap-2">
          {savedMsg && <span className="text-xs text-green-500 font-medium">{savedMsg}</span>}
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['subscriptionConfig'] })}
            className="p-2 rounded-lg border border-border hover:bg-muted"
            title="بروزرسانی"
          >
            <RotateCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 bg-green-500/10 rounded-lg">
              <DollarSign className="w-5 h-5 text-green-500" />
            </div>
            <h3 className="font-bold text-sm">نرخ ارز</h3>
          </div>
          <NumberField
            label="نرخ دلار به تومان"
            value={form.usd_to_toman_rate}
            onChange={(v) => updateField('usd_to_toman_rate', v)}
            suffix="تومان"
            icon={DollarSign}
          />
          <p className="text-xs text-muted-foreground">
            این نرخ برای تبدیل هزینه‌های دلاری API به تومان استفاده می‌شود.
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <Wallet className="w-5 h-5 text-blue-500" />
            </div>
            <h3 className="font-bold text-sm">قیمت‌های پیش‌فرض</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label="قیمت ماهیانه پیش‌فرض"
              value={form.monthly_price_toman}
              onChange={(v) => updateField('monthly_price_toman', v)}
              suffix="تومان"
              icon={CreditCard}
            />
            <NumberField
              label="اعتبار هدیه پیش‌فرض"
              value={form.gift_credit_toman}
              onChange={(v) => updateField('gift_credit_toman', v)}
              suffix="تومان"
              icon={Gift}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            این مقادیر فقط برای پلن‌هایی استفاده می‌شود که قیمت/اعتبار اختصاصی نداشته باشند.
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-2 bg-amber-500/10 rounded-lg">
              <Percent className="w-5 h-5 text-amber-500" />
            </div>
            <h3 className="font-bold text-sm">تخفیف‌ها و Markup</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label="Markup مصرف API"
              value={form.api_markup_percent}
              onChange={(v) => updateField('api_markup_percent', v)}
              suffix="%"
              step="0.01"
              icon={TrendingUp}
            />
            <NumberField
              label="تخفیف اولین شارژ"
              value={form.first_topup_discount_percent}
              onChange={(v) => updateField('first_topup_discount_percent', v)}
              suffix="%"
              step="0.01"
              icon={Percent}
            />
            <NumberField
              label="سقف تخفیف اولین شارژ"
              value={form.first_topup_discount_cap_toman}
              onChange={(v) => updateField('first_topup_discount_cap_toman', v)}
              suffix="تومان"
              icon={Wallet}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            نمونه شارژ اول ۳۰۰٬۰۰۰ تومانی: پرداخت{' '}
            {formatToman(
              Math.round(
                300000 *
                  (1 + (parseFloat(form.api_markup_percent) || 0) / 100) *
                  (1 - (parseFloat(form.first_topup_discount_percent) || 0) / 100)
              )
            )}
          </p>
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg text-sm font-bold hover:bg-primary/90 disabled:opacity-60 transition-colors"
        >
          <Save className="w-4 h-4" />
          <span>{saveMutation.isPending ? 'در حال ذخیره...' : 'ذخیره تنظیمات'}</span>
        </button>
      </div>
    </div>
  );
}

function Gift(props: React.ComponentProps<'svg'>) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="8" width="18" height="4" rx="1" />
      <path d="M12 8v13" />
      <path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7" />
      <path d="M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5" />
    </svg>
  );
}
