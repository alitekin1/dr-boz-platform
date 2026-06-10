import React, { useEffect, useState } from 'react';
import * as api from '../../lib/api';
import { ErrorLog } from '../../lib/types';
import { AlertTriangle, CheckCircle2, Clock, Terminal } from 'lucide-react';

export const ErrorLogTable: React.FC = () => {
  const [errors, setErrors] = useState<ErrorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);

  const fetchErrors = async () => {
    try {
      const data = await api.getErrors();
      setErrors(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchErrors();
    const interval = setInterval(fetchErrors, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleResolve = async (id: number) => {
    try {
      await api.resolveError(id);
      fetchErrors();
    } catch (err) {
      alert('Failed to resolve error');
    }
  };

  if (loading && errors.length === 0) {
    return (
      <div className="flex items-center justify-center p-12 bg-card border rounded-xl border-dashed">
        <div className="flex flex-col items-center text-muted-foreground">
          <Clock className="w-8 h-8 mb-2 animate-spin" />
          <p>Loading error logs...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-destructive" />
          <h2 className="text-xl font-semibold">Error Logs</h2>
        </div>
        <button 
          onClick={fetchErrors}
          className="text-xs font-medium px-3 py-1.5 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors"
        >
          Refresh
        </button>
      </div>

      <div className="bg-card border rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs font-medium text-muted-foreground bg-muted/50 border-b">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Message</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {errors.map((error) => (
                <tr key={error.id} className={`group hover:bg-muted/30 transition-colors ${!error.resolved ? 'bg-destructive/5' : ''}`}>
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground tabular-nums">
                    {new Date(error.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      error.source === 'API' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
                    }`}>
                      {error.source}
                    </span>
                  </td>
                  <td className="px-4 py-3 max-w-md">
                    <div className="font-medium truncate" title={error.error_message}>
                      {error.error_message}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-center">
                      {error.resolved ? (
                        <div className="flex items-center text-emerald-600 gap-1 text-xs">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Resolved</span>
                        </div>
                      ) : (
                        <div className="flex items-center text-destructive gap-1 text-xs">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Active</span>
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                    <button 
                      onClick={() => setSelectedTrace(error.stack_trace)}
                      className="p-1.5 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground"
                      title="View Stack Trace"
                    >
                      <Terminal className="w-4 h-4" />
                    </button>
                    {!error.resolved && (
                      <button 
                        onClick={() => handleResolve(error.id)}
                        className="px-2.5 py-1 text-xs font-semibold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
                      >
                        Resolve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {errors.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground italic bg-muted/10">
                    No errors logged. Everything looks good!
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedTrace && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-200">
          <div className="bg-card border rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-4 border-b flex justify-between items-center bg-muted/20">
              <div className="flex items-center gap-2">
                <Terminal className="w-5 h-5 text-primary" />
                <h3 className="font-bold text-lg">Detailed Stack Trace</h3>
              </div>
              <button 
                onClick={() => setSelectedTrace(null)}
                className="p-2 hover:bg-muted rounded-full transition-colors"
              >
                <Clock className="w-5 h-5 rotate-45" /> {/* Using Clock as close icon for simplicity or Lucide-X if I had it */}
                <span className="sr-only">Close</span>
              </button>
            </div>
            <div className="p-6 overflow-auto bg-slate-950 text-slate-300 font-mono text-[11px] leading-relaxed flex-1">
              <pre>{selectedTrace}</pre>
            </div>
            <div className="p-4 border-t flex justify-end">
              <button 
                onClick={() => setSelectedTrace(null)}
                className="px-4 py-2 bg-primary text-primary-foreground font-semibold rounded-xl hover:opacity-90 transition-opacity"
              >
                Close Trace
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
