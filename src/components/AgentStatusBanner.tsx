import React from 'react';
import {
  Compass,
  FileText,
  Volume2,
  Film,
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  RotateCw,
  Cpu,
  Tv,
  Instagram,
  Sparkles,
} from 'lucide-react';
import { AgentState } from '../types';

interface AgentStatusBannerProps {
  state: AgentState | null;
  onRefresh: () => void;
}

const STAGES = [
  { id: 'researching', label: '1. Trend Radar', icon: Compass },
  { id: 'scripting', label: '2. Script & Fact-Check', icon: FileText },
  { id: 'synthesizing_audio', label: '3. Voiceover & Audio', icon: Volume2 },
  { id: 'assembling', label: '4. Video & Subtitles', icon: Film },
  { id: 'publishing', label: '5. Social Dispatch', icon: UploadCloud },
];

export const AgentStatusBanner: React.FC<AgentStatusBannerProps> = ({ state, onRefresh }) => {
  if (!state) return null;

  const getStatusBadge = () => {
    switch (state.status) {
      case 'idle':
        return (
          <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-md">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            STANDBY (IDLE)
          </span>
        );
      case 'paused':
        return (
          <span className="flex items-center gap-1.5 text-xs font-mono text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2.5 py-1 rounded-md">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            AGENT PAUSED
          </span>
        );
      case 'ready_for_approval':
        return (
          <span className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-800/60 px-2.5 py-1 rounded-md">
            <CheckCircle2 className="w-3.5 h-3.5" />
            AWAITING OPERATOR APPROVAL
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1.5 text-xs font-mono text-rose-400 bg-rose-950/60 border border-rose-800/60 px-2.5 py-1 rounded-md">
            <AlertTriangle className="w-3.5 h-3.5" />
            EXECUTION ANOMALY
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 text-xs font-mono text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 px-2.5 py-1 rounded-md">
            <RotateCw className="w-3.5 h-3.5 animate-spin" />
            PIPELINE ACTIVE ({state.status.toUpperCase()})
          </span>
        );
    }
  };

  const currentStageIndex = () => {
    if (state.status === 'researching') return 0;
    if (state.status === 'planning' || state.status === 'scripting') return 1;
    if (state.status === 'synthesizing_audio' || state.status === 'sourcing_visuals') return 2;
    if (state.status === 'assembling' || state.status === 'evaluating') return 3;
    if (state.status === 'publishing') return 4;
    return -1;
  };

  const activeIdx = currentStageIndex();

  return (
    <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-5 shadow-xl relative overflow-hidden backdrop-blur-sm">
      {/* Background ambient glow */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-600/5 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />

      {/* Top Bar: Status, Task, Refresh */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-zinc-800/80">
        <div className="flex flex-wrap items-center gap-3">
          {getStatusBadge()}
          <span className="text-xs text-zinc-400 font-mono flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-zinc-500" />
            Gemini 3.8 Flash Core
          </span>
        </div>

        {/* Daily Stats Counters */}
        <div className="flex items-center gap-4 text-xs font-mono text-zinc-300">
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-500">Target:</span>
            <span className="text-white font-semibold">1 Video / Day</span>
          </div>
          <div className="h-3 w-px bg-zinc-800" />
          <div className="flex items-center gap-1.5">
            <Tv className="w-3.5 h-3.5 text-red-400" />
            <span className="text-zinc-500">YouTube:</span>
            <span className="text-white font-semibold">
              {state.platforms.youtube.uploadsToday}/5
            </span>
          </div>
          <div className="h-3 w-px bg-zinc-800" />
          <div className="flex items-center gap-1.5">
            <Instagram className="w-3.5 h-3.5 text-pink-400" />
            <span className="text-zinc-500">Instagram:</span>
            <span className="text-white font-semibold">
              {state.platforms.instagram.postsToday}/4
            </span>
          </div>
          <button
            onClick={onRefresh}
            className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            title="Refresh status"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Current Task Description */}
      <div className="py-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <h2 className="text-sm font-semibold text-zinc-200">Autonomous Agent Objective</h2>
          </div>
          <span className="text-xs font-mono text-indigo-400 font-bold">{state.progress}%</span>
        </div>
        <p className="text-sm text-zinc-300 font-medium bg-zinc-950/70 p-3 rounded-xl border border-zinc-800/80">
          {state.currentTask}
        </p>

        {/* Linear Progress Bar */}
        <div className="w-full bg-zinc-950 rounded-full h-2 mt-3 overflow-hidden border border-zinc-800">
          <div
            className="bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-400 h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.max(5, state.progress)}%` }}
          />
        </div>
      </div>

      {/* 5-Stage Autonomous Pipeline Visualization */}
      <div className="pt-2 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2.5">
        {STAGES.map((st, idx) => {
          const isPassed = activeIdx > idx || state.status === 'idle';
          const isCurrent = activeIdx === idx;
          const Icon = st.icon;

          return (
            <div
              key={st.id}
              className={`flex items-center gap-2.5 p-2.5 rounded-xl border transition-all ${
                isCurrent
                  ? 'bg-indigo-950/60 border-indigo-500/60 text-indigo-200 shadow-md shadow-indigo-500/10'
                  : isPassed
                  ? 'bg-zinc-950/40 border-zinc-800/70 text-zinc-400'
                  : 'bg-zinc-950/20 border-zinc-900 text-zinc-600'
              }`}
            >
              <div
                className={`p-1.5 rounded-lg ${
                  isCurrent
                    ? 'bg-indigo-600 text-white'
                    : isPassed
                    ? 'bg-zinc-800 text-zinc-300'
                    : 'bg-zinc-900 text-zinc-600'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isCurrent ? 'animate-pulse' : ''}`} />
              </div>
              <div className="truncate">
                <p className="text-xs font-medium truncate">{st.label}</p>
                <p className="text-[10px] font-mono text-zinc-500">
                  {isCurrent ? 'ACTIVE' : isPassed ? 'COMPLETE' : 'QUEUED'}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
