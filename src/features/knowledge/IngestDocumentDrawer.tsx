import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { ApiError } from '../../services/api/errors';
import { ingestDocument, type IngestionResult, type KnowledgeSource } from '../../services/api/knowledge';
import { extractionStatusLabel, extractionStatusTone } from './knowledgeLabels';
import { StatusBadge } from '../../components/ui/StatusBadge';

export interface IngestDocumentDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  /** Combined organization + global sources this caller can see —
   * ingestion targets one of them, chosen explicitly, never inferred. */
  sources: KnowledgeSource[];
  onIngested: (result: IngestionResult) => void;
}

const SUPPORTED_TYPES_HELP =
  'Supported: PDF, DOCX, XLSX, PPTX, TXT, RTF, CSV, JSON, XML, HTML, PNG, JPEG, TIFF. Up to 25 MB (server-enforced).';

/**
 * "Upload document" — `POST /knowledge/ingestion`, the one controlled
 * entry point for adding content to the knowledge base
 * (`backend/app/api/v1/ingestion.py`). Creates a new document (requires a
 * title) unless an existing document id is supplied, in which case the
 * upload becomes a new version of that document instead — mirrors
 * `IngestionService._resolve_document`'s own validation.
 */
export function IngestDocumentDrawer({ isOpen, onClose, organizationId, sources, onIngested }: IngestDocumentDrawerProps) {
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [documentType, setDocumentType] = useState('');
  const [existingDocumentId, setExistingDocumentId] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<IngestionResult | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setSourceId('');
    setFile(null);
    setTitle('');
    setDocumentType('');
    setExistingDocumentId('');
    setValidationError(null);
    setSubmitError(null);
    setResult(null);
  }, [isOpen]);

  const selectedSource = sources.find((source) => source.id === sourceId) ?? null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!sourceId) {
      setValidationError('Choose a knowledge source.');
      return;
    }
    if (!file) {
      setValidationError('Choose a file to upload.');
      return;
    }
    if (!existingDocumentId.trim() && !title.trim()) {
      setValidationError('Title is required when creating a new document (or supply an existing document id to add a version instead).');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const outcome = await ingestDocument({
        file,
        sourceId,
        organizationId: selectedSource?.scope_type === 'ORGANIZATION' ? organizationId : undefined,
        documentId: existingDocumentId.trim() || undefined,
        title: title.trim() || undefined,
        documentType: documentType.trim() || undefined,
      });
      setResult(outcome);
      onIngested(outcome);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError("You don't have permission to add knowledge to this source. Ask an administrator for knowledge:manage access.");
      } else if (error instanceof ApiError && error.status === 415) {
        setSubmitError(error.message);
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not upload this document.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Upload document">
      {result ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <StatusBadge tone={extractionStatusTone(result.extraction_status)} label={`Extraction: ${extractionStatusLabel(result.extraction_status)}`} />
          </div>
          <p className="text-sm text-text-secondary">
            {result.chunk_count} chunk{result.chunk_count === 1 ? '' : 's'} produced from {(result.file_size / 1024).toFixed(1)} KB
            ({result.detected_media_type}).
          </p>
          {result.warnings.length > 0 && (
            <div className="rounded-md border border-warning bg-warning-surface p-3">
              <p className="text-xs font-medium text-warning">Warnings</p>
              <ul className="mt-1 list-disc pl-4 text-xs text-text-secondary">
                {result.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-text-muted">
            Document id: <span className="font-mono">{result.document_id ?? '—'}</span>
            {result.version_id && (
              <>
                {' · '}Version id: <span className="font-mono">{result.version_id}</span>
              </>
            )}
          </p>
          <div className="flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
          <Select
            label="Knowledge source"
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            options={[
              { value: '', label: 'Choose a source' },
              ...sources.map((source) => ({
                value: source.id,
                label: `${source.name} (${source.scope_type === 'GLOBAL' ? 'Global' : 'Organization'})`,
              })),
            ]}
          />

          <div className="flex flex-col gap-1">
            <label htmlFor="knowledge-upload-file" className="text-xs font-medium text-text-secondary">
              File
            </label>
            <input
              id="knowledge-upload-file"
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text-primary file:mr-3 file:rounded file:border-0 file:bg-surface-muted file:px-2 file:py-1 file:text-xs file:font-medium"
            />
            <p className="text-xs text-text-muted">{SUPPORTED_TYPES_HELP}</p>
          </div>

          <Input label="Title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} helperText="Required for a new document. Leave blank if adding a version to an existing document below." />
          <Input label="Document type" value={documentType} onChange={(event) => setDocumentType(event.target.value)} maxLength={100} helperText="Optional — inferred from the file type if left blank." />
          <Input
            label="Existing document id"
            value={existingDocumentId}
            onChange={(event) => setExistingDocumentId(event.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            helperText="Optional advanced field — adds this upload as a new version of an existing document instead of creating one. Must belong to the chosen source."
          />

          {validationError && (
            <p role="alert" className="text-sm text-critical">
              {validationError}
            </p>
          )}
          {submitError && (
            <p role="alert" className="text-sm text-critical">
              {submitError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Uploading…' : 'Upload'}
            </Button>
          </div>
        </form>
      )}
    </Drawer>
  );
}
