export interface AgentLog {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'thought' | 'agent';
  stage: string;
  message: string;
  data?: any;
}

export interface PlatformStatus {
  connected: boolean;
  uploadsToday?: number;
  postsToday?: number;
  maxDaily: number;
  lastUpload?: string | null;
  lastPost?: string | null;
  error?: string | null;
  privacy?: string;
}

export interface AgentState {
  status:
    | 'idle'
    | 'researching'
    | 'planning'
    | 'scripting'
    | 'synthesizing_audio'
    | 'sourcing_visuals'
    | 'assembling'
    | 'evaluating'
    | 'ready_for_approval'
    | 'publishing'
    | 'optimizing_memory'
    | 'paused'
    | 'error';
  progress: number;
  currentTask: string;
  currentTopic: string | null;
  mode: 'autonomous' | 'approval';
  isPaused: boolean;
  activeProcessId: number | null;
  logs: AgentLog[];
  dailyProduction: {
    target: number;
    createdToday: number;
    publishedToday: number;
    lastRun: string | null;
    nextRun: string | null;
  };
  platforms: {
    youtube: PlatformStatus;
    instagram: PlatformStatus;
  };
  geminiKeyConfigured: boolean;
  pixabayKeyConfigured: boolean;
  historyCount: number;
}

export interface VideoItem {
  id: string;
  isCurrent: boolean;
  title: string;
  topic: string;
  format: 'short' | 'long' | 'story';
  description: string;
  hashtags: string[];
  category: string;
  style: string;
  sizeBytes: number;
  createdAt: string;
  videoUrl: string;
  thumbnailUrl: string | null;
  status: 'draft' | 'ready_for_review' | 'completed' | 'published' | 'archived';
  scenes?: { text: string; search_terms: string[] }[];
}

export interface TrendIdea {
  topic: string;
  angle: string;
  why_trending: string;
  format: 'short' | 'long' | 'story';
  style: string;
  score: number;
  used: boolean;
}

export interface TrendRadarData {
  date: string;
  ideas: TrendIdea[];
  formatTrends: string[];
  titlePatterns: string[];
  cached: boolean;
}

export interface MemoryData {
  topicsCount: number;
  recentTopics: string[];
  categoryWeights: Record<string, number>;
  styleWeights: Record<string, number>;
  recentCategories: string[];
  lastStyle: string;
}

export interface SystemConfig {
  categories: string[];
  ttsVoice: string;
  voicesAvailable: { id: string; name: string }[];
  videoDuration: string;
  longDuration: string;
  keys: {
    gemini: boolean;
    groq: boolean;
    pixabay: boolean;
    pexels: boolean;
    youtube: boolean;
    instagram: boolean;
    cloudinary: boolean;
  };
}
