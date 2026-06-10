import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3, CheckCircle2, KeyRound, Plus, RefreshCw, Terminal, Trash2, XCircle } from 'lucide-react';
import {
  createCapacityPool,
  createCodexAccount,
  deleteCapacityPool,
  deleteCodexAccount,
  ensureDefaultCodexProvider,
  getCapacityPools,
  getCodexAccounts,
  getModels,
  getProviders,
  refreshCodexAccountAuthStatus,
  refreshCodexAccountLimitStatus,
  startCodexAccountAuth,
  updateCapacityPool,
  updateCodexAccount,
} from '../../lib/api';
import { CapacityPool, CodexAccount, CodexAccountAuthStart, CodexAccountAuthStatus, Model, Provider } from '../../lib/types';

const formatNumber = (value: number | undefined) => {
  if (!value) return '0';
  return new Intl.NumberFormat('en-US').format(value);
};

const formatDateTime = (value: string | undefined | null) => {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Never';
  return date.toLocaleString();
};

const CodexAccountList: React.FC = () => {
  const [label, setLabel] = React.useState('');
  const [providerId, setProviderId] = React.useState<number | ''>('');
  const [poolId, setPoolId] = React.useState<number | ''>('');
  const [poolName, setPoolName] = React.useState('');
  const [poolMaxUsers, setPoolMaxUsers] = React.useState('50');
  const [poolFallbackBehavior, setPoolFallbackBehavior] = React.useState<'reject' | 'fallback_model'>('reject');
  const [poolFallbackModelId, setPoolFallbackModelId] = React.useState<number | ''>('');
  const [authCommand, setAuthCommand] = React.useState<CodexAccountAuthStart | null>(null);
  const [statusMessage, setStatusMessage] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: accounts, isLoading } = useQuery<CodexAccount[]>({
    queryKey: ['codex-accounts'],
    queryFn: getCodexAccounts,
  });

  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: getProviders,
  });

  const { data: pools } = useQuery<CapacityPool[]>({
    queryKey: ['capacity-pools'],
    queryFn: getCapacityPools,
  });

  const { data: models } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: getModels,
  });

  const codexProviders = React.useMemo(
    () => (providers || []).filter((provider) => provider.kind === 'codex_subscription'),
    [providers]
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createCodexAccount({
        label: label.trim() || 'Codex account',
        provider_id: providerId === '' ? null : providerId,
        pool_id: poolId === '' ? null : poolId,
        is_active: true,
        status: 'active',
        max_users: 50,
        safety_buffer_percent: 30,
      }),
    onSuccess: () => {
      setLabel('');
      queryClient.invalidateQueries({ queryKey: ['codex-accounts'] });
    },
  });

  const createPoolMutation = useMutation({
    mutationFn: () =>
      createCapacityPool({
        name: poolName.trim() || 'Codex Pool',
        max_users: Math.max(0, Number(poolMaxUsers) || 0),
        active_users: 0,
        status: 'active',
        fallback_behavior: poolFallbackBehavior,
        fallback_model_id: poolFallbackBehavior === 'fallback_model' && poolFallbackModelId !== '' ? poolFallbackModelId : null,
      }),
    onSuccess: () => {
      setPoolName('');
      setPoolMaxUsers('50');
      setPoolFallbackBehavior('reject');
      setPoolFallbackModelId('');
      queryClient.invalidateQueries({ queryKey: ['capacity-pools'] });
    },
  });

  const updatePoolMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => updateCapacityPool(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['capacity-pools'] }),
  });

  const deletePoolMutation = useMutation({
    mutationFn: (id: number) => deleteCapacityPool(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['capacity-pools'] }),
  });

  const updateAccountMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => updateCodexAccount(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['codex-accounts'] }),
  });

  const ensureProviderMutation = useMutation({
    mutationFn: ensureDefaultCodexProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteCodexAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['codex-accounts'] });
    },
  });

  const startAuthMutation = useMutation({
    mutationFn: (id: number) => startCodexAccountAuth(id),
    onSuccess: (data: CodexAccountAuthStart) => {
      setAuthCommand(data);
      setStatusMessage(null);
      queryClient.invalidateQueries({ queryKey: ['codex-accounts'] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: (id: number) => refreshCodexAccountAuthStatus(id),
    onSuccess: (data: CodexAccountAuthStatus) => {
      setStatusMessage(data.is_authenticated ? 'Authenticated' : data.stderr || data.stdout || 'Not authenticated yet');
      queryClient.invalidateQueries({ queryKey: ['codex-accounts'] });
    },
  });

  const limitStatusMutation = useMutation({
    mutationFn: (id: number) => refreshCodexAccountLimitStatus(id),
    onSuccess: () => {
      setStatusMessage('Codex CLI status refreshed');
      queryClient.invalidateQueries({ queryKey: ['codex-accounts'] });
    },
    onError: (error: any) => {
      setStatusMessage(error?.response?.data?.detail || error?.message || 'Codex CLI status failed');
    },
  });

  const providerName = (id: number | null) => {
    if (id == null) return 'Shared pool';
    return providers?.find((provider) => provider.id === id)?.name || `Provider ${id}`;
  };

  const capacityPoolName = (id: number | null) => {
    if (id == null) return 'No capacity pool';
    return pools?.find((pool) => pool.id === id)?.name || `Pool ${id}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Codex Accounts</h3>
          <p className="text-xs text-muted-foreground">Manage ChatGPT/Codex login slots for Codex subscription providers.</p>
        </div>
        {codexProviders.length === 0 && (
          <button
            type="button"
            onClick={() => ensureProviderMutation.mutate()}
            disabled={ensureProviderMutation.isPending}
            className="inline-flex items-center space-x-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            <Plus className="w-4 h-4" />
            <span>{ensureProviderMutation.isPending ? 'Creating...' : 'Create Codex Provider'}</span>
          </button>
        )}
      </div>

      <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Capacity pools</p>
            <p className="text-xs text-muted-foreground">Users buy a pool slot; Codex requests route inside that pool.</p>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-[1fr_120px_160px_220px_auto]">
          <input
            type="text"
            value={poolName}
            onChange={(event) => setPoolName(event.target.value)}
            placeholder="Pool name"
            className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
          />
          <input
            type="number"
            min="0"
            value={poolMaxUsers}
            onChange={(event) => setPoolMaxUsers(event.target.value)}
            className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            title="Max users"
          />
          <select
            value={poolFallbackBehavior}
            onChange={(event) => setPoolFallbackBehavior(event.target.value as 'reject' | 'fallback_model')}
            className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
          >
            <option value="reject">Reject when full</option>
            <option value="fallback_model">Fallback model</option>
          </select>
          <select
            value={poolFallbackModelId}
            onChange={(event) => setPoolFallbackModelId(event.target.value ? Number(event.target.value) : '')}
            disabled={poolFallbackBehavior !== 'fallback_model'}
            className="w-full bg-background border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
          >
            <option value="">Fallback model</option>
            {(models || []).map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name || model.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => createPoolMutation.mutate()}
            disabled={createPoolMutation.isPending}
            className="inline-flex items-center justify-center space-x-2 bg-primary text-primary-foreground px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            <Plus className="w-4 h-4" />
            <span>{createPoolMutation.isPending ? 'Adding...' : 'Add Pool'}</span>
          </button>
        </div>
        <div className="grid gap-2">
          {(pools || []).map((pool) => (
            <div key={pool.id} className="grid gap-2 rounded-md border border-border bg-background/70 p-2 md:grid-cols-[1fr_110px_120px_140px_160px_190px_auto] md:items-center">
              <input
                defaultValue={pool.name}
                onBlur={(event) => {
                  if (event.target.value !== pool.name) {
                    updatePoolMutation.mutate({ id: pool.id, data: { name: event.target.value } });
                  }
                }}
                className="bg-muted border border-border rounded-md px-2 py-1 text-xs"
              />
              <input
                type="number"
                min="0"
                defaultValue={pool.max_users}
                onBlur={(event) => updatePoolMutation.mutate({ id: pool.id, data: { max_users: Number(event.target.value) || 0 } })}
                className="bg-muted border border-border rounded-md px-2 py-1 text-xs"
                title="Max users"
              />
              <span className="text-xs text-muted-foreground">Active: {pool.active_users}</span>
              <select
                value={pool.status}
                onChange={(event) => updatePoolMutation.mutate({ id: pool.id, data: { status: event.target.value } })}
                className="bg-muted border border-border rounded-md px-2 py-1 text-xs"
              >
                <option value="active">Active</option>
                <option value="disabled">Disabled</option>
              </select>
              <select
                value={pool.fallback_behavior}
                onChange={(event) => updatePoolMutation.mutate({ id: pool.id, data: { fallback_behavior: event.target.value } })}
                className="bg-muted border border-border rounded-md px-2 py-1 text-xs"
              >
                <option value="reject">Reject when full</option>
                <option value="fallback_model">Fallback model</option>
              </select>
              <select
                value={pool.fallback_model_id ?? ''}
                onChange={(event) => updatePoolMutation.mutate({ id: pool.id, data: { fallback_model_id: event.target.value ? Number(event.target.value) : null } })}
                disabled={pool.fallback_behavior !== 'fallback_model'}
                className="bg-muted border border-border rounded-md px-2 py-1 text-xs disabled:opacity-50"
              >
                <option value="">Fallback model</option>
                {(models || []).map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm('Delete this capacity pool?')) {
                    deletePoolMutation.mutate(pool.id);
                  }
                }}
                disabled={deletePoolMutation.isPending}
                className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                title="Delete pool"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-[1fr_220px_220px_auto]">
        <input
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Account label"
          className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
        />
        <select
          value={providerId}
          onChange={(event) => setProviderId(event.target.value ? Number(event.target.value) : '')}
          className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
        >
          <option value="">Shared pool</option>
          {codexProviders.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
        <select
          value={poolId}
          onChange={(event) => setPoolId(event.target.value ? Number(event.target.value) : '')}
          className="w-full bg-muted border border-border rounded-lg py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
        >
          <option value="">No capacity pool</option>
          {(pools || []).map((pool) => (
            <option key={pool.id} value={pool.id}>
              {pool.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="inline-flex items-center justify-center space-x-2 bg-primary text-primary-foreground px-3 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          <span>{createMutation.isPending ? 'Adding...' : 'Add Account'}</span>
        </button>
      </div>

      {authCommand && (
        <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
          <div className="flex items-center space-x-2 text-sm font-medium">
            <Terminal className="w-4 h-4 text-primary" />
            <span>Auth command</span>
          </div>
          <code className="block whitespace-pre-wrap break-all rounded-md bg-background border border-border p-3 text-xs">
            {authCommand.shell}
          </code>
        </div>
      )}

      {statusMessage && (
        <div className="rounded-lg border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
          {statusMessage}
        </div>
      )}

      <div className="grid gap-3">
        {isLoading ? (
          <div className="p-6 text-center text-muted-foreground">Loading Codex accounts...</div>
        ) : (
          accounts?.map((account) => {
            const usage = account.metadata_json?.usage;
            const limitStatus = account.metadata_json?.limit_status;
            return (
              <div
                key={account.id}
                className="flex flex-col gap-4 p-4 bg-muted/30 border border-border rounded-xl"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold">{account.label}</span>
                      {account.auth_status === 'authenticated' ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                      ) : (
                        <XCircle className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{providerName(account.provider_id)}</p>
                    <p className="text-xs text-muted-foreground">{capacityPoolName(account.pool_id)}</p>
                    <p className="text-[11px] text-muted-foreground font-mono truncate max-w-xl">{account.codex_home}</p>
                    {account.last_error && <p className="text-xs text-destructive">{account.last_error}</p>}
                  </div>

                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={() => startAuthMutation.mutate(account.id)}
                      disabled={startAuthMutation.isPending}
                      className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                      title="Start auth"
                    >
                      <KeyRound className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => statusMutation.mutate(account.id)}
                      disabled={statusMutation.isPending}
                      className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                      title="Check status"
                    >
                      <RefreshCw className={`w-4 h-4 ${statusMutation.isPending ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => limitStatusMutation.mutate(account.id)}
                      disabled={limitStatusMutation.isPending}
                      className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                      title="Refresh Codex CLI status"
                    >
                      <BarChart3 className={`w-4 h-4 ${limitStatusMutation.isPending ? 'animate-pulse' : ''}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm('Delete this Codex account?')) {
                          deleteMutation.mutate(account.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  <label className="text-xs text-muted-foreground">
                    Pool
                    <select
                      value={account.pool_id ?? ''}
                      onChange={(event) => updateAccountMutation.mutate({ id: account.id, data: { pool_id: event.target.value ? Number(event.target.value) : null } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    >
                      <option value="">No capacity pool</option>
                      {(pools || []).map((pool) => (
                        <option key={pool.id} value={pool.id}>
                          {pool.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Status
                    <select
                      value={account.status}
                      onChange={(event) => updateAccountMutation.mutate({ id: account.id, data: { status: event.target.value } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    >
                      <option value="active">Active</option>
                      <option value="limited">Limited</option>
                      <option value="disabled">Disabled</option>
                    </select>
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Enabled
                    <select
                      value={account.is_active ? 'true' : 'false'}
                      onChange={(event) => updateAccountMutation.mutate({ id: account.id, data: { is_active: event.target.value === 'true' } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    >
                      <option value="true">Enabled</option>
                      <option value="false">Disabled</option>
                    </select>
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Max users
                    <input
                      type="number"
                      min="0"
                      defaultValue={account.max_users}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { max_users: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Safety buffer %
                    <input
                      type="number"
                      min="0"
                      max="95"
                      defaultValue={account.safety_buffer_percent}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { safety_buffer_percent: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Five-hour limit
                    <input
                      type="number"
                      min="0"
                      defaultValue={account.five_hour_limit}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { five_hour_limit: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Five-hour used
                    <input
                      type="number"
                      min="0"
                      defaultValue={account.five_hour_used}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { five_hour_used: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Weekly limit
                    <input
                      type="number"
                      min="0"
                      defaultValue={account.weekly_limit}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { weekly_limit: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    Weekly used
                    <input
                      type="number"
                      min="0"
                      defaultValue={account.weekly_used}
                      onBlur={(event) => updateAccountMutation.mutate({ id: account.id, data: { weekly_used: Number(event.target.value) || 0 } })}
                      className="mt-1 w-full bg-background border border-border rounded-md px-2 py-1 text-xs"
                    />
                  </label>
                </div>

                <div className="rounded-lg border border-border bg-background/50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center space-x-2 text-sm font-medium">
                      <BarChart3 className="w-4 h-4 text-primary" />
                      <span>Tracked usage</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      Last run: {usage?.last_run?.model || 'None'} · {formatDateTime(usage?.last_run?.at)}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-md bg-muted/40 px-3 py-2">
                      <p className="text-[11px] text-muted-foreground">Requests</p>
                      <p className="text-sm font-semibold">{formatNumber(usage?.request_count)}</p>
                    </div>
                    <div className="rounded-md bg-muted/40 px-3 py-2">
                      <p className="text-[11px] text-muted-foreground">Total tokens</p>
                      <p className="text-sm font-semibold">{formatNumber(usage?.total_tokens)}</p>
                    </div>
                    <div className="rounded-md bg-muted/40 px-3 py-2">
                      <p className="text-[11px] text-muted-foreground">Input / cached</p>
                      <p className="text-sm font-semibold">
                        {formatNumber(usage?.input_tokens)} / {formatNumber(usage?.cached_input_tokens)}
                      </p>
                    </div>
                    <div className="rounded-md bg-muted/40 px-3 py-2">
                      <p className="text-[11px] text-muted-foreground">Output / reasoning</p>
                      <p className="text-sm font-semibold">
                        {formatNumber(usage?.output_tokens)} / {formatNumber(usage?.reasoning_output_tokens)}
                      </p>
                    </div>
                  </div>
                </div>

                {limitStatus?.status_text && (
                  <div className="rounded-lg border border-border bg-background/50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center space-x-2 text-sm font-medium">
                        <BarChart3 className="w-4 h-4 text-primary" />
                        <span>Codex CLI status</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        {formatDateTime(limitStatus.checked_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      This is the raw Codex `/status` output. It shows quota only if the CLI returns quota details.
                    </p>
                    <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
                      {limitStatus.status_text}
                    </pre>
                  </div>
                )}
              </div>
            );
          })
        )}

        {!isLoading && accounts?.length === 0 && (
          <div className="p-6 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No Codex accounts configured.
          </div>
        )}
      </div>
    </div>
  );
};

export default CodexAccountList;
