import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Folder, Plus, Trash2, Upload, File, Loader2, Info, ChevronRight, X, Database, Settings, AlertCircle
} from 'lucide-react';
import { 
  getProjects, createProject, deleteProject, 
  getDocuments, uploadDocument, deleteDocument,
  updateProject, getProjectImports
} from '../lib/api';
import { Project, Document } from '../lib/types';

interface ProjectSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
}

const ProjectImportsModal: React.FC<ProjectSettingsModalProps> = ({ isOpen, onClose, project }) => {
  const { data: imports = [], isLoading } = useQuery<Project[]>({
    queryKey: ['project-imports', project?.id],
    queryFn: () => getProjectImports(project!.id),
    enabled: isOpen && !!project,
  });

  if (!isOpen || !project) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Database className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Project Imports: {project.name}</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 max-h-[60vh] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center p-12 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              <span>Loading imports...</span>
            </div>
          ) : imports.length === 0 ? (
            <div className="text-center p-12 text-muted-foreground font-medium italic">
              <p>No imports found for this project.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {imports.map(imp => (
                <div key={imp.id} className="p-4 border border-border rounded-xl bg-card hover:bg-muted/30 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="overflow-hidden">
                      <p className="font-bold text-sm truncate">{imp.name}</p>
                      <div className="flex items-center space-x-2 mt-1">
                        <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                          Imported {new Date(imp.created_at).toLocaleDateString()}
                        </p>
                        {imp.owner_user_id && (
                          <>
                            <span className="text-muted-foreground/30">•</span>
                            <p className="text-[10px] text-muted-foreground font-medium">Owner ID: {imp.owner_user_id}</p>
                          </>
                        )}
                      </div>
                    </div>
                    {imp.import_count !== undefined && imp.import_count > 0 && (
                      <div className="flex items-center space-x-1 px-2 py-1 bg-primary/10 text-primary rounded-lg">
                        <Database className="w-3 h-3" />
                        <span className="text-[10px] font-black">{imp.import_count} sub-imports</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="p-4 border-t border-border bg-muted/20 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 rounded-lg text-sm font-bold bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

const ProjectSettingsModal: React.FC<ProjectSettingsModalProps> = ({ isOpen, onClose, project }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [error, setError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  React.useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description || '');
      setInstructions(project.instructions || '');
    }
  }, [project]);

  const mutation = useMutation({
    mutationFn: () => {
      if (!project) throw new Error('No project selected');
      return updateProject(project.id, { name, description, instructions });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    },
  });

  if (!isOpen || !project) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Project name is required');
      return;
    }
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Settings className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Project Settings</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground px-1 uppercase tracking-wider">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground px-1 uppercase tracking-wider">Description</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 h-20 resize-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground px-1 uppercase tracking-wider">Instructions</label>
            <textarea
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 h-32 resize-none"
              placeholder="System prompt instructions for this project..."
            />
          </div>

          {error && (
            <div className="p-3 bg-destructive/10 text-destructive text-xs rounded-lg flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex space-x-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-lg text-sm font-medium bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex-1 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-lg shadow-primary/20"
            >
              {mutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const Projects: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [viewingImports, setViewingImports] = useState<Project | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [newProject, setNewProject] = useState({ name: '', description: '', instructions: '' });
  
  // Upload state
  const [uploadProgress, setUploadProgress] = useState<{
    current: number;
    total: number;
    fileName: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: projects = [], isLoading: isLoadingProjects } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => getProjects({ root_only: true }),
  });

  const { data: documents = [], isLoading: isLoadingDocuments } = useQuery<Document[]>({
    queryKey: ['documents', selectedProjectId],
    queryFn: () => getDocuments(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setIsCreating(false);
      setNewProject({ name: '', description: '', instructions: '' });
    },
  });

  const deleteProjectMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      if (selectedProjectId) {
        setSelectedProjectId(null);
      }
    },
  });

  const deleteDocMutation = useMutation({
    mutationFn: (docId: number) => deleteDocument(selectedProjectId!, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', selectedProjectId] });
    },
  });

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProject.name.trim()) return;
    createMutation.mutate(newProject);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !selectedProjectId) return;

    const fileList = Array.from(files);
    setUploadProgress({ current: 0, total: fileList.length, fileName: '' });

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      setUploadProgress({ current: i + 1, total: fileList.length, fileName: file.name });
      
      try {
        await uploadDocument(selectedProjectId, file);
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
      }
    }

    setUploadProgress(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    queryClient.invalidateQueries({ queryKey: ['documents', selectedProjectId] });
  };

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
        <p className="text-muted-foreground">
          Manage your projects and their knowledge base documents.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Left Column: Project List */}
        <div className="md:col-span-1 space-y-4">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-xl font-semibold">All Projects</h2>
            <button
              onClick={() => setIsCreating(!isCreating)}
              className="p-2 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors"
              title="New Project"
            >
              <Plus className="w-5 h-5" />
            </button>
          </div>

          {isCreating && (
            <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-4 animate-in fade-in slide-in-from-top-2">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-sm">Create New Project</h3>
                <button onClick={() => setIsCreating(false)} className="text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <form onSubmit={handleCreateProject} className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground px-1">NAME</label>
                  <input
                    type="text"
                    placeholder="e.g. Health Knowledge Base"
                    value={newProject.name}
                    onChange={e => setNewProject({ ...newProject, name: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground px-1">DESCRIPTION</label>
                  <textarea
                    placeholder="What is this project about?"
                    value={newProject.description}
                    onChange={e => setNewProject({ ...newProject, description: e.target.value })}
                    className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 h-20 resize-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="w-full py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-lg shadow-primary/20"
                >
                  {createMutation.isPending ? 'Creating...' : 'Create Project'}
                </button>
              </form>
            </div>
          )}

          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2 scrollbar-thin">
            {isLoadingProjects ? (
              <div className="flex items-center justify-center p-12 text-muted-foreground">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                <span>Loading projects...</span>
              </div>
            ) : projects.length === 0 ? (
              <div className="text-center p-12 bg-muted/30 rounded-2xl border border-dashed border-border text-muted-foreground">
                <Folder className="w-10 h-10 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No projects found</p>
                <p className="text-xs mt-1">Create one to get started</p>
              </div>
            ) : (
              projects.map(project => (
                <button
                  key={project.id}
                  onClick={() => setSelectedProjectId(project.id)}
                  className={`
                    w-full flex items-center justify-between p-4 rounded-xl border transition-all text-left group
                    ${selectedProjectId === project.id 
                      ? 'bg-primary/5 border-primary shadow-sm' 
                      : 'bg-card border-border hover:border-primary/50 hover:bg-muted/30'}
                  `}
                >
                  <div className="flex items-center space-x-3 overflow-hidden">
                    <div className={`p-2.5 rounded-lg shrink-0 transition-colors ${selectedProjectId === project.id ? 'bg-primary text-primary-foreground shadow-md' : 'bg-muted text-muted-foreground group-hover:bg-primary/10'}`}>
                      <Folder className="w-4 h-4" />
                    </div>
                    <div className="overflow-hidden">
                      <p className="font-semibold text-sm truncate">{project.name}</p>
                      {project.description && (
                        <p className="text-xs text-muted-foreground line-clamp-1">{project.description}</p>
                      )}
                    </div>
                    {project.import_count !== undefined && project.import_count > 0 && (
                      <div 
                        onClick={(e) => { e.stopPropagation(); setViewingImports(project); }}
                        className="flex items-center space-x-1 px-2 py-1 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors cursor-pointer"
                        role="button"
                        title="View Imports"
                      >
                        <Database className="w-3 h-3" />
                        <span className="text-[10px] font-bold">{project.import_count} imports</span>
                      </div>
                    )}
                  </div>
                  <ChevronRight className={`w-4 h-4 shrink-0 transition-transform duration-300 ${selectedProjectId === project.id ? 'translate-x-1 text-primary' : 'text-muted-foreground opacity-0 group-hover:opacity-100'}`} />
                </button>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Project Details & Documents */}
        <div className="md:col-span-2 space-y-6">
          {selectedProject ? (
            <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden animate-in fade-in slide-in-from-right-4 duration-500">
              <div className="p-6 border-b border-border bg-muted/20 flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">{selectedProject.name}</h2>
                  <p className="text-xs text-muted-foreground mt-1 flex items-center">
                    <Info className="w-3 h-3 mr-1" />
                    Created on {new Date(selectedProject.created_at).toLocaleDateString(undefined, { dateStyle: 'long' })}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setIsEditing(true)}
                    className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors group"
                    title="Project Settings"
                  >
                    <Settings className="w-5 h-5 transition-transform group-hover:rotate-90" />
                  </button>
                  <button 
                    onClick={() => {
                      if (confirm('Are you sure you want to delete this project? All associated documents and embeddings will be removed.')) {
                        deleteProjectMutation.mutate(selectedProject.id);
                      }
                    }}
                    className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors group"
                    title="Delete Project"
                  >
                    <Trash2 className="w-5 h-5 transition-transform group-hover:scale-110" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-8">
                {/* Description / Instructions */}
                {(selectedProject.description || selectedProject.instructions) && (
                  <div className="space-y-4">
                    <div className="flex items-center space-x-2 text-muted-foreground">
                      <h3 className="text-xs font-bold uppercase tracking-widest">About Project</h3>
                      <div className="h-px bg-border flex-1"></div>
                    </div>
                    <div className="grid grid-cols-1 gap-4">
                      {selectedProject.description && (
                        <div className="p-4 bg-muted/30 rounded-xl border border-border/50">
                          <p className="text-[10px] font-bold text-primary mb-2 uppercase tracking-tight">Description</p>
                          <p className="text-sm whitespace-pre-wrap leading-relaxed">{selectedProject.description}</p>
                        </div>
                      )}
                      {selectedProject.instructions && (
                        <div className="p-4 bg-muted/30 rounded-xl border border-border/50">
                          <p className="text-[10px] font-bold text-primary mb-2 uppercase tracking-tight">Custom Instructions</p>
                          <p className="text-sm whitespace-pre-wrap leading-relaxed italic text-muted-foreground">{selectedProject.instructions}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Documents Section */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2 text-muted-foreground">
                      <h3 className="text-xs font-bold uppercase tracking-widest">Documents & Knowledge</h3>
                      <div className="h-px bg-border w-24"></div>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileUpload}
                        className="hidden"
                        multiple
                      />
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={!!uploadProgress}
                        className="flex items-center space-x-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:bg-primary/90 transition-all disabled:opacity-50 shadow-md shadow-primary/10 active:scale-95"
                      >
                        {uploadProgress ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Upload className="w-4 h-4" />
                        )}
                        <span>{uploadProgress ? 'Uploading...' : 'Upload Knowledge'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Upload Progress Indicator */}
                  {uploadProgress && (
                    <div className="p-4 bg-primary/5 border border-primary/20 rounded-2xl animate-in zoom-in-95 duration-300">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center space-x-2">
                          <div className="p-1.5 bg-primary/10 rounded-lg">
                            <Loader2 className="w-4 h-4 animate-spin text-primary" />
                          </div>
                          <span className="text-sm font-bold text-primary">
                            Processing file {uploadProgress.current} of {uploadProgress.total}
                          </span>
                        </div>
                        <span className="text-xs font-mono bg-primary/10 px-2 py-1 rounded text-primary">
                          {Math.round((uploadProgress.current / uploadProgress.total) * 100)}%
                        </span>
                      </div>
                      <div className="w-full bg-primary/10 rounded-full h-2 mb-3 overflow-hidden">
                        <div 
                          className="bg-primary h-full rounded-full transition-all duration-500 ease-out shadow-[0_0_8px_rgba(var(--primary),0.5)]"
                          style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
                        />
                      </div>
                      <div className="flex items-center space-x-2 px-1">
                        <File className="w-3 h-3 text-muted-foreground" />
                        <p className="text-xs text-muted-foreground truncate italic">
                          {uploadProgress.fileName}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Documents List */}
                  <div className="grid grid-cols-1 gap-2.5">
                    {isLoadingDocuments ? (
                      <div className="flex flex-col items-center justify-center p-12 text-muted-foreground space-y-3">
                        <Loader2 className="w-8 h-8 animate-spin opacity-50" />
                        <span className="text-sm">Fetching document index...</span>
                      </div>
                    ) : documents.length === 0 ? (
                      <div className="text-center p-16 bg-muted/10 rounded-3xl border border-dashed border-border/50 group hover:bg-muted/20 transition-colors">
                        <div className="w-16 h-16 bg-background border border-border rounded-2xl flex items-center justify-center mx-auto mb-4 text-muted-foreground/30 group-hover:scale-110 transition-transform duration-500">
                          <File className="w-8 h-8" />
                        </div>
                        <h3 className="font-bold text-lg">Empty Knowledge Base</h3>
                        <p className="text-sm text-muted-foreground mt-2 max-w-[240px] mx-auto">
                          Upload PDFs, text files or documents to train the AI on your specific data.
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-2.5">
                        {documents.map(doc => (
                          <div 
                            key={doc.id}
                            className="group flex items-center justify-between p-3.5 bg-card border border-border/60 rounded-2xl hover:border-primary/40 hover:bg-primary/[0.02] hover:shadow-sm transition-all duration-200"
                          >
                            <div className="flex items-center space-x-4 overflow-hidden">
                              <div className="p-2.5 bg-muted rounded-xl text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                                <File className="w-4 h-4" />
                              </div>
                              <div className="overflow-hidden">
                                <p className="text-sm font-semibold truncate group-hover:text-foreground transition-colors">{doc.filename}</p>
                                <div className="flex items-center space-x-3 text-[10px] text-muted-foreground font-medium uppercase tracking-wider mt-0.5">
                                  <span className="px-1.5 py-0.5 bg-muted rounded text-xs">{doc.file_type}</span>
                                  <span className="flex items-center"><Database className="w-3 h-3 mr-1" /> {doc.chunk_count || 0} chunks</span>
                                  <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                                </div>
                              </div>
                            </div>
                            <button
                              onClick={() => {
                                if (confirm(`Delete document "${doc.filename}"? This cannot be undone.`)) {
                                  deleteDocMutation.mutate(doc.id);
                                }
                              }}
                              className="p-2.5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-xl transition-all"
                              title="Delete Document"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-[600px] flex flex-col items-center justify-center p-12 bg-muted/10 rounded-3xl border border-dashed border-border/50 text-center animate-in fade-in zoom-in-95 duration-700">
              <div className="w-24 h-24 bg-background border border-border rounded-3xl flex items-center justify-center mb-6 text-muted-foreground/20 shadow-inner">
                <Folder className="w-12 h-12" />
              </div>
              <h2 className="text-2xl font-black tracking-tight">Knowledge Workspace</h2>
              <p className="text-muted-foreground mt-3 max-w-[320px] leading-relaxed">
                Select a project from the left panel to manage its training data, configurations, and specialized knowledge.
              </p>
              <div className="mt-8 flex items-center space-x-2 text-xs font-bold text-primary bg-primary/10 px-4 py-2 rounded-full uppercase tracking-widest">
                <ChevronRight className="w-3 h-3 animate-pulse" />
                <span>Select to begin</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <ProjectSettingsModal 
        isOpen={isEditing} 
        onClose={() => setIsEditing(false)} 
        project={selectedProject || null} 
      />

      <ProjectImportsModal 
        isOpen={!!viewingImports} 
        onClose={() => setViewingImports(null)} 
        project={viewingImports} 
      />
    </div>
  );
};

export default Projects;
