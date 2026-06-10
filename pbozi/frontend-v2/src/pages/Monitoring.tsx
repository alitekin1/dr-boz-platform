import React from 'react';
import { UsageFeed } from '../components/monitoring/UsageFeed';
import { AuditLog } from '../components/monitoring/AuditLog';
import { ErrorLogTable } from '../components/monitoring/ErrorLogTable';
import { UsageChart } from '../components/monitoring/UsageChart';
import { Activity, BarChart3, ListFilter } from 'lucide-react';

const Monitoring: React.FC = () => {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Monitoring & Logs</h1>
        <p className="text-muted-foreground mt-2">
          Track system activity, token usage, and administrative actions in real-time.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-8">
          <section id="traffic-monitor">
            <UsageChart />
          </section>

          <section id="usage-feed">
            <UsageFeed />
          </section>
...
          <section id="audit-log">
            <AuditLog />
          </section>

          <section id="error-logs">
            <ErrorLogTable />
          </section>
        </div>

        <div className="space-y-6">
          <div className="bg-card border rounded-xl p-6 shadow-sm">
            <h3 className="font-semibold flex items-center mb-4">
              <BarChart3 className="w-4 h-4 mr-2 text-primary" />
              Quick Stats
            </h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Status</span>
                <span className="flex items-center text-emerald-600 font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 mr-2 animate-pulse"></span>
                  Active
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Polling Rate</span>
                <span>10s / 30s</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Log Limit</span>
                <span>50 entries</span>
              </div>
            </div>
          </div>

          <div className="bg-muted/30 border border-dashed rounded-xl p-6">
            <h3 className="font-semibold flex items-center mb-4 text-muted-foreground">
              <ListFilter className="w-4 h-4 mr-2" />
              Filters (Coming Soon)
            </h3>
            <p className="text-xs text-muted-foreground italic">
              Advanced filtering by user, model, and date range will be available in the next update.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-primary/5 border border-primary/10">
            <h4 className="text-sm font-semibold text-primary flex items-center mb-2">
              <Activity className="w-4 h-4 mr-2" />
              System Health
            </h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              All backend services are operating normally. Latency is within expected parameters.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Monitoring;
