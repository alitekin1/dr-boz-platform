import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Edit2, Trash2, CheckCircle2, XCircle, Plus, RefreshCw, Code } from 'lucide-react';
import { getTools, deleteTool, syncBuiltinTools, createTool, updateTool } from '../../lib/api';
import { Tool } from '../../lib/types';

const ToolList: React.FC = () => {
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [selectedTool, setSelectedTool] = React.useState<Tool | null>(null);
  
  const queryClient = useQueryClient();

  const { data: tools, isLoading, error } = useQuery<Tool[]>({
    queryKey: ['tools'],
    queryFn: getTools,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteTool(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: syncBuiltinTools,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const handleEdit = (tool: Tool) => {
    setSelectedTool(tool);
    setIsFormOpen(true);
  };

  const handleAdd = () => {
    setSelectedTool(null);
    setIsFormOpen(true);
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this tool?')) {
      deleteMutation.mutate(id);
    }
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading tools...</div>;
  if (error) return <div className="p-8 text-center text-destructive">Error loading tools</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Available Tools</h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="flex items-center space-x-2 bg-secondary text-secondary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-secondary/80 transition-colors disabled:opacity-50"
            title="Sync Built-in Tools"
          >
            <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            <span>Sync Built-ins</span>
          </button>
          <button
            onClick={handleAdd}
            className="flex items-center space-x-2 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Tool</span>
          </button>
        </div>
      </div>

      <div className="grid gap-4">
        {tools?.map((tool) => (
          <div
            key={tool.id}
            className="flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl hover:border-primary/30 transition-all group"
          >
            <div className="space-y-1 flex-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold">{tool.display_name || tool.name}</span>
                {tool.is_builtin && (
                  <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded uppercase font-bold tracking-wider">
                    Built-in
                  </span>
                )}
                {tool.is_active ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              <p className="text-xs text-muted-foreground line-clamp-1">{tool.description}</p>
              <div className="flex items-center space-x-3 text-[10px] font-mono text-muted-foreground">
                <span>NAME: {tool.name}</span>
                <span>KIND: {tool.kind}</span>
              </div>
            </div>

            <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => handleEdit(tool)}
                className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                title="Edit"
              >
                <Edit2 className="w-4 h-4" />
              </button>
              {!tool.is_builtin && (
                <button
                  onClick={() => handleDelete(tool.id)}
                  className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ))}

        {tools?.length === 0 && (
          <div className="p-8 text-center border-2 border-dashed border-border rounded-xl text-muted-foreground">
            No tools configured. Sync built-ins or add a custom tool.
          </div>
        )}
      </div>

      {isFormOpen && (
        <ToolForm
          tool={selectedTool}
          onClose={() => setIsFormOpen(false)}
        />
      )}
    </div>
  );
};

interface ToolFormProps {
  tool: Tool | null;
  onClose: () => void;
}

const ToolForm: React.FC<ToolFormProps> = ({ tool, onClose }) => {
  const queryClient = useQueryClient();
  const [formData, setFormData] = React.useState({
    name: tool?.name || '',
    display_name: tool?.display_name || '',
    description: tool?.description || '',
    kind: tool?.kind || 'builtin',
    implementation_key: tool?.implementation_key || '',
    input_schema: tool?.input_schema ? JSON.stringify(tool.input_schema, null, 2) : '{}',
    is_active: tool?.is_active ?? true,
  });

  const mutation = useMutation({
    mutationFn: (data: any) => {
      const payload = {
        display_name: data.display_name,
        description: data.description,
        input_schema: JSON.parse(data.input_schema),
        is_active: data.is_active,
      };
      if (!tool?.is_builtin) {
        Object.assign(payload, {
          kind: data.kind,
          implementation_key: data.implementation_key,
        });
      }
      if (tool) {
        return updateTool(tool.id, payload);
      }
      return createTool({
        ...payload,
        name: data.name,
        kind: data.kind,
        implementation_key: data.implementation_key,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] });
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      mutation.mutate(formData);
    } catch (err) {
      alert('Invalid JSON in input schema');
    }
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border w-full max-w-lg rounded-2xl shadow-xl overflow-hidden">
        <div className="p-6 border-b border-border flex items-center justify-between bg-muted/30">
          <h3 className="text-xl font-bold">{tool ? 'Edit Tool' : 'Add Tool'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg transition-colors">
            <XCircle className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Internal Name</label>
              <input
                type="text"
                required
                disabled={!!tool && tool.is_builtin}
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="e.g. calculator"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Display Name</label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="e.g. Advanced Calculator"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Description</label>
            <textarea
              required
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[80px]"
              placeholder="What does this tool do?"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Kind</label>
              <select
                disabled={!!tool && tool.is_builtin}
                value={formData.kind}
                onChange={(e) => setFormData({ ...formData, kind: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="builtin">Built-in</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Implementation Key</label>
              <input
                type="text"
                disabled={!!tool && tool.is_builtin}
                value={formData.implementation_key}
                onChange={(e) => setFormData({ ...formData, implementation_key: e.target.value })}
                className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="Internal key"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium flex items-center space-x-2">
                <Code className="w-4 h-4" />
                <span>Input Schema (JSON)</span>
              </label>
            </div>
            <textarea
              value={formData.input_schema}
              onChange={(e) => setFormData({ ...formData, input_schema: e.target.value })}
              className="w-full bg-muted/50 border border-border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[120px]"
            />
          </div>

          <div className="flex items-center space-x-2 pt-2">
            <input
              type="checkbox"
              id="is_active"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-muted/50"
            />
            <label htmlFor="is_active" className="text-sm font-medium">Active and available</label>
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
              disabled={mutation.isPending}
              className="bg-primary text-primary-foreground px-6 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving...' : (tool ? 'Update Tool' : 'Create Tool')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ToolList;
