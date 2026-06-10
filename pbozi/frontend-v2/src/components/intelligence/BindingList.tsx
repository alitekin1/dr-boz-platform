import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Trash2, CheckCircle2, XCircle, Plus, Wrench as ToolIcon, Globe, Folder, MessageSquare } from 'lucide-react';
import { getToolBindings, deleteToolBinding, createToolBinding, updateToolBinding, getTools } from '../../lib/api';
import { ToolBinding, Tool } from '../../lib/types';

const BindingList: React.FC = () => {
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [selectedBinding, setSelectedBinding] = React.useState<ToolBinding | null>(null);
  
  const queryClient = useQueryClient();

  const { data: bindings, isLoading, error } = useQuery<ToolBinding[]>({
    queryKey: ['tool-bindings'],
    queryFn: getToolBindings,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteToolBinding(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-bindings'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const handleEdit = (binding: ToolBinding) => {
    setSelectedBinding(binding);
    setIsFormOpen(true);
  };

  const handleAdd = () => {
    setSelectedBinding(null);
    setIsFormOpen(true);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this tool binding?')) {
      deleteMutation.mutate(id);
    }
  };

  const getScopeIcon = (scope: string) => {
    switch (scope) {
      case 'global': return <Globe className="w-4 h-4" />;
      case 'project': return <Folder className="w-4 h-4" />;
      case 'chat': return <MessageSquare className="w-4 h-4" />;
      default: return null;
    }
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading bindings...</div>;
  if (error) return <div className="p-8 text-center text-destructive">Error loading bindings</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Tool Bindings</h3>
        <button
          onClick={handleAdd}
          className="flex items-center space-x-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New Binding</span>
        </button>
      </div>

      <div className="grid gap-4">
        {bindings?.map((binding) => (
          <div
            key={binding.id}
            className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl hover:border-primary/30 transition-all group"
          >
            <div className="space-y-1 flex-1">
              <div className="flex items-center space-x-2">
                <ToolIcon className="w-4 h-4 text-primary" />
                <span className="font-semibold">{binding.tool.display_name || binding.tool.name}</span>
                {binding.is_enabled ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              <div className="flex items-center space-x-3 text-xs text-muted-foreground">
                <div className="flex items-center space-x-1 capitalize bg-muted px-2 py-0.5 rounded">
                  {getScopeIcon(binding.scope_type)}
                  <span>{binding.scope_type}</span>
                </div>
                {binding.scope_id && (
                  <span className="font-mono">ID: {binding.scope_id}</span>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => handleEdit(binding)}
                className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                title="Edit"
              >
                <Edit2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleDelete(binding.id)}
                className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {bindings?.length === 0 && (
          <div className="p-8 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No tool bindings configured. Bind tools to global, project, or chat scopes.
          </div>
        )}
      </div>

      {isFormOpen && (
        <BindingForm
          binding={selectedBinding}
          onClose={() => setIsFormOpen(false)}
        />
      )}
    </div>
  );
};

interface BindingFormProps {
  binding: ToolBinding | null;
  onClose: () => void;
}

const BindingForm: React.FC<BindingFormProps> = ({ binding, onClose }) => {
  const queryClient = useQueryClient();
  const [formData, setFormData] = React.useState({
    tool_id: binding?.tool_id || 0,
    scope_type: binding?.scope_type || 'global',
    scope_id: binding?.scope_id || '',
    is_enabled: binding?.is_enabled ?? true,
  });

  const { data: tools } = useQuery<Tool[]>({
    queryKey: ['tools'],
    queryFn: getTools,
  });

  const mutation = useMutation({
    mutationFn: (data: any) => {
      const payload = {
        ...data,
        tool_id: parseInt(data.tool_id),
        scope_id: data.scope_id ? parseInt(data.scope_id) : null,
      };
      if (binding) {
        return updateToolBinding(binding.id, payload);
      }
      return createToolBinding(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-bindings'] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(formData);
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border w-full max-w-md rounded-2xl shadow-xl overflow-hidden">
        <div className="p-6 border-b border-border flex items-center justify-between bg-muted/30">
          <h3 className="text-xl font-bold">{binding ? 'Edit Binding' : 'New Binding'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg transition-colors">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Tool</label>
            <select
              required
              disabled={!!binding}
              value={formData.tool_id}
              onChange={(e) => setFormData({ ...formData, tool_id: parseInt(e.target.value) })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value={0} disabled>Select a tool...</option>
              {tools?.map(t => (
                <option key={t.id} value={t.id}>{t.display_name || t.name}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Scope Type</label>
              <select
                value={formData.scope_type}
                onChange={(e) => setFormData({ ...formData, scope_type: e.target.value, scope_id: e.target.value === 'global' ? '' : formData.scope_id })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="global">Global</option>
                <option value="project">Project</option>
                <option value="chat">Chat</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Scope ID</label>
              <input
                type="number"
                disabled={formData.scope_type === 'global'}
                required={formData.scope_type !== 'global'}
                value={formData.scope_id}
                onChange={(e) => setFormData({ ...formData, scope_id: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
                placeholder="ID"
              />
            </div>
          </div>

          <div className="flex items-center space-x-2 pt-2">
            <input
              type="checkbox"
              id="is_enabled"
              checked={formData.is_enabled}
              onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
              className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-muted/50"
            />
            <label htmlFor="is_enabled" className="text-sm font-medium">Enabled</label>
          </div>

          <div className="flex items-center justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending || !formData.tool_id}
              className="bg-primary text-primary-foreground px-6 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving...' : (binding ? 'Update' : 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default BindingList;
