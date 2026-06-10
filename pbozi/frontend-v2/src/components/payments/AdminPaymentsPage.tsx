import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPaymentMethods,
  createPaymentMethod,
  updatePaymentMethod,
  deletePaymentMethod,
  getPaymentRequests,
  approvePaymentRequest,
  rejectPaymentRequest,
} from '../../lib/api';
import { PaymentMethod, PaymentRequest } from '../../lib/types';
import { CreditCard, Check, X, Clock, Upload, Eye, DollarSign, AlertCircle } from 'lucide-react';

export default function AdminPaymentsPage() {
  const [activeTab, setActiveTab] = useState<'methods' | 'requests'>('methods');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showForm, setShowForm] = useState(false);
  const [editingMethod, setEditingMethod] = useState<PaymentMethod | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<PaymentRequest | null>(null);
  const [adminNote, setAdminNote] = useState('');

  const queryClient = useQueryClient();

  const { data: methods, isLoading: methodsLoading } = useQuery({
    queryKey: ['payment-methods'],
    queryFn: getPaymentMethods,
  });

  const { data: requests, isLoading: requestsLoading } = useQuery({
    queryKey: ['payment-requests', filterStatus],
    queryFn: () => getPaymentRequests(filterStatus === 'all' ? undefined : filterStatus),
  });

  const createMutation = useMutation({
    mutationFn: createPaymentMethod,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] });
      setShowForm(false);
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => updatePaymentMethod(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] });
      setShowForm(false);
      setEditingMethod(null);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deletePaymentMethod,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) => approvePaymentRequest(id, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-requests'] });
      setSelectedRequest(null);
      setAdminNote('');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) => rejectPaymentRequest(id, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-requests'] });
      setSelectedRequest(null);
      setAdminNote('');
    },
  });

  const [formData, setFormData] = useState({
    card_number: '',
    cardholder_name: '',
    bank_name: '',
    description: '',
    sort_order: 0,
  });

  const resetForm = () => {
    setFormData({ card_number: '', cardholder_name: '', bank_name: '', description: '', sort_order: 0 });
  };

  const handleEdit = (method: PaymentMethod) => {
    setEditingMethod(method);
    setFormData({
      card_number: method.card_number,
      cardholder_name: method.cardholder_name,
      bank_name: method.bank_name,
      description: method.description || '',
      sort_order: method.sort_order,
    });
    setShowForm(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingMethod) {
      updateMutation.mutate({ id: editingMethod.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
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

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
      approved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
      rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    };
    const labels: Record<string, string> = {
      pending: 'در انتظار',
      approved: 'تأیید شده',
      rejected: 'رد شده',
    };
    return (
      <span className={`px-2 py-1 text-xs font-medium rounded-full ${styles[status] || ''}`}>
        {labels[status] || status}
      </span>
    );
  };

  const pendingCount = requests?.filter(r => r.status === 'pending').length || 0;

  return (
    <div className="space-y-6" dir="rtl">
      <div>
        <h1 className="text-2xl font-bold">پرداخت‌ها</h1>
        <p className="text-muted-foreground mt-1">مدیریت شماره کارت‌ها و درخواست‌های پرداخت دستی</p>
      </div>

      <div className="flex gap-2 border-b border-border">
        <button
          onClick={() => setActiveTab('methods')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'methods' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <CreditCard className="w-4 h-4 inline ml-1" />
          شماره کارت‌ها
        </button>
        <button
          onClick={() => setActiveTab('requests')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'requests' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'
          }`}
        >
          <Upload className="w-4 h-4 inline ml-1" />
          درخواست‌ها
          {pendingCount > 0 && (
            <span className="mr-1 px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded-full">
              {pendingCount}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'methods' && (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">شماره کارت‌های فعال</h2>
            <button
              onClick={() => { setShowForm(true); setEditingMethod(null); resetForm(); }}
              className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
            >
              افزودن شماره کارت
            </button>
          </div>

          {showForm && (
            <div className="bg-card border border-border rounded-xl p-6 mb-4">
              <h3 className="font-semibold mb-4">{editingMethod ? 'ویرایش شماره کارت' : 'شماره کارت جدید'}</h3>
              <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">شماره کارت</label>
                  <input
                    type="text"
                    value={formData.card_number}
                    onChange={(e) => setFormData({ ...formData, card_number: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="0000-0000-0000-0000"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">نام صاحب کارت</label>
                  <input
                    type="text"
                    value={formData.cardholder_name}
                    onChange={(e) => setFormData({ ...formData, cardholder_name: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">نام بانک</label>
                  <input
                    type="text"
                    value={formData.bank_name}
                    onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-muted-foreground mb-1">ترتیب نمایش</label>
                  <input
                    type="number"
                    value={formData.sort_order}
                    onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-sm text-muted-foreground mb-1">توضیحات</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    rows={2}
                  />
                </div>
                <div className="md:col-span-2 flex gap-2">
                  <button
                    type="submit"
                    disabled={createMutation.isPending || updateMutation.isPending}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50"
                  >
                    {editingMethod ? 'ذخیره تغییرات' : 'افزودن'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowForm(false); setEditingMethod(null); resetForm(); }}
                    className="px-4 py-2 bg-muted border border-border rounded-lg hover:bg-muted/80"
                  >
                    انصراف
                  </button>
                </div>
              </form>
            </div>
          )}

          {methodsLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : methods && methods.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {methods.map((method) => (
                <div key={method.id} className="bg-card border border-border rounded-xl p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <CreditCard className="w-5 h-5 text-primary" />
                      <span className="font-mono text-lg font-semibold tracking-wider">{method.card_number}</span>
                    </div>
                    <span className={`px-2 py-0.5 text-xs rounded-full ${method.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                      {method.is_active ? 'فعال' : 'غیرفعال'}
                    </span>
                  </div>
                  <div className="space-y-1 text-sm text-muted-foreground">
                    <div>صاحب کارت: <span className="text-foreground">{method.cardholder_name}</span></div>
                    <div>بانک: <span className="text-foreground">{method.bank_name}</span></div>
                    {method.description && <div className="text-xs mt-2">{method.description}</div>}
                  </div>
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => handleEdit(method)}
                      className="flex-1 px-3 py-1.5 text-sm bg-muted border border-border rounded-lg hover:bg-muted/80"
                    >
                      ویرایش
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('آیا از حذف این شماره کارت اطمینان دارید؟')) {
                          deleteMutation.mutate(method.id);
                        }
                      }}
                      className="px-3 py-1.5 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100"
                    >
                      حذف
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">شماره کارتی ثبت نشده است</div>
          )}
        </div>
      )}

      {activeTab === 'requests' && (
        <div>
          <div className="flex gap-2 mb-4">
            {['all', 'pending', 'approved', 'rejected'].map((status) => (
              <button
                key={status}
                onClick={() => setFilterStatus(status)}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                  filterStatus === status
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-muted border-border hover:bg-muted/80'
                }`}
              >
                {status === 'all' ? 'همه' : status === 'pending' ? 'در انتظار' : status === 'approved' ? 'تأیید شده' : 'رد شده'}
              </button>
            ))}
          </div>

          {requestsLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : requests && requests.length > 0 ? (
            <div className="space-y-3">
              {requests.map((req) => (
                <div key={req.id} className="bg-card border border-border rounded-xl p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="font-semibold">{req.first_name || req.username || `کاربر #${req.user_id}`}</span>
                        {getStatusBadge(req.status)}
                      </div>
                      <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <DollarSign className="w-4 h-4" />
                          {formatToman(req.amount_toman)} تومان
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" />
                          {formatDate(req.created_at)}
                        </span>
                      </div>
                      {req.description && (
                        <div className="mt-2 text-sm text-muted-foreground">{req.description}</div>
                      )}
                      {req.admin_note && (
                        <div className="mt-2 text-sm text-muted-foreground">
                          <span className="font-medium">یادداشت ادمین:</span> {req.admin_note}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setSelectedRequest(req)}
                        className="px-3 py-1.5 text-sm bg-muted border border-border rounded-lg hover:bg-muted/80"
                      >
                        <Eye className="w-4 h-4 inline ml-1" />
                        مشاهده رسید
                      </button>
                      {req.status === 'pending' && (
                        <>
                          <button
                            onClick={() => {
                              setSelectedRequest(req);
                              approveMutation.mutate({ id: req.id, note: adminNote || undefined });
                            }}
                            disabled={approveMutation.isPending}
                            className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                          >
                            <Check className="w-4 h-4 inline ml-1" />
                            تأیید
                          </button>
                          <button
                            onClick={() => {
                              if (adminNote.trim()) {
                                rejectMutation.mutate({ id: req.id, note: adminNote });
                              } else {
                                alert('لطفاً دلیل رد را وارد کنید');
                              }
                            }}
                            disabled={rejectMutation.isPending}
                            className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                          >
                            <X className="w-4 h-4 inline ml-1" />
                            رد
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">درخواستی وجود ندارد</div>
          )}
        </div>
      )}

      {selectedRequest && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setSelectedRequest(null)}>
          <div className="bg-card rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4">جزئیات درخواست پرداخت</h3>
            <div className="space-y-3">
              <div>
                <span className="text-sm text-muted-foreground">کاربر:</span>
                <div className="font-medium">{selectedRequest.first_name || selectedRequest.username || `کاربر #${selectedRequest.user_id}`}</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">مبلغ:</span>
                <div className="font-medium text-primary">{formatToman(selectedRequest.amount_toman)} تومان</div>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">وضعیت:</span>
                <div className="mt-1">{getStatusBadge(selectedRequest.status)}</div>
              </div>
              {selectedRequest.description && (
                <div>
                  <span className="text-sm text-muted-foreground">توضیحات:</span>
                  <div className="mt-1">{selectedRequest.description}</div>
                </div>
              )}
              <div>
                <span className="text-sm text-muted-foreground">تصویر رسید:</span>
                <div className="mt-2">
                  <img
                    src={`/api/files/deliver/${selectedRequest.receipt_image_path.split('/').pop()}`}
                    alt="رسید پرداخت"
                    className="max-w-full h-auto rounded-lg border border-border"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = '';
                      (e.target as HTMLImageElement).alt = 'تصویر رسید یافت نشد';
                    }}
                  />
                </div>
              </div>
              {selectedRequest.status === 'pending' && (
                <div className="mt-4">
                  <label className="block text-sm text-muted-foreground mb-1">یادداشت ادمین</label>
                  <textarea
                    value={adminNote}
                    onChange={(e) => setAdminNote(e.target.value)}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    rows={2}
                    placeholder="دلیل رد یا یادداشت تأیید..."
                  />
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setSelectedRequest(null)}
                className="px-4 py-2 bg-muted border border-border rounded-lg hover:bg-muted/80"
              >
                بستن
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
