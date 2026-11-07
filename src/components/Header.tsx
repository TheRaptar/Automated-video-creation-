import React from 'react';
import {
  Play,
  Pause,
  Sparkles,
  Bot,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Radio,
  Flame,
  Download,
} from 'lucide-react';
import { AgentState } from '../types';

interface HeaderProps {
  state: AgentState | null;
  onTriggerRun: () => void;
  onTogglePause: () => void;
  onToggleMode: (mode: 'autonomous' | 'approval') => void;
  onOpenGenerateModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  state,
  onTriggerRun,
  onTogglePause,
  onToggleMode,
  onOpenGenerateModal,
}) => {
  const isRunning = Boolean(
    state &&
      state.status !== 'idle' &&
      state.status !== 'paused' &&
      state.status !== 'ready_for_approval'
  );

  const formatCountdown = (isoString?: string | null) => {
    if (!isoString) return '--:--';
    const target = new Date(isoString).getTime();
    const diff = Math.max(0, Math.floor((target - Date.now()) / 1000));
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    return `${h}h ${m}m`;
  };

  return (
    <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-40 px-4 lg:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        {/* Brand & Identity */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-violet-600 to-cyan-400 p-[1px] shadow-lg shadow-indigo-500/20">
            <div className="h-full w-full bg-zinc-950 rounded-[11px] flex items-center justify-center">
              <Flame className="w-5 h-5 text-indigo-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                RAPTAR
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/25">
                  v2.0 AUTONOMOUS
                </span>
              </h1>
            </div>
            <p className="text-xs text-zinc-400">
              Autonomous AI Video Creation &amp; Social Publishing Network
            </p>
          </div>
        </div>

        {/* Global Agent Control Badges & Actions */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 w-full md:w-auto">
          {/* Autonomous vs Approval Mode Switcher */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 text-xs">
            <button
              onClick={() => onToggleMode('autonomous')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium transition-colors ${
                state?.mode === 'autonomous'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              title="Autonomous Mode: Researches, plans, scripts, creates, and auto-publishes without human intervention"
            >
              <Bot className="w-3.5 h-3.5" />
              <span>Full Auto</span>
            </button>
            <button
              onClick={() => onToggleMode('approval')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium transition-colors ${
                state?.mode === 'approval'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              title="Approval Mode: Generates video then waits for human review before publishing"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Approval Gate</span>
            </button>
          </div>

          {/* Daily Schedule Timer */}
          <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900/60 border border-zinc-800 text-xs text-zinc-300">
            <Clock className="w-3.5 h-3.5 text-zinc-400" />
            <span>Next Cycle:</span>
            <span className="font-mono text-indigo-400 font-semibold">
              {formatCountdown(state?.dailyProduction?.nextRun)}
            </span>
          </div>

          {/* Pause / Resume Button */}
          <button
            onClick={onTogglePause}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
              state?.isPaused
                ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20'
                : 'bg-zinc-900 text-zinc-300 border-zinc-800 hover:bg-zinc-800'
            }`}
          >
            {state?.isPaused ? (
              <>
                <Play className="w-3.5 h-3.5 text-amber-400" />
                <span>Resume Agent</span>
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5 text-zinc-400" />
                <span>Pause Agent</span>
              </>
            )}
          </button>

          {/* Download Project ZIP */}
          <a
            href="/api/download/project"
            download="raptar_v2_upgraded.zip"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 text-xs font-medium transition-all"
            title="Download complete source code package as ZIP"
          >
            <Download className="w-3.5 h-3.5 text-cyan-400" />
            <span>Download ZIP</span>
          </a>

          {/* Generate Now Button */}
          <button
            onClick={onOpenGenerateModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700/60 text-xs font-medium transition-all"
          >
            <Sparkles className="w-3.5 h-3.5 text-violet-400" />
            <span>Custom Topic</span>
          </button>

          {/* Instant Autonomous Run Trigger */}
          <button
            onClick={onTriggerRun}
            disabled={isRunning}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white transition-all shadow-md ${
              isRunning
                ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700'
                : 'bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 shadow-indigo-600/20 border border-indigo-500/40'
            }`}
          >
            {isRunning ? (
              <>
                <Radio className="w-3.5 h-3.5 animate-pulse text-indigo-400" />
                <span>Executing...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>Run Cycle Now</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
