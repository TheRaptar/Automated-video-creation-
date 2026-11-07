import React, { useState } from 'react';
import {
  Film,
  Play,
  Clock,
  Sparkles,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  Eye,
  Filter,
  Plus,
} from 'lucide-react';
import { VideoItem } from '../types';

interface VideoStudioTabProps {
  videos: VideoItem[];
  onSelectVideo: (v: VideoItem) => void;
  onOpenGenerateModal: () => void;
  onApprove: (id: string) => void;
}

export const VideoStudioTab: React.FC<VideoStudioTabProps> = ({
  videos,
  onSelectVideo,
  onOpenGenerateModal,
  onApprove,
}) => {
  const [filterFormat, setFilterFormat] = useState<string>('all');

  const filtered = videos.filter((v) => {
    if (filterFormat === 'all') return true;
    return v.format === filterFormat;
  });

  return (
    <div className="space-y-6">
      {/* Studio Header & Filter Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Film className="w-4 h-4 text-indigo-400" />
            AI Video Production Studio &amp; Archive
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Rendered high-definition MP4s, timed subtitles, scene layouts, and publishing packages.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Format Filter */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 text-xs">
            {['all', 'short', 'story', 'long'].map((fmt) => (
              <button
                key={fmt}
                onClick={() => setFilterFormat(fmt)}
                className={`px-2.5 py-1 rounded font-medium capitalize transition-colors ${
                  filterFormat === fmt
                    ? 'bg-zinc-800 text-white'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {fmt === 'all' ? 'All Formats' : fmt}
              </button>
            ))}
          </div>

          <button
            onClick={onOpenGenerateModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Generate Video</span>
          </button>
        </div>
      </div>

      {/* Videos Grid */}
      {filtered.length === 0 ? (
        <div className="text-center py-16 bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-8">
          <Film className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-zinc-300">No Videos in this Category</h3>
          <p className="text-xs text-zinc-500 max-w-sm mx-auto mt-1 mb-4">
            Trigger the autonomous agent or generate a video on-demand to see it rendered here.
          </p>
          <button
            onClick={onOpenGenerateModal}
            className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-500 transition-colors"
          >
            Create First Video
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((vid) => (
            <div
              key={vid.id}
              className="bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800/80 hover:border-zinc-700 rounded-2xl overflow-hidden transition-all duration-200 flex flex-col justify-between group shadow-lg"
            >
              {/* Media Preview Box */}
              <div
                onClick={() => onSelectVideo(vid)}
                className="relative bg-black aspect-[9/14] overflow-hidden cursor-pointer group"
              >
                {vid.thumbnailUrl ? (
                  <img
                    src={vid.thumbnailUrl}
                    alt={vid.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-indigo-950 via-zinc-900 to-black p-4 text-center">
                    <Film className="w-8 h-8 text-indigo-400 mb-2 opacity-60" />
                    <p className="text-xs text-zinc-400 font-mono line-clamp-2">{vid.topic}</p>
                  </div>
                )}

                {/* Overlay Play Icon */}
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <div className="h-12 w-12 rounded-full bg-indigo-600/90 text-white flex items-center justify-center shadow-xl">
                    <Play className="w-5 h-5 fill-white ml-0.5" />
                  </div>
                </div>

                {/* Format & Live Badges */}
                <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5">
                  <span className="text-[10px] font-mono uppercase font-bold px-2 py-0.5 rounded bg-black/80 text-white border border-zinc-700/60 backdrop-blur-sm">
                    {vid.format}
                  </span>
                  {vid.isCurrent && (
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-600 text-white shadow-sm">
                      LATEST
                    </span>
                  )}
                </div>

                {/* Status Indicator */}
                <div className="absolute bottom-2.5 right-2.5">
                  {vid.status === 'ready_for_review' ? (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/90 text-cyan-300 border border-cyan-700/60 backdrop-blur-sm flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      REVIEW
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-700/60 backdrop-blur-sm flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      READY
                    </span>
                  )}
                </div>
              </div>

              {/* Card Body */}
              <div className="p-4 flex flex-col justify-between flex-1">
                <div>
                  <h3
                    onClick={() => onSelectVideo(vid)}
                    className="text-sm font-bold text-white line-clamp-2 hover:text-indigo-400 cursor-pointer transition-colors leading-snug"
                  >
                    {vid.title}
                  </h3>
                  <p className="text-xs text-zinc-400 line-clamp-1 mt-1 font-mono">
                    {vid.category}
                  </p>
                </div>

                {/* Card Actions */}
                <div className="pt-3 mt-3 border-t border-zinc-800/80 flex items-center justify-between gap-2">
                  <button
                    onClick={() => onSelectVideo(vid)}
                    className="flex items-center gap-1 text-xs text-zinc-300 hover:text-white transition-colors py-1"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>Inspect</span>
                  </button>

                  <button
                    onClick={() => onApprove(vid.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-medium transition-all"
                    title="Publish to YouTube and Instagram"
                  >
                    <UploadCloud className="w-3.5 h-3.5" />
                    <span>Publish</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
