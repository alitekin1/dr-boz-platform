import React from 'react';
import { Wrench, Link as LinkIcon, Search, Database, Mic, FileArchive } from 'lucide-react';
import ToolList from '../components/intelligence/ToolList';
import BindingList from '../components/intelligence/BindingList';
import WebSearchForm from '../components/intelligence/WebSearchForm';
import EmbeddingForm from '../components/intelligence/EmbeddingForm';
import TranscriptionForm from '../components/intelligence/TranscriptionForm';
import KnowledgeBase from '../components/intelligence/KnowledgeBase';
import PythonSandbox from '../components/intelligence/PythonSandbox';
import SkillList from '../components/intelligence/SkillList';

const Intelligence: React.FC = () => {
  const [activeTab, setActiveTab] = React.useState<'skills' | 'tools' | 'bindings' | 'search' | 'embeddings' | 'transcription' | 'kb' | 'python'>('skills');

  const tabs = [
    { id: 'skills', label: 'Skills', icon: FileArchive },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'bindings', label: 'Bindings', icon: LinkIcon },
    { id: 'kb', label: 'Knowledge Base', icon: Database },
    { id: 'search', label: 'Web Search', icon: Search },
    { id: 'embeddings', label: 'Embeddings', icon: Database },
    { id: 'transcription', label: 'Transcription', icon: Mic },
    { id: 'python', label: 'Python Sandbox', icon: Wrench },
  ] as const;

  return (
    <div className="space-y-8">
      <div className="flex flex-col space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Intelligence & Capabilities</h1>
        <p className="text-muted-foreground">
          Manage skills, tools, bindings, web search, embedding, and voice transcription configurations.
        </p>
      </div>

      <div className="flex space-x-1 bg-muted/50 p-1 rounded-xl w-fit">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`
                flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
                ${activeTab === tab.id 
                  ? 'bg-background text-foreground shadow-sm' 
                  : 'text-muted-foreground hover:text-foreground hover:bg-background/50'}
              `}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        <div className="p-6">
          {activeTab === 'skills' && <SkillList />}
          {activeTab === 'tools' && <ToolList />}
          {activeTab === 'bindings' && <BindingList />}
          {activeTab === 'kb' && <KnowledgeBase />}
          {activeTab === 'search' && <WebSearchForm />}
          {activeTab === 'embeddings' && <EmbeddingForm />}
          {activeTab === 'transcription' && <TranscriptionForm />}
          {activeTab === 'python' && <PythonSandbox />}
        </div>
      </div>
    </div>
  );
};

export default Intelligence;
