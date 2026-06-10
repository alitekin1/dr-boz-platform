import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getUsers, toggleUserPro, grantTrial, bulkGrantTrial, broadcastTrialInvite, getTrialConfig } from '../lib/api';
import { User } from '../lib/types';
import { UserTable } from '../components/users/UserTable';
import CreditAdjustmentModal from '../components/users/CreditAdjustmentModal';
import PromoCodeManager from '../components/users/PromoCodeManager';
import PromoCodeRedeemModal from '../components/users/PromoCodeRedeemModal';
import { Search, RefreshCw, Gift, Send } from 'lucide-react';

const UsersPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [selectedRedeemUser, setSelectedRedeemUser] = useState<User | null>(null);
  const [showBulkTrialModal, setShowBulkTrialModal] = useState(false);
  const [showBroadcastTrialModal, setShowBroadcastTrialModal] = useState(false);
  const [bulkTrialMessage, setBulkTrialMessage] = useState('');
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [broadcastButtonText, setBroadcastButtonText] = useState('');
  const [bulkTrialResult, setBulkTrialResult] = useState<any>(null);
  const [broadcastResult, setBroadcastResult] = useState<any>(null);
  const queryClient = useQueryClient();

  const { data: trialConfig } = useQuery({
    queryKey: ['trialConfig'],
    queryFn: getTrialConfig,
  });

  const { data: users = [], isLoading, error, refetch } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: getUsers,
  });

  const toggleProMutation = useMutation({
    mutationFn: (userId: number) => toggleUserPro(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const grantTrialMutation = useMutation({
    mutationFn: (userId: number) => grantTrial(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      alert('Trial subscription granted successfully!');
    },
    onError: (error: any) => {
      alert(`Failed to grant trial: ${error.response?.data?.detail || error.message}`);
    }
  });

  const bulkGrantTrialMutation = useMutation({
    mutationFn: (data: { user_ids?: number[]; skip_if_used?: boolean }) => bulkGrantTrial(data),
    onSuccess: (data) => {
      setBulkTrialResult(data);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error: any) => {
      alert(`Failed to bulk grant trials: ${error.response?.data?.detail || error.message}`);
    }
  });

  const broadcastTrialMutation = useMutation({
    mutationFn: (data: { message?: string; button_text?: string; target_user_ids?: (number | string)[] }) => broadcastTrialInvite(data),
    onSuccess: (data) => {
      setBroadcastResult(data);
    },
    onError: (error: any) => {
      alert(`Failed to send broadcast: ${error.response?.data?.detail || error.message}`);
    }
  });

  const safeUsers = users.filter((user): user is User => Boolean(user) && typeof user === 'object');

  const filteredUsers = safeUsers.filter((user) => {
    const search = searchQuery.toLowerCase();
    const telegramUserId = String(user?.telegram_user_id ?? '');
    const username = String(user?.username ?? '').toLowerCase();
    const firstName = String(user?.first_name ?? '').toLowerCase();
    const preferredName = String(user?.preferred_name ?? '').toLowerCase();
    const phoneNumber = String(user?.phone_number ?? '').toLowerCase();
    return (
      telegramUserId.includes(search) ||
      username.includes(search) ||
      firstName.includes(search) ||
      preferredName.includes(search) ||
      phoneNumber.includes(search)
    );
  });

  const handleBulkGrantTrial = () => {
    const targetIds = searchQuery
      ? filteredUsers.map(u => u.id)
      : undefined;
    bulkGrantTrialMutation.mutate({ user_ids: targetIds, skip_if_used: true });
  };

  const handleBroadcastTrial = () => {
    const targetIds = searchQuery
      ? filteredUsers.map(u => u.telegram_user_id ?? u.id)
      : undefined;
    broadcastTrialMutation.mutate({
      message: broadcastMessage,
      button_text: broadcastButtonText,
      target_user_ids: targetIds,
    });
  };

  if (error) {
    return (
      <div className="p-8 text-center bg-destructive/10 border border-destructive text-destructive rounded-lg">
        <p className="font-bold">Failed to load users</p>
        <p className="text-sm">{(error as any).message}</p>
        <button onClick={() => refetch()} className="mt-4 px-4 py-2 bg-destructive text-destructive-foreground rounded-md text-sm">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">User Management</h1>
          <p className="text-muted-foreground">Manage telegram users and their credit balances.</p>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={() => refetch()} 
            disabled={isLoading}
            className="p-2 border rounded-md hover:bg-muted disabled:opacity-50 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 px-3 py-2 bg-card border rounded-lg shadow-sm">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search users by ID, name, username or phone..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 bg-transparent border-none focus:ring-0 text-sm outline-none"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card rounded-lg border border-border shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <Gift className="w-5 h-5 text-amber-500" />
            <h3 className="font-semibold">Bulk Trial Activation</h3>
          </div>
          <p className="text-sm text-muted-foreground mb-3">
            {searchQuery
              ? `Grant trial to ${filteredUsers.filter(u => !u.trial_used).length} eligible users matching search`
              : 'Grant trial to all eligible users who haven\'t used their trial yet'}
          </p>
          <button
            onClick={() => setShowBulkTrialModal(true)}
            disabled={bulkGrantTrialMutation.isPending}
            className="w-full px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
          >
            {bulkGrantTrialMutation.isPending ? 'Processing...' : 'Activate Trials'}
          </button>
        </div>

        <div className="bg-card rounded-lg border border-border shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <Send className="w-5 h-5 text-blue-500" />
            <h3 className="font-semibold">Send Trial Invitation</h3>
          </div>
          <p className="text-sm text-muted-foreground mb-3">
            {searchQuery
              ? `Send invitation to ${filteredUsers.filter(u => !u.trial_used).length} eligible users matching search`
              : 'Send invitation message with activation button to all eligible users'}
          </p>
          <button
            onClick={() => setShowBroadcastTrialModal(true)}
            disabled={broadcastTrialMutation.isPending}
            className="w-full px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
          >
            {broadcastTrialMutation.isPending ? 'Sending...' : 'Send Invitations'}
          </button>
        </div>
      </div>

      {bulkTrialResult && (
        <div className="bg-card rounded-lg border border-border shadow-sm p-4">
          <h3 className="font-semibold mb-2">Bulk Trial Result</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-md">
              <div className="text-green-600 dark:text-green-400 font-bold text-lg">{bulkTrialResult.success_count}</div>
              <div className="text-green-500">Activated</div>
            </div>
            <div className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-md">
              <div className="text-yellow-600 dark:text-yellow-400 font-bold text-lg">{bulkTrialResult.skipped_count}</div>
              <div className="text-yellow-500">Skipped</div>
            </div>
            <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-md">
              <div className="text-red-600 dark:text-red-400 font-bold text-lg">{bulkTrialResult.error_count}</div>
              <div className="text-red-500">Errors</div>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-md">
              <div className="text-blue-600 dark:text-blue-400 font-bold text-lg">{bulkTrialResult.total_targeted}</div>
              <div className="text-blue-500">Total Targeted</div>
            </div>
          </div>
          <button onClick={() => setBulkTrialResult(null)} className="mt-3 text-sm text-muted-foreground hover:text-foreground">
            Dismiss
          </button>
        </div>
      )}

      {broadcastResult && (
        <div className="bg-card rounded-lg border border-border shadow-sm p-4">
          <h3 className="font-semibold mb-2">Broadcast Result</h3>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-md">
              <div className="text-green-600 dark:text-green-400 font-bold text-lg">{broadcastResult.success_count}</div>
              <div className="text-green-500">Sent</div>
            </div>
            <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-md">
              <div className="text-red-600 dark:text-red-400 font-bold text-lg">{broadcastResult.failure_count}</div>
              <div className="text-red-500">Failed</div>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-md">
              <div className="text-blue-600 dark:text-blue-400 font-bold text-lg">{broadcastResult.total_targeted}</div>
              <div className="text-blue-500">Total Targeted</div>
            </div>
          </div>
          <button onClick={() => setBroadcastResult(null)} className="mt-3 text-sm text-muted-foreground hover:text-foreground">
            Dismiss
          </button>
        </div>
      )}

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center space-y-4">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="text-sm text-muted-foreground">Loading users...</p>
          </div>
        ) : (
          <UserTable 
            users={filteredUsers} 
            onAdjustCredit={(user) => setSelectedUser(user)}
            onRedeemCode={(user) => setSelectedRedeemUser(user)}
            onTogglePro={(user) => toggleProMutation.mutate(user.id)}
            onGrantTrial={(user) => {
              if (window.confirm(`Are you sure you want to grant a trial subscription to ${user.preferred_name || user.first_name || 'this user'}?`)) {
                grantTrialMutation.mutate(user.id);
              }
            }}
          />
        )}
      </div>

      <PromoCodeManager />

      {selectedUser && (
        <CreditAdjustmentModal 
          isOpen={!!selectedUser}
          user={selectedUser} 
          onClose={() => {
            setSelectedUser(null);
            refetch();
          }} 
        />
      )}

      {selectedRedeemUser && (
        <PromoCodeRedeemModal
          isOpen={!!selectedRedeemUser}
          user={selectedRedeemUser}
          onClose={() => {
            setSelectedRedeemUser(null);
            refetch();
          }}
        />
      )}

      {showBulkTrialModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-lg border border-border shadow-lg max-w-md w-full p-6">
            <h3 className="text-lg font-semibold mb-4">Confirm Bulk Trial Activation</h3>
            <p className="text-sm text-muted-foreground mb-4">
              {searchQuery
                ? `This will activate trial subscriptions for ${filteredUsers.filter(u => !u.trial_used).length} eligible users matching your search.`
                : 'This will activate trial subscriptions for ALL eligible users who haven\'t used their trial yet.'}
            </p>
            <p className="text-sm text-muted-foreground mb-4">
              Users who already used their trial will be skipped automatically.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowBulkTrialModal(false)}
                className="px-4 py-2 border rounded-md text-sm hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  handleBulkGrantTrial();
                  setShowBulkTrialModal(false);
                }}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-md text-sm font-medium transition-colors"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {showBroadcastTrialModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-lg border border-border shadow-lg max-w-md w-full p-6">
            <h3 className="text-lg font-semibold mb-4">Send Trial Invitations</h3>
            <p className="text-sm text-muted-foreground mb-4">
              This will send a message with an activation button to eligible users.
            </p>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Message</label>
              <textarea
                value={broadcastMessage}
                onChange={(e) => setBroadcastMessage(e.target.value)}
                placeholder={trialConfig?.invitation_message || 'Default invitation message'}
                rows={4}
                className="w-full px-3 py-2 border rounded-md text-sm bg-background focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Button Text</label>
              <input
                type="text"
                value={broadcastButtonText}
                onChange={(e) => setBroadcastButtonText(e.target.value)}
                placeholder={trialConfig?.invitation_button_text || 'فعال‌سازی اشتراک رایگان'}
                className="w-full px-3 py-2 border rounded-md text-sm bg-background focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowBroadcastTrialModal(false)}
                className="px-4 py-2 border rounded-md text-sm hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  handleBroadcastTrial();
                  setShowBroadcastTrialModal(false);
                }}
                className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-md text-sm font-medium transition-colors"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UsersPage;
