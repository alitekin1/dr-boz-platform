import React, { useState, useEffect } from 'react';
import { Plus, Search, Trash2, FileText, FileArchive, Eye, Code, Info, AlertCircle, ChevronDown, ChevronRight, Check } from 'lucide-react';
import { getSkills, uploadSkill, updateSkill, deleteSkill } from '../../lib/api';
import { Skill } from '../../lib/types';
import ReactMarkdown from 'react-markdown';

export default function SkillList() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  
  // For file tree toggle simulation in sidebar
  const [treeOpen, setTreeOpen] = useState(true);

  useEffect(() => {
    fetchSkills();
  }, []);

  const fetchSkills = async () => {
    try {
      setLoading(true);
      const data = await getSkills();
      setSkills(data);
      if (data.length > 0 && !selectedSkill) {
        setSelectedSkill(data[0]);
      } else if (selectedSkill) {
        const stillExists = data.find((s: Skill) => s.id === selectedSkill.id);
        if (stillExists) setSelectedSkill(stillExists);
        else setSelectedSkill(data.length > 0 ? data[0] : null);
      }
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load skills');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.zip')) {
      setError('Please upload a valid .zip file containing the skill.');
      return;
    }

    try {
      setUploading(true);
      setError(null);
      const newSkill = await uploadSkill(file);
      await fetchSkills();
      setSelectedSkill(newSkill);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload skill');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleToggleActive = async (skill: Skill) => {
    try {
      const updated = await updateSkill(skill.id, { is_active: !skill.is_active });
      setSkills(skills.map(s => s.id === skill.id ? { ...s, is_active: updated.is_active } : s));
      if (selectedSkill?.id === skill.id) {
        setSelectedSkill({ ...selectedSkill, is_active: updated.is_active });
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update skill');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this skill?')) return;
    try {
      await deleteSkill(id);
      setSkills(skills.filter(s => s.id !== id));
      if (selectedSkill?.id === id) {
        setSelectedSkill(null);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete skill');
    }
  };

  const filteredSkills = skills.filter(s => s.name.toLowerCase().includes(searchQuery.toLowerCase()));

  if (loading && skills.length === 0) {
    return <div className="flex justify-center p-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>;
  }

  return (
    <div className="h-[75vh] flex flex-col relative">
      {error && (
        <div className="absolute top-4 right-4 z-50 p-4 bg-red-50 text-red-600 rounded-lg flex items-start space-x-2 border border-red-100 shadow-md">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span className="text-sm pr-4">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-700">×</button>
        </div>
      )}

      <div className="flex-1 flex border border-border rounded-xl overflow-hidden bg-background shadow-sm">
        {/* Left Sidebar */}
        <div className="w-[300px] border-r border-border bg-[#fafafa] dark:bg-[#1a1b1e] flex flex-col text-sm">
          <div className="p-4 flex items-center justify-between">
            <h2 className="font-semibold text-base text-foreground">Skills</h2>
            <div className="flex items-center gap-2 text-muted-foreground">
              <button className="p-1 hover:text-foreground hover:bg-muted rounded"><Search className="w-4 h-4" /></button>
              <label className="p-1 hover:text-foreground hover:bg-muted rounded cursor-pointer relative">
                <Plus className="w-4 h-4" />
                <input
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={handleFileUpload}
                  disabled={uploading}
                />
              </label>
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto pb-4">
            <div className="px-2 mb-1">
              <button 
                className="flex items-center w-full text-left text-xs font-medium text-muted-foreground hover:text-foreground px-2 py-1"
                onClick={() => setTreeOpen(!treeOpen)}
              >
                {treeOpen ? <ChevronDown className="w-3 h-3 mr-1" /> : <ChevronRight className="w-3 h-3 mr-1" />}
                Personal skills
              </button>
            </div>

            {treeOpen && (
              <div className="px-2 space-y-[2px]">
                {filteredSkills.map(skill => (
                  <div key={skill.id} className="flex flex-col">
                    <button
                      onClick={() => setSelectedSkill(skill)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-md w-full text-left transition-colors ${
                        selectedSkill?.id === skill.id 
                          ? 'bg-primary/10 text-primary dark:bg-white/10 dark:text-white' 
                          : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                      }`}
                    >
                      <FileArchive className="w-4 h-4 shrink-0" />
                      <span className="truncate">{skill.name}</span>
                    </button>
                    
                    {selectedSkill?.id === skill.id && (
                      <div className="ml-6 pl-2 py-1 border-l border-border/50 space-y-1 mt-1 text-muted-foreground">
                        {(skill.files?.length ? skill.files : ['SKILL.md']).slice(0, 12).map(path => (
                          <div key={path} className="flex items-center gap-2 px-2 py-1 text-foreground">
                            <FileText className="w-3.5 h-3.5 opacity-70" />
                            <span className="truncate text-xs" title={path}>{path}</span>
                          </div>
                        ))}
                        {(skill.files?.length || 0) > 12 && (
                          <div className="px-2 py-1 text-[11px] text-muted-foreground">
                            +{(skill.files?.length || 0) - 12} more files
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {filteredSkills.length === 0 && (
                  <div className="px-4 py-8 text-center text-muted-foreground opacity-70">
                    <p className="text-xs">No skills found.</p>
                  </div>
                )}
              </div>
            )}
          </div>
          
          {uploading && (
            <div className="p-3 border-t border-border bg-muted/30 flex items-center justify-center gap-2">
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent" />
              <span className="text-xs text-muted-foreground">Uploading...</span>
            </div>
          )}
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col bg-card relative">
          {selectedSkill ? (
            <>
              {/* Header */}
              <div className="px-8 py-6 border-b border-border">
                <div className="flex justify-between items-start mb-6">
                  <h1 className="text-xl font-semibold text-foreground tracking-tight">
                    {selectedSkill.name}
                  </h1>
                  <div className="flex items-center gap-4">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        className="sr-only peer" 
                        checked={selectedSkill.is_active} 
                        onChange={() => handleToggleActive(selectedSkill)} 
                      />
                      <div className="w-9 h-5 bg-muted peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-primary"></div>
                    </label>
                    <button 
                      onClick={() => handleDelete(selectedSkill.id)}
                      className="text-muted-foreground hover:text-red-500 transition-colors"
                      title="Delete Skill"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 text-sm">
                  <div>
                    <div className="text-muted-foreground mb-1 text-xs">Added by</div>
                    <div className="text-foreground">Admin</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground mb-1 text-xs">Last updated</div>
                    <div className="text-foreground">{new Date(selectedSkill.updated_at).toLocaleDateString()}</div>
                  </div>
                  {selectedSkill.file_path && (
                    <div className="col-span-2">
                      <div className="text-muted-foreground mb-1 text-xs">Server path</div>
                      <div className="text-foreground text-xs truncate font-mono" title={selectedSkill.file_path}>
                        {selectedSkill.file_path}
                      </div>
                    </div>
                  )}
                  {selectedSkill.when_to_use && (
                    <div className="col-span-2">
                      <div className="text-muted-foreground mb-1 text-xs flex items-center gap-1">
                        When to use <Check className="w-3 h-3 text-green-500" />
                      </div>
                      <div className="text-foreground text-xs line-clamp-2" title={selectedSkill.when_to_use}>
                        {selectedSkill.when_to_use}
                      </div>
                    </div>
                  )}
                  {selectedSkill.avoid_when && (
                    <div className="col-span-2">
                      <div className="text-muted-foreground mb-1 text-xs flex items-center gap-1">
                        Avoid when <AlertCircle className="w-3 h-3 text-red-500" />
                      </div>
                      <div className="text-foreground text-xs line-clamp-2" title={selectedSkill.avoid_when}>
                        {selectedSkill.avoid_when}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-6">
                  <div className="text-muted-foreground mb-1 text-xs flex items-center gap-1">
                    Description <Info className="w-3 h-3" />
                  </div>
                  <p className="text-sm text-foreground/90 leading-relaxed max-w-3xl">
                    {selectedSkill.description || selectedSkill.usage_rules || "No description provided."}
                  </p>
                </div>
              </div>

              {/* Instructions Editor / Markdown Area */}
              <div className="flex-1 overflow-y-auto p-8 bg-[#fafafa] dark:bg-[#111111]">
                <div className="rounded-xl border border-border/50 bg-[#282a36] shadow-sm overflow-hidden flex flex-col h-full min-h-[300px]">
                  <div className="flex items-center justify-end px-3 py-2 bg-[#1f2029] border-b border-white/5">
                    <div className="flex bg-[#282a36] rounded border border-white/10 overflow-hidden">
                      <button className="px-2.5 py-1 text-white bg-white/10 hover:bg-white/20 transition-colors">
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button className="px-2.5 py-1 text-white/50 hover:bg-white/10 transition-colors border-l border-white/10">
                        <Code className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="p-6 overflow-y-auto text-gray-300 font-mono text-sm leading-relaxed whitespace-pre-wrap">
                    {selectedSkill.instructions || (
                      <span className="text-gray-500 italic">No markdown instructions found.</span>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground opacity-50">
              <FileArchive className="w-16 h-16 mb-4" />
              <p>Select a skill to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
