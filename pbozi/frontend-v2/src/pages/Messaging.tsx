import React, { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Send, Users, User, AlertTriangle, CheckCircle, Loader2, Image as ImageIcon, X, Plus, Trash } from "lucide-react";
import { broadcastMessage, getReferrals } from "../lib/api";

export default function Messaging() {
  const [searchParams] = useSearchParams();
  const [message, setMessage] = useState("");
  const [targetType, setTargetType] = useState<"all" | "active" | "suspended" | "individual">("all");
  const [targetUserId, setTargetUserId] = useState("");
  const [referralCampaignId, setReferralCampaignId] = useState<string>("");
  const [buttons, setButtons] = useState<any[]>([]);

  const { data: referrals } = useQuery({
    queryKey: ['referrals'],
    queryFn: getReferrals
  });
  
  useEffect(() => {
    const userId = searchParams.get("userId");
    if (userId) {
      setTargetType("individual");
      setTargetUserId(userId);
    }
  }, [searchParams]);

  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<{ success: number; failure: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhoto(file);
      const reader = new FileReader();
      reader.onloadend = () => setPhotoPreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const removePhoto = () => {
    setPhoto(null);
    setPhotoPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const addButton = () => {
    setButtons([...buttons, { label: "", type: "url", value: "" }]);
  };

  const removeButton = (index: number) => {
    setButtons(buttons.filter((_, i) => i !== index));
  };

  const updateButton = (index: number, field: string, value: string) => {
    const newButtons = [...buttons];
    newButtons[index][field] = value;
    setButtons(newButtons);
  };

  const handleSend = async () => {
    if (!message.trim()) return;
    if (targetType === "individual" && !targetUserId.trim()) return;
    
    setIsSending(true);
    setResult(null);
    setError(null);

    try {
      const data = await broadcastMessage({
        message: message.trim(),
        target_groups: targetType === "all" || targetType === "individual" ? undefined : [targetType],
        target_user_ids: targetType === "individual" ? [targetUserId.trim()] : undefined,
        photo: photo,
        referral_campaign_id: referralCampaignId ? parseInt(referralCampaignId) : undefined,
        buttons: buttons.filter(b => b.label && b.value),
      });
      setResult({
        success: data.success_count,
        failure: data.failure_count,
        total: data.total_targeted,
      });
      if (data.success_count > 0) {
        setMessage("");
        setTargetUserId("");
        removePhoto();
        setButtons([]);
        setReferralCampaignId("");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to send message");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-left">Messaging (Broadcast)</h1>
        <p className="text-muted-foreground text-left">Send messages to all or specific groups of users.</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium block text-left">Message Content</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Write your message here..."
              className="w-full h-40 p-3 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-left"
              dir="ltr"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium block text-left">Image (Optional)</label>
            <div className="flex flex-col gap-4">
              {!photoPreview ? (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full py-4 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-primary/5 transition-all flex flex-col items-center justify-center gap-2 text-muted-foreground"
                >
                  <ImageIcon className="w-8 h-8" />
                  <span className="text-xs">Select Image</span>
                </button>
              ) : (
                <div className="relative rounded-lg overflow-hidden border border-border group">
                  <img src={photoPreview} alt="Preview" className="w-full h-48 object-cover" />
                  <button
                    onClick={removePhoto}
                    className="absolute top-2 right-2 p-1 bg-destructive text-destructive-foreground rounded-full opacity-0 group-hover:opacity-100 transition-opacity shadow-lg"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
              <input
                type="file"
                ref={fileInputRef}
                onChange={handlePhotoChange}
                accept="image/*"
                className="hidden"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium block text-left">Referral Campaign (Optional)</label>
            <select
              value={referralCampaignId}
              onChange={(e) => setReferralCampaignId(e.target.value)}
              className="w-full p-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-left"
              dir="ltr"
            >
              <option value="">No Campaign</option>
              {Array.isArray(referrals) && referrals.map((item: any) => (
                <option key={item.campaign.id} value={item.campaign.id}>
                  {item.campaign.description || item.campaign.code}
                </option>
              ))}
            </select>
            <p className="text-[10px] text-muted-foreground text-left">If a user clicks a button from this message, they will be linked to this campaign.</p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium block text-left">Message Buttons (Inline)</label>
              <button
                onClick={addButton}
                className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                <Plus className="w-3 h-3" />
                Add Button
              </button>
            </div>
            <div className="space-y-3">
              {buttons.map((button, index) => (
                <div key={index} className="p-3 border rounded-lg bg-muted/50 space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Button Label"
                      value={button.label}
                      onChange={(e) => updateButton(index, "label", e.target.value)}
                      className="flex-1 p-1 bg-background border border-border rounded text-xs text-left"
                      dir="ltr"
                    />
                    <button onClick={() => removeButton(index)} className="text-destructive hover:bg-destructive/10 p-1 rounded">
                      <Trash className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <select
                      value={button.type}
                      onChange={(e) => updateButton(index, "type", e.target.value)}
                      className="p-1 bg-background border border-border rounded text-xs"
                    >
                      <option value="url">Link (URL)</option>
                      <option value="prompt">Command (Prompt)</option>
                    </select>
                    <input
                      type="text"
                      placeholder={button.type === "url" ? "https://..." : "Command text..."}
                      value={button.value}
                      onChange={(e) => updateButton(index, "value", e.target.value)}
                      className="flex-1 p-1 bg-background border border-border rounded text-xs text-left"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium block text-left">Target Group</label>
            <div className="flex flex-wrap gap-2 justify-start">
              <button
                onClick={() => setTargetType("all")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  targetType === "all" 
                    ? "bg-primary text-primary-foreground" 
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                All Users
              </button>
              <button
                onClick={() => setTargetType("active")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  targetType === "active" 
                    ? "bg-primary text-primary-foreground" 
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                Active Users
              </button>
              <button
                onClick={() => setTargetType("suspended")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  targetType === "suspended" 
                    ? "bg-primary text-primary-foreground" 
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                Suspended Users
              </button>
              <button
                onClick={() => setTargetType("individual")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  targetType === "individual" 
                    ? "bg-primary text-primary-foreground" 
                    : "bg-muted text-muted-foreground hover:bg-accent"
                }`}
              >
                Individual User (ID)
              </button>
            </div>
          </div>

          {targetType === "individual" && (
            <div className="space-y-2">
              <label className="text-sm font-medium block text-left">User Identifier (ID, Telegram ID or Phone)</label>
              <input
                type="text"
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
                placeholder="123 or +98912..."
                className="w-full p-2 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all text-left"
              />
            </div>
          )}

          <button
            onClick={handleSend}
            disabled={isSending || !message.trim()}
            className="w-full py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-all flex items-center justify-center gap-2 disabled:opacity-50 shadow-lg shadow-primary/20"
          >
            {isSending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
            <span>Send Message</span>
          </button>
        </div>

        <div className="space-y-6">
          {result && (
            <div className="p-6 border rounded-xl bg-green-500/10 border-green-500/20 text-green-700 space-y-3">
              <div className="flex items-center gap-2 justify-start text-green-600">
                <CheckCircle className="w-5 h-5" />
                <span className="font-bold text-left">Broadcast Report</span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="bg-background/50 p-3 rounded-lg">
                  <p className="text-xs text-muted-foreground">Total Targets</p>
                  <p className="text-xl font-bold">{result.total}</p>
                </div>
                <div className="bg-background/50 p-3 rounded-lg">
                  <p className="text-xs text-green-600">Successful</p>
                  <p className="text-xl font-bold">{result.success}</p>
                </div>
                <div className="bg-background/50 p-3 rounded-lg">
                  <p className="text-xs text-red-600">Failed</p>
                  <p className="text-xl font-bold">{result.failure}</p>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="p-6 border rounded-xl bg-destructive/10 border-destructive/20 text-destructive flex items-start gap-3 justify-start">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <div className="text-left">
                <p className="font-bold">Send Error</p>
                <p className="text-sm opacity-90">{error}</p>
              </div>
            </div>
          )}

          <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm">
            <h3 className="text-lg font-bold mb-4 text-left">Help / Guidelines</h3>
            <ul className="space-y-3 text-sm text-muted-foreground text-left" dir="ltr">
              <li className="flex items-start gap-2 justify-start">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                <span>Messages are sent directly to users via the bot.</span>
              </li>
              <li className="flex items-start gap-2 justify-start">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                <span>Sending to large groups may take time due to rate limits.</span>
              </li>
              <li className="flex items-start gap-2 justify-start">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                <span>Users who have blocked the bot will not receive the message and will be marked as "Failed".</span>
              </li>
              <li className="flex items-start gap-2 justify-start">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                <span><span className="text-primary font-bold">New:</span> You can now add buttons (URL or Command) to your messages.</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
