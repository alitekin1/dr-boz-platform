import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getUsageEvents } from '../../lib/api';
import { UsageEvent } from '../../lib/types';
import { Activity, Clock, Cpu, CreditCard } from 'lucide-react';

export const UsageFeed: React.FC = () => {
  const { data: events, isLoading, error } = useQuery<UsageEvent[]>({
    queryKey: ['usage-events'],
    queryFn: () => getUsageEvents(50),
    refetchInterval: 10000, // 10 seconds auto-polling
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 border border-destructive/50 bg-destructive/10 text-destructive rounded-lg">
        Failed to load usage events.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center">
          <Activity className="w-5 h-5 mr-2 text-primary" />
          Live Usage Feed
        </h3>
        <span className="text-xs text-muted-foreground italic">Updating every 10s</span>
      </div>

      <div className="border rounded-lg overflow-hidden bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-muted/50 text-muted-foreground border-b">
              <tr>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">User ID</th>
                <th className="px-4 py-3 font-medium">Operation</th>
                <th className="px-4 py-3 font-medium">Model</th>
                <th className="px-4 py-3 font-medium text-right">Tokens (I/O)</th>
                <th className="px-4 py-3 font-medium text-right">Cost (USD)</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {events?.map((event) => {
                const codexUsage = event.metadata_json?.codex_provider_usage as
                  | { input_tokens?: number; output_tokens?: number; total_tokens?: number; cached_input_tokens?: number; reasoning_output_tokens?: number }
                  | undefined;
                return (
                <tr key={event.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                    <div className="flex items-center">
                      <Clock className="w-3 h-3 mr-1" />
                      {new Date(event.created_at).toLocaleTimeString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{event.user_id}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      event.operation_type === 'chat' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                      event.operation_type === 'tool_call' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' :
                      'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
                    }`}>
                      {event.operation_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 truncate max-w-[150px]" title={event.model_name_snapshot || 'N/A'}>
                    <div className="flex items-center">
                      <Cpu className="w-3 h-3 mr-1 text-muted-foreground" />
                      {event.model_name_snapshot || 'N/A'}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <div>
                      <span className="font-medium">{event.input_tokens}</span>
                      <span className="text-muted-foreground mx-1">/</span>
                      <span className="font-medium">{event.output_tokens}</span>
                    </div>
                    {codexUsage && (
                      <div className="text-[10px] text-muted-foreground">
                        Codex raw: {codexUsage.input_tokens || 0}/{codexUsage.output_tokens || 0}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <div className="flex items-center justify-end text-emerald-600 dark:text-emerald-400 font-medium">
                      <CreditCard className="w-3 h-3 mr-1" />
                      ${(event.actual_cost_minor / 1_000_000).toFixed(6)}
                    </div>
                    {event.usage_source && (
                      <div className="text-[10px] text-muted-foreground">{event.usage_source}</div>
                    )}
                  </td>
                </tr>
              );
              })}
              {events?.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground italic">
                    No usage events recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
