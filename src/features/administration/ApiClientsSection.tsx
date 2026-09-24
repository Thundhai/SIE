import { useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { Modal } from '../../components/ui/Modal';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ApiError } from '../../services/api/errors';
import {
  listApiClients,
  revokeApiClient,
  rotateApiClientSecret,
  type ApiClient,
  type ApiClientCreated,
} from '../../services/api/administration';
import type { AsyncState } from '../../types/common';
import { apiClientStatusTone } from './administrationLabels';
import { CreateApiClientDrawer } from './CreateApiClientDrawer';

export interface ApiClientsSectionProps {
  organizationId: string;
}

function formatTimestamp(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/**
 * API Clients. The backend hands back a raw secret only from create and
 * rotate — never from list — so `revealedSecret` is the *only* place a
 * secret is ever held in this section, it is cleared the moment the
 * reveal panel is dismissed, and it is never derived from `clients`
 * (the list state never carries a secret to begin with).
 */
export function ApiClientsSection({ organizationId }: ApiClientsSectionProps) {
  const [clientsState, setClientsState] = useState<AsyncState<ApiClient[]>>({ status: 'loading' });
  const [refreshToken, setRefreshToken] = useState(0);

  const [createOpen, setCreateOpen] = useState(false);
  const [revealedSecret, setRevealedSecret] = useState<ApiClientCreated | null>(null);

  const [rotatingClient, setRotatingClient] = useState<ApiClient | null>(null);
  const [rotating, setRotating] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);

  const [revokingClient, setRevokingClient] = useState<ApiClient | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setClientsState({ status: 'loading' });
    listApiClients(organizationId, controller.signal)
      .then((clients) => setClientsState({ status: 'success', data: clients }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 403) {
          setClientsState({ status: 'error', message: "You don't have permission to view API clients in this organization." });
        } else {
          setClientsState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load API clients.' });
        }
      });
    return () => controller.abort();
  }, [organizationId, refreshToken]);

  async function handleRotate() {
    if (!rotatingClient) return;
    setRotating(true);
    setRotateError(null);
    try {
      const rotated = await rotateApiClientSecret(organizationId, rotatingClient.id);
      setRotatingClient(null);
      setRefreshToken((token) => token + 1);
      setRevealedSecret(rotated);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setRotateError("You don't have permission to rotate this API client's secret.");
      } else {
        setRotateError(error instanceof Error ? error.message : 'Could not rotate this secret.');
      }
    } finally {
      setRotating(false);
    }
  }

  async function handleRevoke() {
    if (!revokingClient) return;
    setRevoking(true);
    setRevokeError(null);
    try {
      await revokeApiClient(organizationId, revokingClient.id);
      setRevokingClient(null);
      setRefreshToken((token) => token + 1);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setRevokeError("You don't have permission to revoke this API client.");
      } else {
        setRevokeError(error instanceof Error ? error.message : 'Could not revoke this API client.');
      }
    } finally {
      setRevoking(false);
    }
  }

  return (
    <>
      <Section
        title="API clients"
        description="Machine credentials for programmatic access to this organization's SIE data."
        action={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            Create API client
          </Button>
        }
      >
        {clientsState.status === 'loading' && <LoadingState label="Loading API clients…" />}
        {clientsState.status === 'error' && <ErrorState description={clientsState.message} />}
        {clientsState.status === 'success' && clientsState.data.length === 0 && (
          <EmptyState title="No API clients yet" description="Create a credential to let another system authenticate against this organization's data." />
        )}
        {clientsState.status === 'success' && clientsState.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Client ID</th>
                  <th className="px-3 py-2">Secret prefix</th>
                  <th className="px-3 py-2">Scopes</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Last used</th>
                  <th className="px-3 py-2">Expires</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {clientsState.data.map((client) => (
                  <tr key={client.id} className="border-b border-border align-top">
                    <td className="px-3 py-3 font-medium text-text-primary">{client.name}</td>
                    <td className="px-3 py-3 font-mono text-xs text-text-secondary">{client.client_id}</td>
                    <td className="px-3 py-3 font-mono text-xs text-text-secondary">{client.secret_prefix}…</td>
                    <td className="px-3 py-3 text-xs text-text-secondary">{client.scopes.join(', ')}</td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={apiClientStatusTone(client.status)} label={client.status} />
                    </td>
                    <td className="px-3 py-3 text-text-secondary">{formatTimestamp(client.created_at)}</td>
                    <td className="px-3 py-3 text-text-secondary">{formatTimestamp(client.last_used_at)}</td>
                    <td className="px-3 py-3 text-text-secondary">{formatTimestamp(client.expires_at)}</td>
                    <td className="px-3 py-3">
                      <div className="flex justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={() => setRotatingClient(client)} disabled={client.status === 'REVOKED'}>
                          Rotate
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRevokingClient(client)} disabled={client.status === 'REVOKED'}>
                          Revoke
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <CreateApiClientDrawer
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        organizationId={organizationId}
        onCreated={(client) => {
          setRefreshToken((token) => token + 1);
          setRevealedSecret(client);
        }}
      />

      <Modal
        isOpen={rotatingClient !== null}
        onClose={() => {
          if (rotating) return;
          setRotatingClient(null);
          setRotateError(null);
        }}
        title="Rotate API client secret"
      >
        {rotatingClient && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">
              Rotating <span className="font-medium text-text-primary">{rotatingClient.name}</span> issues a new secret
              and immediately invalidates the previous one. Any system using the old secret will stop authenticating.
            </p>
            {rotateError && (
              <p role="alert" className="text-sm text-critical">
                {rotateError}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setRotatingClient(null)} disabled={rotating}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleRotate} disabled={rotating}>
                {rotating ? 'Rotating…' : 'Rotate secret'}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={revokingClient !== null}
        onClose={() => {
          if (revoking) return;
          setRevokingClient(null);
          setRevokeError(null);
        }}
        title="Revoke API client"
      >
        {revokingClient && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">
              Revoking <span className="font-medium text-text-primary">{revokingClient.name}</span> immediately and
              permanently disables this credential. This cannot be undone.
            </p>
            {revokeError && (
              <p role="alert" className="text-sm text-critical">
                {revokeError}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setRevokingClient(null)} disabled={revoking}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleRevoke} disabled={revoking}>
                {revoking ? 'Revoking…' : 'Revoke client'}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal isOpen={revealedSecret !== null} onClose={() => setRevealedSecret(null)} title="API client secret">
        {revealedSecret && (
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium text-warning">
              This secret is shown once and cannot be retrieved again. Copy it now and store it securely.
            </p>
            <div className="rounded-md border border-border-strong bg-surface-muted p-3">
              <p className="text-xs text-text-muted">Client ID</p>
              <p className="mb-2 break-all font-mono text-sm text-text-primary">{revealedSecret.client_id}</p>
              <p className="text-xs text-text-muted">Secret</p>
              <p className="break-all font-mono text-sm text-text-primary">{revealedSecret.secret}</p>
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => setRevealedSecret(null)}
              >
                I've stored this secret
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
