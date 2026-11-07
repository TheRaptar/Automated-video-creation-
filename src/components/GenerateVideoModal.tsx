import React, { useState } from 'react';
import { X, Sparkles, Film, Compass, Play, Layers } from 'lucide-react';

interface GenerateVideoModalProps {
  onClose: () => void;
  onSubmit: (topic?: string, format?: 'short' | 'long' | 'story') => void;
  categories: string[];
}

export const GenerateVideoModal: React.FC<GenerateVideoModalProps> = ({
  onClose,
  onSubmit,
  categories,
}) => {
  const [topic, setTopic] = useState('');
  const [format, setFormat] = useState<'short' | 'long' | 'story'>('short');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedStyle, setSelectedStyle] = useState<string>('fact');

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    let finalTopic = topic.trim();
    if (!finalTopic && selectedCategory) {
      finalTopic = `A fascinating explainer in ${selectedCategory} focusing on a surprising, verifiable real-world phenomenon.`;
    }
    onSubmit(finalTopic || undefined, format);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-xl bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950/60">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">Produce AI Video On-Demand</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleCreate} className="p-6 space-y-5">
          {/* Format Selection */}
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-2">
              Select Video Format
            </label>
            <div className="grid grid-cols-3 gap-2.5">
              {[
                {
                  id: 'short',
                  name: 'Short / Reel',
                  ratio: '9:16 Vertical',
                  dur: '40-60 sec',
                  desc: 'High viral pacing & kinetic subtitles',
                },
                {
                  id: 'story',
                  name: 'Illustrated Story',
                  ratio: '9:16 Vertical',
                  dur: '45-75 sec',
                  desc: 'AI visual scenes + narrative arc',
                },
                {
                  id: 'long',
                  name: 'Long-Form Doc',
                  ratio: '16:9 Landscape',
                  dur: '5-7 min',
                  desc: 'Deep multi-chapter documentary',
                },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFormat(f.id as any)}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    format === f.id
                      ? 'bg-indigo-950/60 border-indigo-500 text-white shadow-md shadow-indigo-500/10'
                      : 'bg-zinc-950/50 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-zinc-200">{f.name}</p>
                    <span className="text-[10px] font-mono text-indigo-400">{f.ratio}</span>
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-1">{f.desc}</p>
                  <p className="text-[10px] font-mono text-zinc-500 mt-2">{f.dur}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Topic Custom Input */}
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-1.5">
              Custom Topic / Angle (Optional)
            </label>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Why deep sea creatures can survive crushing pressures, or how quantum dots create screen colors..."
              rows={3}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <p className="text-[11px] text-zinc-500 mt-1">
              Leave blank to let RAPTAR autonomous agent research and pick the highest scoring
              real-time market trend.
            </p>
          </div>

          {/* Category Quick Pick */}
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-1.5">
              Or Restrict to Knowledge Category
            </label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2.5 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="">AI Autonomous Choice (Weighted by Audience History)</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-zinc-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-zinc-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Launch Production</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
