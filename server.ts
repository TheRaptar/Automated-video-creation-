import express from 'express';
import { createServer as createViteServer } from 'vite';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;

app.use(express.json({ limit: '50mb' }));

// Directories
const WORKSPACE_DIR = __dirname;
const SCRIPT_DIR = path.join(WORKSPACE_DIR, 'Automated-video-creation');
const OUTPUT_DIR = path.join(SCRIPT_DIR, 'output');
const ARCHIVE_DIR = path.join(SCRIPT_DIR, 'archive');
const HISTORY_FILE = path.join(SCRIPT_DIR, 'history.json');
const STATE_FILE = path.join(SCRIPT_DIR, 'state.json');
const STATUS_FILE = path.join(SCRIPT_DIR, 'agent_status.json');

// Ensure directories exist
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(ARCHIVE_DIR)) fs.mkdirSync(ARCHIVE_DIR, { recursive: true });

// Initialize Gemini Client
const geminiApiKey = process.env.GEMINI_API_KEY || '';
const ai = geminiApiKey ? new GoogleGenAI({ apiKey: geminiApiKey }) : null;

// Global Agent State
interface AgentLog {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'thought' | 'agent';
  stage: string;
  message: string;
  data?: any;
}

interface AgentState {
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
    youtube: {
      connected: boolean;
      uploadsToday: number;
      maxDaily: number;
      lastUpload: string | null;
      error: string | null;
      privacy: string;
    };
    instagram: {
      connected: boolean;
      postsToday: number;
      maxDaily: number;
      lastPost: string | null;
      error: string | null;
    };
  };
}

const agentState: AgentState = {
  status: 'idle',
  progress: 100,
  currentTask: 'Agent standing by. Ready for autonomous creation cycle.',
  currentTopic: null,
  mode: 'approval', // Safety: default to Approval Gate mode to prevent accidental live publishing
  isPaused: false,
  activeProcessId: null,
  logs: [],
  dailyProduction: {
    target: 1,
    createdToday: 0,
    publishedToday: 0,
    lastRun: new Date().toISOString(),
    nextRun: new Date(Date.now() + 6 * 3600 * 1000).toISOString(),
  },
  platforms: {
    youtube: {
      connected: Boolean(process.env.YT_CLIENT_ID && process.env.YT_REFRESH_TOKEN),
      uploadsToday: 0,
      maxDaily: 5,
      lastUpload: null,
      error: null,
      privacy: process.env.YT_PRIVACY || 'public',
    },
    instagram: {
      connected: Boolean(process.env.IG_ACCESS_TOKEN),
      postsToday: 0,
      maxDaily: 4,
      lastPost: null,
      error: null,
    },
  },
};

function addLog(level: AgentLog['level'], stage: string, message: string, data?: any) {
  const log: AgentLog = {
    id: Math.random().toString(36).substring(2, 9),
    timestamp: new Date().toISOString(),
    level,
    stage,
    message,
    data,
  };
  agentState.logs.unshift(log);
  if (agentState.logs.length > 250) {
    agentState.logs.pop();
  }
  console.log(`[RAPTAR ${level.toUpperCase()}] [${stage}] ${message}`);
}

addLog('info', 'SYSTEM', 'RAPTAR Autonomous AI Video & Social Media Engine initialized.');

// Helper to read and write state
function getHistory(): string[] {
  try {
    if (fs.existsSync(HISTORY_FILE)) {
      return JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf-8'));
    }
  } catch (err) {
    console.error('Error reading history:', err);
  }
  return [];
}

function getState(): Record<string, any> {
  try {
    if (fs.existsSync(STATE_FILE)) {
      return JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
    }
  } catch (err) {
    console.error('Error reading state.json:', err);
  }
  return {};
}

function saveState(state: Record<string, any>) {
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf-8');
  } catch (err) {
    console.error('Error writing state.json:', err);
  }
}

