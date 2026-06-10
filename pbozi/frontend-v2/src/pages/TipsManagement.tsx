import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getTips,
  createTip,
  updateTip,
  deleteTip,
  getTipDeliveryLogs,
} from '../lib/api';
import {
  Tip,
  TipCreate,
  TipUpdate,
} from '../lib/types';
import {
  Lightbulb,
  Plus,
  RefreshCcw,
  X,
  Edit,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Clock,
  Calendar,
  History,
  User,
} from 'lucide-react';

const TIP_TYPE_LABELS: Record<string, string> = {
  event: 'رویداد-محور (Event)',
  scheduled: 'زمان‌بندی شده (Scheduled)',
};

const TipsManagement = () => {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingTip, setEditingTip] = useState<Tip | null>(null);
  const [view, setView] = useState<'tips' | 'logs'>('tips');

  const { data: tips, isLoading: tipsLoading } = useQuery<Tip[]>({
    queryKey: ['tips'],
    queryFn: getTips,
    enabled: view === 'tips',
  });

  const { data: logs, isLoading: logsLoading } = useQuery<any[]>({
    queryKey: ['tip-delivery-logs'],
    queryFn: getTipDeliveryLogs,
    enabled: view === 'logs',
  });

  const createMutation = useMutation({
    mutationFn: createTip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tips'] });
      setShowCreateModal(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: TipUpdate }) =>
      updateTip(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tips'] });
      setEditingTip(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tips'] });
    },
  });

  const handleCreate = (data: TipCreate) => {
    createMutation.mutate(data);
  };

  const handleUpdate = (id: number, data: TipUpdate) => {
    updateMutation.mutate({ id, data });
  };

  const handleDelete = (id: number) => {
    if (confirm('آیا از حذف این راهنما مطمئن هستید؟')) {
      deleteMutation.mutate(id);
    }
  };

  const toggleActive = (tip: Tip) => {
    updateMutation.mutate({ id: tip.id, data: { is_active: !tip.is_active } });
  };

  const toTehranTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('fa-IR', { timeZone: 'Asia/Tehran' });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">مدیریت راهنماها (Tips)</h1>
          <p className="text-muted-foreground">
            ایجاد و مدیریت پیام‌های راهنمای هوشمند برای کاربران ربات.
          </p>
        </div>
        <div className="flex gap-2">
          <div className="bg-muted p-1 rounded-lg flex gap-1 mr-4">
            <button
              onClick={() => setView('tips')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                view === 'tips' ? 'bg-background shadow-sm' : 'hover:text-foreground'
              }`}
            >
              لیست راهنماها
            </button>
            <button
              onClick={() => setView('logs')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                view === 'logs' ? 'bg-background shadow-sm' : 'hover:text-foreground'
              }`}
            >
              تاریخچه ارسال
            </button>
          </div>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: view === 'tips' ? ['tips'] : ['tip-delivery-logs'] })}
            className="flex items-center px-4 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
          >
            <RefreshCcw className="w-4 h-4 mr-2" />
            بروزرسانی
          </button>
          {view === 'tips' && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4 mr-2" />
              افزودن راهنما
            </button>
          )}
        </div>
      </div>

      {view === 'tips' ? (
        tipsLoading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-muted-foreground">در حال بارگذاری...</p>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">شناسه / کلید</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">نوع</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">محتوا</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">وضعیت</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tips?.map((tip) => (
                  <tr key={tip.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs text-primary font-bold">{tip.trigger_key}</div>
                      <div className="text-[10px] text-muted-foreground">ID: {tip.id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 text-sm">
                        {tip.tip_type === 'event' ? <Clock className="w-3 h-3" /> : <Calendar className="w-3 h-3" />}
                        <span>{TIP_TYPE_LABELS[tip.tip_type]}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm line-clamp-2 max-w-md" dir="rtl">
                        {tip.content}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => toggleActive(tip)}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium transition-colors ${
                          tip.is_active
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                      >
                        {tip.is_active ? (
                          <>
                            <ToggleRight className="w-4 h-4" /> فعال
                          </>
                        ) : (
                          <>
                            <ToggleLeft className="w-4 h-4" /> غیرفعال
                          </>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-left">
                      <div className="flex items-center justify-start gap-1">
                        <button
                          onClick={() => setEditingTip(tip)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                          title="ویرایش"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(tip.id)}
                          className="p-1.5 rounded-lg hover:bg-muted transition-colors text-destructive"
                          title="حذف"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {tips?.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                      هیچ راهنمایی یافت نشد. برای شروع یکی بسازید.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )
      ) : (
        logsLoading ? (
          <div className="flex items-center justify-center h-64">
            <p className="text-muted-foreground">در حال بارگذاری تاریخچه...</p>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
            <table className="w-full">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">کاربر</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">کلید راهنما</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">نوع</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-muted-foreground">زمان ارسال</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {logs?.map((log) => (
                  <tr key={log.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-muted-foreground" />
                        <div>
                          <div className="font-medium text-sm">{log.first_name || 'بدون نام'}</div>
                          <div className="text-[10px] text-muted-foreground">@{log.username || '---'} (UID: {log.user_id})</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full">
                        {log.trigger_key}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {log.tip_type === 'event' ? 'رویدادی' : 'زمان‌بندی'}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {toTehranTime(log.delivered_at)}
                    </td>
                  </tr>
                ))}
                {logs?.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">
                      تاریخچه ارسالی یافت نشد.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )
      )}

      {(showCreateModal || editingTip) && (
        <CreateEditModal
          tip={editingTip}
          onClose={() => {
            setShowCreateModal(false);
            setEditingTip(null);
          }}
          onSubmit={(data) => {
            if (editingTip) {
              handleUpdate(editingTip.id, data);
            } else {
              handleCreate(data as TipCreate);
            }
          }}
          isPending={createMutation.isPending || updateMutation.isPending}
        />
      )}
    </div>
  );
};

interface CreateEditModalProps {
  tip?: Tip | null;
  onClose: () => void;
  onSubmit: (data: TipCreate | TipUpdate) => void;
  isPending: boolean;
}

const CreateEditModal: React.FC<CreateEditModalProps> = ({ tip, onClose, onSubmit, isPending }) => {
  const [triggerKey, setTriggerKey] = useState(tip?.trigger_key || '');
  const [tipType, setTipType] = useState<'event' | 'scheduled'>(tip?.tip_type || 'event');
  const [content, setContent] = useState(tip?.content || '');
  const [isActive, setIsActive] = useState(tip?.is_active ?? true);
  const [delaySeconds, setDelaySeconds] = useState(tip?.delay_seconds || 0);
  const [autoDeleteSeconds, setAutoDeleteSeconds] = useState(tip?.auto_delete_seconds || 30);
  const [minAccountAgeDays, setMinAccountAgeDays] = useState(tip?.min_account_age_days || 0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      trigger_key: triggerKey,
      tip_type: tipType,
      content,
      is_active: isActive,
      delay_seconds: delaySeconds,
      auto_delete_seconds: autoDeleteSeconds,
      min_account_age_days: minAccountAgeDays,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" dir="rtl">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg mx-4 shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold">{tip ? 'ویرایش راهنما' : 'ایجاد راهنمای جدید'}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-muted transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2 text-right">
              <label className="text-sm font-medium">کلید فراخوانی (Trigger Key)</label>
              <input
                type="text"
                value={triggerKey}
                onChange={(e) => setTriggerKey(e.target.value)}
                placeholder="مثلا: model_menu"
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 font-mono text-sm"
                required
                dir="ltr"
              />
            </div>
            <div className="space-y-2 text-right">
              <label className="text-sm font-medium">نوع راهنما</label>
              <select
                value={tipType}
                onChange={(e) => setTipType(e.target.value as 'event' | 'scheduled')}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="event">رویداد-محور (پس از اکشن کاربر)</option>
                <option value="scheduled">زمان‌بندی شده (هوشمند)</option>
              </select>
            </div>
          </div>

          <div className="bg-primary/5 p-3 rounded-lg border border-primary/10 text-right">
            <p className="text-[10px] font-bold text-primary mb-1">لیست کلیدهای استاندارد:</p>
            <div className="flex flex-wrap gap-1 justify-end">
              {['model_menu', 'new_chat', 'projects', 'account', 'plans', 'topup', 'daily_tip'].map(key => (
                <button 
                  key={key}
                  type="button"
                  onClick={() => setTriggerKey(key)}
                  className="text-[10px] px-1.5 py-0.5 bg-background border border-border rounded hover:border-primary transition-colors font-mono"
                >
                  {key}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2 text-right">
            <label className="text-sm font-medium">محتوای راهنما (متن پیام)</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="چیزی بنویسید که به کاربر کمک کند..."
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none min-h-[100px]"
              required
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2 text-right">
              <label className="text-xs font-medium">تاخیر ارسال (ثانیه)</label>
              <input
                type="number"
                value={delaySeconds}
                onChange={(e) => setDelaySeconds(Number(e.target.value))}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                min={0}
              />
            </div>
            <div className="space-y-2 text-right">
              <label className="text-xs font-medium">حذف خودکار (ثانیه)</label>
              <input
                type="number"
                value={autoDeleteSeconds}
                onChange={(e) => setAutoDeleteSeconds(Number(e.target.value))}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                min={0}
              />
            </div>
            <div className="space-y-2 text-right">
              <label className="text-xs font-medium">حداقل سن اکانت (روز)</label>
              <input
                type="number"
                value={minAccountAgeDays}
                onChange={(e) => setMinAccountAgeDays(Number(e.target.value))}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                min={0}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <input
              type="checkbox"
              id="is_active"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 text-primary rounded border-border"
            />
            <label htmlFor="is_active" className="text-sm font-medium cursor-pointer">
              این راهنما فعال باشد
            </label>
          </div>

          <div className="flex gap-2 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
            >
              انصراف
            </button>
            <button
              type="submit"
              disabled={isPending || !triggerKey || !content}
              className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isPending ? 'در حال ذخیره...' : tip ? 'بروزرسانی' : 'ایجاد راهنما'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default TipsManagement;
