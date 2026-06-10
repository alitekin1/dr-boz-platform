import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getUserBillingAccount, getTopupQuote, applyTopup, getUserLedger, getUserPaymentMethods, createUserPaymentRequest, getUserPaymentRequests } from '../../lib/api';
import { LedgerEntry, TopupQuote, PaymentMethod, PaymentRequest } from '../../lib/types';
import { Wallet, ArrowUpRight, Clock, Receipt, AlertCircle, Check, CreditCard, Upload, FileImage } from 'lucide-react';

interface UserBillingPageProps {
  telegramUserId: number;
}

const ENTRY_TYPE_LABELS: Record<string, string> = {
  subscription_payment: 'خرید اشتراک',
  subscription_gift_credit: 'اعتبار هدیه',
  paid_topup_credit: 'شارژ کیف پول',
  chat_completion_usage: 'مصرف چت',
  first_topup_discount_used: 'تخفیف اولین شارژ',
  admin_adjustment: 'تعدیل ادمین',
  manual_payment: 'پرداخت دستی',
};

const PAYMENT_STATUS_LABELS: Record<string, string> = {
  pending: 'در انتظار بررسی',
  approved: 'تأیید شده',
  rejected: 'رد شده',
};

const PAYMENT_STATUS_COLORS: Record<string, string> = {
  pending: 'text-yellow-600 bg-yellow-50',
  approved: 'text-green-600 bg-green-50',
  rejected: 'text-red-600 bg-red-50',
};

