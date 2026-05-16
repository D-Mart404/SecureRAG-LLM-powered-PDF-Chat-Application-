import React, { useState, useRef } from 'react';
import { uploadDocument, getApiMessage } from '../utils/api';
import toast from 'react-hot-toast';

interface SourcesPanelProps {
  files: File[];
  activeIndex?: number;
  onAddFiles?: (files: File[]) => void;
  onSelectFile?: (index: number) => void;
  mobileOpen?: boolean;
  onClose?: () => void;
}

export const SourcesPanel: React.FC<SourcesPanelProps> = ({
  files,
  activeIndex = 0,
  onAddFiles,
  onSelectFile,
  mobileOpen = false,
  onClose,
}) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  
  // NEW: State for tracking the upload process
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const openFilePicker = () => {
    if (!uploading) {
      inputRef.current?.click();
    }
  };

  // FIX: Properly upload the file to the backend before updating the UI state
  const handleFilesPicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.currentTarget.value = ''; // Reset input to allow selecting same file again
    
    if (picked.length === 0) return;

    setUploading(true);
    setProgress(0);
    const successfulFiles: File[] = [];

    // Process files sequentially to prevent overwhelming the backend memory
    for (const file of picked) {
      try {
        await uploadDocument(file, (percent) => setProgress(percent));
        successfulFiles.push(file);
        toast.success(`${file.name} successfully indexed.`);
      } catch (error) {
        toast.error(getApiMessage(error, `Failed to process ${file.name}`));
      }
    }

    setUploading(false);
    setProgress(0);

    // Only update the main App state if the upload actually succeeded
    if (successfulFiles.length > 0) {
      onAddFiles?.(successfulFiles);
    }
  };

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/40 transition-opacity sm:hidden ${mobileOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
        onClick={() => onClose?.()}
        aria-hidden={!mobileOpen}
      />
      <aside
        className={`rag-panel flex h-full w-[19rem] shrink-0 flex-col overflow-hidden border-r border-border/70 px-4 py-4 bg-paper fixed top-0 left-0 z-50 transform transition-transform sm:static sm:translate-x-0 sm:w-[19rem] ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        role="dialog"
        aria-modal={mobileOpen}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0 text-base font-semibold text-ink">Sources</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={openFilePicker}
              disabled={uploading}
              className="text-sm font-medium text-accent transition-colors hover:text-accent-strong disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? 'Uploading...' : 'Add'}
            </button>
            <button
              type="button"
              onClick={() => onClose?.()}
              className="sm:hidden rounded-md bg-transparent p-2 text-sm text-ink-muted hover:text-ink"
              aria-label="Close sources panel"
            >
              {/* Added a missing close icon for mobile views */}
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            multiple
            onChange={handleFilesPicked}
            className="hidden"
          />
        </div>

        {/* NEW: Upload Progress UI */}
        {uploading && (
          <div className="mb-4 rounded-xl border border-border bg-paper-soft p-3 shadow-sm">
            <div className="mb-2 flex items-center justify-between text-xs text-ink-muted">
              <span className="font-semibold text-ink truncate mr-2">Processing Document...</span>
              <span className="font-mono">{progress}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-border overflow-hidden">
              <div
                className="h-full rounded-full bg-accent transition-all duration-200 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {files.length === 0 && !uploading && (
          <div className="rounded-xl border border-dashed border-border bg-paper px-4 py-3 text-sm text-ink-muted">
            No sources yet. Upload a PDF to begin.
          </div>
        )}

        <ul className="m-0 flex list-none flex-col gap-2 p-0 overflow-y-auto scrollbar-thin">
          {files.map((f, idx) => (
            <li
              key={idx}
              onClick={() => {
                onSelectFile?.(idx)
                if (mobileOpen) {
                  onClose?.()
                }
              }}
              className={`flex cursor-pointer items-center gap-3 rounded-xl border bg-paper px-3 py-3 shadow-sm transition-colors ${
                idx === activeIndex ? 'border-accent/70' : 'border-border hover:border-accent/40'
              }`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M6 2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-ink" title={f.name}>{f.name}</div>
                <div className="text-xs text-ink-muted">Ready</div>
              </div>
              <div className="shrink-0">
                <input
                  type="checkbox"
                  checked={idx === activeIndex}
                  readOnly
                  className="h-4 w-4 rounded border-border text-accent focus:ring-accent"
                />
              </div>
            </li>
          ))}
        </ul>
      </aside>
    </>
  );
};