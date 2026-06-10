import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAdminActions } from '../../lib/api';
import { AdminAction } from '../../lib/types';
import { Shield, Clock, Tag, Fingerprint } from 'lucide-react';

export const AuditLog: React.FC = () => {
  const { data: actions, isLoading, error } = useQuery<AdminAction[]>({
    queryKey: ['admin-actions'],
    queryFn: () => getAdminActions(50),
    refetchInterval: 30000, // 30 seconds for audit logs
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
        Failed to load audit logs.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center">
          <Shield className="w-5 h-5 mr-2 text-primary" />
          Admin Audit Log
        </h3>
        <span className="text-xs text-muted-foreground italic">Updating every 30s</span>
      </div>

      <div className="border rounded-lg overflow-hidden bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-muted/50 text-muted-foreground border-b">
              <tr>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Target</th>
                <th className="px-4 py-3 font-medium">Reason / Details</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {actions?.map((action) => (
                <tr key={action.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                    <div className="flex items-center text-xs">
                      <Clock className="w-3 h-3 mr-1" />
                      {new Date(action.created_at).toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="font-semibold text-foreground uppercase text-[10px] bg-primary/10 text-primary px-2 py-0.5 rounded border border-primary/20">
                      {action.action_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <div className="flex items-center text-xs text-muted-foreground">
                        <Tag className="w-3 h-3 mr-1" />
                        {action.target_type}
                      </div>
                      {action.target_id && (
                        <div className="flex items-center text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                          <Fingerprint className="w-3 h-3 mr-1" />
                          ID: {action.target_id}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-sm text-muted-foreground line-clamp-2 max-w-md" title={action.reason || ''}>
                      {action.reason || <span className="italic text-muted-foreground/50">No details provided</span>}
                    </p>
                  </td>
                </tr>
              ))}
              {actions?.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground italic">
                    No administrative actions recorded yet.
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
