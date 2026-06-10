import axios from "axios";
import { API_URL, ADMIN_PASSWORD_KEY } from "./config";
import {
  CapacityPoolInput,
  CodexAccountCreateInput,
  PromoCodePayload,
  PromoCodeRedemptionPayload,
  ProviderUpsertInput,
  ModelImportCSVResponse,
  SubscriptionPlan,
  SubscriptionPlanCreate,
  SubscriptionPlanUpdate,
  SubscriptionConfig,
  SubscriptionConfigUpdate,
  AdminUserSubscription,
  SubscriptionPlanRule,
  SubscriptionPlanRuleCreate,
  TrialConfig,
  TrialConfigUpdate,
  UserBillingAccount,
  UserSubscriptionStatus,
  UserUsagePermission,
  LedgerEntry,
  TopupQuote,
  UserSubscriptionPlan,
  PaymentMethod,
  PaymentMethodCreate,
  PaymentMethodUpdate,
  PaymentRequest,
  PromotionalLink,
  PromotionalLinkCreate,
  PromotionalLinkUpdate,
  PromotionalLinkStats,
  PromotionalLinkClick,
} from "./types";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

const userApi = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Inject Bearer token from localStorage for all admin routes
api.interceptors.request.use((config) => {
  const password = localStorage.getItem(ADMIN_PASSWORD_KEY);
  // Ensure we add the header if it's an admin route or if we have a password
  // (Most routes in this app are admin routes anyway)
  const hasAuthHeader =
    Boolean(config.headers?.Authorization) ||
    Boolean((config.headers as any)?.authorization);
  if (password && !hasAuthHeader) {
    config.headers.set('Authorization', `Bearer ${password}`);
  }
  return config;
});

export default api;

// ---- Typed API Helpers ----
export const verifyAdminPassword = (password: string) =>
  axios
    .get(`${API_URL}/admin/auth-check`, {
      headers: {
        Authorization: `Bearer ${password}`,
        "Content-Type": "application/json",
      },
    })
    .then((r) => r.data);

export const getTelegramBotStatus = () => api.get("/admin/telegram-bot/status").then((r) => r.data);
export const startTelegramBot = () => api.post("/admin/telegram-bot/start").then((r) => r.data);
export const stopTelegramBot = () => api.post("/admin/telegram-bot/stop").then((r) => r.data);
export const getTelegramBillingGroups = (limit = 200) =>
  api.get(`/admin/telegram-group-billing/groups?limit=${limit}`).then((r) => r.data);
export const getTelegramBillingGroup = (groupId: number) =>
  api.get(`/admin/telegram-group-billing/groups/${groupId}`).then((r) => r.data);
export const updateTelegramBillingGroup = (
  groupId: number,
  data: { trigger_phrases_json?: string[]; is_enabled?: boolean; min_active_members?: number }
) => api.patch(`/admin/telegram-group-billing/groups/${groupId}`, data).then((r) => r.data);
export const getTelegramBillingGroupMembers = (groupId: number) =>
  api.get(`/admin/telegram-group-billing/groups/${groupId}/members`).then((r) => r.data);
export const getTelegramBillingGroupUsageEvents = (
  groupId: number,
  params?: { limit?: number; include_shares?: boolean }
) => {
  const searchParams = new URLSearchParams();
  if (params?.limit != null) searchParams.set("limit", String(params.limit));
  if (params?.include_shares != null) searchParams.set("include_shares", String(params.include_shares));
  const query = searchParams.toString();
  const path = `/admin/telegram-group-billing/groups/${groupId}/usage-events${query ? `?${query}` : ""}`;
  return api.get(path).then((r) => r.data);
};

export const getStats = () => api.get("/admin/stats").then((r) => r.data);
export const getProviders = () => api.get("/admin/providers").then((r) => r.data);
export const discoverProviderModels = (data: { base_url: string; api_key?: string }) =>
  api.post("/admin/providers/discover-models", data).then((r) => r.data);
export const createProvider = (data: ProviderUpsertInput) => api.post("/admin/providers", data).then((r) => r.data);
export const updateProvider = (id: number, data: ProviderUpsertInput) => api.patch(`/admin/providers/${id}`, data).then((r) => r.data);
export const deleteProvider = (id: number) => api.delete(`/admin/providers/${id}`).then((r) => r.data);

