import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Save, Eye, EyeOff, Loader2, Sparkles } from 'lucide-react';
import { getPrompts, updatePrompt, createPrompt, previewPrompt } from '../../lib/api';
import { SystemPrompt } from '../../lib/types';

const DEFAULT_PROMPT_NAME = 'default';

const SystemPromptEditor: React.FC = () => {
  const queryClient = useQueryClient();
  const [content, setContent] = React.useState('');
  const [previewText, setPreviewText] = React.useState('');
  const [showPreview, setShowPreview] = React.useState(false);

  const { data: prompts, isLoading } = useQuery<SystemPrompt[]>({
    queryKey: ['prompts'],
    queryFn: getPrompts,
  });

  const defaultPrompt = React.useMemo(
    () => (prompts || []).find((p) => p.name === DEFAULT_PROMPT_NAME) || null,
    [prompts]
  );

  React.useEffect(() => {
    if (defaultPrompt) {
      setContent(defaultPrompt.content || '');
    }
  }, [defaultPrompt]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (defaultPrompt) {
        return updatePrompt(defaultPrompt.id, { content });
      } else {
        return createPrompt({
          name: DEFAULT_PROMPT_NAME,
          content,
          is_active: true,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
      alert('System prompt saved successfully!');
    },
  });

  const previewMutation = useMutation({
    mutationFn: (text: string) => previewPrompt(text),
    onSuccess: (data) => {
      setPreviewText(data.resolved);
      setShowPreview(true);
    },
  });

  const handlePreview = () => {
    if (showPreview) {
      setShowPreview(false);
    } else {
      previewMutation.mutate(content);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <MessageSquare className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">System Prompt</h3>
            <p className="text-sm text-muted-foreground">
              Define the core behavior and identity of the AI agent.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handlePreview}
            disabled={previewMutation.isPending}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg border border-border hover:bg-muted/50 transition-colors text-sm font-medium"
          >
            {previewMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : showPreview ? (
              <EyeOff className="w-4 h-4" />
            ) : (
              <Eye className="w-4 h-4" />
            )}
            <span>{showPreview ? 'Hide Preview' : 'Preview'}</span>
          </button>
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity text-sm font-medium"
          >
            {saveMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>Save Changes</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-muted-foreground">Prompt Template</label>
            <div className="flex items-center space-x-2 text-[10px] text-muted-foreground bg-muted/50 px-2 py-0.5 rounded border border-border">
              <Sparkles className="w-3 h-3" />
              <span>Supports @today, @skills, @tools, @path/to/file</span>
            </div>
          </div>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full h-80 rounded-xl border border-border bg-background p-4 text-sm font-mono focus:ring-2 focus:ring-primary/20 outline-none transition-all resize-none"
            placeholder="Enter system prompt template here..."
          />
        </div>

        {showPreview && (
          <div className="space-y-2 animate-in slide-in-from-top-2 duration-300">
            <label className="text-sm font-medium text-muted-foreground">Resolved Preview</label>
            <div className="w-full min-h-[10rem] max-h-[30rem] overflow-y-auto rounded-xl border border-border bg-muted/30 p-4 text-sm whitespace-pre-wrap font-sans">
              {previewText}
            </div>
          </div>
        )}
      </div>

      <div className="bg-primary/5 border border-primary/10 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-primary mb-2 flex items-center">
          <Sparkles className="w-4 h-4 mr-2" />
          Pro Tip: Dynamic Variables
        </h4>
        <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
          <li>Use <code className="text-primary font-mono px-1 bg-primary/10 rounded">@today</code> for current date.</li>
          <li>Use <code className="text-primary font-mono px-1 bg-primary/10 rounded">@skills</code> to list active skills from database.</li>
          <li>Use <code className="text-primary font-mono px-1 bg-primary/10 rounded">@tools</code> to list available tools.</li>
          <li>Use <code className="text-primary font-mono px-1 bg-primary/10 rounded">@backend/app/main.py</code> to include any file content.</li>
        </ul>
      </div>
    </div>
  );
};

export default SystemPromptEditor;
