import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Folder, 
  FileText, 
  Upload, 
  Plus, 
  Trash2, 
  Loader2, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  Search,
  ChevronRight,
  Database
} from 'lucide-react';
import { 
  getProjects, 
  createProject, 
  deleteProject, 
  getDocuments, 
  uploadDocument, 
  deleteDocument 
} from '../../lib/api';
import { Project, Document } from '../../lib/types';

interface UploadProgress {
  filename: string;
  status: 'pending' | 'uploading' | 'indexing' | 'completed' | 'error';
  progress: number;
  error?: string;
}

const KnowledgeBase: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [isCreatingProject, setIsIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadQueue, setUploadQueue] = useState<UploadProgress[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: projects = [], isLoading: isLoadingProjects } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => getProjects()
  });

  const { data: documents = [], isLoading: isLoadingDocs } = useQuery<Document[]>({
    queryKey: ['documents', selectedProjectId],
    queryFn: () => selectedProjectId ? getDocuments(selectedProjectId) : Promise.resolve([]),
    enabled: !!selectedProjectId
  });

  const createProjectMutation = useMutation({
    mutationFn: (name: string) => createProject({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setNewProjectName('');
      setIsIsCreatingProject(false);
    }
  });

  const deleteProjectMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      if (selectedProjectId) setSelectedProjectId(null);
    }
  });

  const deleteDocMutation = useMutation({
    mutationFn: ({ projId, docId }: { projId: number, docId: number }) => deleteDocument(projId, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', selectedProjectId] });
    }
  });

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || !selectedProjectId) return;

    const newUploads: UploadProgress[] = Array.from(files).map(f => ({
      filename: f.name,
      status: 'pending',
      progress: 0
    }));

    setUploadQueue(prev => [...newUploads, ...prev]);

    // Process files one by one
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      
      setUploadQueue(prev => prev.map(u => 
        u.filename === file.name ? { ...u, status: 'uploading', progress: 30 } : u
      ));

      try {
        setUploadQueue(prev => prev.map(u => 
          u.filename === file.name ? { ...u, status: 'indexing', progress: 60 } : u
        ));

        await uploadDocument(selectedProjectId, file);

        setUploadQueue(prev => prev.map(u => 
          u.filename === file.name ? { ...u, status: 'completed', progress: 100 } : u
        ));
        
        queryClient.invalidateQueries({ queryKey: ['documents', selectedProjectId] });
      } catch (err: any) {
        setUploadQueue(prev => prev.map(u => 
          u.filename === file.name ? { ...u, status: 'error', error: err.message || 'Upload failed' } : u
        ));
      }
    }

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-[600px]">
      {/* Projects List */}
      <div className="md:col-span-1 border border-border rounded-xl bg-card/30 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
          <h3 className="font-semibold flex items-center gap-2">
            <Folder className="w-4 h-4 text-primary" />
            Projects
          </h3>
          <button 
            onClick={() => setIsIsCreatingProject(true)}
            className="p-1 hover:bg-primary/10 rounded-full text-primary transition-colors"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>

        <div className="p-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input 
              type="text"
              placeholder="Search projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-muted/50 border border-border rounded-lg py-1.5 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isCreatingProject && (
            <div className="p-2 space-y-2 border border-primary/30 rounded-lg bg-primary/5 animate-in fade-in slide-in-from-top-1">
              <input 
                autoFocus
                type="text"
                placeholder="Project name..."
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') createProjectMutation.mutate(newProjectName);
                  if (e.key === 'Escape') setIsIsCreatingProject(false);
                }}
                className="w-full bg-background border border-border rounded-md py-1 px-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <div className="flex justify-end gap-2">
                <button 
                  onClick={() => setIsIsCreatingProject(false)}
                  className="text-xs px-2 py-1 text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
                <button 
                  onClick={() => createProjectMutation.mutate(newProjectName)}
                  disabled={!newProjectName.trim() || createProjectMutation.isPending}
                  className="text-xs px-2 py-1 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
                >
                  Create
                </button>
              </div>
            </div>
          )}

          {isLoadingProjects ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : filteredProjects.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No projects found
            </div>
          ) : (
            filteredProjects.map(project => (
              <button
                key={project.id}
                onClick={() => setSelectedProjectId(project.id)}
                className={`w-full flex items-center justify-between p-3 rounded-lg text-sm transition-all ${
                  selectedProjectId === project.id 
                    ? 'bg-primary text-primary-foreground shadow-sm' 
                    : 'hover:bg-muted text-foreground'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Folder className={`w-4 h-4 ${selectedProjectId === project.id ? 'text-primary-foreground' : 'text-primary'}`} />
                  <span className="font-medium truncate">{project.name}</span>
                </div>
                <ChevronRight className={`w-4 h-4 opacity-50 ${selectedProjectId === project.id ? 'block' : 'hidden'}`} />
              </button>
            ))
          )}
        </div>
      </div>

      {/* Documents List & Upload */}
      <div className="md:col-span-2 border border-border rounded-xl bg-card/30 overflow-hidden flex flex-col">
        {selectedProjectId ? (
          <>
            <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
              <div>
                <h3 className="font-semibold flex items-center gap-2">
                  <FileText className="w-4 h-4 text-primary" />
                  {selectedProject?.name}
                </h3>
                <p className="text-xs text-muted-foreground">Manage documents and Knowledge Base</p>
              </div>
              <div className="flex gap-2">
                <input 
                  type="file"
                  multiple
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary/90 transition-colors shadow-sm"
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload Files
                </button>
                <button 
                  onClick={() => {
                    if (confirm('Delete this project and all its documents?')) {
                      deleteProjectMutation.mutate(selectedProjectId);
                    }
                  }}
                  className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-hidden flex flex-col">
              {/* Upload Progress Area */}
              {uploadQueue.length > 0 && (
                <div className="p-4 border-b border-border bg-muted/10 space-y-3 max-h-40 overflow-y-auto">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium">Upload Progress</span>
                    <button 
                      onClick={() => setUploadQueue([])}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      Clear
                    </button>
                  </div>
                  {uploadQueue.map((item, idx) => (
                    <div key={`${item.filename}-${idx}`} className="space-y-1">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="truncate max-w-[70%]">{item.filename}</span>
                        <span className={`flex items-center gap-1 ${
                          item.status === 'completed' ? 'text-green-500' : 
                          item.status === 'error' ? 'text-red-500' : 'text-primary'
                        }`}>
                          {item.status === 'uploading' && 'Uploading...'}
                          {item.status === 'indexing' && 'Indexing...'}
                          {item.status === 'completed' && <><CheckCircle2 className="w-3 h-3" /> Done</>}
                          {item.status === 'error' && <><XCircle className="w-3 h-3" /> Error</>}
                        </span>
                      </div>
                      <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                        <div 
                          className={`h-full transition-all duration-300 ${
                            item.status === 'completed' ? 'bg-green-500' : 
                            item.status === 'error' ? 'bg-red-500' : 'bg-primary animate-pulse'
                          }`}
                          style={{ width: `${item.progress}%` }}
                        />
                      </div>
                      {item.error && <p className="text-[10px] text-red-400 truncate">{item.error}</p>}
                    </div>
                  ))}
                </div>
              )}

              <div className="flex-1 overflow-y-auto p-4">
                {isLoadingDocs ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
                  </div>
                ) : documents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
                    <div className="p-4 bg-muted/50 rounded-full">
                      <Database className="w-8 h-8 text-muted-foreground/50" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">No documents indexed</p>
                      <p className="text-xs text-muted-foreground">Upload files to start building your Knowledge Base</p>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2">
                    {documents.map(doc => (
                      <div 
                        key={doc.id}
                        className="group flex items-center justify-between p-3 border border-border rounded-lg hover:border-primary/30 hover:bg-muted/30 transition-all"
                      >
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-muted rounded-md group-hover:bg-primary/10 transition-colors">
                            <FileText className="w-4 h-4 text-muted-foreground group-hover:text-primary" />
                          </div>
                          <div>
                            <p className="text-sm font-medium">{doc.filename}</p>
                            <p className="text-[11px] text-muted-foreground flex items-center gap-2">
                              <span>{doc.file_type.toUpperCase()}</span>
                              <span>•</span>
                              <span>{doc.chunk_count || 0} chunks</span>
                              <span>•</span>
                              <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                            </p>
                          </div>
                        </div>
                        <button 
                          onClick={() => {
                            if (confirm(`Delete ${doc.filename}?`)) {
                              deleteDocMutation.mutate({ projId: doc.project_id, docId: doc.id });
                            }
                          }}
                          className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md opacity-0 group-hover:opacity-100 transition-all"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center p-8 space-y-4">
            <div className="p-6 bg-primary/5 rounded-full">
              <Folder className="w-12 h-12 text-primary/40" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Select a Project</h3>
              <p className="text-sm text-muted-foreground max-w-[280px]">
                Choose a project from the left to manage its documents or create a new one to get started.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default KnowledgeBase;
