import React, { useState, useEffect } from 'react';
import { Archive, Play, Square, RefreshCw, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { getBackupStatus, runBackup, startBackupScheduler, stopBackupScheduler } from '../lib/api';
import type { BackupStatus, BackupRun } from '../lib/types';

const Backups: React.FC = () => {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [lastRun, setLastRun] = useState<BackupRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getBackupStatus();
      setStatus(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to fetch backup status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleRunBackup = async () => {
    try {
      setActionLoading('run');
      setError(null);
      const result = await runBackup();
      setLastRun(result);
      await fetchStatus();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Backup run failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleScheduler = async () => {
    if (!status) return;
    try {
      setActionLoading(status.running ? 'stop' : 'start');
      setError(null);
      if (status.running) {
        await stopBackupScheduler();
      } else {
        await startBackupScheduler();
      }
      await fetchStatus();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Scheduler toggle failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Backups</h1>
          <p className="text-muted-foreground">Manage automated database and data backups to Google Drive.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-sm font-medium transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
              <Archive className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Auto Backup</p>
              <p className="text-lg font-semibold">{status?.enabled ? 'Enabled' : 'Disabled'}</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Backups run every {status?.interval_minutes ?? 5} minutes and keep the last {status?.max_count ?? 6} archives on Google Drive.
          </p>
        </div>

        <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
              <Clock className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Scheduler</p>
              <p className="text-lg font-semibold">{status?.running ? 'Running' : 'Stopped'}</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {status?.next_run ? `Next run: ${new Date(status.next_run).toLocaleString()}` : 'No upcoming run scheduled.'}
          </p>
        </div>

        <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
              {lastRun?.status === 'success' ? (
                <CheckCircle className="w-5 h-5 text-green-500" />
              ) : lastRun?.status === 'error' ? (
                <XCircle className="w-5 h-5 text-destructive" />
              ) : (
                <Archive className="w-5 h-5 text-primary" />
              )}
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Last Run</p>
              <p className="text-lg font-semibold">{lastRun?.status ? lastRun.status.charAt(0).toUpperCase() + lastRun.status.slice(1) : 'N/A'}</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {lastRun?.timestamp ? new Date(lastRun.timestamp).toLocaleString() : 'No manual run yet.'}
          </p>
        </div>
      </div>

      <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold mb-4">Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleRunBackup}
            disabled={actionLoading === 'run'}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {actionLoading === 'run' ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            <span>Back Up Now</span>
          </button>

          <button
            onClick={handleToggleScheduler}
            disabled={actionLoading === 'start' || actionLoading === 'stop'}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
              status?.running
                ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                : 'bg-green-500/10 text-green-600 hover:bg-green-500/20'
            }`}
          >
            {actionLoading === 'start' || actionLoading === 'stop' ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : status?.running ? (
              <Square className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            <span>{status?.running ? 'Stop Scheduler' : 'Start Scheduler'}</span>
          </button>
        </div>
      </div>

      {lastRun?.status === 'success' && (
        <div className="bg-background border border-border rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4">Last Backup Result</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Archive</span>
              <span className="font-medium">{lastRun.archive_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Drive File ID</span>
              <span className="font-medium">{lastRun.drive_file_id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Timestamp</span>
              <span className="font-medium">{new Date(lastRun.timestamp).toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}

      {lastRun?.status === 'error' && (
        <div className="flex items-center gap-2 p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm">{lastRun.error || 'Backup failed with an unknown error.'}</p>
        </div>
      )}
    </div>
  );
};

export default Backups;
