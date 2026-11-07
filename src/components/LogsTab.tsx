import React, { useState } from 'react';
import {
  Terminal,
  Filter,
  Trash2,
  Download,
  AlertTriangle,
  Info,
  Sparkles,
  Bot,
  CheckCircle2,
} from 'lucide-react';
import { AgentLog } from '../types';

interface LogsTabProps {
  logs: AgentLog[];
  onClear?: () => void;
}

export const LogsTab: React.FC<LogsTabProps> = ({ logs, onClear }) => {
  const [filterLevel, setFilterLevel] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredLogs = logs.filter((log) => {
    if (filterLevel !== 'all' && log.level !== filterLevel) return false;
    if (searchTerm) {
      const match =
        log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.stage.toLowerCase().includes(searchTerm.toLowerCase());
      if (!match) return false;
    }
    return true;
  });

  const getLogBadge = (level: AgentLog['level']) => {
    switch (level) {
      case 'thought':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-violet-950/70 text-violet-300 border border-violet-800/60 flex items-center gap-1">
            <Sparkles className="w-2.5 h-2.5" />
            THOUGHT
          </span>
        );
      case 'agent':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-800/60 flex items-center gap-1">
            <Bot className="w-2.5 h-2.5" />
            AGENT
          </span>
        );
      case 'error':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-800/60 flex items-center gap-1">
            <AlertTriangle className="w-2.5 h-2.5" />
            ERROR
          </span>
        );
      case 'warn':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800/60 flex items-center gap-1">
            <AlertTriangle className="w-2.5 h-2.5" />
            WARN
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 flex items-center gap-1">
            <Info className="w-2.5 h-2.5" />
            INFO
          </span>
        );
    }
  };

  const exportLogs = () => {
    const dataStr =
      'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(logs, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `raptar_logs_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="space-y-4">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-indigo-400" />
            Autonomous Agent Mindstream &amp; Execution Telemetry
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Real-time internal thoughts, script fact-checking logs, FFmpeg commands, and API traces.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Level Filter */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 text-xs">
            {['all', 'thought', 'agent', 'info', 'warn', 'error'].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setFilterLevel(lvl)}
                className={`px-2 py-0.5 rounded font-mono text-[11px] capitalize transition-colors ${
                  filterLevel === lvl ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>

          <button
            onClick={exportLogs}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 text-xs font-medium transition-all"
            title="Export JSON"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export</span>
          </button>
        </div>
      </div>

      {/* Terminal View Container */}
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl p-4 font-mono text-xs shadow-2xl min-h-[460px] max-h-[600px] overflow-y-auto space-y-2">
        {filteredLogs.length === 0 ? (
          <div className="text-center py-20 text-zinc-600">
            <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No log records match current filter</p>
          </div>
        ) : (
          filteredLogs.map((log) => (
            <div
              key={log.id}
              className="flex items-start gap-3 p-2 rounded-lg bg-zinc-900/30 hover:bg-zinc-900/80 border border-transparent hover:border-zinc-800/80 transition-colors"
            >
              <span className="text-zinc-500 text-[11px] shrink-0 pt-0.5">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <div className="shrink-0">{getLogBadge(log.level)}</div>
              <span className="text-indigo-400 font-bold shrink-0">[{log.stage}]</span>
              <span className="text-zinc-200 leading-relaxed break-all flex-1">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
