import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getUserSubscription, getUserBillingAccount, checkUsagePermission, claimTrial } from '../../lib/api';
import { UserSubscriptionStatus, UserBillingAccount } from '../../lib/types';
import { Clock, AlertTriangle, Check, RefreshCw, Zap, Calendar, Wallet } from 'lucide-react';

interface MySubscriptionPageProps {
  telegramUserId: number;
  onNavigate: (page: string) => void;
}

export default function MySubscriptionPage({ telegramUserId, onNavigate }: MySubscriptionPageProps) {
  const queryClient = useQueryClient();
  const [cooldownRemaining, setCooldownRemaining] = useState<number | null>(null);
  const [permissionResult, setPermissionResult] = useState<any>(null);
  const [checkingPermission, setCheckingPermission] = useState(false);

  const { data: subscription, isLoading: subLoading } = useQuery({
    queryKey: ['user-subscription', telegramUserId],
    queryFn: () => getUserSubscription(telegramUserId),
    enabled: !!telegramUserId,
    refetchInterval: 30000,
  });

  const { data: billingAccount } = useQuery({
    queryKey: ['user-billing', telegramUserId],
    queryFn: () => getUserBillingAccount(telegramUserId),
    enabled: !!telegramUserId,
  });

  useEffect(() => {
    if (subscription?.is_in_cooldown && subscription.cooldown_remaining_seconds) {
      setCooldownRemaining(subscription.cooldown_remaining_seconds);
      const interval = setInterval(() => {
        setCooldownRemaining((prev) => {
          if (prev === null || prev <= 0) {
            clearInterval(interval);
            queryClient.invalidateQueries({ queryKey: ['user-subscription', telegramUserId] });
            return null;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [subscription, telegramUserId, queryClient]);

  const handleCheckPermission = async () => {
    setCheckingPermission(true);
    try {
      const result = await checkUsagePermission(telegramUserId);
      setPermissionResult(result);
    } catch {
      setPermissionResult(null);
    } finally {
      setCheckingPermission(false);
    }
  };

  const handleClaimTrial = async () => {
    try {
      await claimTrial(telegramUserId);
      queryClient.invalidateQueries({ queryKey: ['user-subscription', telegramUserId] });
    } catch (err: any) {
      alert(err.response?.data?.detail || 'خطا در دریافت تریال');
    }
  };

  const formatToman = (amount: number) => new Intl.NumberFormat('fa-IR').format(amount);

  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h} ساعت و ${m} دقیقه`;
    if (m > 0) return `${m} دقیقه و ${s} ثانیه`;
    return `${s} ثانیه`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('fa-IR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  if (subLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!subscription) {
    return (
      <div className="space-y-6" dir="rtl">
        <div>
          <h1 className="text-2xl font-bold">اشتراک من</h1>
          <p className="text-muted-foreground mt-1">وضعیت اشتراک و لیمیت‌های مصرف</p>
        </div>

        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
            <Wallet className="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 className="text-lg font-semibold mb-2">اشتراکی ندارید</h2>
          <p className="text-muted-foreground mb-6">
            برای استفاده از تمام امکانات، یک پلن اشتراک انتخاب کنید
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => onNavigate('plans')}
              className="px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90"
            >
              مشاهده پلن‌ها
            </button>
            <button
              onClick={handleClaimTrial}
              className="px-6 py-2.5 bg-muted border border-border rounded-lg hover:bg-muted/80"
            >
              دریافت دوره آزمایشی
            </button>
          </div>
        </div>

        {billingAccount && (
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">موجودی کیف پول:</span>
              <span className="text-lg font-semibold">{formatToman(billingAccount.total_balance_toman)} تومان</span>
            </div>
            <button
              onClick={() => onNavigate('billing')}
              className="mt-3 text-sm text-primary hover:underline"
            >
              شارژ کیف پول
            </button>
          </div>
        )}
      </div>
    );
  }

  const isInCooldown = subscription.is_in_cooldown;
  const isWeeklyLimitReached = subscription.weekly_limit_toman > 0 && subscription.weekly_spent_toman >= subscription.weekly_limit_toman;

  return (
    <div className="space-y-6" dir="rtl">
      <div>
        <h1 className="text-2xl font-bold">اشتراک من</h1>
        <p className="text-muted-foreground mt-1">وضعیت اشتراک و لیمیت‌های مصرف</p>
      </div>

      {isInCooldown && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            <h3 className="font-semibold text-amber-800 dark:text-amber-200">لیمیت مصرف رسیدید</h3>
          </div>
          <p className="text-amber-700 dark:text-amber-300 mb-4">
            {cooldownRemaining !== null
              ? `زمان باقی‌مانده تا باز شدن مجدد: ${formatTime(cooldownRemaining)}`
              : 'در حال محاسبه زمان باقی‌مانده...'}
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleCheckPermission}
              disabled={checkingPermission}
              className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 flex items-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${checkingPermission ? 'animate-spin' : ''}`} />
              بررسی مجدد
            </button>
            <button
              onClick={() => onNavigate('plans')}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
            >
              ارتقای پلن
            </button>
            <button
              onClick={() => onNavigate('billing')}
              className="px-4 py-2 bg-muted border border-border rounded-lg hover:bg-muted/80"
            >
              شارژ حساب
            </button>
          </div>
        </div>
      )}

      {permissionResult && !permissionResult.can_chat && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-5">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <div>
              <h3 className="font-semibold text-red-800 dark:text-red-200">امکان چت وجود ندارد</h3>
              <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                {permissionResult.reason === 'cooldown_limit_reached' && 'سقف مصرف پلن رسیده‌اید'}
                {permissionResult.reason === 'weekly_limit_reached' && 'سقف هفتگی رسیده‌اید'}
                {permissionResult.reason === 'insufficient_toman_credit' && 'موجودی کافی نیست'}
              </p>
            </div>
          </div>
        </div>
      )}

      {permissionResult?.can_chat && (
        <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <Check className="w-5 h-5" />
            <span>می‌توانید چت کنید</span>
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-6">
          <Zap className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-xl font-semibold">{subscription.plan_name}</h2>
            <p className="text-sm text-muted-foreground">
              {subscription.is_active_now ? (
                <span className="text-emerald-600">فعال</span>
              ) : (
                <span className="text-red-600">غیرفعال</span>
              )}
            </p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <Calendar className="w-5 h-5 text-muted-foreground" />
            <div>
              <div className="text-sm text-muted-foreground">تاریخ انقضا</div>
              <div className="font-medium">{formatDate(subscription.expires_at)}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <Wallet className="w-5 h-5 text-muted-foreground" />
            <div>
              <div className="text-sm text-muted-foreground">نوع پلن</div>
              <div className="font-medium">{subscription.plan_type === 'tiered_cooldown' ? 'پلکانی' : 'ماهانه'}</div>
            </div>
          </div>
        </div>
      </div>

      {subscription.plan_type === 'tiered_cooldown' && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">لیمیت‌های مصرف</h3>
          <div className="space-y-4">
            {subscription.cooldown_limit_toman > 0 && (
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span>سقف هر دوره</span>
                  <span>{formatToman(subscription.cooldown_spent_toman)} / {formatToman(subscription.cooldown_limit_toman)} تومان</span>
                </div>
                <div className="w-full bg-muted rounded-full h-2.5">
                  <div
                    className="bg-amber-500 h-2.5 rounded-full transition-all"
                    style={{ width: `${Math.min(100, (subscription.cooldown_spent_toman / subscription.cooldown_limit_toman) * 100)}%` }}
                  />
                </div>
              </div>
            )}
            {subscription.weekly_limit_toman > 0 && (
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span>سقف هفتگی</span>
                  <span>{formatToman(subscription.weekly_spent_toman)} / {formatToman(subscription.weekly_limit_toman)} تومان</span>
                </div>
                <div className="w-full bg-muted rounded-full h-2.5">
                  <div
                    className={`h-2.5 rounded-full transition-all ${isWeeklyLimitReached ? 'bg-red-500' : 'bg-blue-500'}`}
                    style={{ width: `${Math.min(100, (subscription.weekly_spent_toman / subscription.weekly_limit_toman) * 100)}%` }}
                  />
                </div>
                {subscription.week_resets_at && (
                  <div className="text-xs text-muted-foreground mt-1">
                    ریست هفتگی: {formatDate(subscription.week_resets_at)}
                  </div>
                )}
              </div>
            )}
            {subscription.cooldown_hours > 0 && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="w-4 h-4" />
                <span>مدت cooldown: {subscription.cooldown_hours} ساعت</span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => onNavigate('plans')}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
        >
          تغییر پلن
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
