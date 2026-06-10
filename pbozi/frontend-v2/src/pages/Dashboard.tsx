import React from "react";
import { 
  Users, 
  MessageSquare, 
  Loader2,
  AlertCircle
} from "lucide-react";
import { useStats } from "../hooks/useStats";

interface StatCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
  isLoading?: boolean;
}

const StatCard = ({ title, value, icon, description, isLoading }: StatCardProps) => (
  <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm flex items-start gap-4">
    <div className="p-2 bg-primary/10 rounded-lg text-primary">
      {icon}
    </div>
    <div className="flex-1">
      <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      <div className="mt-1 flex items-baseline gap-2">
        {isLoading ? (
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        ) : (
          <p className="text-2xl font-bold">{value.toLocaleString()}</p>
        )}
      </div>
      {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
    </div>
  </div>
);

export default function Dashboard() {
  const { data: stats, isLoading, isError, error } = useStats();

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <div className="text-center">
          <h2 className="text-xl font-semibold">Failed to load statistics</h2>
          <p className="text-muted-foreground">{(error as Error)?.message || "Unknown error occurred"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Billing and subscription overview.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <StatCard
          title="Users"
          value={stats?.users ?? 0}
          icon={<Users className="h-5 w-5" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Chats"
          value={stats?.chats ?? 0}
          icon={<MessageSquare className="h-5 w-5" />}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