// Check uploads today from state.json
function refreshPlatformStats() {
  const st = getState();
  const uploads = st.uploads || [];
  const todayStr = new Date().toISOString().slice(0, 10);
  const todaysUploads = uploads.filter((u: string) => u.startsWith(todayStr));
  agentState.platforms.youtube.uploadsToday = todaysUploads.length;
  agentState.platforms.youtube.connected = Boolean(
    process.env.YT_CLIENT_ID && process.env.YT_REFRESH_TOKEN
  );
  agentState.platforms.instagram.connected = Boolean(process.env.IG_ACCESS_TOKEN);
  agentState.dailyProduction.publishedToday = todaysUploads.length;
}
refreshPlatformStats();

// -------------------------------------------------------------
// Autonomous Video Pipeline Runner
// -------------------------------------------------------------
let isRunningPipeline = false;

async function runAutonomousPipeline(customTopic?: string, format: 'short' | 'long' | 'story' = 'short') {
  if (isRunningPipeline) {
    throw new Error('Pipeline is already actively executing.');
  }
  if (agentState.isPaused) {
    throw new Error('Agent is currently paused. Please resume first.');
  }

  isRunningPipeline = true;
  agentState.status = 'researching';
  agentState.progress = 5;
  agentState.currentTask = customTopic
    ? `Initializing production for topic: "${customTopic}"`
    : 'Researching real-time market trends (Google Trends, Wikipedia, YouTube)...';

  addLog('agent', 'RESEARCH', agentState.currentTask);

  const env = {
    ...process.env,
    VIDEO_FORMAT: format,
    OFFLINE_TEST: process.env.GEMINI_API_KEY ? '0' : '1',
    PYTHONUNBUFFERED: '1',
  };

  const args = ['make_video.py', '--format', format];
  if (customTopic) {
    args.push(customTopic);
  }

  addLog('thought', 'AGENT_DECISION', `Selected format: ${format.toUpperCase()}. Spawning video production engine...`);

  return new Promise<{ success: boolean; topic: string; metadata: any }>((resolve, reject) => {
    const pythonBin = fs.existsSync('/root/.local/bin/python3')
      ? '/root/.local/bin/python3'
      : 'python3';

    const child = spawn(pythonBin, args, {
      cwd: SCRIPT_DIR,
      env,
    });

    agentState.activeProcessId = child.pid || null;

    child.stdout.on('data', (chunk: Buffer) => {
      const text = chunk.toString();
      const lines = text.split('\n').filter((l) => l.trim().length > 0);
      for (const line of lines) {
        // Parse progress heuristics
        if (line.includes('Researching today') || line.includes('Trend idea picked')) {
          agentState.status = 'researching';
          agentState.progress = 15;
          agentState.currentTask = line.trim();
          addLog('info', 'TRENDS', line.trim());
        } else if (line.includes('Choosing topic and writing')) {
          agentState.status = 'scripting';
          agentState.progress = 25;
          agentState.currentTask = 'Generating viral narrative script and fact-checking scenes...';
          addLog('info', 'SCRIPT', line.trim());
        } else if (line.includes('Topic:') || line.includes('Title:')) {
          agentState.currentTopic = line.replace(/Topic:|Title:/, '').trim();
          addLog('agent', 'TOPIC', line.trim());
        } else if (line.includes('Scene')) {
          agentState.status = 'assembling';
          agentState.progress = Math.min(85, agentState.progress + 10);
          agentState.currentTask = line.trim();
          addLog('info', 'PRODUCTION', line.trim());
        } else if (line.includes('Joining scenes')) {
          agentState.status = 'assembling';
          agentState.progress = 90;
          agentState.currentTask = 'Assembling audio, video clips, kinetic typography, and rendering final MP4...';
          addLog('info', 'FFMPEG', line.trim());
        } else if (line.includes('Done! ->')) {
          agentState.progress = 100;
          addLog('agent', 'COMPLETION', line.trim());
        } else {
          addLog('info', 'LOG', line.trim());
        }
      }
    });

    child.stderr.on('data', (chunk: Buffer) => {
      const text = chunk.toString().trim();
      if (text.length > 0) {
        addLog('warn', 'SUBPROCESS', text.slice(0, 200));
      }
    });

    child.on('close', async (code) => {
      isRunningPipeline = false;
      agentState.activeProcessId = null;

      if (code !== 0) {
        agentState.status = 'error';
        agentState.currentTask = `Pipeline process failed with exit code ${code}`;
        addLog('error', 'PIPELINE_ERROR', `Execution stopped with error code ${code}`);
        reject(new Error(`Video pipeline exited with code ${code}`));
        return;
      }

      // Read resulting metadata
      let meta: any = {};
      const metaPath = path.join(OUTPUT_DIR, 'metadata.json');
      const videoPath = path.join(OUTPUT_DIR, 'video.mp4');

      if (fs.existsSync(metaPath)) {
        try {
          meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
        } catch (e) {
          meta = { title: agentState.currentTopic || 'AI Generated Video' };
        }
      }

      // Check if thumbnail exists, if not generate frame
      const thumbPath = path.join(OUTPUT_DIR, 'thumbnail.jpg');
      if (!fs.existsSync(thumbPath) && fs.existsSync(videoPath)) {
        try {
          spawn('ffmpeg', [
            '-y',
            '-ss',
            '00:00:02',
            '-i',
            videoPath,
            '-vframes',
            '1',
            '-q:v',
            '2',
            thumbPath,
          ]);
        } catch (e) {
          // ignore
        }
      }

      // Archive a copy for dashboard persistence
      const archiveId = `vid_${Date.now()}`;
      const itemArchiveDir = path.join(ARCHIVE_DIR, archiveId);
      fs.mkdirSync(itemArchiveDir, { recursive: true });
      if (fs.existsSync(videoPath)) {
        fs.copyFileSync(videoPath, path.join(itemArchiveDir, 'video.mp4'));
      }
      if (fs.existsSync(metaPath)) {
        fs.copyFileSync(metaPath, path.join(itemArchiveDir, 'metadata.json'));
      }
      if (fs.existsSync(thumbPath)) {
        fs.copyFileSync(thumbPath, path.join(itemArchiveDir, 'thumbnail.jpg'));
      }

      agentState.dailyProduction.createdToday += 1;
      agentState.dailyProduction.lastRun = new Date().toISOString();

      if (agentState.mode === 'autonomous') {
        agentState.status = 'publishing';
        agentState.currentTask = 'Autonomous mode active: executing social media distribution...';
        addLog('agent', 'AUTONOMOUS_PUBLISH', 'Auto-publishing to connected social platforms...');

        try {
          // Upload to YouTube if configured
          if (agentState.platforms.youtube.connected) {
            addLog('info', 'YOUTUBE', 'Dispatching official YouTube Data API uploader...');
            await runScript('upload_youtube.py');
          } else {
            addLog('warn', 'YOUTUBE', 'YouTube credentials not set in secrets; skipped auto-upload.');
          }

          // Upload to Instagram if configured and format is short/story
          if (agentState.platforms.instagram.connected && format !== 'long') {
            addLog('info', 'INSTAGRAM', 'Dispatching Instagram Graph API uploader...');
            await runScript('upload_instagram.py');
          } else {
            addLog('warn', 'INSTAGRAM', 'Instagram credentials not set or format is long; skipped Instagram upload.');
          }
        } catch (pubErr: any) {
          addLog('error', 'PUBLISHING_ERROR', pubErr.message || 'Error uploading video');
        }

        agentState.status = 'idle';
        agentState.progress = 100;
        agentState.currentTask = 'Cycle complete. Standing by for next scheduled automation.';
        addLog('agent', 'CYCLE_COMPLETE', `Video successfully created and processed: ${meta.title || 'Video'}`);
      } else {
        agentState.status = 'ready_for_approval';
        agentState.progress = 100;
        agentState.currentTask = 'Video produced and staged. Waiting for creator approval.';
        addLog('info', 'APPROVAL_GATE', `Video ready for review: "${meta.title || 'New Video'}"`);
      }

      refreshPlatformStats();
      resolve({ success: true, topic: meta.title, metadata: meta });
    });
  });
}

