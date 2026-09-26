import React, { useState, useEffect } from 'react';
import { Film, Download, Copy, Check, Loader2, Play, User } from 'lucide-react';
import { getApiUrl } from '../config';
import SegmentedControl from './ui/SegmentedControl';
import Modal from './ui/Modal';

export default function UGCGallery() {
  const [tab, setTab] = useState('videos');
  const [videos, setVideos] = useState([]);
  const [avatars, setAvatars] = useState([]);
  const [loadingVideos, setLoadingVideos] = useState(true);
  const [loadingAvatars, setLoadingAvatars] = useState(false);
  const [avatarsLoaded, setAvatarsLoaded] = useState(false);
  const [copied, setCopied] = useState('');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setLoadingVideos(true);
    fetch(getApiUrl('/api/saasshorts/gallery?limit=100'))
      .then((r) => (r.ok ? r.json() : { videos: [] }))
      .then((d) => setVideos(d.videos || []))
      .catch(() => {})
      .finally(() => setLoadingVideos(false));
  }, []);

  useEffect(() => {
    if (tab !== 'avatars' || avatarsLoaded) return;
    setLoadingAvatars(true);
    fetch(getApiUrl('/api/saasshorts/actor-gallery'))
      .then((r) => (r.ok ? r.json() : { images: [] }))
      .then((d) => setAvatars(d.images || []))
      .catch(() => {})
      .finally(() => {
        setLoadingAvatars(false);
        setAvatarsLoaded(true);
      });
  }, [tab, avatarsLoaded]);

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(''), 2000);
  };

  const loading = (tab === 'videos' && loadingVideos) || (tab === 'avatars' && loadingAvatars);

  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow mb-1">05 · UGC GALLERY</p>
        <h2 className="font-display lowercase text-2xl md:text-3xl text-ink">ugc gallery</h2>
        <p className="readout mt-2">
          {loadingVideos ? '…' : videos.length} videos
          {avatarsLoaded ? ` · ${avatars.length} avatars` : ''}
        </p>
      </div>

      <div className="max-w-xs w-full">
        <SegmentedControl
          size="sm"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'videos', label: `Videos (${loadingVideos ? '…' : videos.length})`, icon: <Film size={14} /> },
            { value: 'avatars', label: `Avatars (${avatarsLoaded ? avatars.length : '…'})`, icon: <User size={14} /> },
          ]}
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 size={24} className="animate-spin text-brass" />
          <span className="ml-2 text-muted lowercase">Loading gallery...</span>
        </div>
      ) : tab === 'videos' ? (
        videos.length === 0 ? (
          <div className="text-center py-16">
            <Film size={40} className="mx-auto text-muted opacity-40 mb-3" />
            <p className="text-sm text-muted lowercase">No videos yet. Generate one from AI Shorts.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
            {videos.map((video) => (
              <VideoCard
                key={video.video_id}
                video={video}
                copied={copied}
                onCopy={handleCopy}
                onOpen={() => setSelected(video)}
              />
            ))}
          </div>
        )
      ) : avatars.length === 0 ? (
        <div className="text-center py-16">
          <User size={40} className="mx-auto text-muted opacity-40 mb-3" />
          <p className="text-sm text-muted lowercase">No avatars yet. Generate actors from AI Shorts.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          {avatars.map((avatar, i) => (
            <AvatarCard key={avatar.key || i} avatar={avatar} copied={copied} onCopy={handleCopy} />
          ))}
        </div>
      )}

      {selected && (
        <Modal
          isOpen
          onClose={() => setSelected(null)}
          size="sm"
          eyebrow={selected.video_mode === 'lowcost' ? 'LOW COST' : 'PREMIUM'}
          title={selected.title || 'Untitled'}
        >
          <video
            src={selected.video_url}
            poster={selected.actor_url}
            controls
            autoPlay
            playsInline
            className="w-full rounded-input bg-black aspect-[9/16] object-contain max-h-[60vh]"
          />
          <p className="readout mt-3">
            {selected.duration?.toFixed(0)}s
            {selected.cost_estimate?.total != null ? ` · $${selected.cost_estimate.total.toFixed(2)}` : ''}
          </p>
          {selected.caption && (
            <p className="text-sm text-muted mt-2 leading-relaxed">{selected.caption}</p>
          )}
          <a
            href={selected.video_url}
            download
            className="btn-ghost w-full mt-4 justify-center text-sm"
          >
            <Download size={14} /> Download
          </a>
        </Modal>
      )}
    </div>
  );
}

