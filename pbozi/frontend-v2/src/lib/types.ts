export interface User {
  id: number;
  telegram_user_id: number | null;
  first_name: string | null;
  username: string | null;
  preferred_name: string | null;
  phone_number: string | null;
  account_status: string;
  is_pro: boolean;
  is_admin: boolean;
  trial_used: boolean;
  credit_balance_usd: number;
  gift_balance_toman: number;
  paid_balance_toman: number;
  total_balance_toman: number;
  created_at: string;
}

export interface PromoCode {
  id: number;
  code: string;
  description: string | null;
  bonus_type: 'fixed' | 'percent';
  currency: 'USD' | 'TOMAN';
  bonus_value_usd: number;
  bonus_value_toman: number;
  minimum_charge_usd: number;
  minimum_charge_toman: number;
  max_redemptions_total: number | null;
  max_redemptions_per_user: number;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromoCodePayload {
  code: string;
  description?: string | null;
  bonus_type: 'fixed' | 'percent';
  currency?: 'USD' | 'TOMAN';
  bonus_value: number;
  minimum_charge: number;
  max_redemptions_total?: number | null;
  max_redemptions_per_user: number;
  is_active: boolean;
  expires_at?: string | null;
}

export interface PromoCodeRedemptionPayload {
  code: string;
  charge_amount: number;
  charge_amount_toman?: number;
  currency?: 'USD' | 'TOMAN';
}

export interface PromoCodeRedemption {
  id: number;
  promo_code_id: number;
  user_id: number;
  charge_amount_usd: number;
  charge_amount_toman: number;
  bonus_amount_usd: number;
  bonus_amount_toman: number;
  total_credit_usd: number;
  total_credit_toman: number;
  credit_ledger_entry_id: number | null;
  toman_ledger_entry_id: number | null;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  instructions: string | null;
  created_at: string;
  import_count?: number;
  owner_user_id?: number;
}

export interface Document {
  id: number;
  project_id: number;
  filename: string;
  file_type: string;
  chunk_count: number | null;
  created_at: string;
}

export interface Stats {
  providers: number;
  models: number;
  projects: number;
  chats: number;
  messages: number;
  users: number;
  tools: number;
  tool_bindings: number;
  tool_calls: number;
}

export interface Provider {
  id: number;
  name: string;
  base_url: string;
  api_key: string;
  kind?: 'openai_compatible' | 'codex_subscription' | string;
  config_json?: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
}

export interface ImportedProviderModelConfigInput {
  name: string;
  display_name?: string | null;
  pricing_input: number;
  pricing_output: number;
  context_window: number;
  is_active: boolean;
}

export interface ProviderUpsertInput {
  name: string;
  base_url: string;
  api_key: string;
  kind?: 'openai_compatible' | 'codex_subscription' | string;
  config_json?: Record<string, unknown> | null;
  is_active: boolean;
  sync_models?: boolean;
  model_names?: string[];
  imported_models?: ImportedProviderModelConfigInput[];
  activate_imported_models?: boolean;
}

export interface ProviderModelDiscoverResponse {
  models: string[];
}

export interface CodexUsageRun {
  model?: string;
  at?: string;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
}

export interface CodexUsageStats {
  request_count?: number;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
  by_model?: Record<string, CodexUsageRun & { request_count?: number }>;
  last_run?: CodexUsageRun;
}

export interface CapacityPool {
  id: number;
  name: string;
  max_users: number;
  active_users: number;
  status: 'active' | 'disabled' | string;
  fallback_behavior: 'reject' | 'fallback_model' | string;
  fallback_model_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export type CapacityPoolInput = Omit<CapacityPool, 'id' | 'created_at' | 'updated_at'>;

export interface CodexAccount {
  id: number;
  label: string;
  provider_id: number | null;
  pool_id: number | null;
  codex_home: string;
  auth_status: string;
  is_active: boolean;
  status: 'active' | 'limited' | 'disabled' | string;
  max_users: number;
  five_hour_limit: number;
  five_hour_used: number;
  weekly_limit: number;
  weekly_used: number;
  safety_buffer_percent: number;
  last_error: string | null;
  cooldown_until: string | null;
  last_used_at: string | null;
  metadata_json: (Record<string, unknown> & {
    usage?: CodexUsageStats;
    limit_status?: CodexAccountLimitStatus;
  }) | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CodexAccountLimitStatus {
  account_id?: number;
  checked_at: string;
  status_text: string;
  usage?: Record<string, number>;
  stderr?: string;
}

export interface CodexAccountCreateInput {
  label: string;
  provider_id?: number | null;
  pool_id?: number | null;
  is_active: boolean;
  status?: 'active' | 'limited' | 'disabled' | string;
  max_users?: number;
  five_hour_limit?: number;
  five_hour_used?: number;
  weekly_limit?: number;
  weekly_used?: number;
  safety_buffer_percent?: number;
}

export interface CodexAccountAuthStart {
  account_id: number;
  codex_home: string;
  argv: string[];
  env: Record<string, string>;
  shell: string;
}

export interface CodexAccountAuthStatus {
  account_id: number;
  auth_status: string;
  is_authenticated: boolean;
  stdout: string;
  stderr: string;
}

export interface Model {
  id: number;
  name: string;
  display_name: string | null;
  provider_id: number | null;
  pricing_input: number;
  pricing_output: number;
  pricing_input_toman: number;
  pricing_output_toman: number;
  context_window: number;
  is_active: boolean;
  is_default: boolean;
  capabilities: ModelCapabilities | null;
}

export interface AutoRouterConfig {
  router_model_id?: number | null;
  easy_model_id?: number | null;
  medium_model_id?: number | null;
  hard_model_id?: number | null;
  vision_model_id?: number | null;
  research_model_id?: number | null;
  fallback_model_id?: number | null;
}

export interface ModelCapabilities {
  model_type?: 'normal' | 'auto_router' | string;
  image_input?: boolean | number | string;
  auto_router?: AutoRouterConfig;
  [key: string]: unknown;
}

export interface ModelImportCSVResponse {
  success: number;
  failed: number;
  errors: string[];
}

export interface Tool {
  id: number;
  name: string;
  display_name: string | null;
  description: string;
  kind: string;
  implementation_key: string | null;
  input_schema: any | null;
  is_active: boolean;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface ToolBinding {
  id: number;
  tool_id: number;
  scope_type: string;
  scope_id: number | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
  tool: Tool;
}

export interface WebSearchConfig {
  id: number;
  name: string;
  provider: string;
  base_url: string;
  api_key_set: boolean;
  search_type: string;
  max_results: number;
  include_domains: string[] | null;
  exclude_domains: string[] | null;
  contents_options: any | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmbeddingConfig {
  id: number;
  name: string;
  provider: string;
  model: string;
  api_key: string | null;
  base_url: string | null;
  pricing_input: number;
  is_active: boolean;
  created_at: string;
}

export interface TranscriptionConfig {
  id: number;
  name: string;
  provider: string;
  model: string;
  base_url: string;
  api_key_set: boolean;
  pricing_input: number;
  pricing_output: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StarterCreditConfig {
  id: number;
  name: string;
  amount_usd: number;
  amount_toman: number;
  welcome_message: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UsageEvent {
  id: number;
  user_id: number;
  operation_type: string;
  model_name_snapshot: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  usage_source: string | null;
  actual_cost_minor: number;
  metadata_json?: Record<string, any> | null;
  status: string;
  created_at: string;
}

export interface AdminAction {
  id: number;
  action_type: string;
  target_type: string;
  target_id: number | null;
  reason: string | null;
  created_at: string;
}

export interface TelegramBotStatus {
  running: boolean;
  pid: number | null;
  managed: boolean;
  started_at: string | null;
  detail: string | null;
}

export interface SystemPrompt {
  id: number;
  name: string;
  content: string;
  is_active: boolean;
  auto_tool_guidance_enabled: boolean | null;
  tool_guidance_style: string | null;
  tool_guidance_template: string | null;
  created_at: string;
}

export interface TelegramGroupBillingGroup {
  id: number;
  title?: string | null;
  telegram_chat_id?: number | null;
  chat_id?: number | null;
  status?: string | null;
  is_enabled?: boolean | null;
  enabled?: boolean | null;
  is_active?: boolean | null;
  trigger_phrases_json?: string[] | null;
  trigger_phrases?: string[] | null;
  min_active_members?: number | null;
  minimum_active_members?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface TelegramGroupBillingGroupUpdate {
  trigger_phrases_json?: string[];
  is_enabled?: boolean;
  min_active_members?: number;
}

export interface TelegramGroupBillingMember {
  id: number;
  group_id?: number;
  user_id?: number | null;
  telegram_user_id?: number | null;
  preferred_name?: string | null;
  username?: string | null;
  status?: string | null;
  shared_billing_enabled?: boolean | null;
  is_active?: boolean | null;
  created_at?: string;
  updated_at?: string;
}

export interface GroupUsageShare {
  id: number;
  user_id?: number | null;
  estimated_share_minor?: number | null;
  actual_share_minor?: number | null;
  status?: string | null;
  error?: string | null;
  created_at?: string;
}

export interface TelegramGroupUsageEvent {
  id: number;
  group_id?: number;
  triggered_by_user_id?: number | null;
  estimated_cost_minor?: number | null;
  actual_cost_minor?: number | null;
  split_member_count?: number | null;
  status?: string | null;
  error?: string | null;
  created_at?: string;
  completed_at?: string | null;
  shares?: GroupUsageShare[];
}

export interface Skill {
  id: number;
  name: string;
  description?: string;
  usage_rules?: string;
  when_to_use?: string;
  avoid_when?: string;
  instructions?: string;
  file_path?: string;
  files?: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ErrorLog {
  id: number;
  timestamp: string;
  source: string;
  error_message: string;
  stack_trace: string;
  user_id: number | null;
  resolved: boolean;
}

export interface ReferralCampaign {
  id: number;
  code: string;
  description: string | null;
  created_by_admin_id: number | null;
  is_active: boolean;
  created_at: string;
}

export interface ReferralStat {
  campaign: ReferralCampaign;
  starts: number;
  signups: number;
  purchases: number;
  revenue_usd: number;
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  plan_type: string;
  monthly_price_toman: number;
  gift_credit_toman: number;
  cooldown_limit_toman: number;
  cooldown_hours: number;
  weekly_limit_toman: number;
  allowed_tools_json: string[] | null;
  allowed_skills_json: string[] | null;
  is_agentic: boolean;
  is_active: boolean;
}

export interface SubscriptionPlanCreate {
  name: string;
  plan_type: string;
  monthly_price_toman: number;
  gift_credit_toman: number;
  cooldown_limit_toman: number;
  cooldown_hours: number;
  weekly_limit_toman: number;
  allowed_tools_json: string[] | null;
  allowed_skills_json: string[] | null;
  is_agentic: boolean;
  is_active: boolean;
}

export interface SubscriptionPlanUpdate {
  name?: string;
  plan_type?: string;
  monthly_price_toman?: number;
  gift_credit_toman?: number;
  cooldown_limit_toman?: number;
  cooldown_hours?: number;
  weekly_limit_toman?: number;
  allowed_tools_json?: string[] | null;
  allowed_skills_json?: string[] | null;
  is_agentic?: boolean;
  is_active?: boolean;
}

export interface TrialConfig {
  id: number;
  plan_id: number | null;
  duration_hours: number;
  is_enabled: boolean;
  apply_automatically: boolean;
  welcome_message: string | null;
  invitation_message: string | null;
  invitation_button_text: string | null;
  updated_at: string;
}

export interface TrialConfigUpdate {
  plan_id?: number | null;
  duration_hours?: number;
  is_enabled?: boolean;
  apply_automatically?: boolean;
  welcome_message?: string | null;
  invitation_message?: string | null;
  invitation_button_text?: string | null;
}

export interface SubscriptionPlanRule {
  id: number;
  plan_id: number;
  model_id: number;
  free_chats_count: number;
  free_tokens_per_chat: number;
  discount_percent: number;
  is_active: boolean;
}

export interface SubscriptionPlanRuleCreate {
  model_id: number;
  free_chats_count: number;
  free_tokens_per_chat: number;
  discount_percent: number;
  is_active: boolean;
}

export interface SubscriptionConfig {
  id: number;
  is_enabled: boolean;
  monthly_price_toman: number;
  gift_credit_toman: number;
  api_markup_percent: number;
  first_topup_discount_percent: number;
  first_topup_discount_cap_toman: number;
  usd_to_toman_rate: number;
}

export type SubscriptionConfigUpdate = Partial<Omit<SubscriptionConfig, 'id'>>;

export interface AdminUserSubscription {
  id: number;
  user_id: number;
  telegram_user_id: number | null;
  first_name: string | null;
  username: string | null;
  phone_number: string | null;
  gift_balance_toman: number;
  paid_balance_toman: number;
  total_balance_toman: number;
  plan_id: number;
  plan_name: string | null;
  pool_id: number | null;
  pool_name: string | null;
  status: string;
  purchased_at: string;
  expires_at: string;
  is_active_now: boolean;
}

export interface BackupStatus {
  enabled: boolean;
  interval_minutes: number;
  max_count: number;
  running: boolean;
  next_run: string | null;
}

export interface BackupRun {
  status: string;
  archive_name?: string | null;
  drive_file_id?: string | null;
  timestamp: string;
  error?: string | null;
}

export interface UserBillingAccount {
  user_id: number;
  gift_balance_toman: number;
  paid_balance_toman: number;
  total_balance_toman: number;
  total_gift_granted_toman: number;
  total_gift_spent_toman: number;
  total_paid_topup_toman: number;
  total_paid_spent_toman: number;
  total_subscription_paid_toman: number;
  first_topup_discount_used: boolean;
}

export interface UserSubscriptionStatus {
  id: number;
  plan_id: number;
  plan_name: string | null;
  plan_type: string | null;
  status: string;
  purchased_at: string;
  expires_at: string;
  is_active_now: boolean;
  cooldown_spent_toman: number;
  cooldown_limit_toman: number;
  cooldown_hours: number;
  cooldown_ends_at: string | null;
  is_in_cooldown: boolean;
  cooldown_remaining_seconds: number | null;
  weekly_spent_toman: number;
  weekly_limit_toman: number;
  week_resets_at: string | null;
}

export interface UserUsagePermission {
  can_chat: boolean;
  reason: string | null;
  billing_account: UserBillingAccount | null;
  subscription: UserSubscriptionStatus | null;
  billable_cost_toman: number;
  cooldown_remaining_seconds: number | null;
}

export interface LedgerEntry {
  id: number;
  amount_toman: number;
  gift_delta_toman: number;
  paid_delta_toman: number;
  gift_balance_after_toman: number;
  paid_balance_after_toman: number;
  entry_type: string;
  reason: string | null;
  created_at: string;
}

export interface TopupQuote {
  credit_amount_toman: number;
  normal_payment_toman: number;
  payment_due_toman: number;
  discount_toman: number;
  discount_applied: boolean;
  markup_percent: number;
  discount_percent: number;
}

export interface UserSubscriptionPlan {
  id: number;
  name: string;
  plan_type: string;
  monthly_price_toman: number;
  gift_credit_toman: number;
  cooldown_limit_toman: number;
  cooldown_hours: number;
  weekly_limit_toman: number;
  is_agentic: boolean;
}

export interface PaymentMethod {
  id: number;
  card_number: string;
  cardholder_name: string;
  bank_name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string | null;
}

export interface PaymentMethodCreate {
  card_number: string;
  cardholder_name: string;
  bank_name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
}

export interface PaymentMethodUpdate {
  card_number?: string;
  cardholder_name?: string;
  bank_name?: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
}

export interface PaymentRequest {
  id: number;
  user_id: number;
  first_name: string | null;
  username: string | null;
  amount_toman: number;
  receipt_image_path: string;
  description: string | null;
  status: 'pending' | 'approved' | 'rejected';
  admin_note: string | null;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface PromotionalLink {
  id: number;
  code: string;
  title: string;
  description: string | null;
  offer_type: 'credit_grant' | 'free_subscription' | 'topup_discount';
  offer_value_toman: number;
  offer_duration_hours: number;
  plan_id: number | null;
  discount_percent: number;
  max_redemptions: number | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  created_by: number | null;
  total_clicks: number;
  total_redemptions: number;
}

export interface PromotionalLinkClick {
  id: number;
  promotional_link_id: number;
  user_id: number;
  clicked_at: string;
  redeemed_at: string | null;
  redemption_status: 'pending' | 'redeemed' | 'failed' | 'already_used';
}

export interface PromotionalLinkStats {
  total_clicks: number;
  total_redemptions: number;
  total_failed: number;
  total_already_used: number;
  conversion_rate: number;
  clicks: PromotionalLinkClick[];
}

export interface PromotionalLinkCreate {
  title: string;
  description?: string | null;
  offer_type: 'credit_grant' | 'free_subscription' | 'topup_discount';
  offer_value_toman?: number;
  offer_duration_hours?: number;
  plan_id?: number | null;
  discount_percent?: number;
  max_redemptions?: number | null;
  expires_at?: string | null;
}

export interface PromotionalLinkUpdate {
  title?: string;
  description?: string | null;
  offer_type?: 'credit_grant' | 'free_subscription' | 'topup_discount';
  offer_value_toman?: number;
  offer_duration_hours?: number;
  plan_id?: number | null;
  discount_percent?: number;
  max_redemptions?: number | null;
  expires_at?: string | null;
  is_active?: boolean;
}

export interface Tip {
  id: number;
  trigger_key: string;
  tip_type: 'event' | 'scheduled';
  content: string;
  is_active: boolean;
  delay_seconds: number;
  auto_delete_seconds: number;
  min_account_age_days: number;
  created_at: string;
  updated_at: string;
}

export interface TipCreate {
  trigger_key: string;
  tip_type: 'event' | 'scheduled';
  content: string;
  is_active?: boolean;
  delay_seconds?: number;
  auto_delete_seconds?: number;
  min_account_age_days?: number;
}

export interface TipUpdate {
  trigger_key?: string;
  tip_type?: 'event' | 'scheduled';
  content?: string;
  is_active?: boolean;
  delay_seconds?: number;
  auto_delete_seconds?: number;
  min_account_age_days?: number;
}