function runScript(scriptName: string) {
  return new Promise((resolve, reject) => {
    const pythonBin = fs.existsSync('/root/.local/bin/python3')
      ? '/root/.local/bin/python3'
      : 'python3';
    const p = spawn(pythonBin, [scriptName], {
      cwd: SCRIPT_DIR,
      env: process.env,
    });
    p.stdout.on('data', (d) => addLog('info', scriptName, d.toString().trim()));
    p.stderr.on('data', (d) => addLog('warn', scriptName, d.toString().trim()));
    p.on('close', (c) => (c === 0 ? resolve(true) : reject(new Error(`${scriptName} failed with code ${c}`))));
  });
}

// -------------------------------------------------------------
// API Endpoints
// -------------------------------------------------------------

// 1. Agent State & Status
app.get('/api/agent/state', (req, res) => {
  refreshPlatformStats();
  res.json({
    ...agentState,
    geminiKeyConfigured: Boolean(process.env.GEMINI_API_KEY),
    pixabayKeyConfigured: Boolean(process.env.PIXABAY_API_KEY),
    historyCount: getHistory().length,
  });
});

// 2. Agent Mode (Autonomous vs Approval)
app.post('/api/agent/mode', (req, res) => {
  const { mode } = req.body;
  if (mode === 'autonomous' || mode === 'approval') {
    agentState.mode = mode;
    addLog('info', 'CONFIG', `Agent operating mode changed to: ${mode.toUpperCase()}`);
    res.json({ success: true, mode: agentState.mode });
  } else {
    res.status(400).json({ error: 'Invalid mode' });
  }
});

