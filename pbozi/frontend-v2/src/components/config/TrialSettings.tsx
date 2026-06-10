import React, { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Gift, Save, Clock, Info, CheckCircle2, AlertCircle } from 'lucide-react';
import { getTrialConfig, updateTrialConfig, getSubscriptionPlans } from '../../lib/api';
import { TrialConfig, SubscriptionPlan } from '../../lib/types';

export function TrialSettings() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    plan_id: '',
    duration_hours: '',
    is_enabled: false,
    apply_automatically: false,
    welcome_message: '',
    invitation_message: '',
    invitation_button_text: '',
  });

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['trialConfig'],
    queryFn: getTrialConfig,
  });

  const { data: plans, isLoading: plansLoading } = useQuery({
    queryKey: ['subscriptionPlans'],
    queryFn: getSubscriptionPlans,
  });

  useEffect(() => {
    if (config) {
      setForm({
        plan_id: config.plan_id ? String(config.plan_id) : '',
        duration_hours: String(config.duration_hours),
        is_enabled: config.is_enabled,
        apply_automatically: config.apply_automatically,
        welcome_message: config.welcome_message || '',
        invitation_message: config.invitation_message || '',
        invitation_button_text: config.invitation_button_text || '',
      });
    }
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: any) => updateTrialConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trialConfig'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      plan_id: form.plan_id ? parseInt(form.plan_id, 10) : null,
      duration_hours: parseInt(form.duration_hours, 10) || 0,
      is_enabled: form.is_enabled,
      apply_automatically: form.apply_automatically,
      welcome_message: form.welcome_message,
      invitation_message: form.invitation_message,
      invitation_button_text: form.invitation_button_text,
    });
  };

  const updateField = (key: keyof typeof form, value: any) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  if (configLoading || plansLoading) {
    return <div className="flex justify-center p-8">در حال بارگذاری...</div>;
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">تنظیمات دوره آزمایشی (Trial)</h2>
          <p className="text-sm text-muted-foreground">مدیریت نحوه تخصیص اشتراک رایگان موقت به کاربران جدید</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="p-4 bg-card border border-border rounded-xl space-y-4 shadow-sm">
              <div className="flex items-center gap-2 text-primary">
                <Gift className="w-5 h-5" />
                <h3 className="text-sm font-bold">پیکربندی اصلی</h3>
              </div>

              <div className="space-y-4">
                <label className="block">
                  <span className="block text-xs font-medium mb-1">پلن اشتراک آزمایشی</span>
                  <select
                    value={form.plan_id}
                    onChange={(e) => updateField('plan_id', e.target.value)}
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                  >
                    <option value="">انتخاب پلن...</option>
                    {plans?.filter(p => p.is_active).map((plan) => (
                      <option key={plan.id} value={plan.id}>
                        {plan.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-muted-foreground mt-1">این پلن برای دوره آزمایشی به کاربر اختصاص داده می‌شود.</p>
                </label>

                <label className="block">
                  <span className="block text-xs font-medium mb-1">مدت زمان (ساعت)</span>
                  <div className="flex items-center bg-muted border border-border rounded-lg overflow-hidden">
                    <input
                      type="number"
                      min="1"
                      value={form.duration_hours}
                      onChange={(e) => updateField('duration_hours', e.target.value)}
                      className="w-full bg-transparent py-2 px-3 text-sm focus:outline-none"
                    />
                    <div className="px-3 border-r border-border text-muted-foreground">
                      <Clock className="w-4 h-4" />
                    </div>
                  </div>
                </label>
              </div>
            </div>

            <div className="p-4 bg-card border border-border rounded-xl space-y-4 shadow-sm">
              <div className="flex items-center gap-2 text-primary">
                <Info className="w-5 h-5" />
                <h3 className="text-sm font-bold">وضعیت و قوانین</h3>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors">
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium">فعال‌سازی سیستم Trial</div>
                    <div className="text-xs text-muted-foreground">اجازه استفاده از سیستم دوره آزمایشی</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => updateField('is_enabled', !form.is_enabled)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                      form.is_enabled ? 'bg-primary' : 'bg-muted-foreground/30'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        form.is_enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                <div className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors">
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium">اعمال خودکار</div>
                    <div className="text-xs text-muted-foreground">تخصیص خودکار به کاربران جدید هنگام عضویت</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => updateField('apply_automatically', !form.apply_automatically)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                      form.apply_automatically ? 'bg-primary' : 'bg-muted-foreground/30'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        form.apply_automatically ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="p-4 bg-card border border-border rounded-xl space-y-4 shadow-sm h-full flex flex-col">
              <div className="flex items-center gap-2 text-primary">
                <Info className="w-5 h-5" />
                <h3 className="text-sm font-bold">اطلاع‌رسانی</h3>
              </div>

              <div className="space-y-4 flex-1">
                <label className="block">
                  <span className="block text-xs font-medium mb-1">پیام خوش‌آمدگویی Trial</span>
                  <textarea
                    value={form.welcome_message}
                    onChange={(e) => updateField('welcome_message', e.target.value)}
                    placeholder="تبریک! اشتراک آزمایشی ۴۸ ساعته برای شما فعال شد..."
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all min-h-[100px]"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">این پیام پس از فعال‌سازی اشتراک آزمایشی برای کاربر ارسال می‌شود.</p>
                </label>

                <label className="block">
                  <span className="block text-xs font-medium mb-1">متن پیام دعوت‌نامه</span>
                  <textarea
                    value={form.invitation_message}
                    onChange={(e) => updateField('invitation_message', e.target.value)}
                    placeholder="🎁 اشتراک تست ۲۴ ساعته رایگان برای شما فعال نشده است. آیا می‌خواهید آن را فعال کنید؟"
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all min-h-[100px]"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">این پیام هنگام ارسال دعوت‌نامه اشتراک رایگان به کاربران استفاده می‌شود.</p>
                </label>

                <label className="block">
                  <span className="block text-xs font-medium mb-1">متن دکمه فعال‌سازی</span>
                  <input
                    type="text"
                    value={form.invitation_button_text}
                    onChange={(e) => updateField('invitation_button_text', e.target.value)}
                    placeholder="فعال‌سازی اشتراک رایگان"
                    className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">متنی که روی دکمه فعال‌سازی در پیام دعوت‌نامه نمایش داده می‌شود.</p>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl">
          <div className="flex items-center gap-3">
            {mutation.isSuccess ? (
              <div className="flex items-center gap-2 text-green-500 text-sm font-medium animate-in fade-in">
                <CheckCircle2 className="w-4 h-4" />
                <span>تنظیمات با موفقیت ذخیره شد</span>
              </div>
            ) : mutation.isError ? (
              <div className="flex items-center gap-2 text-destructive text-sm font-medium animate-in fade-in">
                <AlertCircle className="w-4 h-4" />
                <span>خطا در ذخیره‌سازی تنظیمات</span>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">آخرین بروزرسانی: {config?.updated_at ? new Date(config.updated_at).toLocaleString('fa-IR') : 'هرگز'}</div>
            )}
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg text-sm font-bold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            <span>{mutation.isPending ? 'در حال ذخیره...' : 'ذخیره تنظیمات'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
