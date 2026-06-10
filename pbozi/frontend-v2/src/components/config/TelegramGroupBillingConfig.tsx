import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Save, Users, Power, RefreshCw } from 'lucide-react';
import {
  getTelegramBillingGroup,
  getTelegramBillingGroupMembers,
  getTelegramBillingGroupUsageEvents,
  getTelegramBillingGroups,
  updateTelegramBillingGroup,
} from '../../lib/api';
import {
  TelegramGroupBillingGroup,
  TelegramGroupBillingMember,
  TelegramGroupUsageEvent,
} from '../../lib/types';

const TelegramGroupBillingConfig: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = React.useState<number | null>(null);
  const [triggerText, setTriggerText] = React.useState('');
  const [minActiveMembers, setMinActiveMembers] = React.useState<number>(2);
  const [enabled, setEnabled] = React.useState<boolean>(true);

  const { data: groups, isLoading, error, refetch: refetchGroups, isFetching } = useQuery<TelegramGroupBillingGroup[]>({
    queryKey: ['telegram-billing-groups'],
    queryFn: () => getTelegramBillingGroups(200),
  });

  React.useEffect(() => {
    if (selectedGroupId == null && groups && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const { data: selectedGroup } = useQuery<TelegramGroupBillingGroup>({
    queryKey: ['telegram-billing-group', selectedGroupId],
    queryFn: () => getTelegramBillingGroup(Number(selectedGroupId)),
    enabled: selectedGroupId != null,
  });

  const { data: members } = useQuery<TelegramGroupBillingMember[]>({
    queryKey: ['telegram-billing-group-members', selectedGroupId],
    queryFn: () => getTelegramBillingGroupMembers(Number(selectedGroupId)),
    enabled: selectedGroupId != null,
  });

  const { data: usageEvents } = useQuery<TelegramGroupUsageEvent[]>({
    queryKey: ['telegram-billing-group-usage-events', selectedGroupId],
    queryFn: () =>
      getTelegramBillingGroupUsageEvents(Number(selectedGroupId), {
        limit: 10,
        include_shares: true,
      }),
    enabled: selectedGroupId != null,
  });

  const updateMutation = useMutation({
    mutationFn: ({
      groupId,
      payload,
    }: {
      groupId: number;
      payload: { trigger_phrases_json?: string[]; is_enabled?: boolean; min_active_members?: number };
    }) => updateTelegramBillingGroup(groupId, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['telegram-billing-groups'] });
      queryClient.invalidateQueries({ queryKey: ['telegram-billing-group', variables.groupId] });
      queryClient.invalidateQueries({ queryKey: ['telegram-billing-group-members', variables.groupId] });
      queryClient.invalidateQueries({ queryKey: ['telegram-billing-group-usage-events', variables.groupId] });
    },
  });

  React.useEffect(() => {
    if (!selectedGroup) return;
    const phrases = selectedGroup.trigger_phrases_json ?? selectedGroup.trigger_phrases ?? [];
    const minMembers = selectedGroup.min_active_members ?? selectedGroup.minimum_active_members ?? 2;
    const isEnabled =
      typeof selectedGroup.is_enabled === 'boolean'
        ? selectedGroup.is_enabled
        : typeof selectedGroup.enabled === 'boolean'
          ? selectedGroup.enabled
              : typeof selectedGroup.is_active === 'boolean'
                ? selectedGroup.is_active
                : selectedGroup.status
                  ? selectedGroup.status === 'active'
                  : true;

    setTriggerText(phrases.join('\n'));
    setMinActiveMembers(minMembers);
    setEnabled(isEnabled);
  }, [selectedGroup]);

  const activeMembersCount = React.useMemo(() => {
    if (!members) return 0;
    return members.filter((member) => {
      if (typeof member.shared_billing_enabled === 'boolean') return member.shared_billing_enabled;
      if (typeof member.is_active === 'boolean') return member.is_active;
      if (member.status) return member.status === 'active';
      return false;
    }).length;
  }, [members]);

  const saveSettings = () => {
    if (selectedGroupId == null) return;
    const phrases = triggerText
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean);
    updateMutation.mutate({
      groupId: selectedGroupId,
      payload: {
        trigger_phrases_json: phrases,
        min_active_members: Math.max(1, Number(minActiveMembers || 1)),
        is_enabled: enabled,
      },
    });
  };

  const toggleStatus = () => {
    if (selectedGroupId == null) return;
    updateMutation.mutate({
      groupId: selectedGroupId,
      payload: { is_enabled: !enabled },
    });
    setEnabled((prev) => !prev);
  };

  const formatCost = (minor?: number | null) => {
    if (minor == null) return '-';
    return `$${(minor / 1_000_000).toFixed(4)}`;
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading telegram billing groups...</div>;
  if (error) return <div className="p-8 text-center text-destructive">Error loading telegram billing groups</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Telegram Group Billing</h3>
          <p className="text-sm text-muted-foreground">Manage triggers and shared billing policy per Telegram group.</p>
        </div>
        <button
          onClick={() => refetchGroups()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 border border-border bg-background px-3 py-2 rounded-lg text-sm font-medium hover:bg-muted/40 transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4">
        <div className="bg-muted/20 border border-border rounded-xl p-3">
          <div className="text-xs uppercase tracking-wide text-muted-foreground px-2 pb-2">Groups</div>
          <div className="space-y-2">
            {groups?.map((group) => {
              const groupEnabled =
                typeof group.is_enabled === 'boolean'
                  ? group.is_enabled
                  : typeof group.enabled === 'boolean'
                    ? group.enabled
                    : typeof group.is_active === 'boolean'
                      ? group.is_active
                      : group.status
                        ? group.status === 'active'
                        : true;
              return (
                <button
                  key={group.id}
                  onClick={() => setSelectedGroupId(group.id)}
                  className={`w-full text-left p-3 rounded-lg border transition ${
                    selectedGroupId === group.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/40 bg-background'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium truncate">{group.title || `Group #${group.id}`}</div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full ${
                        groupEnabled ? 'bg-green-500/10 text-green-600' : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {groupEnabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground font-mono">
                    {group.telegram_chat_id ?? group.chat_id ?? '-'}
                  </div>
                </button>
              );
            })}
            {groups?.length === 0 && (
              <div className="p-4 border border-dashed border-border rounded-lg text-xs text-muted-foreground text-center">
                No Telegram billing groups found.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {!selectedGroupId && (
            <div className="p-8 border border-dashed border-border rounded-xl text-center text-muted-foreground">
              Select a group to manage billing settings.
            </div>
          )}

          {selectedGroupId && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-4 rounded-xl border border-border bg-muted/20">
                  <div className="text-xs text-muted-foreground">Active paying members</div>
                  <div className="mt-2 text-2xl font-semibold">{activeMembersCount}</div>
                </div>
                <div className="p-4 rounded-xl border border-border bg-muted/20">
                  <div className="text-xs text-muted-foreground">Recent usage events</div>
                  <div className="mt-2 text-2xl font-semibold">{usageEvents?.length ?? 0}</div>
                </div>
                <div className="p-4 rounded-xl border border-border bg-muted/20">
                  <div className="text-xs text-muted-foreground">Group status</div>
                  <div className="mt-2 text-lg font-semibold">{enabled ? 'Enabled' : 'Disabled'}</div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border bg-background space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">Settings</h4>
                  <button
                    onClick={toggleStatus}
                    disabled={updateMutation.isPending}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                      enabled
                        ? 'bg-destructive text-destructive-foreground hover:opacity-90'
                        : 'bg-primary text-primary-foreground hover:opacity-90'
                    } disabled:opacity-60`}
                  >
                    <Power className="w-4 h-4" />
                    <span>{enabled ? 'Disable Group' : 'Enable Group'}</span>
                  </button>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Trigger phrases (one per line)</label>
                  <textarea
                    value={triggerText}
                    onChange={(e) => setTriggerText(e.target.value)}
                    rows={5}
                    className="w-full rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    placeholder="hey doctor boz"
                  />
                </div>

                <div className="space-y-2 max-w-xs">
                  <label className="text-sm font-medium">Minimum active members</label>
                  <input
                    type="number"
                    min={1}
                    value={minActiveMembers}
                    onChange={(e) => setMinActiveMembers(Math.max(1, Number(e.target.value || 1)))}
                    className="w-full rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>

                <div className="flex items-center justify-end">
                  <button
                    onClick={saveSettings}
                    disabled={updateMutation.isPending}
                    className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60"
                  >
                    <Save className="w-4 h-4" />
                    <span>{updateMutation.isPending ? 'Saving...' : 'Save Settings'}</span>
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-border bg-background">
                  <div className="flex items-center gap-2 mb-3">
                    <Users className="w-4 h-4 text-muted-foreground" />
                    <h4 className="font-semibold">Members</h4>
                  </div>
                  <div className="space-y-2 max-h-72 overflow-auto pr-1">
                    {members?.map((member) => {
                      const rowActive =
                        typeof member.shared_billing_enabled === 'boolean'
                          ? member.shared_billing_enabled
                          : typeof member.is_active === 'boolean'
                            ? member.is_active
                            : member.status === 'active';
                      return (
                        <div key={member.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/20 border border-border">
                          <div>
                            <div className="text-sm font-medium">{member.preferred_name || member.username || `User #${member.user_id ?? member.telegram_user_id ?? member.id}`}</div>
                            <div className="text-xs text-muted-foreground">{member.user_id != null ? `User ${member.user_id}` : `Telegram ${member.telegram_user_id ?? '-'}`}</div>
                          </div>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full ${
                              rowActive ? 'bg-green-500/10 text-green-600' : 'bg-muted text-muted-foreground'
                            }`}
                          >
                            {rowActive ? 'Active' : 'Inactive'}
                          </span>
                        </div>
                      );
                    })}
                    {(!members || members.length === 0) && (
                      <div className="text-sm text-muted-foreground text-center py-6">No group members found.</div>
                    )}
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-border bg-background">
                  <div className="flex items-center gap-2 mb-3">
                    <MessageSquare className="w-4 h-4 text-muted-foreground" />
                    <h4 className="font-semibold">Recent Usage</h4>
                  </div>
                  <div className="space-y-2 max-h-72 overflow-auto pr-1">
                    {usageEvents?.map((event) => (
                      <div key={event.id} className="p-2 rounded-lg bg-muted/20 border border-border">
                        <div className="flex items-center justify-between">
                          <div className="text-sm font-medium">Event #{event.id}</div>
                          <span className="text-xs text-muted-foreground">{event.status || 'unknown'}</span>
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Cost: {formatCost(event.actual_cost_minor)} | Split members: {event.split_member_count ?? '-'}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Shares: {event.shares?.length ?? 0}
                        </div>
                      </div>
                    ))}
                    {(!usageEvents || usageEvents.length === 0) && (
                      <div className="text-sm text-muted-foreground text-center py-6">No usage events yet.</div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default TelegramGroupBillingConfig;
