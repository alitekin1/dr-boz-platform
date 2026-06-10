import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getReferrals, createReferralCampaign } from '../lib/api';
import { ReferralStat } from '../lib/types';
import { 
  Link as LinkIcon, 
  Plus, 
  RefreshCcw, 
  TrendingUp, 
  UserPlus, 
  ShoppingBag, 
  DollarSign,
  Copy,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

const Referrals = () => {
  const queryClient = useQueryClient();
  const [description, setDescription] = useState('');
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const { data: referrals, isLoading, isError, refetch } = useQuery<ReferralStat[]>({
    queryKey: ['referrals'],
    queryFn: getReferrals
  });

  const createMutation = useMutation({
    mutationFn: createReferralCampaign,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['referrals'] });
      setDescription('');
    }
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({ description });
  };

  const copyToClipboard = (code: string) => {
    const botUsername = 'drbozai_bot'; 
    const link = `https://ble.ir/${botUsername}?start=${code}`;
    
    // Fallback for environments where navigator.clipboard might be restricted
    const textArea = document.createElement("textarea");
    textArea.value = link;
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch (err) {
      console.error('Fallback: Oops, unable to copy', err);
    }
    document.body.removeChild(textArea);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Referral Campaigns</h1>
          <p className="text-muted-foreground">Manage and track your marketing referral links.</p>
        </div>
        <button 
          onClick={() => refetch()}
          className="flex items-center px-4 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
        >
          <RefreshCcw className="w-4 h-4 mr-2" />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1 bg-card border border-border rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4 flex items-center">
            <Plus className="w-5 h-5 mr-2 text-primary" />
            Create Campaign
          </h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Description</label>
              <input
                type="text"
                placeholder="e.g. Telegram Ad Group A"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                required
              />
            </div>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="w-full py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creating...' : 'Generate Link'}
            </button>
          </form>
        </div>

        <div className="md:col-span-2 space-y-4">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 bg-card border border-border rounded-xl animate-pulse">
              <p className="text-muted-foreground">Loading campaigns...</p>
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center justify-center h-48 bg-card border border-border rounded-xl text-destructive gap-2">
              <AlertCircle className="w-8 h-8" />
              <p>Failed to load referral stats.</p>
            </div>
          ) : referrals?.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 bg-card border border-border rounded-xl text-muted-foreground gap-2">
              <LinkIcon className="w-8 h-8 opacity-20" />
              <p>No referral campaigns created yet.</p>
            </div>
          ) : (
            referrals?.map((item) => (
              <div key={item.campaign.id} className="bg-card border border-border rounded-xl p-5 shadow-sm hover:border-primary/50 transition-colors group">
                <div className="flex flex-col md:flex-row justify-between gap-4 mb-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono bg-primary/10 text-primary px-2 py-0.5 rounded">
                        {item.campaign.code}
                      </span>
                      <h3 className="font-semibold text-lg">{item.campaign.description || 'No description'}</h3>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Created on {new Date(item.campaign.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button 
                    onClick={() => copyToClipboard(item.campaign.code)}
                    className="flex items-center justify-center px-3 py-1.5 bg-muted hover:bg-accent text-accent-foreground rounded-lg text-sm transition-all border border-border"
                  >
                    {copiedCode === item.campaign.code ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 mr-2 text-green-500" />
                        Link Copied
                      </>
                    ) : (
                      <>
                        <Copy className="w-4 h-4 mr-2" />
                        Copy Link
                      </>
                    )}
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="bg-muted/30 p-3 rounded-lg border border-border/50">
                    <div className="flex items-center text-muted-foreground text-xs mb-1">
                      <TrendingUp className="w-3.5 h-3.5 mr-1.5" />
                      Starts
                    </div>
                    <div className="text-xl font-bold">{item.starts}</div>
                  </div>
                  <div className="bg-muted/30 p-3 rounded-lg border border-border/50">
                    <div className="flex items-center text-muted-foreground text-xs mb-1">
                      <UserPlus className="w-3.5 h-3.5 mr-1.5" />
                      Signups
                    </div>
                    <div className="text-xl font-bold">{item.signups}</div>
                  </div>
                  <div className="bg-muted/30 p-3 rounded-lg border border-border/50">
                    <div className="flex items-center text-muted-foreground text-xs mb-1">
                      <ShoppingBag className="w-3.5 h-3.5 mr-1.5" />
                      Purchases
                    </div>
                    <div className="text-xl font-bold">{item.purchases}</div>
                  </div>
                  <div className="bg-primary/5 p-3 rounded-lg border border-primary/10">
                    <div className="flex items-center text-primary/70 text-xs mb-1">
                      <DollarSign className="w-3.5 h-3.5 mr-1.5" />
                      Revenue
                    </div>
                    <div className="text-xl font-bold text-primary">${item.revenue_usd.toFixed(2)}</div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default Referrals;
