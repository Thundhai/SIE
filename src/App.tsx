import React, { useState, useEffect } from 'react';
import { 
  Header 
} from './components/Header';
import { 
  Sidebar 
} from './components/Sidebar';
import { 
  GlobalSearchModal 
} from './components/GlobalSearchModal';
import { 
  NotificationDrawer 
} from './components/NotificationDrawer';
import { 
  EvidenceDetailModal 
} from './components/EvidenceDetailModal';
import { 
  ToastContainer, 
  ToastNotification 
} from './components/Toast';

// Views
import { ExecutiveOverviewView } from './views/ExecutiveOverviewView';
import { IntelligenceCenterView } from './views/IntelligenceCenterView';
import { PredictionDetailView } from './views/PredictionDetailView';
import { KnowledgeCenterView } from './views/KnowledgeCenterView';
import { SourceVerificationView } from './views/SourceVerificationView';
import { OrganizationDataView } from './views/OrganizationDataView';
import { IntelligenceLearningView } from './views/IntelligenceLearningView';
import { InterventionCenterView } from './views/InterventionCenterView';
import { OutcomeLearningView } from './views/OutcomeLearningView';
import { AIAssistantView } from './views/AIAssistantView';
import { APIIntegrationsView } from './views/APIIntegrationsView';
import { CanonicalDataModelView } from './views/CanonicalDataModelView';
import { GovernanceView } from './views/GovernanceView';
import { SettingsView } from './views/SettingsView';

// Mock Data & Types
import { 
  INITIAL_EMERGING_RISKS, 
  KNOWLEDGE_DOCUMENTS, 
  NOTIFICATIONS,
  INTERVENTIONS 
} from './mockData';
import { 
  AppScreen, 
  EmergingRisk, 
  KnowledgeDocument, 
  EvidenceModalData, 
  NotificationItem,
  VerificationStatus,
  GlobalFilterState,
  AlertThresholdConfig
} from './types';
import { INITIAL_FILTER_STATE } from './utils/filterUtils';
import { DEFAULT_ALERT_CONFIG } from './utils/thresholdUtils';