export const getCodexAccounts = () => api.get("/admin/codex-accounts").then((r) => r.data);
export const getCapacityPools = () => api.get("/admin/capacity-pools").then((r) => r.data);
export const createCapacityPool = (data: CapacityPoolInput) => api.post("/admin/capacity-pools", data).then((r) => r.data);
export const updateCapacityPool = (id: number, data: Partial<CapacityPoolInput> | Record<string, unknown>) =>
  api.patch(`/admin/capacity-pools/${id}`, data).then((r) => r.data);
export const deleteCapacityPool = (id: number) => api.delete(`/admin/capacity-pools/${id}`).then((r) => r.data);
export const ensureDefaultCodexProvider = () => api.post("/admin/codex/default-provider").then((r) => r.data);
export const createCodexAccount = (data: CodexAccountCreateInput) =>
  api.post("/admin/codex-accounts", data).then((r) => r.data);
export const updateCodexAccount = (id: number, data: Partial<CodexAccountCreateInput & { auth_status: string; last_error: string | null }> | Record<string, unknown>) =>
  api.patch(`/admin/codex-accounts/${id}`, data).then((r) => r.data);
export const deleteCodexAccount = (id: number) => api.delete(`/admin/codex-accounts/${id}`).then((r) => r.data);
export const startCodexAccountAuth = (id: number) =>
  api.post(`/admin/codex-accounts/${id}/auth/start`).then((r) => r.data);
export const refreshCodexAccountAuthStatus = (id: number) =>
  api.post(`/admin/codex-accounts/${id}/auth/status`).then((r) => r.data);
export const refreshCodexAccountLimitStatus = (id: number) =>
  api.post(`/admin/codex-accounts/${id}/limits/status`).then((r) => r.data);

export const getModels = () => api.get("/admin/models").then((r) => r.data);
export const createModel = (data: any) => api.post("/admin/models", data).then((r) => r.data);
export const updateModel = (id: number, data: any) => api.patch(`/admin/models/${id}`, data).then((r) => r.data);
export const deleteModel = (id: number) => api.delete(`/admin/models/${id}`).then((r) => r.data);
export const bulkUpdateModels = (data: { ids: number[]; action: "delete" | "enable" | "disable" }) =>
  api.post("/admin/models/bulk", data).then((r) => r.data);

export const importProvidersCSV = async (file: File): Promise<ModelImportCSVResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/admin/providers/import-csv', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const importModelsCSV = async (file: File): Promise<ModelImportCSVResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/admin/models/import-csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const getTools = () => api.get("/admin/tools").then((r) => r.data);
export const createTool = (data: any) => api.post("/admin/tools", data).then((r) => r.data);
export const updateTool = (id: number, data: any) => api.patch(`/admin/tools/${id}`, data).then((r) => r.data);
export const deleteTool = (id: number) => api.delete(`/admin/tools/${id}`).then((r) => r.data);
export const syncBuiltinTools = () => api.post("/admin/tools/sync-builtins").then((r) => r.data);

export const getToolBindings = () => api.get("/admin/tool-bindings").then((r) => r.data);
export const createToolBinding = (data: any) => api.post("/admin/tool-bindings", data).then((r) => r.data);
export const updateToolBinding = (id: number, data: any) => api.patch(`/admin/tool-bindings/${id}`, data).then((r) => r.data);
export const deleteToolBinding = (id: number) => api.delete(`/admin/tool-bindings/${id}`).then((r) => r.data);

export const getWebSearchConfig = () => api.get("/admin/web-search-config").then((r) => r.data);
export const updateWebSearchConfig = (data: any) => api.patch("/admin/web-search-config", data).then((r) => r.data);
export const getTranscriptionConfig = () => api.get("/admin/transcription-config").then((r) => r.data);
export const updateTranscriptionConfig = (data: any) => api.patch("/admin/transcription-config", data).then((r) => r.data);
export const getStarterCreditConfig = () => api.get("/admin/starter-credit-config").then((r) => r.data);
export const updateStarterCreditConfig = (data: any) => api.patch("/admin/starter-credit-config", data).then((r) => r.data);

export const getEmbeddingConfigs = () => api.get("/admin/embedding").then((r) => r.data);
export const createEmbeddingConfig = (data: any) => api.post("/admin/embedding", data).then((r) => r.data);
export const updateEmbeddingConfig = (id: number, data: any) => api.patch(`/admin/embedding/${id}`, data).then((r) => r.data);

