import React from 'react';
import {
  UploadCloud,
  Tv,
  Instagram,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldCheck,
  ExternalLink,
  RotateCw,
  Lock,
} from 'lucide-react';
import { AgentState } from '../types';

interface DistributionTabProps {
  state: AgentState | null;
  onRefresh: () => void;
}

export const DistributionTab: React.FC<DistributionTabProps> = ({ state, onRefresh }) => {
  const yt = state?.platforms?.youtube;
  const ig = state?.platforms?.instagram;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-indigo-400" />
            Social Media Publishing &amp; API Distribution Hub
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Official YouTube Data API v3 and Meta Instagram Graph API v23.0 integration status,
            quotas, and safety barriers.
          </p>
        </div>

        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 text-xs font-medium transition-all"
        >
          <RotateCw className="w-3.5 h-3.5" />
          <span>Check API Status</span>
        </button>
      </div>

      {/* Platform Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* YouTube Data API Card */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-red-950/60 border border-red-800/60 text-red-400">
                  <Tv className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">YouTube Shorts &amp; Long-Form</h3>
                  <p className="text-xs text-zinc-400">Official YouTube Data API v3</p>
                </div>
              </div>

              {yt?.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-md">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  CONNECTED
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-mono text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2.5 py-1 rounded-md">
                  <Clock className="w-3.5 h-3.5" />
                  AWAITING KEYS
                </span>
              )}
            </div>

            {/* Metrics */}
            <div className="py-5 space-y-4">
              <div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-zinc-400">Daily Upload Quota</span>
                  <span className="font-mono text-white font-bold">
                    {yt?.uploadsToday || 0} / {yt?.maxDaily || 5} Published Today
                  </span>
                </div>
                <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-zinc-800">
                  <div
                    className="bg-red-500 h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(
                        100,
                        (((yt?.uploadsToday || 0) / (yt?.maxDaily || 5)) * 100)
                      )}%`,
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                  <span className="text-[10px] font-mono text-zinc-500 block">PRIVACY STATUS</span>
                  <span className="font-semibold text-zinc-200 capitalize">
                    {yt?.privacy || 'Public'}
                  </span>
                </div>
                <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                  <span className="text-[10px] font-mono text-zinc-500 block">AI SYNTHETIC TAG</span>
                  <span className="font-semibold text-emerald-400">Auto-declared</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-zinc-800 text-xs text-zinc-400">
            <p className="leading-relaxed">
              Uploads are throttled with exponential backoff and rate-limit guardrails. Synthetic AI
              labels are attached in full compliance with YouTube policies.
            </p>
          </div>
        </div>

        {/* Instagram Graph API Card */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-pink-950/60 border border-pink-800/60 text-pink-400">
                  <Instagram className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Instagram Reels</h3>
                  <p className="text-xs text-zinc-400">Meta Instagram Graph API v23.0</p>
                </div>
              </div>

              {ig?.connected ? (
                <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-md">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  CONNECTED
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-mono text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2.5 py-1 rounded-md">
                  <Clock className="w-3.5 h-3.5" />
                  AWAITING KEYS
                </span>
              )}
            </div>

            {/* Metrics */}
            <div className="py-5 space-y-4">
              <div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-zinc-400">Daily Reels Limit</span>
                  <span className="font-mono text-white font-bold">
                    {ig?.postsToday || 0} / {ig?.maxDaily || 4} Published Today
                  </span>
                </div>
                <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-zinc-800">
                  <div
                    className="bg-gradient-to-r from-purple-500 to-pink-500 h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(
                        100,
                        (((ig?.postsToday || 0) / (ig?.maxDaily || 4)) * 100)
                      )}%`,
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                  <span className="text-[10px] font-mono text-zinc-500 block">LOGIN PROTOCOL</span>
                  <span className="font-semibold text-zinc-200">Unified Graph OAuth</span>
                </div>
                <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                  <span className="text-[10px] font-mono text-zinc-500 block">CONTAINER POLLING</span>
                  <span className="font-semibold text-emerald-400">Two-Phase Safe</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-zinc-800 text-xs text-zinc-400">
            <p className="leading-relaxed">
              Videos are verified for 9:16 aspect ratio, containerized, polled until status is
              FINISHED, and published with clean hashtag clusters.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
