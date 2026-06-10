import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Trash2, CheckCircle2, XCircle, Plus } from 'lucide-react';
import { Download, Upload } from 'lucide-react';
import { getProviders, deleteProvider, importProvidersCSV } from '../../lib/api';
import { Provider } from '../../lib/types';
import ProviderForm from './ProviderForm';
import CodexAccountList from './CodexAccountList';

const ProviderList: React.FC = () => {
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [selectedProvider, setSelectedProvider] = React.useState<Provider | null>(null);
  
  const queryClient = useQueryClient();

  const { data: providers, isLoading, error } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: getProviders,
  });

  
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const importMutation = useMutation({
    mutationFn: (file: File) => importProvidersCSV(file),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      if (fileInputRef.current) fileInputRef.current.value = '';
      alert(`Import complete!\nSuccess: ${data.success}\nFailed: ${data.failed}${data.errors.length > 0 ? '\n\nErrors:\n' + data.errors.join('\n') : ''}`);
    },
    onError: (err: any) => {
      if (fileInputRef.current) fileInputRef.current.value = '';
      alert(`Import failed: ${err.message || 'Unknown error'}`);
    }
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const handleEdit = (provider: Provider) => {
    setSelectedProvider(provider);
    setIsFormOpen(true);
  };

  const handleAdd = () => {
    setSelectedProvider(null);
    setIsFormOpen(true);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this provider?')) {
      deleteMutation.mutate(id);
    }
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading providers...</div>;
  if (error) return <div className="p-8 text-center text-destructive">Error loading providers</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">AI Providers</h3>
<div className="flex items-center space-x-2">
          <a
            href="/providers_models_template.csv"
            download="providers_models_template.csv"
            className="flex items-center space-x-1 text-sm font-medium text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 px-2"
          >
            <Download className="w-4 h-4 mr-1" />
            <span>Template</span>
          </a>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".csv"
            className="hidden"
          />
          <button
            onClick={handleImportClick}
            disabled={importMutation.isPending}
            className="flex items-center space-x-2 bg-muted text-muted-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-muted/80 transition-colors disabled:opacity-50"
          >
            <Upload className="w-4 h-4" />
            <span>{importMutation.isPending ? 'Importing...' : 'Import CSV'}</span>
          </button>
          <button
            onClick={handleAdd}
            className="flex items-center space-x-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Provider</span>
          </button>
        </div>
      </div>

      <div className="grid gap-4">
        {providers?.map((provider) => (
          <div
            key={provider.id}
            className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl hover:border-primary/30 transition-all group"
          >
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold">{provider.name}</span>
                {provider.is_active ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] rounded bg-background border border-border px-2 py-0.5 text-muted-foreground">
                  {provider.kind === 'codex_subscription' ? 'Codex subscription' : 'OpenAI-compatible'}
                </span>
                <p className="text-xs text-muted-foreground font-mono">{provider.base_url}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => handleEdit(provider)}
                className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                title="Edit"
              >
                <Edit2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleDelete(provider.id)}
                className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {providers?.length === 0 && (
          <div className="p-8 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No providers configured. Add your first AI provider.
          </div>
        )}
      </div>

      <ProviderForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        provider={selectedProvider}
      />

      <div className="pt-4 border-t border-border">
        <CodexAccountList />
      </div>
    </div>
  );
};

export default ProviderList;
