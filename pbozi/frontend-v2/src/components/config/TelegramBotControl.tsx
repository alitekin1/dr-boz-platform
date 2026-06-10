import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Power, RefreshCw } from 'lucide-react';
import { createPrompt, getPrompts, getTelegramBotStatus, startTelegramBot, stopTelegramBot, updatePrompt } from '../../lib/api';
import { SystemPrompt, TelegramBotStatus } from '../../lib/types';

const TELEGRAM_START_INTRO_PROMPT_NAME = 'telegram_start_intro';

const TelegramBotControl: React.FC = () => {
  const queryClient = useQueryClient();
  const [introText, setIntroText] = React.useState('');
  const { data, isLoading, error, refetch, isFetching } = useQuery<TelegramBotStatus>({
    queryKey: ['telegram-bot-status'],
    queryFn: getTelegramBotStatus,
    refetchInterval: 5000,
  });
  const {
    data: prompts,
    isLoading: promptsLoading,
    error: promptsError,
  } = useQuery<SystemPrompt[]>({
    queryKey: ['prompts'],
    queryFn: getPrompts,
  });

  const introPrompt = React.useMemo(
    () => (prompts || []).find((prompt) => prompt.name === TELEGRAM_START_INTRO_PROMPT_NAME) || null,
    [prompts],
  );

  React.useEffect(() => {
    setIntroText(introPrompt?.content || '');
  }, [introPrompt?.id, introPrompt?.content]);

  const startMutation = useMutation({
    mutationFn: startTelegramBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['telegram-bot-status'] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: stopTelegramBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['telegram-bot-status'] });
    },
  });
  const saveIntroMutation = useMutation({
    mutationFn: async () => {
      const trimmed = introText.trim();
      if (!trimmed) {
        throw new Error('Please enter an intro message before saving.');
      }
      if (introPrompt) {
        return updatePrompt(introPrompt.id, { content: trimmed, is_active: true });
      }
      return createPrompt({
        name: TELEGRAM_START_INTRO_PROMPT_NAME,
        content: trimmed,
        is_active: true,
        auto_tool_guidance_enabled: false,
        tool_guidance_style: 'compact',
        tool_guidance_template: null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
    },
  });
  const clearIntroMutation = useMutation({
    mutationFn: async () => {
      if (!introPrompt) {
        return null;
      }
      return updatePrompt(introPrompt.id, { content: '', is_active: false });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
    },
  });

  const isMutating = startMutation.isPending || stopMutation.isPending;
  const introMutating = saveIntroMutation.isPending || clearIntroMutation.isPending;

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading Telegram bot status...</div>;
  if (error || !data) return <div className="p-8 text-center text-destructive">Error loading Telegram bot status</div>;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Bot className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Telegram Bot Runtime</h3>
            <p className="text-sm text-muted-foreground">Start or stop the polling bot process from admin.</p>
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-medium ${data.running ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
          {data.running ? 'Running' : 'Stopped'}
        </div>
      </div>

      <div className="bg-muted/30 p-5 rounded-xl border border-border space-y-2">
        <p className="text-sm"><span className="text-muted-foreground">PID:</span> {data.pid ?? '-'}</p>
        <p className="text-sm"><span className="text-muted-foreground">Managed:</span> {data.managed ? 'Yes' : 'No'}</p>
        <p className="text-sm"><span className="text-muted-foreground">Started At:</span> {data.started_at ?? '-'}</p>
        <p className="text-sm"><span className="text-muted-foreground">Detail:</span> {data.detail ?? '-'}</p>
      </div>

      <div className="flex items-center gap-3">
        {data.running ? (
          <button
            onClick={() => stopMutation.mutate()}
            disabled={isMutating}
            className="inline-flex items-center gap-2 bg-destructive text-destructive-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60"
          >
            <Power className="w-4 h-4" />
            <span>{stopMutation.isPending ? 'Stopping...' : 'Turn Off Bot'}</span>
          </button>
        ) : (
          <button
            onClick={() => startMutation.mutate()}
            disabled={isMutating}
            className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60"
          >
            <Power className="w-4 h-4" />
            <span>{startMutation.isPending ? 'Starting...' : 'Turn On Bot'}</span>
          </button>
        )}

        <button
          onClick={() => refetch()}
          disabled={isFetching || isMutating}
          className="inline-flex items-center gap-2 border border-border bg-background px-4 py-2 rounded-lg text-sm font-medium hover:bg-muted/40 transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="border border-border rounded-xl p-5 space-y-4">
        <div className="space-y-1">
          <h4 className="text-base font-semibold">Telegram /start Intro</h4>
          <p className="text-sm text-muted-foreground">
            This message is shown when users run <code>/start</code>.
          </p>
        </div>

        {promptsError ? (
          <div className="text-sm text-destructive">Error loading intro message settings.</div>
        ) : (
          <>
            <textarea
              value={introText}
              onChange={(event) => setIntroText(event.target.value)}
              disabled={promptsLoading || introMutating}
              rows={6}
              placeholder="Write the introduction/announcement shown at /start..."
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-60"
            />

            <div className="flex items-center gap-3">
              <button
                onClick={() => saveIntroMutation.mutate()}
                disabled={promptsLoading || introMutating}
                className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60"
              >
                {saveIntroMutation.isPending ? 'Saving...' : 'Save Intro'}
              </button>
              <button
                onClick={() => clearIntroMutation.mutate()}
                disabled={promptsLoading || introMutating || !introPrompt}
                className="inline-flex items-center gap-2 border border-border bg-background px-4 py-2 rounded-lg text-sm font-medium hover:bg-muted/40 transition disabled:opacity-60"
              >
                {clearIntroMutation.isPending ? 'Clearing...' : 'Clear Intro'}
              </button>
              <span className={`text-xs ${introPrompt?.is_active ? 'text-green-600' : 'text-muted-foreground'}`}>
                {introPrompt?.is_active ? 'Status: Active' : 'Status: Inactive'}
              </span>
            </div>

            {saveIntroMutation.isError && (
              <div className="text-xs text-destructive">
                {(saveIntroMutation.error as Error)?.message || 'Could not save intro message.'}
              </div>
            )}
            {clearIntroMutation.isError && (
              <div className="text-xs text-destructive">
                Could not clear intro message.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default TelegramBotControl;
