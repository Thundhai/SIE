import { type FormEvent, useEffect, useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { ApiError } from '../../services/api/errors';
import { createKnowledgeSource, type KnowledgeScope, type KnowledgeSource } from '../../services/api/knowledge';

export interface CreateKnowledgeSourceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  organizationId: string;
  onCreated: (source: KnowledgeSource) => void;
}

/**
 * "Create knowledge source" — `POST /knowledge/sources`. A source has no
 * verification-status control here: the backend accepts one at creation
 * but exposes no dedicated verify/review endpoint anywhere in this
 * milestone (`knowledge:verify` is a real permission with no route yet),
 * so every source is created PENDING, matching the schema's own default,
 * rather than implying a self-verification workflow that doesn't exist.
 */
export function CreateKnowledgeSourceDrawer({ isOpen, onClose, organizationId, onCreated }: CreateKnowledgeSourceDrawerProps) {
  const [scopeType, setScopeType] = useState<KnowledgeScope>('ORGANIZATION');
  const [publisher, setPublisher] = useState('');
  const [name, setName] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [industrySector, setIndustrySector] = useState('');
  const [authorityLevel, setAuthorityLevel] = useState('');
  const [externalReference, setExternalReference] = useState('');
  const [publicationDate, setPublicationDate] = useState('');
  const [reviewDate, setReviewDate] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setScopeType('ORGANIZATION');
    setPublisher('');
    setName('');
    setSourceType('');
    setJurisdiction('');
    setIndustrySector('');
    setAuthorityLevel('');
    setExternalReference('');
    setPublicationDate('');
    setReviewDate('');
    setValidationError(null);
    setSubmitError(null);
  }, [isOpen]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!publisher.trim() || !name.trim() || !sourceType.trim()) {
      setValidationError('Publisher, name, and source type are required.');
      return;
    }
    setValidationError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const source = await createKnowledgeSource({
        publisher: publisher.trim(),
        name: name.trim(),
        sourceType: sourceType.trim(),
        jurisdiction: jurisdiction.trim() || undefined,
        industrySector: industrySector.trim() || undefined,
        authorityLevel: authorityLevel.trim() || undefined,
        externalReference: externalReference.trim() || undefined,
        publicationDate: publicationDate || undefined,
        reviewDate: reviewDate || undefined,
        scopeType,
        organizationId: scopeType === 'ORGANIZATION' ? organizationId : undefined,
      });
      onCreated(source);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setSubmitError(
          scopeType === 'GLOBAL'
            ? 'Creating a global knowledge source requires platform-wide knowledge:manage access (human callers only).'
            : "You don't have permission to create knowledge sources in this organization. Ask an administrator for knowledge:manage access.",
        );
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Could not create this knowledge source.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Create knowledge source">
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <Select
          label="Scope"
          value={scopeType}
          onChange={(event) => setScopeType(event.target.value as KnowledgeScope)}
          options={[
            { value: 'ORGANIZATION', label: 'This organization' },
            { value: 'GLOBAL', label: 'Global (all organizations)' },
          ]}
        />
        <p className="-mt-2 text-xs text-text-muted">
          {scopeType === 'GLOBAL'
            ? 'Global sources are visible to every organization — requires platform-wide access.'
            : 'Visible only to this organization (plus global sources).'}
        </p>
        <Input label="Publisher" value={publisher} onChange={(event) => setPublisher(event.target.value)} maxLength={255} required />
        <Input label="Name" value={name} onChange={(event) => setName(event.target.value)} maxLength={255} required />
        <Input
          label="Source type"
          value={sourceType}
          onChange={(event) => setSourceType(event.target.value)}
          maxLength={100}
          required
          placeholder="e.g. Regulation, Standard, Internal procedure"
        />
        <Input label="Jurisdiction" value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} maxLength={100} helperText="Optional." />
        <Input label="Industry sector" value={industrySector} onChange={(event) => setIndustrySector(event.target.value)} maxLength={100} helperText="Optional." />
        <Input label="Authority level" value={authorityLevel} onChange={(event) => setAuthorityLevel(event.target.value)} maxLength={100} helperText="Optional." />
        <Input label="External reference" value={externalReference} onChange={(event) => setExternalReference(event.target.value)} helperText="Optional — e.g. a URL or citation." />
        <Input label="Publication date" type="date" value={publicationDate} onChange={(event) => setPublicationDate(event.target.value)} helperText="Optional." />
        <Input label="Review date" type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} helperText="Optional." />

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
            {submitting ? 'Creating…' : 'Create source'}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
