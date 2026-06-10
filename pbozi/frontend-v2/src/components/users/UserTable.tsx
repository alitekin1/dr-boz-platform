import React from 'react';
import { User } from '../../lib/types';
import { Coins, Gift, Shield, User as UserIcon, Zap, Send } from 'lucide-react';

interface UserTableProps {
  users: User[];
  onAdjustCredit: (user: User) => void;
  onRedeemCode: (user: User) => void;
  onTogglePro: (user: User) => void;
  onGrantTrial: (user: User) => void;
}

export const UserTable: React.FC<UserTableProps> = ({ 
  users, 
  onAdjustCredit, 
  onRedeemCode, 
  onTogglePro,
  onGrantTrial
}) => {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-xs uppercase bg-muted/50 text-muted-foreground border-y border-border">
          <tr>
            <th className="px-6 py-4 font-medium">User</th>
            <th className="px-6 py-4 font-medium">Phone</th>
            <th className="px-6 py-4 font-medium">Status</th>
            <th className="px-6 py-4 font-medium">Balance</th>
            <th className="px-6 py-4 font-medium">Created</th>
            <th className="px-6 py-4 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {users.map((user) => (
            <tr key={user.id} className="hover:bg-muted/30 transition-colors">
              <td className="px-6 py-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                    <UserIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="font-semibold flex items-center gap-2">
                      {user.preferred_name || user.first_name || 'Anonymous'}
                      {user.is_admin && (
                        <Shield className="w-3 h-3 text-amber-500" />
                      )}
                      {user.is_pro && (
                        <Zap className="w-3 h-3 text-indigo-500 fill-indigo-500" />
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      @{user.username || 'no_username'} • {user.telegram_user_id ?? 'no telegram id'}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-6 py-4 font-mono">
                {user.phone_number || '-'}
              </td>
              <td className="px-6 py-4">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  user.account_status === 'active' 
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {user.account_status}
                </span>
              </td>
              <td className="px-6 py-4">
                <div className="space-y-0.5">
                  <div className="font-mono text-sm">
                    {user.credit_balance_usd != null ? `$${user.credit_balance_usd.toFixed(2)}` : '-'}
                  </div>
                  <div className="font-mono text-xs text-muted-foreground">
                    {user.total_balance_toman != null ? `${user.total_balance_toman.toLocaleString('fa-IR')} تومان` : '-'}
                  </div>
                </div>
              </td>
              <td className="px-6 py-4 text-muted-foreground">
                {new Date(user.created_at).toLocaleDateString()}
              </td>
              <td className="px-6 py-4 text-right">
                <div className="inline-flex items-center gap-2">
                  <button
                    onClick={() => window.location.href = `/messaging?userId=${user.telegram_user_id || user.id}`}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted transition-colors"
                    title="Send Message"
                  >
                    <Send className="w-3.5 h-3.5" />
                    Message
                  </button>
                  <button
                    onClick={() => onTogglePro(user)}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                      user.is_pro 
                        ? 'border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900/50 dark:bg-indigo-900/20 dark:text-indigo-400' 
                        : 'border-border bg-background hover:bg-muted'
                    }`}
                    title={user.is_pro ? "Remove Pro Status" : "Make Pro User"}
                  >
                    <Zap className={`w-3.5 h-3.5 ${user.is_pro ? 'fill-current' : ''}`} />
                    {user.is_pro ? 'Revoke Pro' : 'Make Pro'}
                  </button>
                  <button
                    onClick={() => onGrantTrial(user)}
                    disabled={user.trial_used}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                      user.trial_used
                        ? 'bg-muted text-muted-foreground cursor-not-allowed opacity-50'
                        : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-400'
                    }`}
                    title={user.trial_used ? "Trial already used" : "Grant Trial Subscription"}
                  >
                    <Gift className="w-3.5 h-3.5" />
                    {user.trial_used ? 'Trial Used' : 'Grant Trial'}
                  </button>
                  <button
                    onClick={() => onRedeemCode(user)}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted transition-colors"
                  >
                    <Gift className="w-3.5 h-3.5" />
                    Apply Code
                  </button>
                  <button
                    onClick={() => onAdjustCredit(user)}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted transition-colors"
                  >
                    <Coins className="w-3.5 h-3.5" />
                    Adjust Credit
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={6} className="px-6 py-10 text-center text-muted-foreground">
                No users found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
