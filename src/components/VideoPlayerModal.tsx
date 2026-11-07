import React, { useState } from 'react';
import {
  X,
  Play,
  UploadCloud,
  CheckCircle2,
  Copy,
  Hash,
  Share2,
  Tv,
  Instagram,
  FileText,
  Clock,
  Sparkles,
  Download,
} from 'lucide-react';
import { VideoItem } from '../types';

interface VideoPlayerModalProps {
  video: VideoItem;
  onClose: () => void;
  onApprove: (id: string) => void;
  isPublishing?: boolean;
}

export const VideoPlayerModal: React.FC<VideoPlayerModalProps> = ({
  video,
  onClose,
  onApprove,
  isPublishing = false,
}) => {
  const [copied, setCopied] = useState(false);

  const copyMetadata = () => {
    const text = `${video.title}\n\n${video.description}\n\n${video.hashtags.join(' ')}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes) return '0 MB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden my-8">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950/60">
          <div className="flex items-center gap-3">
            <span
              className={`text-[11px] font-mono font-bold px-2.5 py-1 rounded-md uppercase tracking-wider ${
                video.format === 'short'
                  ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                  : video.format === 'story'
                  ? 'bg-violet-500/10 text-violet-400 border border-violet-500/30'
                  : 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
              }`}
            >
              {video.format} format (
              {video.format === 'long' ? '16:9 Landscape' : '9:16 Portrait'})
            </span>
            <span className="text-xs font-mono text-zinc-400">
              Created: {new Date(video.createdAt).toLocaleTimeString()}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 p-6">
          {/* Video Player Column */}
          <div className="lg:col-span-5 flex flex-col items-center">
            <div
              className={`w-full bg-black rounded-xl overflow-hidden border border-zinc-800 relative shadow-inner flex items-center justify-center ${
                video.format === 'long' ? 'aspect-video' : 'aspect-[9/16] max-h-[520px]'
              }`}
            >
              <video
                src={video.videoUrl}
                controls
                autoPlay
                playsInline
                className="w-full h-full object-contain"
                poster={video.thumbnailUrl || undefined}
              />
            </div>
            <div className="w-full flex items-center justify-between mt-3 text-xs text-zinc-400 px-1 font-mono">
              <span>Size: {formatFileSize(video.sizeBytes)}</span>
              <a
                href={video.videoUrl}
                download={`${video.title || 'video'}.mp4`}
                className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Save MP4</span>
              </a>
            </div>
          </div>

          {/* Metadata & Actions Column */}
          <div className="lg:col-span-7 flex flex-col justify-between space-y-4">
            <div className="space-y-4">
              {/* Title & Topic */}
              <div>
                <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider block mb-1">
                  Video Title
                </span>
                <h3 className="text-lg font-bold text-white leading-snug">{video.title}</h3>
                <p className="text-xs text-zinc-400 mt-1 flex items-center gap-1.5">
                  <span className="text-zinc-500">Topic:</span>
                  <span className="text-indigo-300 font-medium">{video.topic}</span>
                </p>
              </div>

              {/* Category & Style Badges */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-2.5 py-1 rounded bg-zinc-800 text-zinc-300 font-medium">
                  {video.category}
                </span>
                <span className="px-2.5 py-1 rounded bg-indigo-950/60 border border-indigo-800/50 text-indigo-300 font-mono">
                  Style: {video.style.toUpperCase()}
                </span>
                <span className="px-2.5 py-1 rounded bg-zinc-800/80 text-zinc-400 font-mono">
                  Status: {video.status.toUpperCase()}
                </span>
              </div>

              {/* Description */}
              <div>
                <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider block mb-1.5">
                  Publishing Description
                </span>
                <div className="bg-zinc-950/80 border border-zinc-800 rounded-xl p-3 text-xs text-zinc-300 max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {video.description || 'No description provided.'}
                </div>
              </div>

              {/* Hashtags */}
              {video.hashtags && video.hashtags.length > 0 && (
                <div>
                  <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider block mb-1.5">
                    Tags &amp; SEO Keywords
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {video.hashtags.map((tag, idx) => (
                      <span
                        key={idx}
                        className="text-xs text-indigo-400 bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-800/40 font-mono"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Publishing & Control Actions */}
            <div className="pt-4 border-t border-zinc-800/80 flex flex-col sm:flex-row items-center justify-between gap-3">
              <button
                onClick={copyMetadata}
                className="w-full sm:w-auto flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium transition-colors"
              >
                {copied ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span>Copy Text &amp; Tags</span>
                  </>
                )}
              </button>

              <button
                onClick={() => onApprove(video.id)}
                disabled={isPublishing}
                className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition-all disabled:opacity-50"
              >
                <UploadCloud className="w-4 h-4" />
                <span>
                  {isPublishing
                    ? 'Publishing to YouTube & Instagram...'
                    : 'Approve & Publish to Social Channels'}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
