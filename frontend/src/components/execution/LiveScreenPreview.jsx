import React, { useState } from 'react';
import {
  Monitor,
  Tablet,
  Smartphone,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
} from 'lucide-react';

export default function LiveScreenPreview({ previewData, isPreviewLoading, onRefresh }) {
  const [device, setDevice] = useState('desktop');
  const [version, setVersion] = useState('after');

  if (isPreviewLoading) {
    return (
      <div className="py-20 text-center space-y-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
        <RefreshCw className="w-7 h-7 animate-spin text-[#CCFF00] mx-auto" />
        <p className="text-xs text-zinc-300 font-medium">Reconstructing live screen preview from repository snapshot...</p>
        <p className="text-[11px] text-zinc-500">Inlining patched CSS and styles in real-time</p>
      </div>
    );
  }

  if (!previewData?.has_preview) {
    return (
      <div className="p-8 text-center space-y-3 bg-zinc-950/60 rounded-xl border border-zinc-800/80">
        <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto text-zinc-500">
          <Monitor className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h5 className="text-xs font-semibold text-zinc-200">Live Screen Preview Not Available</h5>
          <p className="text-[11px] text-zinc-500 max-w-md mx-auto">
            {previewData?.reason ||
              'Live screen preview is designed for web applications with HTML entrypoints (e.g. index.html). You can review all code changes in the Diff View tab.'}
          </p>
        </div>
      </div>
    );
  }

  const currentHtml = version === 'after' ? previewData.html_after : previewData.html_before;

  const deviceWidthClass =
    device === 'mobile'
      ? 'max-w-[380px]'
      : device === 'tablet'
      ? 'max-w-[768px]'
      : 'w-full';

  const openInNewTab = () => {
    if (!currentHtml) return;
    const blob = new Blob([currentHtml], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  return (
    <div className="space-y-3">
      {/* Top Controls Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-xl bg-zinc-900/90 border border-zinc-800 text-xs shadow-md">
        {/* Device Switcher */}
        <div className="flex items-center space-x-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
          <button
            type="button"
            onClick={() => setDevice('desktop')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-[11px] transition font-medium ${
              device === 'desktop'
                ? 'bg-zinc-800 text-[#CCFF00] shadow-sm'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            <Monitor className="w-3.5 h-3.5" />
            <span>Desktop</span>
          </button>
          <button
            type="button"
            onClick={() => setDevice('tablet')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-[11px] transition font-medium ${
              device === 'tablet'
                ? 'bg-zinc-800 text-[#CCFF00] shadow-sm'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            <Tablet className="w-3.5 h-3.5" />
            <span>Tablet (768px)</span>
          </button>
          <button
            type="button"
            onClick={() => setDevice('mobile')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-[11px] transition font-medium ${
              device === 'mobile'
                ? 'bg-zinc-800 text-[#CCFF00] shadow-sm'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            <Smartphone className="w-3.5 h-3.5" />
            <span>Mobile (380px)</span>
          </button>
        </div>

        {/* Before / After Version Toggle */}
        <div className="flex items-center space-x-1.5 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
          <button
            type="button"
            onClick={() => setVersion('after')}
            className={`flex items-center space-x-1 px-3 py-1.5 rounded-md text-[11px] font-semibold transition ${
              version === 'after'
                ? 'bg-[#CCFF00] text-black shadow-sm'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Live Patched (After)</span>
          </button>
          <button
            type="button"
            onClick={() => setVersion('before')}
            className={`flex items-center space-x-1 px-3 py-1.5 rounded-md text-[11px] font-medium transition ${
              version === 'before'
                ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <span>Original Baseline (Before)</span>
          </button>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-1.5 ml-auto">
          <button
            type="button"
            onClick={onRefresh}
            className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition"
            title="Refresh preview frame"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={openInNewTab}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 text-[11px] text-zinc-200 hover:text-white bg-zinc-800 hover:bg-zinc-700/80 border border-zinc-700 rounded-md transition font-medium"
            title="Open in new browser window"
          >
            <ExternalLink className="w-3.5 h-3.5 text-[#CCFF00]" />
            <span>Open in Tab</span>
          </button>
        </div>
      </div>

      {/* Browser Shell Frame */}
      <div className={`transition-all duration-300 mx-auto ${deviceWidthClass}`}>
        <div className="rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl overflow-hidden">
          {/* Browser Chrome Header */}
          <div className="flex items-center space-x-2 px-3 py-2 bg-zinc-900/90 border-b border-zinc-800">
            <div className="flex space-x-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
            </div>
            <div className="flex-1 max-w-sm mx-auto bg-zinc-950 border border-zinc-800 rounded px-2.5 py-0.5 text-[10px] text-zinc-400 font-mono text-center truncate">
              mysde://live-screen/{previewData.entrypoint}
            </div>
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold ${
                version === 'after'
                  ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60'
                  : 'bg-zinc-800 text-zinc-400 border border-zinc-700'
              }`}
            >
              {version === 'after' ? 'LIVE PATCHED' : 'BASELINE'}
            </span>
          </div>

          {/* Sandboxed Live Screen iframe */}
          <iframe
            title="Live Screen Preview"
            srcDoc={currentHtml}
            sandbox="allow-scripts allow-same-origin"
            className="w-full h-[520px] bg-white border-none block"
          />
        </div>
      </div>
    </div>
  );
}
