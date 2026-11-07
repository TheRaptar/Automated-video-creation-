import React, { useState } from 'react';
import {
  Settings,
  Key,
  Mic,
  Clock,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Save,
  Cpu,
  Video,
  ExternalLink,
} from 'lucide-react';
import { SystemConfig } from '../types';

interface SettingsTabProps {
  config: SystemConfig | null;
  onSaveConfig: (updated: Partial<SystemConfig>) => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({ config, onSaveConfig }) => {
  const [ttsVoice, setTtsVoice] = useState(config?.ttsVoice || 'en-US-GuyNeural');
  const [videoDuration, setVideoDuration] = useState(config?.videoDuration || '40-60');
  const [longDuration, setLongDuration] = useState(config?.longDuration || '300-420');
  const [savedSuccess, setSavedSuccess] = useState(false);

  React.useEffect(() => {
    if (config) {
      setTtsVoice(config.ttsVoice);
      setVideoDuration(config.videoDuration);
      setLongDuration(config.longDuration);
    }
  }, [config]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    onSaveConfig({
      ttsVoice,
      videoDuration,
      longDuration,
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Settings className="w-4 h-4 text-indigo-400" />
            System Configuration &amp; API Infrastructure
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Voice synthesis models, video pacing duration, and connected API credential verification.
          </p>
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
        >
          {savedSuccess ? (
            <>
              <CheckCircle2 className="w-4 h-4 text-emerald-300" />
              <span>Settings Saved!</span>
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              <span>Save Configuration</span>
            </>
          )}
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Voice & Duration Settings */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-5">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Mic className="w-4 h-4 text-violet-400" />
            Voiceover &amp; Video Production Rules
          </h3>

          {/* TTS Voice Picker */}
          <div>
            <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-2">
              AI Voice Persona (edge-tts Neural Model)
            </label>
            <div className="space-y-2">
              {(config?.voicesAvailable || []).map((v) => (
                <label
                  key={v.id}
                  className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all ${
                    ttsVoice === v.id
                      ? 'bg-indigo-950/60 border-indigo-500 text-white'
                      : 'bg-zinc-950/50 border-zinc-800/80 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="voice"
                      value={v.id}
                      checked={ttsVoice === v.id}
                      onChange={() => setTtsVoice(v.id)}
                      className="accent-indigo-500"
                    />
                    <span className="text-xs font-semibold text-zinc-200">{v.name}</span>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-500">{v.id}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Duration Configs */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div>
              <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-1">
                Shorts Target Seconds
              </label>
              <input
                type="text"
                value={videoDuration}
                onChange={(e) => setVideoDuration(e.target.value)}
                placeholder="40-60"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[10px] text-zinc-500 mt-1 block">Default: 40-60 sec</span>
            </div>

            <div>
              <label className="text-xs font-mono uppercase tracking-wider text-zinc-400 block mb-1">
                Long-Form Target Seconds
              </label>
              <input
                type="text"
                value={longDuration}
                onChange={(e) => setLongDuration(e.target.value)}
                placeholder="300-420"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[10px] text-zinc-500 mt-1 block">Default: 5-7 min</span>
            </div>
          </div>
        </div>

        {/* API Credentials & Secret Health Status */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Key className="w-4 h-4 text-cyan-400" />
            API Ecosystem &amp; Secret Health Monitor
          </h3>
          <p className="text-xs text-zinc-400 leading-relaxed">
            API keys are injected via environment variables or the GitHub Actions / AI Studio
            Secrets vault.
          </p>

          <div className="space-y-2.5">
            {[
              {
                id: 'gemini',
                name: 'Google Gemini API',
                desc: 'Powers Autonomous Agent, Trend Ideation, Scriptwriting & Fact-Check',
                status: config?.keys?.gemini,
                required: true,
              },
              {
                id: 'pixabay',
                name: 'Pixabay Video API',
                desc: 'Free stock footage clips for visual scenes and background variety',
                status: config?.keys?.pixabay,
                required: false,
              },
              {
                id: 'pexels',
                name: 'Pexels API',
                desc: 'Alternative stock video provider (optional secondary)',
                status: config?.keys?.pexels,
                required: false,
              },
              {
                id: 'youtube',
                name: 'YouTube Data API v3',
                desc: 'OAuth Client ID + Secret + Refresh Token for automated channel uploads',
                status: config?.keys?.youtube,
                required: false,
              },
              {
                id: 'instagram',
                name: 'Meta Instagram Graph API',
                desc: 'Reels posting via Unified Login token and Instagram business ID',
                status: config?.keys?.instagram,
                required: false,
              },
            ].map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between p-3 rounded-xl bg-zinc-950/60 border border-zinc-800/80"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-zinc-200">{k.name}</span>
                    {k.required && (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800/40">
                        PRIMARY
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5">{k.desc}</p>
                </div>

                <div className="shrink-0 ml-3">
                  {k.status ? (
                    <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 px-2 py-0.5 rounded">
                      <CheckCircle2 className="w-3 h-3" />
                      ACTIVE
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[11px] font-mono text-zinc-500 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded">
                      NOT DETECTED
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
