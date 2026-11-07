import React, { useState, useEffect } from 'react';
import {
  Film,
  Compass,
  Brain,
  UploadCloud,
  Terminal,
  Settings,
  Sparkles,
  Bot,
  AlertCircle,
} from 'lucide-react';
import { Header } from './components/Header';
import { AgentStatusBanner } from './components/AgentStatusBanner';
import { VideoStudioTab } from './components/VideoStudioTab';
import { TrendRadarTab } from './components/TrendRadarTab';
import { AgentMemoryTab } from './components/AgentMemoryTab';
import { DistributionTab } from './components/DistributionTab';
import { LogsTab } from './components/LogsTab';
import { SettingsTab } from './components/SettingsTab';
import { VideoPlayerModal } from './components/VideoPlayerModal';
import { GenerateVideoModal } from './components/GenerateVideoModal';
import {
  AgentState,
  VideoItem,
  TrendRadarData,
  TrendIdea,
  MemoryData,
  SystemConfig,
} from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState<
    'studio' | 'radar' | 'memory' | 'distribution' | 'logs' | 'settings'
  >('studio');

  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [trends, setTrends] = useState<TrendRadarData | null>(null);
  const [memory, setMemory] = useState<MemoryData | null>(null);
  const [config, setConfig] = useState<SystemConfig | null>(null);

  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isRefreshingTrends, setIsRefreshingTrends] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3500);
  };

  // Poll agent state
  const fetchState = async () => {
    try {
      const res = await fetch('/api/agent/state');
      if (res.ok) {
        const data = await res.json();
        setAgentState(data);
      }
    } catch (err) {
      console.error('Failed to fetch agent state:', err);
    }
  };

  const fetchVideos = async () => {
    try {
      const res = await fetch('/api/videos');
      if (res.ok) {
        const data = await res.json();
        setVideos(data.videos || []);
      }
    } catch (err) {
      console.error('Failed to fetch videos:', err);
    }
  };

  const fetchTrends = async () => {
    try {
      const res = await fetch('/api/trends');
      if (res.ok) {
        const data = await res.json();
        setTrends(data);
      }
    } catch (err) {
      console.error('Failed to fetch trends:', err);
    }
  };

  const fetchMemory = async () => {
    try {
      const res = await fetch('/api/memory');
      if (res.ok) {
        const data = await res.json();
        setMemory(data);
      }
    } catch (err) {
      console.error('Failed to fetch memory:', err);
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (err) {
      console.error('Failed to fetch config:', err);
    }
  };

  useEffect(() => {
    fetchState();
    fetchVideos();
    fetchTrends();
    fetchMemory();
    fetchConfig();

    const interval = setInterval(() => {
      fetchState();
      fetchVideos();
    }, 2500);

    return () => clearInterval(interval);
  }, []);

  // Action handlers
  const handleTriggerRun = async () => {
    try {
      showNotification('Triggering autonomous AI video production cycle...');
      const res = await fetch('/api/agent/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'short' }),
      });
      if (res.ok) {
        fetchState();
      }
    } catch (err: any) {
      showNotification(`Failed to trigger: ${err.message}`);
    }
  };

  const handleCustomGenerate = async (topic?: string, format: 'short' | 'long' | 'story' = 'short') => {
    try {
      showNotification(`Spawning video pipeline for: ${topic || 'Trending Topic'} (${format})...`);
      const res = await fetch('/api/agent/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, format }),
      });
      if (res.ok) {
        fetchState();
        setActiveTab('studio');
      }
    } catch (err: any) {
      showNotification(`Failed to trigger: ${err.message}`);
    }
  };

  const handleTogglePause = async () => {
    const isCurrentlyPaused = agentState?.isPaused;
    const endpoint = isCurrentlyPaused ? '/api/agent/resume' : '/api/agent/pause';
    try {
      const res = await fetch(endpoint, { method: 'POST' });
      if (res.ok) {
        fetchState();
        showNotification(isCurrentlyPaused ? 'Agent loop resumed.' : 'Agent loop paused.');
      }
    } catch (err: any) {
      showNotification(`Pause/Resume failed: ${err.message}`);
    }
  };

  const handleToggleMode = async (mode: 'autonomous' | 'approval') => {
    try {
      const res = await fetch('/api/agent/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (res.ok) {
        fetchState();
        showNotification(`Agent operating mode set to: ${mode.toUpperCase()}`);
      }
    } catch (err: any) {
      showNotification(`Mode toggle failed: ${err.message}`);
    }
  };

  const handleApproveVideo = async (id: string) => {
    setIsPublishing(true);
    showNotification('Dispatching video to YouTube and Instagram APIs...');
    try {
      const res = await fetch(`/api/videos/${id}/approve`, {
        method: 'POST',
      });
      if (res.ok) {
        showNotification('Video successfully queued and published!');
        fetchState();
        fetchVideos();
        setSelectedVideo(null);
      } else {
        const errData = await res.json();
        showNotification(`Publishing error: ${errData.error || 'Failed'}`);
      }
    } catch (err: any) {
      showNotification(`Publish error: ${err.message}`);
    } finally {
      setIsPublishing(false);
    }
  };

  const handleRefreshTrends = async () => {
    setIsRefreshingTrends(true);
    try {
      const res = await fetch('/api/trends/refresh', { method: 'POST' });
      if (res.ok) {
        await fetchTrends();
        showNotification('Trend radar updated with fresh AI virality scores.');
      }
    } catch (err: any) {
      showNotification(`Trend refresh error: ${err.message}`);
    } finally {
      setIsRefreshingTrends(false);
    }
  };

  const handleSaveWeights = async (
    catWeights: Record<string, number>,
    styleWeights: Record<string, number>
  ) => {
    try {
      const res = await fetch('/api/memory', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categoryWeights: catWeights, styleWeights }),
      });
      if (res.ok) {
        fetchMemory();
        showNotification('Agent strategic weights updated and saved to persistent memory.');
      }
    } catch (err: any) {
      showNotification(`Memory update error: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans antialiased selection:bg-indigo-500 selection:text-white">
      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 bg-zinc-900 border border-indigo-500/50 text-zinc-100 text-xs px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2 backdrop-blur-md animate-in fade-in slide-in-from-bottom-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span>{notification}</span>
        </div>
      )}

      {/* Navigation Header */}
      <Header
        state={agentState}
        onTriggerRun={handleTriggerRun}
        onTogglePause={handleTogglePause}
        onToggleMode={handleToggleMode}
        onOpenGenerateModal={() => setShowGenerateModal(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6 space-y-6">
        {/* Live Autonomous Agent Status & Pipeline Tracker */}
        <AgentStatusBanner state={agentState} onRefresh={fetchState} />

        {/* Tab Navigation Navigation Bar */}
        <div className="flex items-center gap-1.5 border-b border-zinc-800 pb-px overflow-x-auto">
          {[
            { id: 'studio', label: 'Production Studio', icon: Film, count: videos.length },
            { id: 'radar', label: 'Trend Radar', icon: Compass, count: trends?.ideas?.length },
            { id: 'memory', label: 'Agent Memory & Learning', icon: Brain },
            { id: 'distribution', label: 'Social Distribution', icon: UploadCloud },
            { id: 'logs', label: 'Agent Thought Stream', icon: Terminal, count: agentState?.logs?.length },
            { id: 'settings', label: 'System & API Config', icon: Settings },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all whitespace-nowrap border-b-2 ${
                  isActive
                    ? 'border-indigo-500 text-white bg-zinc-900/60'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/30'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-indigo-400' : 'text-zinc-500'}`} />
                <span>{tab.label}</span>
                {typeof tab.count === 'number' && (
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                      isActive ? 'bg-indigo-950 text-indigo-300' : 'bg-zinc-800 text-zinc-500'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Active Tab View */}
        <div className="pt-2">
          {activeTab === 'studio' && (
            <VideoStudioTab
              videos={videos}
              onSelectVideo={(v) => setSelectedVideo(v)}
              onOpenGenerateModal={() => setShowGenerateModal(true)}
              onApprove={handleApproveVideo}
            />
          )}

          {activeTab === 'radar' && (
            <TrendRadarTab
              trendData={trends}
              isLoading={isRefreshingTrends}
              onRefresh={handleRefreshTrends}
              onTriggerIdea={(idea: TrendIdea) => handleCustomGenerate(idea.topic, idea.format)}
            />
          )}

          {activeTab === 'memory' && (
            <AgentMemoryTab memoryData={memory} onSaveWeights={handleSaveWeights} />
          )}

          {activeTab === 'distribution' && (
            <DistributionTab state={agentState} onRefresh={fetchState} />
          )}

          {activeTab === 'logs' && <LogsTab logs={agentState?.logs || []} />}

          {activeTab === 'settings' && (
            <SettingsTab
              config={config}
              onSaveConfig={(updated) => {
                showNotification('Configuration preferences saved.');
              }}
            />
          )}
        </div>
      </main>

      {/* Video Details & Review Modal */}
      {selectedVideo && (
        <VideoPlayerModal
          video={selectedVideo}
          onClose={() => setSelectedVideo(null)}
          onApprove={handleApproveVideo}
          isPublishing={isPublishing}
        />
      )}

      {/* Custom Video Creation Modal */}
      {showGenerateModal && (
        <GenerateVideoModal
          onClose={() => setShowGenerateModal(false)}
          onSubmit={handleCustomGenerate}
          categories={config?.categories || []}
        />
      )}
    </div>
  );
}
