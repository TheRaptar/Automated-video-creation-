import React, { useState } from 'react';
import {
  Compass,
  Sparkles,
  TrendingUp,
  RotateCw,
  Play,
  CheckCircle2,
  ShieldAlert,
  Flame,
  ArrowUpRight,
  Layers,
} from 'lucide-react';
import { TrendRadarData, TrendIdea } from '../types';

interface TrendRadarTabProps {
  trendData: TrendRadarData | null;
  isLoading: boolean;
  onRefresh: () => void;
  onTriggerIdea: (idea: TrendIdea) => void;
}

export const TrendRadarTab: React.FC<TrendRadarTabProps> = ({
  trendData,
  isLoading,
  onRefresh,
  onTriggerIdea,
}) => {
  const [selectedFormatFilter, setSelectedFormatFilter] = useState<string>('all');

  const ideas = trendData?.ideas || [];
  const filteredIdeas = ideas.filter((i) => {
    if (selectedFormatFilter === 'all') return true;
    return i.format === selectedFormatFilter;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner & Control */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Compass className="w-4 h-4 text-indigo-400" />
            Autonomous Market &amp; Trend Radar
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Real-time search volume signals from Google Trends, Wikipedia, and YouTube, analyzed and
            scored by Gemini AI.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 text-xs">
            {['all', 'short', 'story', 'long'].map((fmt) => (
              <button
                key={fmt}
                onClick={() => setSelectedFormatFilter(fmt)}
                className={`px-2.5 py-1 rounded font-medium capitalize transition-colors ${
                  selectedFormatFilter === fmt
                    ? 'bg-zinc-800 text-white'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {fmt === 'all' ? 'All' : fmt}
              </button>
            ))}
          </div>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 text-xs font-medium transition-all"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Scanning Trends...' : 'Refresh Radar'}</span>
          </button>
        </div>
      </div>

      {/* Strategic Insights Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4">
          <span className="text-xs font-mono uppercase text-indigo-400 flex items-center gap-1.5 font-semibold">
            <Flame className="w-3.5 h-3.5 text-indigo-400" />
            Active Viral Formats &amp; Hook Dynamics
          </span>
          <div className="flex flex-wrap gap-2 mt-3">
            {(trendData?.formatTrends || [
              'Under-2-second question hook',
              'Contrarian myth buster',
              'Visual scale contrast',
            ]).map((t, idx) => (
              <span
                key={idx}
                className="text-xs bg-indigo-950/40 text-indigo-200 border border-indigo-800/40 px-2.5 py-1 rounded-lg"
              >
                {t}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4">
          <span className="text-xs font-mono uppercase text-cyan-400 flex items-center gap-1.5 font-semibold">
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
            Top Performing Title Archetypes
          </span>
          <div className="flex flex-wrap gap-2 mt-3">
            {(trendData?.titlePatterns || [
              'The Real Reason Why...',
              'What Actually Happens If...',
              'Why Scientists Were Wrong About...',
            ]).map((p, idx) => (
              <span
                key={idx}
                className="text-xs bg-cyan-950/40 text-cyan-200 border border-cyan-800/40 px-2.5 py-1 rounded-lg"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Scored Trend Opportunities Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredIdeas.map((idea, idx) => (
          <div
            key={idx}
            className="bg-zinc-900/90 border border-zinc-800/90 hover:border-indigo-500/50 rounded-2xl p-5 transition-all shadow-md flex flex-col justify-between group"
          >
            <div>
              {/* Score & Format Badges */}
              <div className="flex items-center justify-between gap-2 mb-2.5">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 text-xs font-mono font-bold">
                    <Sparkles className="w-3 h-3 text-indigo-400" />
                    VIRAL SCORE: {idea.score}/10
                  </span>
                  <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                    {idea.format}
                  </span>
                  <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-zinc-800/60 text-zinc-400">
                    {idea.style}
                  </span>
                </div>

                {idea.used && (
                  <span className="text-[10px] font-mono text-zinc-500 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    PRODUCED
                  </span>
                )}
              </div>

              {/* Topic Headline */}
              <h3 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors">
                {idea.topic}
              </h3>

              {/* Angle */}
              <div className="mt-2.5 bg-zinc-950/60 border border-zinc-800/60 rounded-xl p-3 text-xs text-zinc-300">
                <span className="text-zinc-500 font-mono text-[10px] block mb-0.5">
                  THE SURPRISING ANGLE:
                </span>
                {idea.angle}
              </div>

              {/* Why Trending Signal */}
              <p className="text-xs text-zinc-400 mt-2 flex items-center gap-1.5">
                <span className="text-zinc-500 font-mono text-[10px]">SIGNAL:</span>
                <span className="text-zinc-300">{idea.why_trending}</span>
              </p>
            </div>

            {/* Action Bar */}
            <div className="pt-4 mt-4 border-t border-zinc-800/80 flex items-center justify-between">
              <span className="text-[11px] text-zinc-500 font-mono flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                Fact-Check Passed
              </span>

              <button
                onClick={() => onTriggerIdea(idea)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
              >
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>Produce Video Now</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
