import { useState } from 'react';
import type { ClipResult } from '../api/searchApi';
import { youtubeEmbedUrl, youtubeId, youtubeThumbnail } from '../utils/youtube';
import '../styles/ClipCard.css';

interface ClipCardProps {
  clip: ClipResult;
  index: number;
}

const genreColors: Record<string, string> = {
  action: '#ef4444',
  adventure: '#f97316',
  animation: '#22c55e',
  comedy: '#f59e0b',
  crime: '#64748b',
  drama: '#8b5cf6',
  family: '#14b8a6',
  horror: '#7f1d1d',
  musical: '#d946ef',
  romance: '#ec4899',
  scifi: '#06b6d4',
  thriller: '#334155',
  war: '#78716c',
  default: '#6b7280',
};

function genreColor(genre: string): string {
  return genreColors[genre.toLowerCase()] || genreColors.default;
}

function formatDuration(seconds?: number | null): string | null {
  if (!seconds || seconds <= 0) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function pct(value?: number | null): string {
  return value == null ? 'N/A' : `${(Math.max(0, Math.min(1, value)) * 100).toFixed(0)}%`;
}

export function ClipCard({ clip, index }: ClipCardProps) {
  const [playing, setPlaying] = useState(false);
  const color = genreColor(clip.genre);
  const duration = formatDuration(clip.duration_seconds);
  const ytId = youtubeId(clip.video_url);
  const thumbnail = clip.thumbnail_url || (ytId ? youtubeThumbnail(ytId) : null);
  const playable = Boolean(clip.video_url);

  const renderPlayer = () => {
    if (ytId) {
      return (
        <iframe
          className="clip-video"
          src={youtubeEmbedUrl(ytId)}
          title={`${clip.title} - ${clip.movie}`}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          referrerPolicy="strict-origin-when-cross-origin"
          allowFullScreen
        />
      );
    }
    return (
      <video
        className="clip-video"
        src={clip.video_url ?? undefined}
        poster={thumbnail ?? undefined}
        controls
        autoPlay
        playsInline
        preload="metadata"
      />
    );
  };

  return (
    <article
      className="clip-card"
      style={{ animationDelay: `${index * 0.07}s`, '--genre-color': color } as React.CSSProperties}
    >
      <div className="clip-media" style={{ background: `linear-gradient(135deg, ${color}cc, ${color}66)` }}>
        {playable && playing ? (
          renderPlayer()
        ) : (
          <button
            className="clip-poster"
            onClick={() => playable && setPlaying(true)}
            disabled={!playable}
            title={playable ? 'Play clip' : 'No video attached to this clip'}
            style={thumbnail ? { backgroundImage: `url(${thumbnail})` } : undefined}
          >
            <span className="play-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            </span>
            {!thumbnail && <span className="clip-initial">{clip.movie.charAt(0)}</span>}
          </button>
        )}
        <span className="clip-rank">#{clip.rank}</span>
        {!playing && duration && <span className="clip-duration">{duration}</span>}
        {ytId && !playing && <span className="clip-source">YouTube</span>}
      </div>

      <div className="clip-content">
        <h3 className="clip-title">{clip.title}</h3>
        <p className="clip-movie">
          {clip.movie}
          {clip.year ? ` (${clip.year})` : ''}
          {clip.director ? ` · ${clip.director}` : ''}
        </p>
        <span className="clip-genre" style={{ backgroundColor: color }}>
          {clip.genre}
        </span>
        <p className="clip-description">{clip.description}</p>

        <div className="score-breakdown">
          <div className="score-row">
            <span>Hybrid score</span>
            <strong>{clip.hybrid_score?.toFixed(4) ?? 'N/A'}</strong>
          </div>
          <div className="score-row">
            <span>Vector similarity</span>
            <strong>{pct(clip.vector_similarity)}</strong>
          </div>
          <div className="score-row">
            <span>BM25 text score</span>
            <strong>{clip.text_score?.toFixed(2) ?? 'N/A'}</strong>
          </div>
        </div>
      </div>
    </article>
  );
}
