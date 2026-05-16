import React, { useState } from 'react';
import { getApiMessage, uploadDocument, api } from '../utils/api';

interface UploadSectionProps {
  onUploadComplete: (file: File) => void;
}

type UploadStatus = 'idle' | 'uploading' | 'complete' | 'error';

export const UploadSection: React.FC<UploadSectionProps> = ({ onUploadComplete }) => {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [fileName, setFileName] = useState('');
  const [dragActive, setDragActive] = useState(false);

  const handleDrag = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();

    if (event.type === 'dragenter' || event.type === 'dragover') {
      setDragActive(true);
    } else if (event.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);

    const files = event.dataTransfer.files;
    if (files?.[0]) {
      handleFile(files[0]);
    }
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files?.[0]) {
      handleFile(files[0]);
    }
  };

  const handleFile = async (file: File) => {
    setFileName(file.name);
    setError('');
    setProgress(0);
    setStatus('uploading');

    try {
      await uploadDocument(file, (percent) => {
        setProgress(percent);
      });
      setProgress(100);
      setStatus('complete');
      onUploadComplete(file);
    } catch (uploadError) {
      setError(getApiMessage(uploadError, 'Unable to upload the CSV file.'));
      setStatus('error');
    }
  };

  const isProcessing = status === 'uploading';

  return (
    <div className="w-full max-w-6xl">
      <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <section className="space-y-6 text-left">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-paper-soft px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-ink-muted">
            Notebook-style RAG workspace
          </div>

          <div className="space-y-3">
            <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
              RAG Chat Assistant
            </h1>
            <p className="max-w-xl text-base leading-7 text-ink-muted sm:text-lg">
              Upload a CSV, track progress in real time, and ask grounded questions with citations.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['Upload', 'Drop in a CSV and start indexing instantly.'],
              ['Chunk', 'Split the text into retrieval-friendly parts.'],
              ['Ask', 'Get answers with references and context.'],
            ].map(([title, description]) => (
              <div key={title} className="rag-card rounded-2xl border border-border bg-paper-soft p-4">
                <div className="mb-2 text-sm font-semibold text-ink">{title}</div>
                <div className="text-sm leading-6 text-ink-muted">{description}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rag-card rounded-[2rem] border border-border bg-paper-soft p-5 text-center shadow-sm sm:p-6">
          <label
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-[1.5rem] border-2 border-dashed px-8 py-10 transition-all duration-300 ${dragActive ? 'border-accent bg-paper-muted shadow-sm' : 'border-border bg-paper hover:border-accent/70 hover:bg-paper-muted/70'}`}
          >
            <input type="file" accept=".pdf" onChange={handleChange} disabled={isProcessing} className="hidden" />
            <div className="pointer-events-none max-w-sm">
              <svg className="mx-auto mb-4 h-12 w-12 text-accent/80" fill="currentColor" viewBox="0 0 20 20">
                <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" />
              </svg>
              <p className="text-base font-medium text-ink">Drag and drop your PDF here</p>
              <p className="mt-2 text-sm text-ink-muted">or click to select</p>
            </div>
          </label>

          {status !== 'idle' && (
            <div className="mt-5 rounded-2xl border border-border bg-paper px-6 py-6 text-left">
              <h3 className="mb-5 text-sm font-semibold uppercase tracking-[0.18em] text-ink-muted">Upload status</h3>
              <div className="mb-4 text-sm font-semibold text-ink">{fileName}</div>

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </div>
              ) : (
                <div>
                  <div className="mb-3 flex items-center justify-between text-xs text-ink-muted">
                    <span>{status === 'complete' ? 'Upload complete' : 'Uploading PDF...'}</span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-border">
                    <div
                      className="h-2 rounded-full bg-accent transition-all duration-200"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <p className="mt-3 text-xs text-ink-muted">
                    {status === 'complete'
                      ? 'Upload finished. You can start chatting now.'
                      : 'Sending your PDF to SecureRAG...'}
                  </p>
                </div>
              )}

              {status === 'complete' && (
                <div className="mt-4 flex gap-3">
                  <button
                    type="button"
                    onClick={async () => {
                      const question = window.prompt('Enter a question to query the uploaded document:')
                      if (!question) return
                      try {
                        const resp = await api.post('/query', { question, chat_history: [] })
                        window.alert('Answer:\n' + (resp.data.answer ?? JSON.stringify(resp.data)))
                      } catch (e) {
                        window.alert(getApiMessage(e, 'Query failed'))
                      }
                    }}
                    className="rounded-2xl bg-[#FA8112] px-4 py-2 text-sm font-semibold text-white shadow hover:bg-[#e6750c]"
                  >
                    Run Query
                  </button>

                  <button
                    type="button"
                    onClick={async () => {
                      const focus = window.prompt('Optional: enter focus for summary (or leave blank)') ?? ''
                      try {
                        const resp = await api.post('/summarize', { focus })
                        window.alert('Summary:\n' + (resp.data.summary ?? JSON.stringify(resp.data)))
                      } catch (e) {
                        window.alert(getApiMessage(e, 'Summarize failed'))
                      }
                    }}
                    className="rounded-2xl bg-[#222222] px-4 py-2 text-sm font-semibold text-white shadow hover:bg-[#111111]"
                  >
                    Summarize Document
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