// 3. Pause / Resume Agent
app.post('/api/agent/pause', (req, res) => {
  agentState.isPaused = true;
  agentState.status = 'paused';
  agentState.currentTask = 'Agent paused by operator.';
  addLog('warn', 'AGENT_CONTROL', 'Autonomous execution loop paused.');
  res.json({ success: true, isPaused: true });
});

app.post('/api/agent/resume', (req, res) => {
  agentState.isPaused = false;
  if (agentState.status === 'paused') {
    agentState.status = 'idle';
    agentState.currentTask = 'Agent resumed. Monitoring schedule & trend signals.';
  }
  addLog('info', 'AGENT_CONTROL', 'Autonomous execution loop resumed.');
  res.json({ success: true, isPaused: false });
});

// 4. Trigger Video Pipeline
app.post('/api/agent/trigger', async (req, res) => {
  const { topic, format = 'short' } = req.body;
  if (isRunningPipeline) {
    return res.status(409).json({ error: 'A production pipeline is already running.' });
  }

  // Trigger asynchronously so request returns quickly
  runAutonomousPipeline(topic, format).catch((err) => {
    console.error('Pipeline error:', err);
  });

  res.json({
    success: true,
    message: 'Autonomous production pipeline initiated.',
    topic: topic || 'Auto-trend selection',
    format,
  });
});

// 5. Video Catalog
app.get('/api/videos', (req, res) => {
  const list: any[] = [];

  // Check main output/
  const mainVideo = path.join(OUTPUT_DIR, 'video.mp4');
  const mainMeta = path.join(OUTPUT_DIR, 'metadata.json');
  const mainThumb = path.join(OUTPUT_DIR, 'thumbnail.jpg');

  if (fs.existsSync(mainVideo)) {
    let meta: any = {};
    try {
      meta = JSON.parse(fs.readFileSync(mainMeta, 'utf-8'));
    } catch (e) {
      meta = { title: 'Recent Output Video' };
    }
    const stat = fs.statSync(mainVideo);
    list.push({
      id: 'current_output',
      isCurrent: true,
      title: meta.title || 'Current Video',
      topic: meta.topic || 'Auto Topic',
      format: meta.format || 'short',
      description: meta.description || '',
      hashtags: meta.hashtags || [],
      category: meta.category || 'General Science',
      style: meta.style || 'fact',
      sizeBytes: stat.size,
      createdAt: stat.mtime.toISOString(),
      videoUrl: '/api/media/output/video.mp4',
      thumbnailUrl: fs.existsSync(mainThumb) ? '/api/media/output/thumbnail.jpg' : null,
      status: agentState.status === 'ready_for_approval' ? 'ready_for_review' : 'completed',
    });
  }

  // Check archive/
  if (fs.existsSync(ARCHIVE_DIR)) {
    const archives = fs.readdirSync(ARCHIVE_DIR);
    for (const arc of archives) {
      const arcDir = path.join(ARCHIVE_DIR, arc);
      const arcVid = path.join(arcDir, 'video.mp4');
      const arcMeta = path.join(arcDir, 'metadata.json');
      const arcThumb = path.join(arcDir, 'thumbnail.jpg');

      if (fs.existsSync(arcVid)) {
        let meta: any = {};
        try {
          meta = JSON.parse(fs.readFileSync(arcMeta, 'utf-8'));
        } catch (e) {
          meta = { title: arc };
        }
        const stat = fs.statSync(arcVid);
        list.push({
          id: arc,
          isCurrent: false,
          title: meta.title || arc,
          topic: meta.topic || 'Educational Explainer',
          format: meta.format || 'short',
          description: meta.description || '',
          hashtags: meta.hashtags || [],
          category: meta.category || 'Science & Tech',
          style: meta.style || 'fact',
          sizeBytes: stat.size,
          createdAt: stat.mtime.toISOString(),
          videoUrl: `/api/media/archive/${arc}/video.mp4`,
          thumbnailUrl: fs.existsSync(arcThumb) ? `/api/media/archive/${arc}/thumbnail.jpg` : null,
          status: 'archived',
        });
      }
    }
  }

  // Sort newest first
  list.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  res.json({ videos: list });
});

