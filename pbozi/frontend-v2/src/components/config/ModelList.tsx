import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Trash2, CheckCircle2, XCircle, Plus, Zap, Power, ImageIcon, Upload, Download, Star, CheckSquare, Square } from 'lucide-react';
import { getModels, deleteModel, getProviders, updateModel, importModelsCSV, bulkUpdateModels } from '../../lib/api';
import { Model, Provider } from '../../lib/types';
import ModelForm from './ModelForm';

const ModelList: React.FC = () => {
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [selectedModel, setSelectedModel] = React.useState<Model | null>(null);
  const [selectedIds, setSelectedIds] = React.useState<number[]>([]);
  
  const queryClient = useQueryClient();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const { data: models, isLoading: modelsLoading } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: getModels,
  });

  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: getProviders,
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importModelsCSV(file),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      alert(`Import complete!\nSuccess: ${data.success}\nFailed: ${data.failed}${data.errors.length > 0 ? '\n\nErrors:\n' + data.errors.join('\n') : ''}`);
      if (fileInputRef.current) fileInputRef.current.value = '';
    },
    onError: (error: any) => {
      alert(`Import failed: ${error.response?.data?.detail || error.message}`);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteModel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const toggleModelMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      updateModel(id, { is_active: isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
    },
  });

  const bulkMutation = useMutation({
    mutationFn: (data: { ids: number[]; action: "delete" | "enable" | "disable" }) => bulkUpdateModels(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setSelectedIds([]);
    },
    onError: (error: any) => {
      alert(`Bulk action failed: ${error.response?.data?.detail || error.message}`);
    }
  });

  const handleEdit = (model: Model) => {
    setSelectedModel(model);
    setIsFormOpen(true);
  };

  const handleAdd = () => {
    setSelectedModel(null);
    setIsFormOpen(true);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this model?')) {
      deleteMutation.mutate(id);
    }
  };

  const handleToggle = (model: Model) => {
    toggleModelMutation.mutate({ id: model.id, isActive: !model.is_active });
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
    }
  };

  const handleSelectAll = () => {
    if (selectedIds.length === models?.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(models?.map(m => m.id) || []);
    }
  };

  const handleSelectModel = (id: number) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const handleBulkAction = (action: "delete" | "enable" | "disable") => {
    if (action === 'delete') {
      if (!window.confirm(`Are you sure you want to delete ${selectedIds.length} models?`)) return;
    }
    bulkMutation.mutate({ ids: selectedIds, action });
  };

  const getProviderName = (id: number | null) => {
    if (id === null) return 'Virtual';
    return providers?.find(p => p.id === id)?.name || 'Unknown Provider';
  };

  const isAutoRouter = (model: Model): boolean => {
    return model.capabilities?.model_type === 'auto_router';
  };

  const supportsImageInput = (model: Model): boolean => {
    const value = model.capabilities?.image_input;
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      return ['true', '1', 'yes', 'on'].includes(normalized);
    }
    return false;
  };

  if (modelsLoading) return <div className="p-8 text-center text-muted-foreground">Loading models...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h3 className="text-lg font-semibold">AI Models</h3>
          {models && models.length > 0 && (
            <button
              onClick={handleSelectAll}
              className="flex items-center space-x-1.5 text-xs font-medium text-muted-foreground hover:text-primary transition-colors"
            >
              {selectedIds.length === models.length ? (
                <CheckSquare className="w-4 h-4 text-primary" />
              ) : (
                <Square className="w-4 h-4" />
              )}
              <span>{selectedIds.length === models.length ? 'Deselect All' : 'Select All'}</span>
            </button>
          )}
        </div>
        <div className="flex items-center space-x-2">
          {selectedIds.length > 0 ? (
            <div className="flex items-center bg-primary/10 border border-primary/20 rounded-lg px-2 py-1 space-x-2 animate-in fade-in slide-in-from-top-1 duration-200">
              <span className="text-xs font-bold text-primary mr-2">{selectedIds.length} selected</span>
              <button
                onClick={() => handleBulkAction('enable')}
                disabled={bulkMutation.isPending}
                className="text-[10px] bg-green-500/20 text-green-600 px-2 py-1 rounded hover:bg-green-500/30 transition-colors font-bold uppercase"
              >
                Enable
              </button>
              <button
                onClick={() => handleBulkAction('disable')}
                disabled={bulkMutation.isPending}
                className="text-[10px] bg-amber-500/20 text-amber-600 px-2 py-1 rounded hover:bg-amber-500/30 transition-colors font-bold uppercase"
              >
                Disable
              </button>
              <button
                onClick={() => handleBulkAction('delete')}
                disabled={bulkMutation.isPending}
                className="text-[10px] bg-destructive/20 text-destructive px-2 py-1 rounded hover:bg-destructive/30 transition-colors font-bold uppercase"
              >
                Delete
              </button>
              <div className="w-px h-4 bg-primary/20 mx-1" />
              <button
                onClick={() => setSelectedIds([])}
                className="p-1 hover:bg-primary/20 rounded transition-colors"
              >
                <XCircle className="w-4 h-4 text-primary" />
              </button>
            </div>
          ) : (
            <>
              <a
                href="/models_template.csv"
                download="models_template.csv"
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
                <span>Add Model</span>
              </button>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4">
        {models?.map((model) => (
          <div
            key={model.id}
            className={`flex items-center justify-between p-4 border rounded-xl transition-all group ${
              selectedIds.includes(model.id)
                ? 'bg-primary/5 border-primary/50 ring-1 ring-primary/20'
                : 'bg-muted/30 border-border hover:border-primary/30'
            }`}
          >
            <div className="flex items-center space-x-4">
              <button
                onClick={() => handleSelectModel(model.id)}
                className="p-1 rounded hover:bg-primary/10 transition-colors"
              >
                {selectedIds.includes(model.id) ? (
                  <CheckSquare className="w-5 h-5 text-primary" />
                ) : (
                  <Square className="w-5 h-5 text-muted-foreground/50" />
                )}
              </button>
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold">{model.display_name || model.name}</span>
                  {model.is_default && (
                    <span className="inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 font-bold uppercase tracking-wider" title="Global Default Model">
                      <Star className="w-3 h-3 fill-amber-600" />
                      <span>Default</span>
                    </span>
                  )}
                  {model.is_active ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  ) : (
                    <XCircle className="w-4 h-4 text-muted-foreground" />
                  )}
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium uppercase tracking-wider">
                    {getProviderName(model.provider_id)}
                  </span>
                  {isAutoRouter(model) && (
                    <span className="inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded-full bg-sky-500/10 text-sky-600 font-medium uppercase tracking-wider">
                      <Zap className="w-3 h-3" />
                      <span>Auto</span>
                    </span>
                  )}
                  {supportsImageInput(model) && (
                    <span className="inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 font-medium uppercase tracking-wider">
                      <ImageIcon className="w-3 h-3" />
                      <span>Vision</span>
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <Zap className="w-3 h-3" />
                    <span>{model.context_window.toLocaleString()} ctx</span>
                  </div>
                  <span>In: ${model.pricing_input}/1M ({model.pricing_input_toman.toLocaleString()} تومان)</span>
                  <span>Out: ${model.pricing_output}/1M ({model.pricing_output_toman.toLocaleString()} تومان)</span>
                </div>
                <p className="text-[10px] text-muted-foreground/60 font-mono">{model.name}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => handleToggle(model)}
                disabled={toggleModelMutation.isPending}
                className={`inline-flex items-center space-x-1 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                  model.is_active
                    ? 'bg-green-500/10 text-green-600 hover:bg-green-500/20'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                } disabled:opacity-60`}
                title={model.is_active ? 'Disable model' : 'Enable model'}
              >
                <Power className="w-3 h-3" />
                <span>{model.is_active ? 'On' : 'Off'}</span>
              </button>
              <button
                onClick={() => handleEdit(model)}
                className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                title="Edit"
              >
                <Edit2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleDelete(model.id)}
                className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {models?.length === 0 && (
          <div className="p-8 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No models configured. Add your first AI model.
          </div>
        )}
      </div>

      <ModelForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        model={selectedModel}
      />
    </div>
  );
};

export default ModelList;
