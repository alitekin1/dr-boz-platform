import React from 'react';
import { useMutation } from '@tanstack/react-query';
import { Play, Terminal, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { runPython } from '../../lib/api';

const PythonSandbox: React.FC = () => {
  const [code, setCode] = React.useState('import pandas as pd\nimport matplotlib.pyplot as plt\n\n# Example code\ndata = {"Name": ["Apple", "NVIDIA", "OpenAI"], "Revenue": [383, 60, 2]}\ndf = pd.DataFrame(data)\nprint(df)\n\n# To save a plot, use:\n# plt.bar(df["Name"], df["Revenue"])\n# plt.savefig("revenue.png")\n# print("Generated revenue.png")');
  const [output, setOutput] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: runPython,
    onSuccess: (data) => {
      setOutput(data.output);
      setError(data.error);
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || err.message || 'Failed to execute code');
    },
  });

  const handleRun = (e: React.FormEvent) => {
    e.preventDefault();
    setOutput(null);
    setError(null);
    mutation.mutate(code);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Python Sandbox (Admin Only)</h3>
        <button
          onClick={handleRun}
          disabled={mutation.isPending}
          className="flex items-center space-x-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Play className={`w-4 h-4 ${mutation.isPending ? 'animate-pulse' : ''}`} />
          <span>{mutation.isPending ? 'Running...' : 'Run Code'}</span>
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm font-medium flex items-center space-x-2">
            <span>Editor</span>
          </label>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full h-[400px] bg-muted/30 border border-border rounded-xl p-4 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
            spellCheck={false}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium flex items-center space-x-2">
            <Terminal className="w-4 h-4" />
            <span>Output / Terminal</span>
          </label>
          <div className="w-full h-[400px] bg-black/90 text-green-400 rounded-xl p-4 font-mono text-sm overflow-auto">
            {mutation.isPending && (
              <div className="flex items-center space-x-2 animate-pulse">
                <span className="w-2 h-4 bg-green-400"></span>
                <span>Executing...</span>
              </div>
            )}
            {!mutation.isPending && output && (
              <pre className="whitespace-pre-wrap">{output}</pre>
            )}
            {!mutation.isPending && error && (
              <div className="text-red-400 space-y-1">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="font-bold">Execution Error</span>
                </div>
                <pre className="whitespace-pre-wrap">{error}</pre>
              </div>
            )}
            {!mutation.isPending && !output && !error && (
              <span className="text-muted-foreground italic">Ready for input. Output will appear here.</span>
            )}
          </div>
        </div>
      </div>

      <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 flex items-start space-x-3">
        <CheckCircle2 className="w-5 h-5 text-primary mt-0.5" />
        <div className="text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Python Capabilities</p>
          <p>
            You have access to <strong>pandas</strong> for data analysis, <strong>matplotlib</strong> for charts, 
            and <strong>requests</strong> for fetching external data. Code runs in a 60-second timeout.
          </p>
        </div>
      </div>
    </div>
  );
};

export default PythonSandbox;
