import React, { useState } from 'react';
import {
  Brain,
  History,
  Sliders,
  Sparkles,
  TrendingUp,
  Search,
  CheckCircle2,
  RefreshCw,
  Save,
} from 'lucide-react';
import { MemoryData } from '../types';

interface AgentMemoryTabProps {
  memoryData: MemoryData | null;
  onSaveWeights: (catWeights: Record<string, number>, styleWeights: Record<string, number>) => void;
}

export const AgentMemoryTab: React.FC<AgentMemoryTabProps> = ({ memoryData, onSaveWeights }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [catWeights, setCatWeights] = useState<Record<string, number>>(
    memoryData?.categoryWeights || {}
  );
  const [styleWeights, setStyleWeights] = useState<Record<string, number>>(
    memoryData?.styleWeights || {}
  );
  const [savedSuccess, setSavedSuccess] = useState(false);

  // Sync if prop changes
  React.useEffect(() => {
    if (memoryData) {
      setCatWeights(memoryData.categoryWeights || {});
      setStyleWeights(memoryData.styleWeights || {});
    }
  }, [memoryData]);

  const handleWeightChange = (type: 'cat' | 'style', key: string, val: number) => {
    if (type === 'cat') {
      setCatWeights((prev) => ({ ...prev, [key]: val }));
    } else {
      setStyleWeights((prev) => ({ ...prev, [key]: val }));
    }
  };

  const handleSave = () => {
    onSaveWeights(catWeights, styleWeights);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  const topics = memoryData?.recentTopics || [];
  const filteredTopics = topics.filter((t) => t.toLowerCase().includes(searchTerm.toLowerCase()));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Brain className="w-4 h-4 text-indigo-400" />
            Agent Persistent Memory &amp; Self-Optimizing Feedback Loops
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            The agent tracks past performance, dynamically re-weights successful styles, and enforces a
            300-topic anti-repetition memory.
          </p>
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
        >
          {savedSuccess ? (
            <>
              <CheckCircle2 className="w-4 h-4 text-emerald-300" />
              <span>Weights Saved!</span>
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              <span>Save Calibrations</span>
            </>
          )}
        </button>
      </div>

      {/* Strategic Weights Tuner Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Style Performance Weights */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-5 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Sliders className="w-4 h-4 text-violet-400" />
              Content Style Virality Weights
            </h3>
            <span className="text-[11px] font-mono text-zinc-500">
              Auto-calibrated from view counts
            </span>
          </div>

          <div className="space-y-3">
            {Object.entries(styleWeights).map(([style, weight]) => (
              <div key={style} className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold text-zinc-200 uppercase font-mono">{style}</span>
                  <span className="font-mono text-indigo-400 font-bold">{weight.toFixed(2)}x</span>
                </div>
                <input
                  type="range"
                  min="0.4"
                  max="2.0"
                  step="0.05"
                  value={weight}
                  onChange={(e) => handleWeightChange('style', style, parseFloat(e.target.value))}
                  className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Category Affinity Weights */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-5 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              Knowledge Category Weights
            </h3>
            <span className="text-[11px] font-mono text-zinc-500">
              Channel retention tuning
            </span>
          </div>

          <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
            {Object.entries(catWeights).map(([cat, weight]) => (
              <div key={cat} className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3">
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold text-zinc-300 capitalize">{cat}</span>
                  <span className="font-mono text-cyan-400 font-bold">{weight.toFixed(2)}x</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.05"
                  value={weight}
                  onChange={(e) => handleWeightChange('cat', cat, parseFloat(e.target.value))}
                  className="w-full accent-cyan-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg"
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Historical Topics & Anti-Repetition Blacklist */}
      <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-5 shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white">
              Anti-Repetition Topic History ({memoryData?.topicsCount || 0} Topics Guarded)
            </h3>
          </div>

          {/* Search Box */}
          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Filter past topics..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-60 overflow-y-auto pr-1">
          {filteredTopics.map((top, idx) => (
            <div
              key={idx}
              className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-2.5 text-xs text-zinc-300 flex items-center justify-between gap-2"
            >
              <span className="truncate">{top}</span>
              <span className="text-[10px] font-mono text-zinc-500 shrink-0">#{idx + 1}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
