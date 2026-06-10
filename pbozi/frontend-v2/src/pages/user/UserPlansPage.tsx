import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getUserSubscriptionPlans, purchaseUserSubscription, getUserBillingAccount, getUserSubscription } from '../../lib/api';
import { UserSubscriptionPlan } from '../../lib/types';
import { CreditCard, Clock, Shield, Zap, AlertCircle, Check } from 'lucide-react';

interface UserPlansPageProps {
  telegramUserId: number;
  onNavigate: (page: string) => void;
}

const USER_PLAN_LABELS: Record<string, string> = {
  monthly_credit: 'اشتراک ماهانه',
  tiered_cooldown: 'پلن پلکانی',
};

export default function UserPlansPage({ telegramUserId, onNavigate }: UserPlansPageProps) {
  const queryClient = useQueryClient();
  const [selectedPlan, setSelectedPlan] = useState<UserSubscriptionPlan | null>(null);
  const [purchaseError, setPurchaseError] = useState<string | null>(null);
  const [purchaseSuccess, setPurchaseSuccess] = useState(false);

  const { data: plans, isLoading: plansLoading } = useQuery({
    queryKey: ['user-plans'],
    queryFn: getUserSubscriptionPlans,
  });

  const { data: billingAccount } = useQuery({
    queryKey: ['user-billing', telegramUserId],
    queryFn: () => getUserBillingAccount(telegramUserId),
    enabled: !!telegramUserId,
  });

  const { data: currentSubscription } = useQuery({
    queryKey: ['user-subscription', telegramUserId],
    queryFn: () => getUserSubscription(telegramUserId),
    enabled: !!telegramUserId,
  });

  const purchaseMutation = useMutation({
    mutationFn: ({ planId }: { planId: number }) => purchaseUserSubscription(telegramUserId, planId),
    onSuccess: () => {
      setPurchaseSuccess(true);
      setPurchaseError(null);
      queryClient.invalidateQueries({ queryKey: ['user-billing', telegramUserId] });
      queryClient.invalidateQueries({ queryKey: ['user-subscription', telegramUserId] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || 'خطا در خرید اشتراک';
      setPurchaseError(msg);
      setPurchaseSuccess(false);
    },
  });

  const handlePurchase = (plan: UserSubscriptionPlan) => {
    setSelectedPlan(plan);
    setPurchaseError(null);
    setPurchaseSuccess(false);
    purchaseMutation.mutate({ planId: plan.id });
  };

  const formatToman = (amount: number) => {
    return new Intl.NumberFormat('fa-IR').format(amount);
  };

  if (currentSubscription?.is_active_now) {
    return (
      <div className="space-y-6" dir="rtl">
        <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Check className="w-5 h-5 text-emerald-600" />
            <h2 className="text-lg font-semibold text-emerald-800 dark:text-emerald-200">اشتراک فعال دارید</h2>
          </div>
          <p className="text-emerald-700 dark:text-emerald-300">
            پلن: {currentSubscription.plan_name} | انقضا: {new Date(currentSubscription.expires_at).toLocaleDateString('fa-IR')}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => onNavigate('my-subscription')}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
          >
            مشاهده جزئیات اشتراک
          </button>
          <button
            onClick={() => onNavigate('billing')}
            className="px-4 py-2 bg-muted border border-border rounded-lg hover:bg-muted/80"
          >
            کیف پول
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" dir="rtl">
      <div>
        <h1 className="text-2xl font-bold">پلن‌های اشتراک</h1>
        <p className="text-muted-foreground mt-1">پلن مناسب خود را انتخاب کنید</p>
      </div>

      {billingAccount && (
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">موجودی کیف پول:</span>
            <span className="text-lg font-semibold">{formatToman(billingAccount.total_balance_toman)} تومان</span>
          </div>
        </div>
      )}

      {purchaseSuccess && (
        <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <Check className="w-5 h-5" />
            <span>اشتراک با موفقیت خریداری شد!</span>
          </div>
        </div>
      )}

      {purchaseError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
            <AlertCircle className="w-5 h-5" />
            <span>{purchaseError}</span>
          </div>
          <button
            onClick={() => onNavigate('billing')}
            className="mt-2 text-sm text-red-600 dark:text-red-400 underline"
          >
            شارژ کیف پول
          </button>
        </div>
      )}

      {plansLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {plans?.map((plan) => (
            <div
              key={plan.id}
              className={`bg-card border rounded-xl p-6 transition-all hover:shadow-lg ${
                selectedPlan?.id === plan.id
                  ? 'border-primary ring-2 ring-primary/20'
                  : 'border-border'
              }`}
            >
              <div className="flex items-center gap-2 mb-4">
                {plan.plan_type === 'tiered_cooldown' ? (
                  <Zap className="w-5 h-5 text-amber-500" />
                ) : (
                  <Shield className="w-5 h-5 text-blue-500" />
                )}
                <h3 className="text-lg font-semibold">{plan.name}</h3>
              </div>

              <div className="text-3xl font-bold mb-1">
                {formatToman(plan.monthly_price_toman)}
                <span className="text-sm font-normal text-muted-foreground mr-1">تومان</span>
              </div>
              <p className="text-sm text-muted-foreground mb-4">ماهانه</p>

              <div className="space-y-2 text-sm mb-6">
                {plan.gift_credit_toman > 0 && (
                  <div className="flex items-center gap-2 text-emerald-600">
                    <CreditCard className="w-4 h-4" />
                    <span>{formatToman(plan.gift_credit_toman)} تومان اعتبار هدیه</span>
                  </div>
                )}
                {plan.plan_type === 'tiered_cooldown' && (
                  <>
                    {plan.cooldown_limit_toman > 0 && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        <span>سقف مصرف: {formatToman(plan.cooldown_limit_toman)} تومان</span>
                      </div>
                    )}
                    {plan.cooldown_hours > 0 && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        <span>مدت cooldown: {plan.cooldown_hours} ساعت</span>
                      </div>
                    )}
                    {plan.weekly_limit_toman > 0 && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        <span>سقف هفتگی: {formatToman(plan.weekly_limit_toman)} تومان</span>
                      </div>
                    )}
                  </>
                )}
              </div>

              <button
                onClick={() => handlePurchase(plan)}
                disabled={purchaseMutation.isPending}
                className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {purchaseMutation.isPending && selectedPlan?.id === plan.id
                  ? 'در حال خرید...'
                  : 'خرید اشتراک'}
              </button>
            </div>
          ))}
        </div>
      )}

      {(!plans || plans.length === 0) && !plansLoading && (
        <div className="text-center py-12 text-muted-foreground">
          پلنی برای نمایش وجود ندارد
        </div>
      )}
    </div>
  );
}