export default function UserBillingPage({ telegramUserId }: UserBillingPageProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'wallet' | 'manual'>('wallet');
  const [topupAmount, setTopupAmount] = useState('');
  const [topupQuote, setTopupQuote] = useState<TopupQuote | null>(null);
  const [topupError, setTopupError] = useState<string | null>(null);
  const [topupSuccess, setTopupSuccess] = useState(false);

  const [manualAmount, setManualAmount] = useState('');
  const [manualDescription, setManualDescription] = useState('');
  const [manualReceipt, setManualReceipt] = useState<File | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState(false);

  const { data: billingAccount, isLoading: billingLoading } = useQuery({
    queryKey: ['user-billing', telegramUserId],
    queryFn: () => getUserBillingAccount(telegramUserId),
    enabled: !!telegramUserId,
  });

  const { data: ledger, isLoading: ledgerLoading } = useQuery({
    queryKey: ['user-ledger', telegramUserId],
    queryFn: () => getUserLedger(telegramUserId, 20),
    enabled: !!telegramUserId,
  });

  const { data: paymentMethods, isLoading: methodsLoading } = useQuery({
    queryKey: ['user-payment-methods'],
    queryFn: getUserPaymentMethods,
  });

  const { data: userPaymentRequests, isLoading: requestsLoading } = useQuery({
    queryKey: ['user-payment-requests', telegramUserId],
    queryFn: () => getUserPaymentRequests(telegramUserId, 20),
    enabled: !!telegramUserId,
  });

  const quoteMutation = useMutation({
    mutationFn: (amount: number) => getTopupQuote(telegramUserId, amount),
    onSuccess: (data) => {
      setTopupQuote(data);
      setTopupError(null);
    },
    onError: () => {
      setTopupError('خطا در استعلام قیمت');
      setTopupQuote(null);
    },
  });

  const topupMutation = useMutation({
    mutationFn: (amount: number) => applyTopup(telegramUserId, amount),
    onSuccess: () => {
      setTopupSuccess(true);
      setTopupError(null);
      setTopupAmount('');
      setTopupQuote(null);
      queryClient.invalidateQueries({ queryKey: ['user-billing', telegramUserId] });
      queryClient.invalidateQueries({ queryKey: ['user-ledger', telegramUserId] });
      setTimeout(() => setTopupSuccess(false), 5000);
    },
    onError: (err: any) => {
      setTopupError(err.response?.data?.detail || 'خطا در شارژ کیف پول');
      setTopupSuccess(false);
    },
  });

  const manualPaymentMutation = useMutation({
    mutationFn: ({ amount, receipt, description }: { amount: number; receipt: File; description?: string }) =>
      createUserPaymentRequest(telegramUserId, amount, receipt, description),
    onSuccess: () => {
      setManualSuccess(true);
      setManualError(null);
      setManualAmount('');
      setManualDescription('');
      setManualReceipt(null);
      queryClient.invalidateQueries({ queryKey: ['user-payment-requests', telegramUserId] });
      setTimeout(() => setManualSuccess(false), 5000);
    },
    onError: (err: any) => {
      setManualError(err.response?.data?.detail || 'خطا در ثبت درخواست پرداخت');
      setManualSuccess(false);
    },
  });

  const handleQuote = () => {
    const amount = parseInt(topupAmount);
    if (amount > 0) {
      quoteMutation.mutate(amount);
    }
  };

  const handleTopup = () => {
    if (topupQuote) {
      topupMutation.mutate(topupQuote.credit_amount_toman);
    }
  };

  const handleManualPayment = () => {
    const amount = parseInt(manualAmount);
    if (!amount || amount <= 0) {
      setManualError('لطفاً مبلغ معتبر وارد کنید');
      return;
    }
    if (!manualReceipt) {
      setManualError('لطفاً تصویر رسید را آپلود کنید');
      return;
    }
    manualPaymentMutation.mutate({ amount, receipt: manualReceipt, description: manualDescription || undefined });
  };

  const formatToman = (amount: number) => new Intl.NumberFormat('fa-IR').format(amount);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('fa-IR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (billingLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6" dir="rtl">
      <div>
        <h1 className="text-2xl font-bold">کیف پول</h1>
        <p className="text-muted-foreground mt-1">مدیریت موجودی و شارژ حساب</p>
      </div>

      {billingAccount && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <Wallet className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-muted-foreground">موجودی هدیه</span>
            </div>
            <div className="text-2xl font-bold">{formatToman(billingAccount.gift_balance_toman)}</div>
            <div className="text-sm text-muted-foreground">تومان</div>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <Wallet className="w-5 h-5 text-emerald-500" />
              <span className="text-sm text-muted-foreground">موجودی پرداختی</span>
            </div>
            <div className="text-2xl font-bold">{formatToman(billingAccount.paid_balance_toman)}</div>
            <div className="text-sm text-muted-foreground">تومان</div>
          </div>
          <div className="bg-card border border-border rounded-xl p-5 bg-primary/5">
            <div className="flex items-center gap-2 mb-2">
              <Wallet className="w-5 h-5 text-primary" />
              <span className="text-sm text-muted-foreground">مجموع</span>
            </div>
            <div className="text-2xl font-bold text-primary">{formatToman(billingAccount.total_balance_toman)}</div>
            <div className="text-sm text-muted-foreground">تومان</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 border-b border-border">
        <button
          onClick={() => setActiveTab('wallet')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'wallet' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <Wallet className="w-4 h-4 inline ml-1" />
          شارژ آنلاین
        </button>
        <button
          onClick={() => setActiveTab('manual')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'manual' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <CreditCard className="w-4 h-4 inline ml-1" />
          پرداخت کارت به کارت
        </button>
      </div>

      {activeTab === 'wallet' && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">شارژ کیف پول</h2>
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-sm text-muted-foreground mb-1">مبلغ شارژ (تومان)</label>
              <input
                type="number"
                value={topupAmount}
                onChange={(e) => setTopupAmount(e.target.value)}
                placeholder="مثلاً 500000"
                className="w-full px-4 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            <button
              onClick={handleQuote}
              disabled={quoteMutation.isPending || !topupAmount}
              className="px-4 py-2 bg-muted border border-border rounded-lg hover:bg-muted/80 disabled:opacity-50"
            >
              استعلام قیمت
            </button>
          </div>

          {topupQuote && (
            <div className="mt-4 p-4 bg-muted rounded-lg space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">اعتبار دریافتی:</span>
                <span className="font-semibold">{formatToman(topupQuote.credit_amount_toman)} تومان</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">مبلغ قابل پرداخت:</span>
                <span className="font-semibold text-primary">{formatToman(topupQuote.payment_due_toman)} تومان</span>
              </div>
              {topupQuote.discount_applied && (
                <div className="flex justify-between text-emerald-600">
                  <span>تخفیف:</span>
                  <span>{formatToman(topupQuote.discount_toman)} تومان-</span>
                </div>
              )}
              <button
                onClick={handleTopup}
                disabled={topupMutation.isPending}
                className="w-full mt-3 py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50"
              >
                {topupMutation.isPending ? 'در حال شارژ...' : 'تأیید و شارژ'}
              </button>
            </div>
          )}

          {topupSuccess && (
            <div className="mt-4 flex items-center gap-2 text-emerald-600">
              <Check className="w-5 h-5" />
              <span>کیف پول با موفقیت شارژ شد!</span>
            </div>
          )}

          {topupError && (
            <div className="mt-4 flex items-center gap-2 text-red-600">
              <AlertCircle className="w-5 h-5" />
              <span>{topupError}</span>
            </div>
          )}
        </div>
      )}

      {activeTab === 'manual' && (
        <div className="space-y-6">
          {methodsLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : paymentMethods && paymentMethods.length > 0 ? (
            <div className="bg-card border border-border rounded-xl p-6">
              <h2 className="text-lg font-semibold mb-4">شماره کارت‌های مقصد</h2>
              <div className="grid gap-3 md:grid-cols-2">
                {paymentMethods.map((method: PaymentMethod) => (
                  <div key={method.id} className="bg-muted rounded-lg p-4 border border-border">
                    <div className="flex items-center gap-2 mb-2">
                      <CreditCard className="w-5 h-5 text-primary" />
                      <span className="font-mono text-lg font-semibold tracking-wider">{method.card_number}</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      <div>صاحب کارت: <span className="text-foreground">{method.cardholder_name}</span></div>
                      <div>بانک: <span className="text-foreground">{method.bank_name}</span></div>
                      {method.description && <div className="mt-1 text-xs">{method.description}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
              شماره کارتی برای پرداخت ثبت نشده است
            </div>
          )}

          {paymentMethods && paymentMethods.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-6">
              <h2 className="text-lg font-semibold mb-4">ثبت درخواست پرداخت</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">مبلغ پرداختی (تومان)</label>
                  <input
                    type="number"
                    value={manualAmount}
                    onChange={(e) => setManualAmount(e.target.value)}
                    placeholder="مثلاً 500000"
                    className="w-full px-4 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">تصویر رسید پرداخت</label>
                  <div className="relative">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0] || null;
                        setManualReceipt(file);
                      }}
                      className="hidden"
                      id="receipt-upload"
                    />
                    <label
                      htmlFor="receipt-upload"
                      className="flex items-center justify-center gap-2 w-full px-4 py-8 bg-muted border-2 border-dashed border-border rounded-lg cursor-pointer hover:bg-muted/80 transition-colors"
                    >
                      {manualReceipt ? (
                        <>
                          <FileImage className="w-5 h-5 text-emerald-500" />
                          <span className="text-emerald-600 font-medium">{manualReceipt.name}</span>
                        </>
                      ) : (
                        <>
                          <Upload className="w-5 h-5 text-muted-foreground" />
                          <span className="text-muted-foreground">انتخاب تصویر رسید</span>
                        </>
                      )}
                    </label>
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">توضیحات (اختیاری)</label>
                  <textarea
                    value={manualDescription}
                    onChange={(e) => setManualDescription(e.target.value)}
                    placeholder="توضیحات اضافی..."
                    className="w-full px-4 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    rows={2}
                  />
                </div>
                <button
                  onClick={handleManualPayment}
                  disabled={manualPaymentMutation.isPending}
                  className="w-full py-2.5 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50"
                >
                  {manualPaymentMutation.isPending ? 'در حال ارسال...' : 'ارسال درخواست پرداخت'}
                </button>
              </div>

              {manualSuccess && (
                <div className="mt-4 flex items-center gap-2 text-emerald-600">
                  <Check className="w-5 h-5" />
                  <span>درخواست پرداخت با موفقیت ثبت شد!</span>
                </div>
              )}

              {manualError && (
                <div className="mt-4 flex items-center gap-2 text-red-600">
                  <AlertCircle className="w-5 h-5" />
                  <span>{manualError}</span>
                </div>
              )}
            </div>
          )}

          {userPaymentRequests && userPaymentRequests.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Receipt className="w-5 h-5" />
                درخواست‌های پرداخت من
              </h2>
              <div className="space-y-2">
                {userPaymentRequests.map((req: PaymentRequest) => (
                  <div
                    key={req.id}
                    className="flex items-center justify-between py-3 border-b border-border last:border-0"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`px-2 py-1 text-xs font-medium rounded-full ${PAYMENT_STATUS_COLORS[req.status] || ''}`}>
                        {PAYMENT_STATUS_LABELS[req.status] || req.status}
                      </div>
                      <div>
                        <div className="font-medium text-sm">{formatToman(req.amount_toman)} تومان</div>
                        {req.description && (
                          <div className="text-xs text-muted-foreground">{req.description}</div>
                        )}
                        {req.status === 'rejected' && req.admin_note && (
                          <div className="text-xs text-red-600 mt-1">دلیل رد: {req.admin_note}</div>
                        )}
                      </div>
                    </div>
                    <div className="text-left">
                      <div className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(req.created_at)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Receipt className="w-5 h-5" />
          تاریخچه تراکنش‌ها
        </h2>

        {ledgerLoading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
          </div>
        ) : ledger && ledger.length > 0 ? (
          <div className="space-y-2">
            {ledger.map((entry: LedgerEntry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between py-3 border-b border-border last:border-0"
              >
                <div className="flex items-center gap-3">
                  {entry.amount_toman > 0 ? (
                    <ArrowUpRight className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <ArrowUpRight className="w-4 h-4 text-red-500 rotate-180" />
                  )}
                  <div>
                    <div className="font-medium text-sm">
                      {ENTRY_TYPE_LABELS[entry.entry_type] || entry.entry_type}
                    </div>
                    {entry.reason && (
                      <div className="text-xs text-muted-foreground">{entry.reason}</div>
                    )}
                  </div>
                </div>
                <div className="text-left">
                  <div className={`font-semibold text-sm ${entry.amount_toman > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {entry.amount_toman > 0 ? '+' : ''}{formatToman(Math.abs(entry.amount_toman))} تومان
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(entry.created_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">تراکنشی وجود ندارد</div>
        )}
      </div>
    </div>
  );
}