// 6. Manual Approve & Publish
app.post('/api/videos/:id/approve', async (req, res) => {
  addLog('agent', 'APPROVAL', `Operator approved video: ${req.params.id}. Dispatching publishing jobs.`);
  agentState.status = 'publishing';

  try {
    if (agentState.platforms.youtube.connected) {
      await runScript('upload_youtube.py');
    }
    if (agentState.platforms.instagram.connected) {
      await runScript('upload_instagram.py');
    }
    agentState.status = 'idle';
    agentState.currentTask = 'Video published successfully.';
    addLog('info', 'PUBLISH_SUCCESS', 'Video successfully distributed.');
    res.json({ success: true, message: 'Published to configured platforms.' });
  } catch (err: any) {
    agentState.status = 'error';
    addLog('error', 'PUBLISH_FAIL', err.message);
    res.status(500).json({ error: err.message });
  }
});

// 7. Trend Intelligence Radar with Gemini Ideation
app.get('/api/trends', async (req, res) => {
  const state = getState();
  const cachedTrends = state.trends || null;

  if (cachedTrends && cachedTrends.ideas && cachedTrends.ideas.length > 0) {
    return res.json({
      date: cachedTrends.date,
      ideas: cachedTrends.ideas,
      formatTrends: cachedTrends.format_trends || [],
      titlePatterns: cachedTrends.title_patterns || [],
      cached: true,
    });
  }

  // If no cached trends or empty, generate fresh intelligence
  const defaultIdeas = [
    {
      topic: 'Semiconductors and Silicon Nanofabrication',
      angle: 'How do engineers carve billions of nanometer transistors onto a chip?',
      why_trending: 'Global computing hardware race & chip advancements',
      format: 'short',
      style: 'how',
      score: 9.4,
      used: false,
    },
    {
      topic: 'James Webb Space Telescope Deep Cosmic Discoveries',
      angle: 'How JWST found galaxies older than our standard models predicted.',
      why_trending: 'Astrophysics research breakthroughs',
      format: 'short',
      style: 'fact',
      score: 9.1,
      used: false,
    },
    {
      topic: 'The Biology of Extreme Hibernation and Cryptobiosis',
      angle: 'How water bears and wood frogs freeze solid and wake up unharmed.',
      why_trending: 'Cryobiology and cellular preservation',
      format: 'short',
      style: 'whatif',
      score: 8.8,
      used: false,
    },
    {
      topic: 'Atmospheric Rivers and Superstorms',
      angle: 'The invisible rivers of vapor flying across our skies.',
      why_trending: 'Global meteorological patterns and climate science',
      format: 'short',
      style: 'fact',
      score: 8.6,
      used: false,
    },
    {
      topic: 'Quantum Entanglement and Information Speed',
      angle: 'Why Einstein called it spooky action at a distance and what experiments proved.',
      why_trending: 'Quantum physics milestone tests',
      format: 'short',
      style: 'myth',
      score: 8.5,
      used: false,
    },
  ];

  res.json({
    date: new Date().toISOString().slice(0, 10),
    ideas: defaultIdeas,
    formatTrends: ['Surprising opening hook in first 1.5 seconds', 'High-contrast typography'],
    titlePatterns: ['The Secret Behind X', 'Why Nobody Talks About Y', 'How X Actually Works'],
    cached: false,
  });
});

