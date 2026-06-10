import React, { useState, useEffect } from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Line
} from 'recharts';
import api from '../../lib/api';
import { Activity, RefreshCcw } from 'lucide-react';

interface TimeSeriesData {
  time: string;
  input_tokens: number;
  output_tokens: number;
  requests: number;
}

export const UsageChart: React.FC = () => {
  const [data, setData] = useState<TimeSeriesData[]>([]);
  const [days, setDays] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/admin/usage-stats/timeseries?days=${days}`);
      
      if (Array.isArray(response.data)) {
        setData(response.data);
      } else {
        console.error('Invalid timeseries data format:', response.data);
        setData([]);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to fetch timeseries data:', err);
      setError('Failed to load chart data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // Update every minute
    return () => clearInterval(interval);
  }, [days]);

  return (
    <div className="bg-card border rounded-xl shadow-sm overflow-hidden">
      <div className="p-6 border-b flex justify-between items-center bg-muted/30">
        <div className="flex items-center space-x-2">
          <Activity className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold tracking-tight">Bot Traffic (Live)</h2>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex bg-background border rounded-lg p-1">
            {[1, 7, 30].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${
                  days === d 
                    ? 'bg-primary text-primary-foreground font-medium' 
                    : 'hover:bg-muted'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <button 
            onClick={fetchData} 
            disabled={loading}
            className="p-2 hover:bg-background rounded-full transition-colors disabled:opacity-50"
          >
            <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="p-6">
        {error ? (
          <div className="h-[300px] flex items-center justify-center text-destructive text-sm font-medium">
            {error}
          </div>
        ) : loading && data.length === 0 ? (
          <div className="h-[300px] flex items-center justify-center">
            <RefreshCcw className="w-8 h-8 animate-spin text-muted-foreground/30" />
          </div>
        ) : data.length === 0 ? (
          <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm italic">
            No data available for the selected period
          </div>
        ) : (
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={data}
                margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="colorInput" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8884d8" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#8884d8" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorOutput" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#82ca9d" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#82ca9d" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis 
                  dataKey="time" 
                  tickFormatter={(str) => {
                    if (!str) return '';
                    const date = new Date(str);
                    if (isNaN(date.getTime())) return str;
                    return days === 1 
                      ? date.getHours() + ':00' 
                      : (date.getMonth() + 1) + '/' + date.getDate();
                  }}
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  stroke="#9ca3af"
                />
                <YAxis 
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  stroke="#9ca3af"
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#fff', 
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'
                  }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '20px' }} />
                <Area 
                  type="monotone" 
                  dataKey="input_tokens" 
                  name="Input Tokens"
                  stroke="#8884d8" 
                  fillOpacity={1} 
                  fill="url(#colorInput)" 
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Area 
                  type="monotone" 
                  dataKey="output_tokens" 
                  name="Output Tokens"
                  stroke="#82ca9d" 
                  fillOpacity={1} 
                  fill="url(#colorOutput)" 
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="requests" 
                  name="Requests"
                  stroke="#f59e0b" 
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
};
