import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Plus, Trash2, Edit2, Loader2, X, RefreshCcw, Layout
} from 'lucide-react';
import { 
  getStartScenarios, createStartScenario, updateStartScenario, deleteStartScenario 
} from '../lib/api';

const AdminScenarios: React.FC = () => {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState<any>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState({
    label: '',
    prompt: '',
    order: 0,
    is_active: true
  });

  const { data: scenarios = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['start-scenarios'],
    queryFn: getStartScenarios,
  });

  const createMutation = useMutation({
    mutationFn: createStartScenario,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['start-scenarios'] });
      setIsCreating(false);
      setFormData({ label: '', prompt: '', order: 0, is_active: true });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => updateStartScenario(isEditing.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['start-scenarios'] });
      setIsEditing(null);
      setIsCreating(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteStartScenario,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['start-scenarios'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isEditing) {
      updateMutation.mutate(formData);
    } else {
      createMutation.mutate(formData);
    }
  };

  const handleEdit = (scenario: any) => {
    setIsEditing(scenario);
    setFormData({
      label: scenario.label,
      prompt: scenario.prompt,
      order: scenario.order,
      is_active: scenario.is_active
    });
    setIsCreating(true);
  };

  const handleCancel = () => {
    setIsCreating(false);
    setIsEditing(null);
    setFormData({ label: '', prompt: '', order: 0, is_active: true });
  };

  return (
    <div dir="ltr" className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Welcome Scenarios</h1>
          <p className="text-muted-foreground">Manage quick-start scenarios shown to new users.</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={() => refetch()}
            className="flex items-center px-4 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
          >
            <RefreshCcw className="w-4 h-4 mr-2" />
            Refresh
          </button>
          <button 
            onClick={() => setIsCreating(true)}
            className="flex items-center px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Scenario
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {isCreating && (
          <div className="lg:col-span-1 bg-card border border-border rounded-xl p-6 shadow-sm h-fit sticky top-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold flex items-center">
                {isEditing ? <Edit2 className="w-5 h-5 mr-2 text-primary" /> : <Plus className="w-5 h-5 mr-2 text-primary" />}
                {isEditing ? 'Edit Scenario' : 'Create New Scenario'}
              </h2>
              <button onClick={handleCancel} className="text-muted-foreground hover:text-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Label</label>
                <input
                  type="text"
                  value={formData.label}
                  onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                  className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder="e.g., Stock Market Analyst"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">System Prompt</label>
                <textarea
                  value={formData.prompt}
                  onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
                  className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 h-32 resize-none"
                  placeholder="System prompt or initial instructions..."
                  required
                />
              </div>
              <div className="flex gap-4">
                <div className="space-y-2 flex-1">
                  <label className="text-sm font-medium">Display Order</label>
                  <input
                    type="number"
                    value={formData.order}
                    onChange={(e) => setFormData({ ...formData, order: parseInt(e.target.value) })}
                    className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <div className="space-y-2 flex items-end">
                  <label className="flex items-center gap-2 cursor-pointer pb-2">
                    <input
                      type="checkbox"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      className="w-4 h-4 text-primary rounded"
                    />
                    <span className="text-sm font-medium">Active</span>
                  </label>
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleCancel}
                  className="flex-1 py-2 bg-secondary text-secondary-foreground rounded-lg font-medium hover:bg-secondary/80 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {(createMutation.isPending || updateMutation.isPending) ? 'Saving...' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        )}

        <div className={`${isCreating ? 'lg:col-span-2' : 'lg:col-span-3'} space-y-4`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-48 bg-card border border-border rounded-xl animate-pulse">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground mr-2" />
              <p className="text-muted-foreground">Loading scenarios...</p>
            </div>
          ) : scenarios.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 bg-card border border-border rounded-xl text-muted-foreground gap-2">
              <Layout className="w-8 h-8 opacity-20" />
              <p>No welcome scenarios created yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {scenarios.map((scenario) => (
                <div key={scenario.id} className="bg-card border border-border rounded-xl p-5 shadow-sm hover:border-primary/50 transition-colors group">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1 flex-1 text-left">
                      <div className="flex items-center gap-2">
                        <h3 className="font-bold text-lg">{scenario.label}</h3>
                        <span className="text-xs font-mono bg-muted px-2 py-0.5 rounded text-muted-foreground">
                          Order: {scenario.order}
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${scenario.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                          {scenario.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-2 mt-2 bg-muted/30 p-3 rounded-lg border border-border/50">
                        {scenario.prompt}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button 
                        onClick={() => handleEdit(scenario)}
                        className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                        title="Edit Scenario"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button 
                        onClick={() => {
                          if (confirm('Are you sure you want to delete this scenario?')) {
                            deleteMutation.mutate(scenario.id);
                          }
                        }}
                        className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                        title="Delete Scenario"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminScenarios;