function AvatarCard({ avatar, copied, onCopy }) {
  return (
    <div className="group card overflow-hidden transition-colors hover:border-rule2">
      <div className="aspect-[3/4] bg-black">
        <img src={avatar.url} alt="Avatar" loading="lazy" decoding="async" className="w-full h-full object-cover" />
      </div>
      <div className="p-2 space-y-1">
        {avatar.description ? (
          <div className="relative pr-4">
            <p className="text-micro text-muted line-clamp-2">{avatar.description}</p>
            <button
              type="button"
              onClick={() => onCopy(avatar.description, `avatar-${avatar.key}`)}
              className="absolute top-0 right-0 p-0.5 text-muted hover:text-brass transition-colors"
              title="Copy prompt"
            >
              {copied === `avatar-${avatar.key}` ? <Check size={10} className="text-ok" /> : <Copy size={10} />}
            </button>
          </div>
        ) : (
          <p className="text-micro text-muted opacity-60 lowercase">No description</p>
        )}
        <a
          href={avatar.url}
          download
          className="block text-center text-micro lowercase bg-paper3 hover:brightness-110 text-muted hover:text-ink2 py-1 rounded-full transition-all"
        >
          <Download size={10} className="inline mr-0.5" />Download
        </a>
      </div>
    </div>
  );
}

function VideoCard({ video, copied, onCopy, onOpen }) {
  const mode = video.video_mode;
  const caption = video.caption || '';
  const hashtags = (video.hashtags || []).join(' ');

  return (
    <div className="group card overflow-hidden transition-colors hover:border-rule2">
      <button
        type="button"
        onClick={onOpen}
        className="relative aspect-[9/16] w-full p-0 border-0 bg-black overflow-hidden cursor-pointer"
      >
        {video.actor_url ? (
          <img
            src={video.actor_url}
            alt=""
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-paper3" />
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors">
          <Play size={20} className="text-white/80" />
        </div>
        <div className="absolute top-1.5 right-1.5">
          <span className={`${mode === 'lowcost' ? 'badge-ok' : 'badge-brass'} bg-black/70`}>
            {mode === 'lowcost' ? 'LOW COST' : 'PREMIUM'}
          </span>
        </div>
      </button>

      <div className="p-2 space-y-1">
        <h3 className="text-xs font-semibold text-ink truncate">{video.title || 'Untitled'}</h3>
        <p className="readout">
          {video.duration?.toFixed(0)}s · ${video.cost_estimate?.total?.toFixed(2) || '?'}
        </p>
        {caption && (
          <div className="relative pr-4">
            <p className="text-micro text-muted line-clamp-2">{caption}</p>
            <button
              type="button"
              onClick={() => onCopy(`${caption}\n${hashtags}`, `caption-${video.video_id}`)}
              className="absolute top-0 right-0 p-0.5 text-muted hover:text-brass transition-colors"
              title="Copy caption"
            >
              {copied === `caption-${video.video_id}` ? <Check size={10} className="text-ok" /> : <Copy size={10} />}
            </button>
          </div>
        )}
        <a
          href={video.video_url}
          download
          className="block text-center text-micro lowercase bg-paper3 hover:brightness-110 text-muted hover:text-ink2 py-1 rounded-full transition-all"
        >
          <Download size={10} className="inline mr-0.5" />Download
        </a>
      </div>
    </div>
  );
}