export const getPrompts = () => api.get("/admin/prompts").then((r) => r.data);
export const createPrompt = (data: any) => api.post("/admin/prompts", data).then((r) => r.data);
export const updatePrompt = (id: number, data: any) => api.patch(`/admin/prompts/${id}`, data).then((r) => r.data);
export const deletePrompt = (id: number) => api.delete(`/admin/prompts/${id}`).then((r) => r.data);
export const previewPrompt = (content: string) => api.post("/admin/prompts/preview", { content }).then((r) => r.data);

export const getUsers = () => api.get("/admin/users").then((r) => r.data);
export const adjustUserCredit = (userId: number, amount: number, direction: 'credit' | 'debit', reason: string) =>
  api.post(`/admin/users/${userId}/credit-adjustments`, { amount, direction, reason }).then((r) => r.data);
export const redeemPromoCodeForUser = (userId: number, data: PromoCodeRedemptionPayload) =>
  api.post(`/admin/users/${userId}/promo-code-redemptions`, data).then((r) => r.data);
export const toggleUserPro = (userId: number) =>
  api.post(`/admin/users/${userId}/toggle-pro`).then((r) => r.data);

export const getPromoCodes = () => api.get("/admin/promo-codes").then((r) => r.data);
export const createPromoCode = (data: PromoCodePayload) => api.post("/admin/promo-codes", data).then((r) => r.data);
export const updatePromoCode = (id: number, data: Partial<PromoCodePayload>) => api.patch(`/admin/promo-codes/${id}`, data).then((r) => r.data);
export const deactivatePromoCode = (id: number) => api.delete(`/admin/promo-codes/${id}`).then((r) => r.data);
export const getPromoCodeRedemptions = (limit = 100) => api.get(`/admin/promo-code-redemptions?limit=${limit}`).then((r) => r.data);

export const getFeedbackEntries = () => api.get("/admin/feedback").then((r) => r.data);
export const getUsageEvents = (limit = 100) => 
  api.get(`/admin/usage-events?limit=${limit}`).then((r) => r.data);
export const getAdminActions = (limit = 100) => 
  api.get(`/admin/admin-actions?limit=${limit}`).then((r) => r.data);

export const getErrors = (limit = 100) =>
  api.get(`/admin/errors?limit=${limit}`).then((r) => r.data);

export const resolveError = (id: number) =>
  api.patch(`/admin/errors/${id}/resolve`).then((r) => r.data);

export const getReferrals = () => api.get("/admin/referrals").then((r) => r.data);
export const createReferralCampaign = (data: { description?: string }) => 
  api.post("/admin/referrals", data).then((r) => r.data);

export const getStartScenarios = () => api.get("/admin/start-scenarios").then((r) => r.data);
export const createStartScenario = (data: any) => api.post("/admin/start-scenarios", data).then((r) => r.data);
export const updateStartScenario = (id: number, data: any) => api.put(`/admin/start-scenarios/${id}`, data).then((r) => r.data);
export const deleteStartScenario = (id: number) => api.delete(`/admin/start-scenarios/${id}`).then((r) => r.data);

export const broadcastMessage = (data: { 
  message: string, 
  target_user_ids?: (number | string)[], 
  target_groups?: string[],
  referral_campaign_id?: number,
  buttons?: any[],
  photo?: File | null
}) => {
  const formData = new FormData();
  formData.append('message', data.message);
  if (data.target_user_ids) formData.append('target_user_ids', JSON.stringify(data.target_user_ids));
  if (data.target_groups) formData.append('target_groups', JSON.stringify(data.target_groups));
  if (data.referral_campaign_id) formData.append('referral_campaign_id', String(data.referral_campaign_id));
  if (data.buttons) formData.append('buttons', JSON.stringify(data.buttons));
  if (data.photo) formData.append('photo', data.photo);
  
  return api.post("/admin/broadcast", formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }).then((r) => r.data);
};

export const getProjects = (params?: { root_only?: boolean }) => {
  const query = params?.root_only ? "?root_only=true" : "";
  return api.get(`/projects${query}`).then((r) => r.data);
};

export const getProjectImports = (projectId: number) =>
  api.get(`/projects/${projectId}/imports`).then((r) => r.data);

export const createProject = (data: { name: string; description?: string; instructions?: string }) =>
  api.post("/projects", data).then((r) => r.data);

export const updateProject = (id: number, data: { name?: string; description?: string; instructions?: string }) =>
  api.patch(`/projects/${id}`, data).then((r) => r.data);

export const deleteProject = (id: number) =>
  api.delete(`/projects/${id}`).then((r) => r.data);

export const getDocuments = (projectId: number) =>
  api.get(`/projects/${projectId}/documents`).then((r) => r.data);

