import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Terminal,
  BarChart3,
  Server,
  Clock,
  Image as ImageIcon,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { getProxyStats, getProxyRequests, getProxyAccounts, type ProxyRequest, type ProxyStats, type CodexAccount } from '../lib/api';

const CodexProxyPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'stats' | 'requests' | 'accounts'>('stats');
  const [statsHours, setStatsHours] = useState(24);
  const [requestLimit, setRequestLimit] = useState(50);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [modelFilter, setModelFilter] = useState<string>('all');
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['codex-proxy-stats', statsHours],
    queryFn: () => getProxyStats(statsHours),
    refetchInterval: 30000,
  });

  const { data: requests, isLoading: requestsLoading, refetch: refetchRequests } = useQuery({
    queryKey: ['codex-proxy-requests', requestLimit, statusFilter, modelFilter],
    queryFn: () => getProxyRequests({
      limit: requestLimit,
      status: statusFilter === 'all' ? undefined : statusFilter,
      model: modelFilter === 'all' ? undefined : modelFilter,
    }),
    refetchInterval: 15000,
  });

  const { data: accounts, isLoading: accountsLoading, refetch: refetchAccounts } = useQuery({
    queryKey: ['codex-proxy-accounts'],
    queryFn: getProxyAccounts,
    refetchInterval: 60000,
  });

  const tabs = [
    { id: 'stats' as const, label: 'Dashboard', icon: BarChart3 },
    { id: 'requests' as const, label: 'Request Logs', icon: Terminal },
    { id: 'accounts' as const, label: 'Accounts', icon: Server },
  ];

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatNumber = (n: number) => n.toLocaleString();

  const StatCard: React.FC<{
    icon: React.ElementType;
    label: string;
    value: string | number;
    sub?: string;
    color?: string;
  }> = ({ icon: Icon, label, value, sub, color = 'text-primary' }) => (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Codex Proxy</h1>
        <p className="text-muted-foreground">
          Manage Codex CLI proxy, monitor usage, and track request logs.
        </p>
      </div>

      <div className="flex space-x-1 bg-muted/50 p-1 rounded-xl w-fit">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
                ${activeTab === tab.id
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background/50'}
              `}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === 'stats' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-sm text-muted-foreground">Period:</span>
              {[1, 6, 24, 168].map((h) => (
                <button
                  key={h}
                  onClick={() => setStatsHours(h)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                    statsHours === h
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {h === 1 ? '1H' : h === 6 ? '6H' : h === 24 ? '24H' : '7D'}
                </button>
              ))}
            </div>
            <button
              onClick={() => refetchStats()}
              className="flex items-center space-x-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>

          {statsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="bg-card border border-border rounded-xl p-5 animate-pulse">
                  <div className="h-4 bg-muted rounded w-20 mb-3" />
                  <div className="h-8 bg-muted rounded w-16" />
                </div>
              ))}
            </div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  icon={Terminal}
                  label="Total Requests"
                  value={formatNumber(stats.total_requests)}
                  sub={`${stats.success_requests} success, ${stats.error_requests} errors`}
                />
                <StatCard
                  icon={BarChart3}
                  label="Total Tokens"
                  value={formatNumber(stats.total_tokens)}
                  sub={`↑ ${formatNumber(stats.prompt_tokens)} in, ↓ ${formatNumber(stats.completion_tokens)} out`}
                />
                <StatCard
                  icon={Clock}
                  label="Avg Duration"
                  value={formatDuration(stats.avg_duration_ms)}
                  color="text-amber-500"
                />
                <StatCard
                  icon={ImageIcon}
                  label="Image Requests"
                  value={formatNumber(stats.image_requests)}
                  sub={stats.total_requests > 0 ? `${((stats.image_requests / stats.total_requests) * 100).toFixed(0)}% of total` : ''}
                  color="text-purple-500"
                />
              </div>

              {stats.by_model.length > 0 && (
                <div className="bg-card border border-border rounded-xl p-6">
                  <h3 className="text-lg font-semibold mb-4">Usage by Model</h3>
                  <div className="space-y-3">
                    {stats.by_model.map((m) => {
                      const pct = stats.total_tokens > 0 ? (m.total_tokens / stats.total_tokens) * 100 : 0;
                      return (
                        <div key={m.model}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium">{m.model}</span>
                            <span className="text-xs text-muted-foreground">
                              {formatNumber(m.requests)} requests · {formatNumber(m.total_tokens)} tokens
                            </span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary rounded-full transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {stats.by_account.length > 0 && (
                <div className="bg-card border border-border rounded-xl p-6">
                  <h3 className="text-lg font-semibold mb-4">Usage by Account</h3>
                  <div className="space-y-3">
                    {stats.by_account.map((a) => {
                      const pct = stats.total_tokens > 0 ? (a.total_tokens / stats.total_tokens) * 100 : 0;
                      return (
                        <div key={a.account_id}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium">Account #{a.account_id}</span>
                            <span className="text-xs text-muted-foreground">
                              {formatNumber(a.requests)} requests · {formatNumber(a.total_tokens)} tokens
                            </span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded-full transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {activeTab === 'requests' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-background border border-border rounded-lg px-3 py-1.5 text-sm"
              >
                <option value="all">All Status</option>
                <option value="success">Success</option>
                <option value="error">Error</option>
              </select>
              <select
                value={modelFilter}
                onChange={(e) => setModelFilter(e.target.value)}
                className="bg-background border border-border rounded-lg px-3 py-1.5 text-sm"
              >
                <option value="all">All Models</option>
                {requests && [...new Set(requests.map((r: ProxyRequest) => r.model))].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <select
                value={requestLimit}
                onChange={(e) => setRequestLimit(Number(e.target.value))}
                className="bg-background border border-border rounded-lg px-3 py-1.5 text-sm"
              >
                <option value={20}>20 rows</option>
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
              </select>
            </div>
            <button
              onClick={() => refetchRequests()}
              className="flex items-center space-x-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>

          {requestsLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="bg-card border border-border rounded-lg p-4 animate-pulse">
                  <div className="h-4 bg-muted rounded w-3/4" />
                </div>
              ))}
            </div>
          ) : requests && requests.length > 0 ? (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">ID</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Model</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Tokens</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Duration</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Image</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Time</th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((req: ProxyRequest) => (
                    <React.Fragment key={req.id}>
                      <tr
                        className="border-b border-border/50 hover:bg-muted/20 cursor-pointer"
                        onClick={() => setExpandedRow(expandedRow === req.id ? null : req.id)}
                      >
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {req.request_id.slice(-8)}
                        </td>
                        <td className="px-4 py-3 font-medium">{req.model}</td>
                        <td className="px-4 py-3">
                          {req.status === 'success' ? (
                            <span className="inline-flex items-center text-emerald-600">
                              <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                              Success
                            </span>
                          ) : (
                            <span className="inline-flex items-center text-red-500">
                              <AlertCircle className="w-3.5 h-3.5 mr-1" />
                              Error
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs">{formatNumber(req.total_tokens)}</td>
                        <td className="px-4 py-3 text-xs">{formatDuration(req.duration_ms)}</td>
                        <td className="px-4 py-3">
                          {req.has_image ? (
                            <span className="inline-flex items-center text-purple-500">
                              <ImageIcon className="w-3.5 h-3.5 mr-1" />
                              {req.image_count}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {new Date(req.created_at).toLocaleTimeString()}
                        </td>
                        <td className="px-4 py-3">
                          {expandedRow === req.id ? (
                            <ChevronUp className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                          )}
                        </td>
                      </tr>
                      {expandedRow === req.id && req.error_message && (
                        <tr>
                          <td colSpan={8} className="px-4 py-3 bg-red-500/5">
                            <div className="text-xs text-red-500 font-mono break-all">
                              {req.error_message}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl p-12 text-center">
              <Terminal className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No requests found</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'accounts' && (
        <div className="space-y-4">
          <div className="flex items-center justify-end">
            <button
              onClick={() => refetchAccounts()}
              className="flex items-center space-x-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>

          {accountsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="bg-card border border-border rounded-xl p-6 animate-pulse">
                  <div className="h-6 bg-muted rounded w-32 mb-4" />
                  <div className="h-4 bg-muted rounded w-48 mb-2" />
                  <div className="h-4 bg-muted rounded w-40" />
                </div>
              ))}
            </div>
          ) : accounts && accounts.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {accounts.map((acct: CodexAccount) => {
                const fiveHourPct = acct.five_hour_limit > 0
                  ? (acct.five_hour_used / acct.five_hour_limit) * 100
                  : 0;
                const weeklyPct = acct.weekly_limit > 0
                  ? (acct.weekly_used / acct.weekly_limit) * 100
                  : 0;

                return (
                  <div key={acct.id} className="bg-card border border-border rounded-xl p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-semibold">
                          {acct.label || `Account #${acct.id}`}
                        </h3>
                        <p className="text-xs text-muted-foreground">ID: {acct.id}</p>
                      </div>
                      <span
                        className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                          acct.auth_status === 'authenticated'
                            ? 'bg-emerald-500/10 text-emerald-600'
                            : 'bg-amber-500/10 text-amber-600'
                        }`}
                      >
                        {acct.auth_status}
                      </span>
                    </div>

                    <div className="space-y-4">
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">5-Hour Usage</span>
                          <span className="text-xs font-medium">
                            {formatNumber(acct.five_hour_used)} / {formatNumber(acct.five_hour_limit)}
                          </span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              fiveHourPct > 80 ? 'bg-red-500' : fiveHourPct > 50 ? 'bg-amber-500' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(fiveHourPct, 100)}%` }}
                          />
                        </div>
                      </div>

                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">Weekly Usage</span>
                          <span className="text-xs font-medium">
                            {formatNumber(acct.weekly_used)} / {formatNumber(acct.weekly_limit)}
                          </span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              weeklyPct > 80 ? 'bg-red-500' : weeklyPct > 50 ? 'bg-amber-500' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(weeklyPct, 100)}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border">
                        <span>Last used</span>
                        <span>
                          {acct.last_used_at
                            ? new Date(acct.last_used_at).toLocaleString()
                            : 'Never'}
                        </span>
                      </div>

                      {acct.last_error && (
                        <div className="text-xs text-red-500 bg-red-500/5 rounded-lg p-2 break-all">
                          <AlertCircle className="w-3 h-3 inline mr-1" />
                          {acct.last_error}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl p-12 text-center">
              <Server className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No Codex accounts configured</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CodexProxyPage;