// 8. Refresh Trends with AI
app.post('/api/trends/refresh', async (req, res) => {
  addLog('info', 'TRENDS', 'Operator triggered manual trend radar refresh.');
  try {
    if (ai) {
      const history = getHistory().slice(-40);
      const prompt = `You are the lead trend analyst and virality strategist for an educational YouTube Shorts and Instagram Reels channel.
Today is ${new Date().toISOString().slice(0, 10)}.
Topics we already published recently (DO NOT repeat): ${history.join(', ') || 'none'}.

Generate 8 brilliant, safe, evergreen, scientifically accurate video ideas based on current curiosity trends.
Return valid JSON with format:
{
  "ideas": [
    {
      "topic": "clear topic",
      "angle": "mindblowing perspective or hook",
      "why_trending": "underlying curiosity or technological advancement",
      "format": "short" | "long" | "story",
      "style": "fact" | "myth" | "how" | "top3" | "story" | "whatif",
      "score": 8.5
    }
  ],
  "format_trends": ["hook trend 1", "hook trend 2"],
  "title_patterns": ["Pattern 1", "Pattern 2"]
}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: prompt,
        config: {
          responseMimeType: 'application/json',
        },
      });

      const parsed = JSON.parse(response.text || '{}');
      if (parsed.ideas && Array.isArray(parsed.ideas)) {
        const state = getState();
        state.trends = {
          date: new Date().toISOString().slice(0, 10),
          ideas: parsed.ideas.map((i: any) => ({ ...i, used: false })),
          format_trends: parsed.format_trends || [],
          title_patterns: parsed.title_patterns || [],
        };
        saveState(state);
        addLog('agent', 'TREND_UPDATE', `Synthesized ${parsed.ideas.length} fresh video ideas with Gemini.`);
        return res.json({ success: true, data: state.trends });
      }
    }
  } catch (err: any) {
    addLog('error', 'TREND_ERROR', err.message);
  }

  res.json({ success: false, message: 'Could not fetch live trends from AI. Using cached radar.' });
});

// 9. Agent Memory & Continuous Learning
app.get('/api/memory', (req, res) => {
  const history = getHistory();
  const state = getState();
  res.json({
    topicsCount: history.length,
    recentTopics: history.slice(-50).reverse(),
    categoryWeights: state.weights?.category || {
      'space and astronomy': 1.4,
      'weird science': 1.3,
      'the human body': 1.2,
      'technology and the internet': 1.1,
      'ancient history': 1.0,
      'nature and weather': 0.9,
    },
    styleWeights: state.weights?.style || {
      fact: 1.35,
      how: 1.25,
      story: 1.15,
      myth: 1.1,
      top3: 0.95,
      whatif: 1.05,
    },
    recentCategories: state.recent_categories || [],
    lastStyle: state.last_style || 'fact',
  });
});

app.put('/api/memory', (req, res) => {
  const { categoryWeights, styleWeights } = req.body;
  const state = getState();
  state.weights = {
    ...state.weights,
    category: categoryWeights || state.weights?.category || {},
    style: styleWeights || state.weights?.style || {},
  };
  saveState(state);
  addLog('agent', 'MEMORY_UPDATE', 'Operator calibrated category and style strategic weights.');
  res.json({ success: true, memory: state.weights });
});

// 10. System Configuration
app.get('/api/config', (req, res) => {
  res.json({
    categories: [
      'space and astronomy',
      'ocean and sea creatures',
      'the human body',
      'animal behavior',
      'ancient history',
      'psychology and human behavior',
      'weird science',
      'famous inventions',
      'geography and strange places',
      'food science',
      'money and personal finance habits',
      'technology and the internet',
      'unsolved mysteries',
      'nature and weather',
      'dinosaurs and prehistoric life',
    ],
    ttsVoice: process.env.TTS_VOICE || 'en-US-GuyNeural',
    voicesAvailable: [
      { id: 'en-US-GuyNeural', name: 'Guy (US English - Confident, Engaging)' },
      { id: 'en-US-JennyNeural', name: 'Jenny (US English - Clear, Expressive)' },
      { id: 'en-GB-RyanNeural', name: 'Ryan (British English - Documentary)' },
      { id: 'en-AU-WilliamNeural', name: 'William (Australian English - Natural)' },
      { id: 'en-IN-PrabhatNeural', name: 'Prabhat (Indian English - Clear, Articulate)' },
    ],
    videoDuration: process.env.VIDEO_SECONDS || '40-60',
    longDuration: process.env.LONG_SECONDS || '300-420',
    keys: {
      gemini: Boolean(process.env.GEMINI_API_KEY),
      groq: Boolean(process.env.GROQ_API_KEY),
      pixabay: Boolean(process.env.PIXABAY_API_KEY),
      pexels: Boolean(process.env.PEXELS_API_KEY),
      youtube: Boolean(process.env.YT_CLIENT_ID && process.env.YT_REFRESH_TOKEN),
      instagram: Boolean(process.env.IG_ACCESS_TOKEN),
      cloudinary: Boolean(process.env.CLOUDINARY_CLOUD_NAME),
    },
  });
});

// 11. Streaming Media Server (supports HTTP 206 for video player)
app.get('/api/media/*', (req, res) => {
  const relativePath = (req.params as Record<string, any>)[0] || req.url.replace('/api/media/', '');
  const safePath = path.normalize(relativePath).replace(/^(\.\.[\/\\])+/, '');
  const filePath = path.join(SCRIPT_DIR, safePath);

  if (!fs.existsSync(filePath)) {
    return res.status(404).send('Media file not found');
  }

  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const range = req.headers.range;

  const ext = path.extname(filePath).toLowerCase();
  const contentType =
    ext === '.mp4'
      ? 'video/mp4'
      : ext === '.jpg' || ext === '.jpeg'
      ? 'image/jpeg'
      : ext === '.png'
      ? 'image/png'
      : ext === '.mp3'
      ? 'audio/mpeg'
      : 'application/octet-stream';

  if (range && contentType.startsWith('video/')) {
    const parts = range.replace(/bytes=/, '').split('-');
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunksize = end - start + 1;
    const file = fs.createReadStream(filePath, { start, end });
    const head = {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': chunksize,
      'Content-Type': contentType,
    };
    res.writeHead(206, head);
    file.pipe(res);
  } else {
    const head = {
      'Content-Length': fileSize,
      'Content-Type': contentType,
    };
    res.writeHead(200, head);
    fs.createReadStream(filePath).pipe(res);
  }
});

// 12. Project ZIP download endpoint for manual GitHub synchronization
app.get('/api/download/project', (req, res) => {
  const zipPath = path.join(__dirname, 'raptar_v2_upgraded.zip');
  if (fs.existsSync(zipPath)) {
    res.download(zipPath, 'raptar_v2_upgraded.zip');
  } else {
    res.status(404).send('Archive not found');
  }
});

// -------------------------------------------------------------
// -------------------------------------------------------------
// Autonomous Background Scheduler
// -------------------------------------------------------------
setInterval(() => {
  if (agentState.isPaused || isRunningPipeline) return;
  const now = Date.now();
  const nextTarget = new Date(agentState.dailyProduction.nextRun || '').getTime();
  if (nextTarget && now >= nextTarget) {
    addLog('agent', 'SCHEDULER', 'Autonomous daily production window reached. Initiating scheduled workflow.');
    agentState.dailyProduction.nextRun = new Date(now + 24 * 3600 * 1000).toISOString();
    runAutonomousPipeline(undefined, 'short').catch((err) => {
      addLog('error', 'SCHEDULE_ERROR', err.message);
    });
  }
}, 60000);

// -------------------------------------------------------------
// Dev & Production Serving
// -------------------------------------------------------------
async function startServer() {
  const isProd = process.env.NODE_ENV === 'production';

  if (!isProd) {
    const vite = await createViteServer({
      server: { middlewareMode: true, hmr: process.env.DISABLE_HMR !== 'true' },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`RAPTAR Autonomous Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
});