export const uploadDocument = (projectId: number, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post(`/projects/${projectId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }).then((r) => r.data);
};

export const deleteDocument = (projectId: number, docId: number) =>
  api.delete(`/projects/${projectId}/documents/${docId}`).then((r) => r.data);

export const getChats = (projectId?: number | null) => {
  const query = projectId == null ? "" : `?project_id=${projectId}`;
  return api.get(`/chats${query}`).then((r) => r.data);
};
export const getMessages = (chatId: number) => 
  api.get(`/chats/${chatId}/messages`).then((r) => r.data);

export const runPython = (code: string) =>
  api.post("/admin/python/run", { code }).then((r) => r.data);

export const getSkills = async (): Promise<any[]> => {
  const res = await api.get('/admin/skills');
  return res.data;
};

export const uploadSkill = async (file: File): Promise<any> => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/admin/skills', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

export const updateSkill = async (id: number, data: any): Promise<any> => {
  const res = await api.patch(`/admin/skills/${id}`, data);
  return res.data;
};

export const deleteSkill = async (id: number): Promise<void> => {
  await api.delete(`/admin/skills/${id}`);
};

export const getSubscriptionPlans = async (): Promise<SubscriptionPlan[]> => {
  const res = await api.get('/admin/subscriptions/plans');
  return res.data;
};

export const createSubscriptionPlan = async (data: SubscriptionPlanCreate): Promise<SubscriptionPlan> => {
  const res = await api.post('/admin/subscriptions/plans', data);
  return res.data;
};

export const updateSubscriptionPlan = async (id: number, data: SubscriptionPlanUpdate): Promise<SubscriptionPlan> => {
  const res = await api.patch(`/admin/subscriptions/plans/${id}`, data);
  return res.data;
};

export const deleteSubscriptionPlan = async (id: number): Promise<{ok: boolean}> => {
  const res = await api.delete(`/admin/subscriptions/plans/${id}`);
  return res.data;
};

export const getSubscriptionPlanRules = async (planId: number): Promise<SubscriptionPlanRule[]> => {
  const res = await api.get(`/admin/subscriptions/plans/${planId}/rules`);
  return res.data;
};

export const createSubscriptionPlanRule = async (planId: number, data: SubscriptionPlanRuleCreate): Promise<SubscriptionPlanRule> => {
  const res = await api.post(`/admin/subscriptions/plans/${planId}/rules`, data);
  return res.data;
};

export const deleteSubscriptionPlanRule = async (ruleId: number): Promise<{ok: boolean}> => {
  const res = await api.delete(`/admin/subscriptions/rules/${ruleId}`);
  return res.data;
};

export const getSubscriptionConfig = async (): Promise<SubscriptionConfig> => {
  const res = await api.get('/admin/subscriptions/config');
  return res.data;
};

export const updateSubscriptionConfig = async (data: SubscriptionConfigUpdate): Promise<SubscriptionConfig> => {
  const res = await api.patch('/admin/subscriptions/config', data);
  return res.data;
};

export const getTrialConfig = async (): Promise<TrialConfig> => {
  const res = await api.get('/admin/trial-config');
  return res.data;
};

export const updateTrialConfig = async (data: TrialConfigUpdate): Promise<TrialConfig> => {
  const res = await api.patch('/admin/trial-config', data);
  return res.data;
};

export const grantTrial = async (userId: number): Promise<any> => {
  const res = await api.post(`/admin/users/${userId}/grant-trial`);
  return res.data;
};

export const bulkGrantTrial = async (data: { user_ids?: number[]; skip_if_used?: boolean }): Promise<any> => {
  const res = await api.post('/admin/users/bulk-grant-trial', data);
  return res.data;
};

export const broadcastTrialInvite = async (data: { message?: string; button_text?: string; target_user_ids?: (number | string)[] }): Promise<any> => {
  const formData = new FormData();
  if (data.message) formData.append('message', data.message);
  if (data.button_text) formData.append('button_text', data.button_text);
  if (data.target_user_ids) formData.append('target_user_ids', JSON.stringify(data.target_user_ids));
  const res = await api.post('/admin/broadcast-trial-invite', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return res.data;
};

export const getUserSubscriptions = async (status = 'all'): Promise<AdminUserSubscription[]> => {
  const res = await api.get('/admin/subscriptions/user-subscriptions', { params: { status } });
  return res.data;
};

export const cancelUserSubscription = async (subscriptionId: number): Promise<AdminUserSubscription> => {
  const res = await api.post(`/admin/subscriptions/user-subscriptions/${subscriptionId}/cancel`);
  return res.data;
};

export const reactivateUserSubscription = async (subscriptionId: number): Promise<AdminUserSubscription> => {
  const res = await api.post(`/admin/subscriptions/user-subscriptions/${subscriptionId}/reactivate`);
  return res.data;
};

export const getBackupStatus = () => api.get("/admin/backups/status").then((r) => r.data);
export const runBackup = () => api.post("/admin/backups/run").then((r) => r.data);

// ---- Codex Proxy ----
export interface ProxyRequest {
  id: number;
  request_id: string;
  model: string;
  account_id: number | null;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  has_image: boolean;
  image_count: number;
  error_message: string | null;
  created_at: string;
}

export interface ProxyStats {
  period_hours: number;
  total_requests: number;
  success_requests: number;
  error_requests: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  avg_duration_ms: number;
  image_requests: number;
  by_model: { model: string; requests: number; total_tokens: number }[];
  by_account: { account_id: number; requests: number; total_tokens: number }[];
}

export interface CodexAccount {
  id: number;
  label: string | null;
  auth_status: string;
  is_active: boolean;
  status: string;
  five_hour_used: number;
  five_hour_limit: number;
  weekly_used: number;
  weekly_limit: number;
  last_used_at: string | null;
  last_error: string | null;
}

export const getProxyStats = async (hours = 24): Promise<ProxyStats> => {
  const res = await api.get('/admin/codex-proxy/stats', { params: { hours } });
  return res.data;
};

export const getProxyRequests = async (params?: {
  limit?: number;
  offset?: number;
  model?: string;
  status?: string;
  account_id?: number;
  has_image?: boolean;
  date_from?: string;
  date_to?: string;
}): Promise<ProxyRequest[]> => {
  const res = await api.get('/admin/codex-proxy/requests', { params });
  return res.data;
};

export const getProxyAccounts = async (): Promise<CodexAccount[]> => {
  const res = await api.get('/admin/codex-proxy/accounts');
  return res.data;
};
export const startBackupScheduler = () => api.post("/admin/backups/start").then((r) => r.data);
export const stopBackupScheduler = () => api.post("/admin/backups/stop").then((r) => r.data);

// ---- User-facing Subscription API ----

export const getUserSubscriptionPlans = async (): Promise<UserSubscriptionPlan[]> => {
  const res = await userApi.get('/user/subscription/plans');
  return res.data;
};

export const getUserBillingAccount = async (telegramUserId: number): Promise<UserBillingAccount> => {
  const res = await userApi.get('/user/billing-account', { params: { telegram_user_id: telegramUserId } });
  return res.data;
};

export const getUserSubscription = async (telegramUserId: number): Promise<UserSubscriptionStatus | null> => {
  const res = await userApi.get('/user/subscription', { params: { telegram_user_id: telegramUserId } });
  return res.data;
};

export const purchaseUserSubscription = async (telegramUserId: number, planId: number): Promise<any> => {
  const res = await userApi.post('/user/subscription/purchase', { plan_id: planId }, { params: { telegram_user_id: telegramUserId } });
  return res.data;
};

export const getTopupQuote = async (telegramUserId: number, amountToman: number): Promise<TopupQuote> => {
  const res = await userApi.get('/user/topup/quote', { params: { telegram_user_id: telegramUserId, amount_toman: amountToman } });
  return res.data;
};

export const applyTopup = async (telegramUserId: number, creditAmountToman: number): Promise<any> => {
  const res = await userApi.post('/user/topup/apply', { credit_amount_toman: creditAmountToman }, { params: { telegram_user_id: telegramUserId } });
  return res.data;
};

export const getUserLedger = async (telegramUserId: number, limit = 50, offset = 0): Promise<LedgerEntry[]> => {
  const res = await userApi.get('/user/ledger', { params: { telegram_user_id: telegramUserId, limit, offset } });
  return res.data;
};

export const checkUsagePermission = async (
  telegramUserId: number,
  modelId?: number,
  inputTokens = 0,
  outputTokens = 1000,
): Promise<UserUsagePermission> => {
  const res = await userApi.post('/user/usage-permission', null, {
    params: { telegram_user_id: telegramUserId, model_id: modelId, input_tokens: inputTokens, output_tokens: outputTokens },
  });
  return res.data;
};

export const claimTrial = async (telegramUserId: number): Promise<any> => {
  const res = await userApi.post('/user/trial/claim', {}, { params: { telegram_user_id: telegramUserId } });
  return res.data;
};

// ---- Payment Methods (Admin) ----

export const getPaymentMethods = async (): Promise<PaymentMethod[]> => {
  const res = await api.get('/admin/payment-methods');
  return res.data;
};

export const createPaymentMethod = async (data: PaymentMethodCreate): Promise<PaymentMethod> => {
  const res = await api.post('/admin/payment-methods', data);
  return res.data;
};

export const updatePaymentMethod = async (id: number, data: PaymentMethodUpdate): Promise<PaymentMethod> => {
  const res = await api.patch(`/admin/payment-methods/${id}`, data);
  return res.data;
};

export const deletePaymentMethod = async (id: number): Promise<{ ok: boolean }> => {
  const res = await api.delete(`/admin/payment-methods/${id}`);
  return res.data;
};

// ---- Payment Requests (Admin) ----

export const getPaymentRequests = async (status?: string, limit = 100): Promise<PaymentRequest[]> => {
  const params: Record<string, any> = { limit };
  if (status) params.status = status;
  const res = await api.get('/admin/payment-requests', { params });
  return res.data;
};

export const getPaymentRequest = async (id: number): Promise<PaymentRequest> => {
  const res = await api.get(`/admin/payment-requests/${id}`);
  return res.data;
};

export const approvePaymentRequest = async (id: number, adminNote?: string): Promise<PaymentRequest> => {
  const res = await api.post(`/admin/payment-requests/${id}/approve`, { admin_note: adminNote });
  return res.data;
};

export const rejectPaymentRequest = async (id: number, adminNote: string): Promise<PaymentRequest> => {
  const res = await api.post(`/admin/payment-requests/${id}/reject`, { admin_note: adminNote });
  return res.data;
};

// ---- Payment Methods (User) ----

export const getUserPaymentMethods = async (): Promise<PaymentMethod[]> => {
  const res = await userApi.get('/user/payment-methods');
  return res.data;
};

// ---- Payment Requests (User) ----

export const createUserPaymentRequest = async (
  telegramUserId: number,
  amountToman: number,
  receiptFile: File,
  description?: string,
): Promise<PaymentRequest> => {
  const formData = new FormData();
  formData.append('amount_toman', String(amountToman));
  if (description) formData.append('description', description);
  formData.append('receipt', receiptFile);
  const res = await userApi.post('/user/payment-requests', formData, {
    params: { telegram_user_id: telegramUserId },
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

export const getUserPaymentRequests = async (telegramUserId: number, limit = 50): Promise<PaymentRequest[]> => {
  const res = await userApi.get('/user/payment-requests', {
    params: { telegram_user_id: telegramUserId, limit },
  });
  return res.data;
};

// ---- Promotional Links ----
export const getPromotionalLinks = async (): Promise<PromotionalLink[]> => {
  const res = await api.get('/admin/promotional-links');
  return res.data;
};

export const createPromotionalLink = async (data: PromotionalLinkCreate): Promise<PromotionalLink> => {
  const res = await api.post('/admin/promotional-links', data);
  return res.data;
};

export const updatePromotionalLink = async (id: number, data: PromotionalLinkUpdate): Promise<PromotionalLink> => {
  const res = await api.patch(`/admin/promotional-links/${id}`, data);
  return res.data;
};

export const deactivatePromotionalLink = async (id: number): Promise<{ ok: boolean }> => {
  const res = await api.delete(`/admin/promotional-links/${id}`);
  return res.data;
};

export const getPromotionalLinkStats = async (id: number): Promise<PromotionalLinkStats> => {
  const res = await api.get(`/admin/promotional-links/${id}/stats`);
  return res.data;
};

// ---- Tips ----
export const getTips = async (): Promise<any[]> => {
  const res = await api.get('/admin/tips');
  return res.data;
};

export const createTip = async (data: any): Promise<any> => {
  const res = await api.post('/admin/tips', data);
  return res.data;
};

export const updateTip = async (id: number, data: any): Promise<any> => {
  const res = await api.put(`/admin/tips/${id}`, data);
  return res.data;
};

export const deleteTip = async (id: number): Promise<{ status: string }> => {
  const res = await api.delete(`/admin/tips/${id}`);
  return res.data;
};

export const getTipDeliveryLogs = async (): Promise<any[]> => {
  const res = await api.get('/admin/tips/delivery-logs');
  return res.data;
};