export function App() {
  const [currentScreen, setCurrentScreen] = useState<AppScreen>('overview');
  const [currentSite, setCurrentSite] = useState<string>('Lagos Operations');
  const [currentTimeRange, setCurrentTimeRange] = useState<string>('Last 90 Days');
  const [globalFilter, setGlobalFilter] = useState<GlobalFilterState>(INITIAL_FILTER_STATE);
  
  // State for data
  const [risks, setRisks] = useState<EmergingRisk[]>(INITIAL_EMERGING_RISKS);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>(KNOWLEDGE_DOCUMENTS);
  const [notifications, setNotifications] = useState<NotificationItem[]>(NOTIFICATIONS);
  
  // Alert Thresholds Configuration State
  const [alertConfig, setAlertConfig] = useState<AlertThresholdConfig>(() => {
    try {
      const saved = localStorage.getItem('safelytic_alert_thresholds');
      if (saved) return JSON.parse(saved);
    } catch (e) {
      console.warn('Failed to load alert thresholds from storage', e);
    }
    return DEFAULT_ALERT_CONFIG;
  });

  const handleSaveAlertConfig = (newConfig: AlertThresholdConfig) => {
    setAlertConfig(newConfig);
    try {
      localStorage.setItem('safelytic_alert_thresholds', JSON.stringify(newConfig));
    } catch (e) {
      console.warn('Failed to save alert thresholds to storage', e);
    }
  };

  const handleTriggerAlerts = (newAlerts: NotificationItem[]) => {
    setNotifications(prev => [...newAlerts, ...prev]);
  };
  
  // Detailed view targets
  const [selectedRiskId, setSelectedRiskId] = useState<string>('RISK-LIFT-01');
  const [selectedDocId, setSelectedDocId] = useState<string>('DOC-HSE-L113');
  const [selectedInterventionId, setSelectedInterventionId] = useState<string>('INT-LIFT-2026-01');
  const [assistantInitialPrompt, setAssistantInitialPrompt] = useState<string | undefined>(undefined);

  // Modals
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [evidenceModalData, setEvidenceModalData] = useState<EvidenceModalData | null>(null);
  
  // Toasts
  const [toasts, setToasts] = useState<ToastNotification[]>([]);

  const addToast = (title: string, message: string, type: 'success' | 'info' | 'warning' | 'error' = 'info') => {
    const newToast: ToastNotification = {
      id: `toast-${Date.now()}-${Math.random()}`,
      title,
      message,
      type
    };
    setToasts(prev => [...prev, newToast]);
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // Keyboard shortcut for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Handlers for navigation & modal triggers
  const handleSelectRisk = (riskId: string) => {
    setSelectedRiskId(riskId);
    setCurrentScreen('prediction-detail');
  };

  const handleSelectDocForValidation = (docId: string) => {
    setSelectedDocId(docId);
    setCurrentScreen('source-verification');
  };

  const handleNavigateToOutcome = (intId: string) => {
    setSelectedInterventionId(intId);
    setCurrentScreen('outcome-learning');
  };

  const handleNavigateToAssistant = (prompt?: string) => {
    setAssistantInitialPrompt(prompt);
    setCurrentScreen('assistant');
  };

  const handleOpenEvidence = (evidence: any) => {
    if (!evidence) return;
    setEvidenceModalData({
      id: evidence.id || 'EVID-REC',
      title: evidence.title || evidence.documentTitle || 'Evidence Record Details',
      type: evidence.type || (evidence.jurisdiction ? 'External Regulatory Standard' : 'Internal Operational Record'),
      severity: evidence.severity || 'Information',
      date: evidence.date || evidence.publicationDate || '2026',
      details: evidence.details || evidence.keyExcerpt || evidence.summary || 'Verified data record ingested and weighted into causal model.',
      source: evidence.source || evidence.publisher || 'Safelytic Core Sensor Lake',
      metrics: evidence.metrics,
      ruleCode: evidence.code || evidence.documentCode,
      citationLink: evidence.citationLink || 'https://sie-governance.safelytic.com/records/' + (evidence.id || 'current')
    });
  };

  const handleUpdateDocStatus = (docId: string, status: VerificationStatus, note: string) => {
    setDocuments(prev => prev.map(doc => {
      if (doc.id === docId) {
        return {
          ...doc,
          verification: status,
          verificationHistory: [
            {
              date: 'Today',
              reviewer: 'Current HSE Reviewer',
              action: `Status marked as ${status}`,
              notes: note
            },
            ...doc.verificationHistory
          ]
        };
      }
      return doc;
    }));

    addToast(
      'Source Validation Updated',
      `Document ${docId} has been updated to "${status}".`,
      status === 'Verified' ? 'success' : status === 'Rejected' ? 'error' : 'warning'
    );
  };

  const handleMarkNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, isRead: true } : n));
  };

  const handleClearNotifications = () => {
    setNotifications(prev => prev.map(n => ({ ...n, isRead: true })));
    addToast('Notifications Cleared', 'All alerts marked as read.', 'info');
  };

  const selectedRiskObject = risks.find(r => r.id === selectedRiskId) || risks[0];
  const selectedDocObject = documents.find(d => d.id === selectedDocId) || documents[0];

  return (
    <div className="min-h-screen bg-[#09090B] text-slate-200 flex flex-col font-sans selection:bg-blue-600/30 selection:text-blue-200">
      {/* Top Navigation Bar */}
      <Header
        currentScreen={currentScreen}
        onNavigate={setCurrentScreen}
        onOpenSearch={() => setIsSearchOpen(true)}
        onOpenNotifications={() => setIsNotificationOpen(true)}
        unreadNotificationsCount={notifications.filter(n => !n.isRead).length}
        currentSite={currentSite}
        onSiteChange={(site) => {
          setCurrentSite(site);
          addToast('Site Filter Applied', `Switched active analytics scope to ${site}.`, 'info');
        }}
        currentTimeRange={currentTimeRange}
        onTimeRangeChange={(range) => {
          setCurrentTimeRange(range);
          const presetMap: Record<string, '7d' | '30d' | '90d' | '180d' | 'ytd'> = {
            'Last 7 Days': '7d',
            'Last 30 Days': '30d',
            'Last 90 Days': '90d',
            'Last 180 Days': '180d',
            'Year to Date (2026)': 'ytd'
          };
          if (presetMap[range]) {
            setGlobalFilter(prev => ({ ...prev, dateRangePreset: presetMap[range] }));
          }
          addToast('Timeframe Adjusted', `Aggregating risk trajectory for ${range}.`, 'info');
        }}
      />

      {/* Main Layout Area: Sidebar + Screen Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <Sidebar
          currentScreen={currentScreen}
          onNavigate={setCurrentScreen}
        />

        {/* Dynamic Screen View Content Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full bg-[#09090B]">
          {currentScreen === 'overview' && (
            <ExecutiveOverviewView
              risks={risks}
              globalFilter={globalFilter}
              onFilterChange={setGlobalFilter}
              onSelectRisk={handleSelectRisk}
              onOpenEvidence={handleOpenEvidence}
              onNavigateToIntelligence={() => setCurrentScreen('intelligence')}
              onNavigateToInterventions={() => setCurrentScreen('interventions')}
              onNavigateToAssistant={handleNavigateToAssistant}
              currentSite={currentSite}
            />
          )}

          {currentScreen === 'intelligence' && (
            <IntelligenceCenterView
              risks={risks}
              globalFilter={globalFilter}
              onFilterChange={setGlobalFilter}
              onSelectRisk={handleSelectRisk}
              onOpenEvidence={handleOpenEvidence}
              onNavigateToInterventions={() => setCurrentScreen('interventions')}
            />
          )}

          {currentScreen === 'prediction-detail' && (
            <PredictionDetailView
              risk={selectedRiskObject}
              allRisks={risks}
              onSelectOtherRisk={setSelectedRiskId}
              onBack={() => setCurrentScreen('intelligence')}
              onOpenEvidence={handleOpenEvidence}
              onNavigateToInterventions={() => setCurrentScreen('interventions')}
            />
          )}

          {currentScreen === 'knowledge-center' && (
            <KnowledgeCenterView
              documents={documents}
              onSelectDocForValidation={handleSelectDocForValidation}
              onOpenEvidence={handleOpenEvidence}
            />
          )}

          {currentScreen === 'source-verification' && (
            <SourceVerificationView
              document={selectedDocObject}
              onBack={() => setCurrentScreen('knowledge-center')}
              onUpdateStatus={handleUpdateDocStatus}
              allDocs={documents}
              onSelectOtherDoc={setSelectedDocId}
            />
          )}

          {currentScreen === 'organization-data' && (
            <OrganizationDataView
              onOpenEvidence={handleOpenEvidence}
            />
          )}

          {currentScreen === 'intelligence-learning' && (
            <IntelligenceLearningView />
          )}

          {currentScreen === 'interventions' && (
            <InterventionCenterView
              onNavigateToOutcome={handleNavigateToOutcome}
              onSelectRisk={handleSelectRisk}
            />
          )}

          {currentScreen === 'outcome-learning' && (
            <OutcomeLearningView
              interventionId={selectedInterventionId}
              onBack={() => setCurrentScreen('interventions')}
              onSelectIntervention={setSelectedInterventionId}
            />
          )}

          {currentScreen === 'assistant' && (
            <AIAssistantView
              onOpenEvidence={handleOpenEvidence}
              onNavigateToInterventions={() => setCurrentScreen('interventions')}
              onNavigateToAnalysis={(riskId) => {
                if (riskId) setSelectedRiskId(riskId);
                setCurrentScreen('prediction-detail');
              }}
              onNavigateToChallenge={(riskId) => {
                setCurrentScreen('intelligence-learning');
              }}
              currentSite={currentSite}
              currentTimeRange={currentTimeRange}
              initialPrompt={assistantInitialPrompt}
            />
          )}

          {currentScreen === 'api-integrations' && (
            <APIIntegrationsView onNavigateToCanonicalModel={() => setCurrentScreen('canonical-model')} />
          )}

          {currentScreen === 'canonical-model' && (
            <CanonicalDataModelView />
          )}

          {currentScreen === 'governance' && (
            <GovernanceView />
          )}

          {currentScreen === 'settings' && (
            <SettingsView
              risks={risks}
              currentConfig={alertConfig}
              onSaveConfig={handleSaveAlertConfig}
              onTriggerAlerts={handleTriggerAlerts}
              onAddToast={addToast}
              onSelectRisk={handleSelectRisk}
            />
          )}
        </main>
      </div>

      {/* Global Command Palette Search Modal */}
      <GlobalSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectRisk={handleSelectRisk}
        onSelectDoc={handleSelectDocForValidation}
        onSelectIntervention={handleNavigateToOutcome}
        risks={risks}
        documents={documents}
        interventions={INTERVENTIONS}
      />

      {/* Live Notification Drawer */}
      <NotificationDrawer
        isOpen={isNotificationOpen}
        onClose={() => setIsNotificationOpen(false)}
        notifications={notifications}
        onMarkAsRead={handleMarkNotificationRead}
        onClearAll={handleClearNotifications}
        onNavigateToSettings={() => setCurrentScreen('settings')}
        onSelectNotification={(notif) => {
          if (notif.relatedRiskId) {
            handleSelectRisk(notif.relatedRiskId);
            setIsNotificationOpen(false);
          }
        }}
      />

      {/* Reusable Evidence Detail Modal */}
      <EvidenceDetailModal
        data={evidenceModalData}
        isOpen={evidenceModalData !== null}
        onClose={() => setEvidenceModalData(null)}
      />

      {/* Toast Feedback Notifications */}
      <ToastContainer
        toasts={toasts}
        onRemove={removeToast}
      />
    </div>
  );
}

export default App;
