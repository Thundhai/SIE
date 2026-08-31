import { 
  EmergingRisk, 
  KnowledgeDocument, 
  InterventionItem, 
  DataIngestionSource, 
  LearningPipelineItem, 
  GovernanceLog, 
  ManagementAttentionItem,
  KnowledgeIngestionItem,
  PredictiveModelModule,
  ExpertFeedbackItem,
  OutcomeLearningRecord
} from './types';

export const INITIAL_EMERGING_RISKS: EmergingRisk[] = [
  {
    id: 'RISK-LIFT-01',
    category: 'Lifting Operations',
    title: 'Elevated Risk in Heavy Crane & Rigging Operations',
    level: 'High',
    probability: 78,
    confidence: 82,
    trajectory: 'Increasing',
    trendPercentage: 14,
    location: 'Yard 4 & Pier 2',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-28',
    evidenceStrength: 'Very Strong',
    mainDriver: '28% increase in simultaneous crane lifts combined with 3 overdue sling inspection actions and higher subcontractor turnover.',
    drivers: [
      '28% increase in heavy lift exposure hours',
      '14 lifting-related unsafe observations logged',
      '3 overdue corrective actions on rigging gear',
      '2 high-potential near misses in 21 days',
      'Increased 3rd-party contractor workforce turnover'
    ],
    status: 'Elevated',
    orgRecordsCount: 24,
    externalSourcesCount: 6,
    modelsUsedCount: 3,
    summary: 'SIE has identified a developing high-severity risk pattern associated with tandem and high-tonnage lifting operations over the last 30 days at Lagos Operations.',
    causalChain: [
      {
        step: 1,
        title: 'Increased Lift Activity',
        description: 'Heavy fabrication milestone led to +28% crane duty cycles and congested ground traffic.',
        metricChange: '+28% Lift Hours'
      },
      {
        step: 2,
        title: 'Exposure & Congestion Surge',
        description: 'Simultaneous operations (SIMOPS) in proximity to fabrication line and pipe staging yard.',
        metricChange: 'SIMOPS Index 8.4/10'
      },
      {
        step: 3,
        title: 'Rise in Field Observations',
        description: '14 observations detailing tag line omission, pinch-point exposure, and sling angle discrepancies.',
        metricChange: '14 Reports logged'
      },
      {
        step: 4,
        title: 'Unresolved Control Weaknesses',
        description: '3 mandatory quarterly rigging gear recertification actions are 12 days overdue in Yard 4.',
        metricChange: '3 Actions Overdue'
      },
      {
        step: 5,
        title: 'Elevated Predictive Risk',
        description: 'Model calculates a 78% probability of a dropped load or sling failure event if unmitigated within 14 days.',
        metricChange: '78% Probability (82% Conf)'
      }
    ],
    contributingFactors: [
      { name: 'Rigging Gear Certification Delays', percentage: 34, impact: 'High', description: 'Third-party NDT certifications pending on two 45t spreader beams.' },
      { name: 'Contractor Competency Variation', percentage: 28, impact: 'High', description: '40% of active riggers on site onboarding within the last 45 days.' },
      { name: 'SIMOPS Ground Congestion', percentage: 22, impact: 'Medium', description: 'Interference between mobile crane outriggers and forklift transport corridors.' },
      { name: 'Environmental Wind Gust Exposure', percentage: 16, impact: 'Medium', description: 'Afternoon coastal gusts (>22 knots) causing intermittent suspended load sway.' }
    ],
    organizationEvidence: [
      {
        id: 'OBS-1044',
        type: 'Observation',
        title: 'Unsafe sling angle exceeding 60-degree safe envelope',
        date: '18 Aug 2026',
        site: 'Lagos Operations',
        location: 'Yard 4 Staging Pad',
        activity: 'Lifting operation',
        hazard: 'Two-leg wire rope bridle rigged at improper spread angle exceeding 60 degrees',
        risk: 'Dropped load / Rigging parting failure & crush injury to riggers',
        severity: 'High',
        status: 'In Remediation',
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Two-leg wire rope bridle rigged at improper spread angle (>60°), reducing safe working load (SWL) capacity by estimated 25% without re-rating calculation.',
        reporterRole: 'Rigging Superintendent',
        isSimulated: true
      },
      {
        id: 'OBS-1021',
        type: 'Observation',
        title: 'Tag line not utilized on 12-ton turbine casing lift',
        date: '12 Aug 2026',
        site: 'Lagos Operations',
        location: 'Pier 2 - Heavy Berth',
        activity: 'Tandem Crane Lift & Casing Guiding',
        hazard: 'Direct manual hands-on guide of suspended 12-tonne load',
        risk: 'Pinch-point crush and struck-by hazard during sudden swing',
        severity: 'High',
        status: 'Open',
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Subcontractor crew guided 12t suspended turbine casing using direct hand contact on load edge rather than approved fiber tag lines during coastal cross-winds.',
        reporterRole: 'Senior HSE Officer',
        isSimulated: true
      },
      {
        id: 'NM-203',
        type: 'Near Miss',
        title: 'Uncontrolled load swing near fuel manifold during gust',
        date: '22 Aug 2026',
        site: 'Lagos Operations',
        location: 'Lagos Main Fabrication Hall',
        activity: 'Overhead Gantry Transit',
        hazard: '8-tonne pipe spool oscillation in proximity to live manifold',
        risk: 'Hydrocarbon line rupture and structural impact',
        severity: 'Critical',
        status: 'Overdue',
        sourceSystem: 'Cority Mobile Reporter',
        details: 'Sudden wind gust caused 8t pipe spool to oscillate within 1.2m of pressurized nitrogen header. Lift stopped via emergency whistle.',
        reporterRole: 'Crane Operator Level II',
        isSimulated: true
      },
      {
        id: 'ACT-884',
        type: 'Audit Finding',
        title: 'Master Rigging Register lacking current color-coding check',
        date: '25 Aug 2026',
        site: 'Lagos Operations',
        location: 'Central Rigging Loft',
        activity: 'Quarterly Equipment Recertification Audit',
        hazard: '18 wire slings in field circulation with outdated inspection color tags',
        risk: 'Use of defective, uninspected, or overloaded lifting slings',
        severity: 'High',
        status: 'Overdue',
        sourceSystem: 'Sphera Audit Manager',
        details: 'Quarterly color tag changeover not systematically applied to 18 wire slings in field circulation across Yard 4. Master Rigging Register shows overdue inspection by 12 days.',
        reporterRole: 'Lead Quality Auditor',
        isSimulated: true
      }
    ],
    externalEvidence: [
      {
        id: 'EXT-HSE-LIFT',
        publisher: 'HSE UK (Health and Safety Executive)',
        documentTitle: 'LOLER 1998 Approved Code of Practice & Rigging Failure Causation Analysis',
        documentType: 'Approved Code of Practice',
        code: 'HSE L113 / 2026 Rev',
        jurisdiction: 'United Kingdom / Global Best Practice',
        publicationDate: '2026',
        revisionVersion: 'Rev 4.2 (2026 Amendment)',
        verificationStatus: 'Verified',
        reliability: 'Very High',
        topic: 'Lifting Equipment Inspection & Pre-use Controls',
        sourceReference: 'HSE L113 § 14.2 / Table 3.1: Sling Angles and Capacity Derating Factors',
        keyExcerpt: 'Over 68% of industrial rigging incidents originate from unverified sling geometry and unrectified pre-use wear during surges in operational tempo.',
        isSimulated: true
      },
      {
        id: 'EXT-OSHA-1926',
        publisher: 'OSHA (Occupational Safety and Health Admin)',
        documentTitle: 'Cranes and Derricks in Construction Standard: SIMOPS and Ground Stability',
        documentType: 'Regulatory Standard',
        code: '29 CFR 1926.1400',
        jurisdiction: 'United States',
        publicationDate: '2025',
        revisionVersion: '2025 Codified Edition',
        verificationStatus: 'Active Standard',
        reliability: 'High',
        topic: 'Simultaneous Operations & Ground Bearing Capacity',
        sourceReference: '29 CFR 1926.1424(a)(2) / Multi-crane Simultaneous Lift Clearances',
        keyExcerpt: 'Simultaneous material transfers within crane swing radii multiply incident likelihood by a factor of 3.4 when spotter communication is non-dedicated.',
        isSimulated: true
      },
      {
        id: 'EXT-IMCA-LR001',
        publisher: 'IMCA (International Marine Contractors Assoc)',
        documentTitle: 'Guidance on the Management of Lifting Operations in High-Tempo Ports',
        documentType: 'Technical Guidance',
        code: 'IMCA LR 001 / Rev 4',
        jurisdiction: 'International Maritime & Energy',
        publicationDate: '2026',
        revisionVersion: 'Rev 4.0 (2026)',
        verificationStatus: 'Validated Benchmark',
        reliability: 'Very High',
        topic: 'Contractor Competency & Blind Lift Controls',
        sourceReference: 'IMCA LR 001 § 6.4: Temporary Personnel Competency Verification in Rigging',
        keyExcerpt: 'A rapid intake of temporary rigging personnel requires mandatory supervisor-led task safety briefings for all lifts exceeding 5 tonnes.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-LIFT-01',
      trend: '+14% 30-Day Escalation Slope',
      baseline: '2.1 lifting precursor events per 1,000 lift cycles (90-day baseline)',
      currentValue: '4.8 lifting precursor events per 1,000 lift cycles',
      deviation: '+128% vs Historical 90-Day Moving Average (z-score: +2.41)',
      historicalComparison: 'Highest precursor density since Q3 2024 turnaround; closely matches the leading-indicator signature observed prior to the 2024 Yard 2 dropped-load incident.',
      contributingFactors: [
        { name: 'Rigging Gear Certification Delays', percentage: 34, impact: 'High', description: 'Third-party NDT certifications pending on two 45t spreader beams.' },
        { name: 'Contractor Competency Variation', percentage: 28, impact: 'High', description: '40% of active riggers on site onboarding within the last 45 days.' },
        { name: 'SIMOPS Ground Congestion', percentage: 22, impact: 'Medium', description: 'Interference between mobile crane outriggers and forklift transport corridors.' },
        { name: 'Environmental Wind Gust Exposure', percentage: 16, impact: 'Medium', description: 'Afternoon coastal gusts (>22 knots) causing intermittent suspended load sway.' }
      ],
      modelTechnique: 'Dynamic Bayesian Network + Tag Line Velocity Tracker (Cox Survival Model)',
      confidenceInterval: '95% CI [74% - 86%] based on 1,284 tenant records',
      isSimulated: true
    },
    aiReasoning: 'Synthesis of 24 internal records across Lagos Operations demonstrates a statistical convergence: heavy lift tempo increased 28%, observation density for rigging errors grew 4.2x above baseline, and 3 critical corrective actions remain unclosed. Cross-referencing with verified HSE UK LOLER benchmark data confirms an identical pre-incident precursor signature seen prior to catastrophic dropped-load events.'
  },
  {
    id: 'RISK-VEH-02',
    category: 'Vehicle Movement',
    title: 'Night Shift Heavy Logistics & Blind Spot Congestion',
    level: 'High',
    probability: 61,
    confidence: 79,
    trajectory: 'Increasing',
    trendPercentage: 9,
    location: 'Logistics Gate 2 & Pipe Staging Road',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-26',
    evidenceStrength: 'Strong',
    mainDriver: '62% rise in flatbed truck deliveries between 20:00 and 04:00 with inadequate high-mast lighting in staging bays.',
    drivers: [
      'High density of low-speed truck reversals at night',
      'Inadequate lux levels reported at Gate 2 bay',
      '8 pedestrian-vehicle separation observations',
      'Telematics shows 11 harsh braking triggers this month'
    ],
    status: 'Elevated',
    orgRecordsCount: 19,
    externalSourcesCount: 4,
    modelsUsedCount: 2,
    summary: 'Elevated collision and pedestrian interface risk identified in nocturnal logistics corridors due to lighting degradation and heightened transport volume.',
    causalChain: [
      { step: 1, title: 'Delivery Shift to Night', description: 'Port congestion caused offloading trucks to arrive between 21:00-03:00.', metricChange: '+62% Night Transits' },
      { step: 2, title: 'Lighting Infrastructure Dip', description: '2 auxiliary floodlights offline awaiting ballast replacement.', metricChange: '<30 Lux Staging Bay' },
      { step: 3, title: 'Driver Fatigue & Reversing Errors', description: 'Contractor drivers exceeding recommended consecutive driving hours.', metricChange: '8 Pedestrian Near-Misses' },
      { step: 4, title: 'Predictive Assessment', description: 'Model flags 61% likelihood of vehicle-structure or vehicle-pedestrian contact without traffic marshals.', metricChange: '61% Probability' }
    ],
    contributingFactors: [
      { name: 'Nocturnal Illumination Gaps', percentage: 42, impact: 'High', description: 'Auxiliary mast lighting failure in truck staging lot.' },
      { name: 'Pedestrian Barrier Breaches', percentage: 31, impact: 'Medium', description: 'Shortcutting walkways across active forklift lanes.' },
      { name: 'Contractor Haulier Telematics Non-Compliance', percentage: 27, impact: 'Medium', description: 'Third-party vehicles lacking certified audible reversing beacons.' }
    ],
    organizationEvidence: [
      { 
        id: 'OBS-1102', 
        type: 'Observation', 
        title: 'Worker crossing unlit flatbed reversing lane', 
        date: '21 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Gate 2 Buffer Zone', 
        activity: 'Heavy logistics dispatch & reversing',
        hazard: 'Unlit transit pathway intersecting active truck blind spots',
        risk: 'Pedestrian runover / vehicle collision',
        severity: 'High', 
        status: 'In Remediation', 
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Technician on foot bypassed designated pedestrian walkway into active blind spot of reversing 30t tractor-trailer during unlit night transfer.', 
        reporterRole: 'Logistics Supervisor',
        isSimulated: true
      },
      { 
        id: 'NM-208', 
        type: 'Near Miss', 
        title: 'Forklift near-collision with pipe flatbed corner', 
        date: '24 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Pipe Staging West', 
        activity: 'Night material transfer & forklift maneuvering',
        hazard: 'Unchocked pallet positioned in darkened travel corridor',
        risk: 'Equipment tip-over & vehicle collision',
        severity: 'Medium', 
        status: 'Closed', 
        sourceSystem: 'Cority Mobile Reporter',
        details: 'Forklift operator swerved abruptly to avoid unchocked pallet in dark zone, narrowly avoiding 40t tubular pipe stack.', 
        reporterRole: 'Forklift Driver',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-NIOSH-VEH', 
        publisher: 'NIOSH (National Institute for Occupational Safety and Health)', 
        documentTitle: 'Preventing Worker Injuries and Deaths from Mobile Equipment Backover', 
        documentType: 'Safety Alert',
        code: 'NIOSH Pub 2025-118', 
        jurisdiction: 'United States / Global',
        publicationDate: '2025', 
        revisionVersion: '2025 Advisory',
        verificationStatus: 'Verified',
        reliability: 'High', 
        topic: 'Internal Traffic Control Plans & Blind Spot Separation', 
        sourceReference: 'NIOSH Report 2025-118 § 3.2: Reversing Alarms & Lighting Thresholds',
        keyExcerpt: 'Physical separation of foot traffic and dedicated marshaling reduces dark-shift mobile equipment incidents by up to 83%.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-VEH-02',
      trend: '+9% 30-Day Logistics Escalation Slope',
      baseline: '1.4 vehicle-pedestrian conflict observations per 100 night transfers',
      currentValue: '3.6 vehicle-pedestrian conflict observations per 100 night transfers',
      deviation: '+157% vs 60-day baseline in low-lux corridors',
      historicalComparison: 'Elevated conflict concentration matching the 2025 pre-turnaround delivery spike.',
      contributingFactors: [
        { name: 'Nocturnal Illumination Gaps', percentage: 42, impact: 'High', description: 'Auxiliary mast lighting failure in truck staging lot.' },
        { name: 'Pedestrian Barrier Breaches', percentage: 31, impact: 'Medium', description: 'Shortcutting walkways across active forklift lanes.' },
        { name: 'Contractor Haulier Telematics Non-Compliance', percentage: 27, impact: 'Medium', description: 'Third-party vehicles lacking certified audible reversing beacons.' }
      ],
      modelTechnique: 'Spatial Congestion Heatmap + Near Miss Markov Process',
      confidenceInterval: '95% CI [70% - 85%]',
      isSimulated: true
    },
    aiReasoning: 'Telematics data matched with 8 site observations highlights an accelerating trend of pedestrian proximity to heavy vehicles during night transfers. Historical correlation indicates a 3.8x risk surge when illumination drops below 50 lux in active maneuvering bays.'
  },
  {
    id: 'RISK-PS-03',
    category: 'Process Safety',
    title: 'Flange Joint Integrity Degradation on High-Pressure Gas Manifold',
    level: 'High',
    probability: 69,
    confidence: 85,
    trajectory: 'Increasing',
    trendPercentage: 11,
    location: 'Gas Compression Train B',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-27',
    evidenceStrength: 'Very Strong',
    mainDriver: 'Micro-vibration harmonics detected by acoustic IoT sensors coupled with deferred bolt re-torquing campaign.',
    drivers: [
      'Acoustic emission spikes on Train B header flange',
      '3 deferred preventive maintenance work orders',
      'Thermal imaging indicates 4.2°C delta on valve bypass',
      'Corrosion CUI inspection interval overdue by 18 days'
    ],
    status: 'Critical Warning',
    orgRecordsCount: 31,
    externalSourcesCount: 5,
    modelsUsedCount: 4,
    summary: 'Acoustic sensing and inspection backlog indicate elevated probability of fugitive hydrocarbon release or seal blow-by on Compression Train B.',
    causalChain: [
      { step: 1, title: 'Operating Duty Cycle Spike', description: 'Train B pushed to 96% throughput capacity during seasonal demand run.', metricChange: '96% Load Factor' },
      { step: 2, title: 'Vibration Resonance', description: 'Acoustic telemetry detected elevated 142 Hz harmonic frequency across header.', metricChange: '+3.1 mm/s RMS' },
      { step: 3, title: 'Deferred Flange Retorque', description: 'Turnaround work order WO-4409 postponed due to spare gasket stockout.', metricChange: '18 Days Overdue' },
      { step: 4, title: 'Loss of Containment Risk', description: 'Predictive envelope forecasts micro-leak breach probability at 69%.', metricChange: '69% Probability' }
    ],
    contributingFactors: [
      { name: 'Flange Bolt Pre-load Relaxation', percentage: 45, impact: 'High', description: 'Cyclic thermal expansion causing bolt stress relief.' },
      { name: 'Maintenance Work Order Backlog', percentage: 33, impact: 'High', description: 'Critical gasket replacement postponed beyond safety window.' },
      { name: 'Sensor Telemetry Anomalies', percentage: 22, impact: 'Medium', description: 'IoT continuous acoustic noise signature matching seal distress.' }
    ],
    organizationEvidence: [
      { 
        id: 'INS-409', 
        type: 'Inspection Defect', 
        title: 'Flange B-104 weeping traces detected via soap bubble test', 
        date: '23 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Train B Skid', 
        activity: 'Gas compression operational pressurization',
        hazard: 'Trace micro-bubble weeping on 6 o-clock flange bolt segment',
        risk: 'Pressurized hydrocarbon release / Vapor cloud explosion',
        severity: 'High', 
        status: 'Open', 
        sourceSystem: 'Enablon Asset Integrity Module',
        details: 'Trace bubble formation on bottom 6 o-clock bolt segment. Hydrocarbon sniffer detected 40ppm background trace near manifold flange.', 
        reporterRole: 'Integrity Engineer',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-API-570', 
        publisher: 'American Petroleum Institute (API)', 
        documentTitle: 'Piping Inspection Code: In-service Inspection, Rating, Repair, and Alteration', 
        documentType: 'Approved Code of Practice',
        code: 'API 570 5th Ed', 
        jurisdiction: 'Global / Energy',
        publicationDate: '2026', 
        revisionVersion: '5th Edition (2026)',
        verificationStatus: 'Verified',
        reliability: 'Very High', 
        topic: 'Piping Integrity & Flange Leakage Control', 
        sourceReference: 'API 570 § 7.3: Flange Bolt Torquing & Acoustic Monitoring Protocols',
        keyExcerpt: 'Flange joint relaxation under cyclic temperature transitions mandates re-torque within 72 hours of initial acoustic vibration alerts.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-PS-03',
      trend: '+11% 30-Day Vibration Harmonic Delta',
      baseline: '0.8 mm/s RMS vibration baseline under standard load',
      currentValue: '3.1 mm/s RMS (142 Hz harmonic frequency spike)',
      deviation: '+287% above nominal acoustic noise baseline',
      historicalComparison: 'Matches pre-leak degradation curves modeled during 2023 compressor overhaul.',
      contributingFactors: [
        { name: 'Flange Bolt Pre-load Relaxation', percentage: 45, impact: 'High', description: 'Cyclic thermal expansion causing bolt stress relief.' },
        { name: 'Maintenance Work Order Backlog', percentage: 33, impact: 'High', description: 'Critical gasket replacement postponed beyond safety window.' },
        { name: 'Sensor Telemetry Anomalies', percentage: 22, impact: 'Medium', description: 'IoT continuous acoustic noise signature matching seal distress.' }
      ],
      modelTechnique: 'Fault Tree Synthesis + Flange Degradation Classifier (Bayesian Survival)',
      confidenceInterval: '95% CI [79% - 91%]',
      isSimulated: true
    },
    aiReasoning: 'Integration of real-time acoustic IoT data, 40ppm gas sniffer readings, and deferred maintenance records indicates high vulnerability to pressurized gas release.'
  },
  {
    id: 'RISK-WAH-04',
    category: 'Work at Height',
    title: 'Scaffold Modification & Harness Lanyard Anchor Inconsistencies',
    level: 'Moderate',
    probability: 54,
    confidence: 76,
    trajectory: 'Stable',
    trendPercentage: 2,
    location: 'Flare Stack Structure & Tank 103 Roof',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-20',
    evidenceStrength: 'Moderate',
    mainDriver: 'Unauthorized scaffold modifications by painters combined with 8 training gap alerts on double-lanyard hook-up.',
    drivers: [
      '3 green scaffold tags removed or altered on site',
      '8 workers lacking verified advanced working-at-height refreshers',
      'Weather alert: Intermittent morning squalls creating slippery decking'
    ],
    status: 'Emerging',
    orgRecordsCount: 16,
    externalSourcesCount: 3,
    modelsUsedCount: 2,
    summary: 'Scaffolding modifications and lanyard anchor compliance gaps flagged in structural maintenance crews.',
    causalChain: [
      { step: 1, title: 'Painting Access Requirements', description: 'Painters adjusting mid-rails to reach tank gusset welds.', metricChange: '3 Tags Invalidated' },
      { step: 2, title: 'Anchor Point Deficiencies', description: 'Temporary beam clamps rigged on non-certified structural members.', metricChange: '6 Anchor Warnings' },
      { step: 3, title: 'Training Refresh Latency', description: '8 subcontracted painters overdue for annual height rescue and 100% tie-off refresher.', metricChange: '8 Training Gaps' }
    ],
    contributingFactors: [
      { name: 'Scaffold Inspection Tag Discipline', percentage: 48, impact: 'High', description: 'Field adjustments without Scaffolding Inspector sign-off.' },
      { name: 'Competency Verification Lapses', percentage: 32, impact: 'Medium', description: 'Subcontractor crew onboarding skipped practical anchor test.' },
      { name: 'Adverse Wind & Moisture Index', percentage: 20, impact: 'Low', description: 'Dew on aluminum decking during early morning shifts.' }
    ],
    organizationEvidence: [
      { 
        id: 'OBS-1055', 
        type: 'Observation', 
        title: 'Painter unclipped while traversing scaffold ledger', 
        date: '19 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Tank 103 Roof Perimeter', 
        activity: 'Structural coating & elevated scaffold painting',
        hazard: 'Complete disconnection of twin lanyards during ledger traversal',
        risk: 'Fall from height (14m elevation) / Fatal trauma',
        severity: 'High', 
        status: 'Closed', 
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Worker unhooked both shock-absorbing lanyards simultaneously to navigate around structural ladder at 14m elevation.', 
        reporterRole: 'HSE Safety Auditor',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-OSHA-1926-502', 
        publisher: 'OSHA', 
        documentTitle: 'Fall Protection Systems Criteria and Practices', 
        documentType: 'Regulatory Standard',
        code: '29 CFR 1926.502', 
        jurisdiction: 'United States',
        publicationDate: '2025', 
        revisionVersion: '2025 Standard',
        verificationStatus: 'Active Standard',
        reliability: 'Very High', 
        topic: '100% Tie-Off & Anchorage Strength', 
        sourceReference: '29 CFR 1926.502(d)(15) / 5,000 lbs Anchor Point Requirements',
        keyExcerpt: 'Continuous tie-off requires redundant twin-tail lanyards or dual self-retracting lifelines whenever moving across un-decked frames.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-WAH-04',
      trend: '+2% 30-Day Height Variance',
      baseline: '0.9 height observations per 50 scaffolding shifts',
      currentValue: '1.8 height observations per 50 scaffolding shifts',
      deviation: '+100% vs 90-day baseline',
      historicalComparison: 'Plateaued after recent contractor tool-box talk intervention.',
      contributingFactors: [
        { name: 'Scaffold Inspection Tag Discipline', percentage: 48, impact: 'High', description: 'Field adjustments without Scaffolding Inspector sign-off.' },
        { name: 'Competency Verification Lapses', percentage: 32, impact: 'Medium', description: 'Subcontractor crew onboarding skipped practical anchor test.' },
        { name: 'Adverse Wind & Moisture Index', percentage: 20, impact: 'Low', description: 'Dew on aluminum decking during early morning shifts.' }
      ],
      modelTechnique: 'Bayesian Inspection Defect Clustering + Environmental Wind Factor',
      confidenceInterval: '95% CI [68% - 82%]',
      isSimulated: true
    },
    aiReasoning: 'Correlation between training gap records and scaffold inspection defects predicts elevated fall vulnerability on elevated tank works.'
  },
  {
    id: 'RISK-CONF-05',
    category: 'Confined Space',
    title: 'Atmospheric Gas Testing Interval Lapses in Storage Tanks',
    level: 'Moderate',
    probability: 48,
    confidence: 84,
    trajectory: 'Decreasing',
    trendPercentage: -6,
    location: 'Crude Slop Tank TK-202',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-15',
    evidenceStrength: 'Very Strong',
    mainDriver: 'Continuous gas monitor bump-test log lag and oxygen displacement potential during sludge desludging.',
    drivers: [
      'Gas test records logged at 4-hour intervals instead of mandatory 2-hour continuous standby',
      'Calibration gas cylinder for LEL sensors expired by 5 days',
      'Standby hole-watch sentry reassigned temporarily during shift handover'
    ],
    status: 'Monitored',
    orgRecordsCount: 12,
    externalSourcesCount: 4,
    modelsUsedCount: 2,
    summary: 'Periodic gas test frequency lapses noted during sludge cleanout; recent supervisor refresher is currently stabilizing risk trend.',
    causalChain: [
      { step: 1, title: 'Desludging Shift Tempo', description: 'Washing operations generate intermittent vapor plumes.', metricChange: 'VOC Fluctuation' },
      { step: 2, title: 'Test Frequency Slippage', description: 'Log sheets showed gaps between continuous multi-gas readings.', metricChange: '4h vs 2h Standard' },
      { step: 3, title: 'Corrective Guidance Issued', description: 'Mandatory continuous aspirated gas monitor deployed.', metricChange: 'Risk Declining (-6%)' }
    ],
    contributingFactors: [
      { name: 'Standby Attendant Continuity', percentage: 40, impact: 'Medium', description: 'Sentry rotation gaps during meal intervals.' },
      { name: 'Gas Monitor Bump Calibration', percentage: 35, impact: 'Medium', description: 'Calibration station located far from tank farm.' },
      { name: 'Ventilation Extraction Rate', percentage: 25, impact: 'Low', description: 'Air horn blower positioned suboptimal to tank manway.' }
    ],
    organizationEvidence: [
      { 
        id: 'AUD-302', 
        type: 'Permit Exception', 
        title: 'Permit-to-Work gas test stamp missing at 14:00 check', 
        date: '14 Aug 2026', 
        site: 'Lagos Operations',
        location: 'TK-202 Manway', 
        activity: 'Storage tank confined space entry & desludging',
        hazard: '90-minute atmospheric test gap during crude washing',
        risk: 'Toxic vapor buildup (H2S/LEL) & oxygen depletion',
        severity: 'Medium', 
        status: 'Closed', 
        sourceSystem: 'Enablon PTW System',
        details: 'Authorized gas tester was called to Tank 101, leaving 90-minute monitoring void on active entry permit.', 
        reporterRole: 'Permit Coordinator',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-HSE-INDG258', 
        publisher: 'HSE UK', 
        documentTitle: 'Safe Work in Confined Spaces: Confined Spaces Regulations 1997', 
        documentType: 'Approved Code of Practice',
        code: 'INDG258 Rev 4', 
        jurisdiction: 'United Kingdom',
        publicationDate: '2026', 
        revisionVersion: 'Rev 4 (2026)',
        verificationStatus: 'Verified',
        reliability: 'Very High', 
        topic: 'Continuous Atmospheric Monitoring & Standby Watch', 
        sourceReference: 'INDG258 § 8: Atmospheric Testing Intervals in Flammable Environments',
        keyExcerpt: 'Continuous monitoring with aspirated gas detection is mandatory when volatile hydrocarbon deposits are subject to mechanical agitation.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-CONF-05',
      trend: '-6% 30-Day Downward Slope',
      baseline: '100% compliant continuous aspirated sensor coverage',
      currentValue: '96% sensor log compliance (post-refresher recovery)',
      deviation: '-4% temporary variance, rapidly normalizing',
      historicalComparison: 'Stable within green threshold after continuous aspirated gas monitor deployment.',
      contributingFactors: [
        { name: 'Standby Attendant Continuity', percentage: 40, impact: 'Medium', description: 'Sentry rotation gaps during meal intervals.' },
        { name: 'Gas Monitor Bump Calibration', percentage: 35, impact: 'Medium', description: 'Calibration station located far from tank farm.' },
        { name: 'Ventilation Extraction Rate', percentage: 25, impact: 'Low', description: 'Air horn blower positioned suboptimal to tank manway.' }
      ],
      modelTechnique: 'Sensor Baseline Drift Model + Permit Deviation Cross-Referencing',
      confidenceInterval: '95% CI [78% - 89%]',
      isSimulated: true
    },
    aiReasoning: 'While training intervention has started reversing the trajectory (-6%), strict automated continuous gas sensor integration is advised to maintain control.'
  },
  {
    id: 'RISK-CONT-06',
    category: 'Contractor Management',
    title: 'Subcontractor Safety Induction & Permit Adherence Disconnect',
    level: 'High',
    probability: 65,
    confidence: 81,
    trajectory: 'Increasing',
    trendPercentage: 12,
    location: 'All Operating Zones',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-25',
    evidenceStrength: 'Strong',
    mainDriver: 'Surge in short-service contract personnel without verified site HSE passport or behavioral safety briefing.',
    drivers: [
      '42 new subcontracted workers onboarded in 10 days',
      '19 minor procedural non-conformances flagged by area leads',
      'Contractor supervision ratio dropped from 1:8 to 1:16'
    ],
    status: 'Elevated',
    orgRecordsCount: 22,
    externalSourcesCount: 3,
    modelsUsedCount: 3,
    summary: 'Subcontractor rapid scaling has diluted field supervisory ratios and generated a 32% spike in permit-to-work boundary oversights.',
    causalChain: [
      { step: 1, title: 'Rapid Project Ramp-up', description: 'Fast-track turnaround schedule brought 3 new sub-tier fabrication contractors.', metricChange: '+42 Personnel' },
      { step: 2, title: 'Supervision Ratio Drop', description: 'Contractor HSE leads overwhelmed across multi-tier workfaces.', metricChange: 'Ratio 1:16' },
      { step: 3, title: 'Boundary Oversights', description: 'Crews working beyond designated permit boundary zones.', metricChange: '19 Non-conformances' },
      { step: 4, title: 'Compounding Risk', description: 'Elevates cross-discipline risks across Lifting, Hot Work, and Heights.', metricChange: '65% Probability' }
    ],
    contributingFactors: [
      { name: 'Supervisory Ratio Dilution', percentage: 44, impact: 'High', description: 'Contractor foreman managing 16 workers across disjointed berths.' },
      { name: 'Language & Briefing Barriers', percentage: 32, impact: 'Medium', description: 'Toolbox talks delivered without verified translated comprehension.' },
      { name: 'Sub-tier Onboarding Passport Gaps', percentage: 24, impact: 'Medium', description: 'Tier-2 subcontractor workers not pre-cleared in LMS.' }
    ],
    organizationEvidence: [
      { 
        id: 'OBS-1088', 
        type: 'Observation', 
        title: 'Contractor pipefitters working hot work zone without fire watch assigned', 
        date: '24 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Yard 4 Welding Bay', 
        activity: 'Hot work torch cutting & pipe fitting',
        hazard: 'Torch cutting without dedicated fire sentry or dry powder extinguisher',
        risk: 'Sparks igniting adjacent solvent wash / Uncontrolled fire',
        severity: 'High', 
        status: 'Open', 
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Contractor commenced torch cutting without dedicated fire watch posted with 9kg dry powder extinguisher within 15m radius.', 
        reporterRole: 'Area Authority',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-ILO-OSH2001', 
        publisher: 'International Labour Organization (ILO)', 
        documentTitle: 'Guidelines on Occupational Safety and Health Management Systems: Contractor Safety', 
        documentType: 'International Standard',
        code: 'ILO-OSH 2001 Sec 3.10', 
        jurisdiction: 'International',
        publicationDate: '2025', 
        revisionVersion: '2025 Standard',
        verificationStatus: 'Verified',
        reliability: 'Very High', 
        topic: 'Contractor Oversight & Co-employment Safety', 
        sourceReference: 'ILO-OSH 2001 § 3.10.4: Subcontractor Ratio Constraints and Induction Controls',
        keyExcerpt: 'Contractor incident rates correlate directly with supervisory ratio thresholds falling below 1 qualified supervisor per 10 workers.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-CONT-06',
      trend: '+12% 30-Day Onboarding Non-conformance Slope',
      baseline: '1 supervisor per 8 contract workers',
      currentValue: '1 supervisor per 16 contract workers',
      deviation: '+100% supervisory strain over 14-day surge',
      historicalComparison: 'Fastest contractor scaling rate in 18 months.',
      contributingFactors: [
        { name: 'Supervisory Ratio Dilution', percentage: 44, impact: 'High', description: 'Contractor foreman managing 16 workers across disjointed berths.' },
        { name: 'Language & Briefing Barriers', percentage: 32, impact: 'Medium', description: 'Toolbox talks delivered without verified translated comprehension.' },
        { name: 'Sub-tier Onboarding Passport Gaps', percentage: 24, impact: 'Medium', description: 'Tier-2 subcontractor workers not pre-cleared in LMS.' }
      ],
      modelTechnique: 'Time-to-Event Survival Analysis + Onboarding Turnover Index',
      confidenceInterval: '95% CI [74% - 87%]',
      isSimulated: true
    },
    aiReasoning: 'Rapid workforce expansion without scaling dedicated contractor HSE supervision has created an upstream driver for lifting, electrical, and hot work anomalies.'
  },
  {
    id: 'RISK-ELEC-07',
    category: 'Electrical',
    title: 'Lockout/Tagout (LOTO) Isolation Verification Compliance',
    level: 'Moderate',
    probability: 42,
    confidence: 88,
    trajectory: 'Stable',
    trendPercentage: 0,
    location: 'Substation 03 & Motor Control Centre (MCC)',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-10',
    evidenceStrength: 'Strong',
    mainDriver: 'Zero-energy test step omitted on 2 low-voltage MCC breaker isolations.',
    drivers: [
      '2 isolation certificate audits showed missing multimeter zero-voltage confirmation signature',
      'Padlock color standardization non-compliance on temporary contractor locks'
    ],
    status: 'Monitored',
    orgRecordsCount: 9,
    externalSourcesCount: 3,
    modelsUsedCount: 2,
    summary: 'LOTO procedures remain solid overall, but zero-energy verification audits require automated digital sign-off to eliminate human signature omissions.',
    causalChain: [
      { step: 1, title: 'Routine Motor Maintenance', description: 'Isolation permits requested for cooling pump maintenance.', metricChange: 'Permit Issued' },
      { step: 2, title: 'Zero-Energy Verification Gap', description: 'Multimeter zero-potential test step executed but unrecorded in log.', metricChange: '2 Audits Flagged' },
      { step: 3, title: 'Risk Stabilized', description: 'Digital isolation padlocks and photo verification introduced.', metricChange: 'Stable at 42%' }
    ],
    contributingFactors: [
      { name: 'Digital vs Paper LOTO Logging', percentage: 55, impact: 'Medium', description: 'Paper-based isolation certificates prone to retrospective sign-off.' },
      { name: 'Contractor Padlock Standardization', percentage: 45, impact: 'Low', description: 'Variety of personal locks used instead of standardized keyed-different master set.' }
    ],
    organizationEvidence: [
      { 
        id: 'AUD-310', 
        type: 'Audit Finding', 
        title: 'MCC Substation 3: Isolation log missing second-person witness check', 
        date: '08 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Substation 3', 
        activity: 'Low-voltage motor control breaker isolation',
        hazard: 'Unwitnessed electrical isolation breaker operation',
        risk: 'Inadvertent re-energization / Arc flash hazard',
        severity: 'Medium', 
        status: 'Closed', 
        sourceSystem: 'Sphera Audit Manager',
        details: 'Electrical isolator operated breaker without recorded second-person witness verification step in logbook.', 
        reporterRole: 'Senior Electrical Engineer',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-NFPA-70E', 
        publisher: 'NFPA (National Fire Protection Association)', 
        documentTitle: 'Standard for Electrical Safety in the Workplace: Article 120 Establishing an Electrically Safe Work Condition', 
        documentType: 'Technical Guidance',
        code: 'NFPA 70E / 2026', 
        jurisdiction: 'United States / Global',
        publicationDate: '2026', 
        revisionVersion: '2026 Edition',
        verificationStatus: 'Verified',
        reliability: 'Very High', 
        topic: 'Zero Energy State & Test Before Touch', 
        sourceReference: 'NFPA 70E Art. 120.5: Process for Establishing & Verifying an Electrically Safe Work Condition',
        keyExcerpt: 'Test-before-touch with an adequately rated voltage detector is the definitive requirement for establishing electrically safe work conditions.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-ELEC-07',
      trend: '0% Variance (Stable)',
      baseline: '100% digital isolation protocol adherence',
      currentValue: '98% compliance across Substation 3',
      deviation: '-2% transient deviation, resolved',
      historicalComparison: 'Consistently low electrical hazard rate over past 12 months.',
      contributingFactors: [
        { name: 'Digital vs Paper LOTO Logging', percentage: 55, impact: 'Medium', description: 'Paper-based isolation certificates prone to retrospective sign-off.' },
        { name: 'Contractor Padlock Standardization', percentage: 45, impact: 'Low', description: 'Variety of personal locks used instead of standardized keyed-different master set.' }
      ],
      modelTechnique: 'LOTO Compliance Markov Chain Model',
      confidenceInterval: '95% CI [82% - 93%]',
      isSimulated: true
    },
    aiReasoning: 'LOTO procedural discipline is high, but automated digital interlocking and zero-voltage witness checks will prevent complacency.'
  },
  {
    id: 'RISK-PPE-08',
    category: 'PPE Compliance',
    title: 'Specialized Respiratory & Eye Protection Compliance in Grinding Bays',
    level: 'Low',
    probability: 38,
    confidence: 80,
    trajectory: 'Decreasing',
    trendPercentage: -8,
    location: 'Fabrication Hall Grinding Bay',
    site: 'Lagos Operations',
    identifiedDate: '2026-08-05',
    evidenceStrength: 'Moderate',
    mainDriver: 'Face shield usage improved following introduction of auto-darkening grinding hoods.',
    drivers: [
      '94% compliance observed during latest HSE walkabout',
      'Dust extraction filter change completed on schedule'
    ],
    status: 'Monitored',
    orgRecordsCount: 8,
    externalSourcesCount: 2,
    modelsUsedCount: 1,
    summary: 'Eye and face protection non-conformances in grinding zones have dropped 8% following ergonomic PPE upgrades.',
    causalChain: [
      { step: 1, title: 'PPE Ergonomic Upgrade', description: 'Comfortable auto-darkening grinding visors distributed.', metricChange: 'Visors Issued' },
      { step: 2, title: 'Field Compliance Rise', description: 'Weekly observation audits showed 94% full shield adoption.', metricChange: '94% Compliance' },
      { step: 3, title: 'Downward Risk Trajectory', description: 'Corneal foreign body near-misses dropped to zero in August.', metricChange: 'Trend -8%' }
    ],
    contributingFactors: [
      { name: 'Equipment Ergonomics & Fogging Resistance', percentage: 65, impact: 'Low', description: 'Anti-fog coatings improving compliance during humid coastal afternoons.' },
      { name: 'Supervisor Spot Checks', percentage: 35, impact: 'Low', description: 'Regular shift supervisor verifications at booth entries.' }
    ],
    organizationEvidence: [
      { 
        id: 'OBS-0980', 
        type: 'Observation', 
        title: 'Worker noted using safety glasses without secondary face shield', 
        date: '04 Aug 2026', 
        site: 'Lagos Operations',
        location: 'Grinding Booth 2', 
        activity: 'Weld seam grinding and slag removal',
        hazard: 'High-speed metal particulate discharge without secondary shield',
        risk: 'Eye penetration / Facial laceration',
        severity: 'Low', 
        status: 'Closed', 
        sourceSystem: 'Intelex HSE Cloud',
        details: 'Operator coached and provided new full-face shield to wear with safety spectacles.', 
        reporterRole: 'Safety Warden',
        isSimulated: true
      }
    ],
    externalEvidence: [
      { 
        id: 'EXT-ANSI-Z87', 
        publisher: 'ANSI / ISEA', 
        documentTitle: 'Occupational and Educational Personal Eye and Face Protection Devices', 
        documentType: 'Technical Guidance',
        code: 'ANSI/ISEA Z87.1-2025', 
        jurisdiction: 'United States / Global',
        publicationDate: '2025', 
        revisionVersion: '2025 Standard',
        verificationStatus: 'Verified',
        reliability: 'Very High', 
        topic: 'Impact-rated Eye and Face Protection', 
        sourceReference: 'ANSI Z87.1 § 6: Impact Rating & Dual-Protection Requirements for High-Velocity Particle Generators',
        keyExcerpt: 'Full face shields must always be worn in conjunction with impact-rated primary eye protection when operating rotary grinding discs.',
        isSimulated: true
      }
    ],
    analyticalEvidence: {
      id: 'ANA-PPE-08',
      trend: '-8% 30-Day Hazard Trend',
      baseline: '86% PPE compliance rate',
      currentValue: '94% PPE compliance rate',
      deviation: '+8% positive behavioral compliance delta',
      historicalComparison: 'Highest PPE adherence recorded in 12 months.',
      contributingFactors: [
        { name: 'Equipment Ergonomics & Fogging Resistance', percentage: 65, impact: 'Low', description: 'Anti-fog coatings improving compliance during humid coastal afternoons.' },
        { name: 'Supervisor Spot Checks', percentage: 35, impact: 'Low', description: 'Regular shift supervisor verifications at booth entries.' }
      ],
      modelTechnique: 'Behavioral Compliance Trend Model',
      confidenceInterval: '95% CI [72% - 88%]',
      isSimulated: true
    },
    aiReasoning: 'Consistent downward trend supported by high worker adoption and reliable PPE inventory management.'
  }
];

export const RISK_TREND_90_DAYS = [
  { day: 'Day 1', date: 'Jun 02', overall: 64, lifting: 52, vehicle: 48, processSafety: 55, height: 50 },
  { day: 'Day 10', date: 'Jun 11', overall: 66, lifting: 54, vehicle: 49, processSafety: 58, height: 51 },
  { day: 'Day 20', date: 'Jun 21', overall: 65, lifting: 56, vehicle: 50, processSafety: 56, height: 49 },
  { day: 'Day 30', date: 'Jul 01', overall: 68, lifting: 59, vehicle: 52, processSafety: 60, height: 52 },
  { day: 'Day 40', date: 'Jul 11', overall: 70, lifting: 63, vehicle: 53, processSafety: 62, height: 53 },
  { day: 'Day 50', date: 'Jul 21', overall: 72, lifting: 68, vehicle: 55, processSafety: 64, height: 52 },
  { day: 'Day 60', date: 'Jul 31', overall: 74, lifting: 72, vehicle: 58, processSafety: 66, height: 54 },
  { day: 'Day 70', date: 'Aug 10', overall: 75, lifting: 74, vehicle: 59, processSafety: 67, height: 55 },
  { day: 'Day 80', date: 'Aug 20', overall: 77, lifting: 76, vehicle: 60, processSafety: 68, height: 54 },
  { day: 'Day 90', date: 'Aug 30', overall: 78, lifting: 78, vehicle: 61, processSafety: 69, height: 54 }
];

export const HISTORICAL_COMPARISON_DATA = [
  { period: 'Q2 2025 (Project Alpha)', liftHours: 1420, observations: 8, nearMisses: 1, incidentRate: 0.12, riskScore: 52 },
  { period: 'Q4 2025 (Pipeline Expansion)', liftHours: 2100, observations: 19, nearMisses: 4, incidentRate: 0.88, riskScore: 84 },
  { period: 'Q1 2026 (Maintenance Surge)', liftHours: 1650, observations: 11, nearMisses: 2, incidentRate: 0.35, riskScore: 61 },
  { period: 'Current 90D (Lagos Operations)', liftHours: 2340, observations: 14, nearMisses: 2, incidentRate: 0.00, riskScore: 78 }
];

export const KNOWLEDGE_DOCUMENTS: KnowledgeDocument[] = [
  // 1. GLOBAL SAFETY KNOWLEDGE (Regulators, Government agencies, Research, Industry bodies, Safety alerts)
  {
    id: 'KNOW-001',
    source: 'Health and Safety Executive (HSE)',
    sourceAuthority: 'Health and Safety Executive (HSE UK Regulatory Body)',
    title: 'LOLER 1998: Lifting Operations and Lifting Equipment Regulations Safe Work Guidance',
    documentCode: 'HSE UK / L113 / 2026 Ed',
    type: 'Regulatory Standard',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United Kingdom / Europe',
    publicationDate: '2026-01-15',
    lastUpdated: '2026-08-10',
    revision: 'Rev 4.2 (2026 Statutory Amendment)',
    reviewDate: '2027-01-15',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Lifting Operations', 'Equipment Certification', 'Safe Working Load (SWL)', 'LOLER'],
    applicableIndustries: ['Oil & Gas', 'Engineering', 'Construction', 'Maritime', 'Energy'],
    summary: 'Statutory regulation on thorough examination, planning of lifting operations, operator competency, and rigging equipment maintenance.',
    extractedKeyRules: [
      'Every lifting operation must be properly planned by a competent person.',
      'Equipment used for lifting persons must be thoroughly examined at least every 6 months.',
      'Lifting accessories (slings, shackles, spreader beams) require 6-monthly independent NDT certification.',
      'Marking of safe working load (SWL) must be clearly visible on all components.'
    ],
    verificationHistory: [
      { date: '2026-08-10', action: 'Regulatory Digest Synchronized', reviewer: 'SIE Automated Regulatory Ingester v3.2', notes: 'Checked against UK National Archives API. Zero amendments pending.' },
      { date: '2026-08-12', action: 'HSE Expert Certification', reviewer: 'Dr. Alistair Vance (Chartered Safety Fellow)', notes: 'Verified rules mapped directly to lifting risk prediction vectors.' }
    ]
  },
  {
    id: 'KNOW-002',
    source: 'OSHA (Occupational Safety and Health Administration)',
    sourceAuthority: 'United States Department of Labor / OSHA',
    title: '29 CFR 1926 Subpart CC: Cranes and Derricks in Construction Standard',
    documentCode: 'OSHA 1926.1400-1442',
    type: 'Regulatory Standard',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United States (Federal)',
    publicationDate: '2025-11-20',
    lastUpdated: '2026-07-18',
    revision: '2025 Standard Update',
    reviewDate: '2026-11-20',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Crane Safety', 'Ground Bearing Capacity', 'Signal Person Qualification', 'Power Line Proximity'],
    applicableIndustries: ['Construction', 'Engineering', 'Oil & Gas', 'Energy'],
    summary: 'Comprehensive OSHA standard governing crane assembly/disassembly, ground stability assessment, power line clearance, and operator certification.',
    extractedKeyRules: [
      'Ground conditions must be inspected and confirmed capable of supporting crane and maximum load.',
      'Dedicated qualified signal person required when operator point of operation is obscured.',
      'Minimum clearance of 20 feet from overhead power lines up to 350 kV.'
    ],
    verificationHistory: [
      { date: '2026-07-18', action: 'Verified & Indexed', reviewer: 'SIE Legal & Compliance Ingestion Agent', notes: 'Cross-checked with Federal Register. No active judicial stays.' }
    ]
  },
  {
    id: 'KNOW-004',
    source: 'National Institute for Occupational Safety and Health (NIOSH)',
    sourceAuthority: 'NIOSH / CDC Center for Disease Control',
    title: 'Criteria for a Recommended Standard: Occupational Exposure in Confined Spaces',
    documentCode: 'NIOSH Pub 80-106 / 2026 Re-evaluation',
    type: 'Research Paper',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United States / Global Research',
    publicationDate: '2026-03-01',
    lastUpdated: '2026-08-01',
    revision: '2026 Scientific Synthesis',
    reviewDate: '2027-03-01',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'High',
    freshness: 'Current',
    topics: ['Confined Space', 'Toxic Atmosphere', 'Ventilation Dynamics', 'Rescue Protocols'],
    applicableIndustries: ['Oil & Gas', 'Manufacturing', 'Maritime', 'Mining', 'Energy'],
    summary: 'Scientific analysis of atmospheric stratification, toxic gas pockets, and physiological effects of oxygen deficiency during tank desludging.',
    extractedKeyRules: [
      'Atmospheric testing must sample top, middle, and bottom of space due to varying vapor densities.',
      'Forced mechanical ventilation must deliver at least 20 air changes per hour for hazardous spaces.'
    ],
    verificationHistory: [
      { date: '2026-08-01', action: 'Peer Review Ingestion', reviewer: 'Industrial Hygiene Working Group', notes: 'Integrated into continuous air testing advisory algorithms.' }
    ]
  },
  {
    id: 'KNOW-007',
    source: 'Health and Safety Executive (HSE)',
    sourceAuthority: 'Health and Safety Executive (HSE Construction Division)',
    title: 'Guidance on Scaffolding and Temporary Access Structures: Advanced Fall Arrest Anchor Testing',
    documentCode: 'HSE UK / CIS10 / Draft 2026',
    type: 'Technical Guidance',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United Kingdom',
    publicationDate: '2026-08-20',
    lastUpdated: '2026-08-28',
    revision: 'Draft Revision for Public Consultation',
    reviewDate: '2026-09-30',
    verification: 'Pending Review',
    verificationStatus: 'Pending Review',
    reliability: 'High',
    freshness: 'Recently Updated',
    topics: ['Working at Height', 'Scaffold Tagging', 'Fall Arrest', 'Anchor Testing'],
    applicableIndustries: ['Construction', 'Engineering', 'Oil & Gas'],
    summary: 'New proposed guidance on wireless torque verification for temporary scaffold clamp anchors.',
    extractedKeyRules: [
      'Scaffold clamp torque must be checked using calibrated wireless torque wrenches with digital logging.',
      'All temporary anchor eye bolts require 10 kN pull test certification before initial worker attachment.'
    ],
    verificationHistory: [
      { date: '2026-08-28', action: 'Candidate Source Ingested', reviewer: 'System Ingestion Bot', notes: 'Pending safety committee approval before inclusion in risk model weighting.' }
    ]
  },
  {
    id: 'KNOW-008',
    source: 'International Marine Contractors Association (IMCA)',
    sourceAuthority: 'IMCA Marine & Subsea Safety Secretariat',
    title: 'Safety Flash 2026-04: UV & Salt Degradation Precursors in Synthetic Rigging',
    documentCode: 'IMCA SF-26-04',
    type: 'Safety Alert',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'International Maritime & Offshore',
    publicationDate: '2026-08-15',
    lastUpdated: '2026-08-25',
    revision: 'Immediate Action Bulletin',
    reviewDate: '2026-11-15',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Recently Updated',
    topics: ['Synthetic Slings', 'UV Exposure', 'Offshore Lifting', 'Parting Precursors'],
    applicableIndustries: ['Maritime', 'Oil & Gas', 'Energy'],
    summary: 'Global safety alert detailing accelerated polymer embrittlement on deck-stored round slings in tropical maritime operations.',
    extractedKeyRules: [
      'Synthetic slings exposed to direct sunlight >30 days must undergo load-bearing core fiber inspection.',
      'Color fading beyond RAL standard 1021 indicates UV threshold exceeded; quarantine mandatory.'
    ],
    verificationHistory: [
      { date: '2026-08-25', action: 'Safety Alert Ingested', reviewer: 'Dr. Fatima Bello', notes: 'Cross-referenced against Yard 4 sling storage audit findings.' }
    ]
  },

  // 2. INDUSTRY KNOWLEDGE (Sector-specific knowledge: Oil & Gas, Construction, Manufacturing, Energy, Maritime, Mining)
  {
    id: 'KNOW-003',
    source: 'American Petroleum Institute (API)',
    sourceAuthority: 'API Upstream Committee on Safety & Fire Protection',
    title: 'API RP 54: Recommended Practice for Occupational Safety for Oil and Gas Well Drilling and Servicing Operations',
    documentCode: 'API RP 54 4th Edition',
    type: 'Industry Benchmark',
    domain: 'Industry Knowledge',
    jurisdiction: 'Global Hydrocarbon Standards',
    publicationDate: '2025-06-10',
    lastUpdated: '2026-06-22',
    revision: '4th Edition (2025 reaffirmed)',
    reviewDate: '2027-06-10',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Process Safety', 'Drilling Operations', 'Hydrogen Sulfide (H2S)', 'Blowout Prevention'],
    applicableIndustries: ['Oil & Gas', 'Energy'],
    summary: 'Industry consensus standard for safety systems, pressure containment, personnel protective protocols, and emergency response in hydrocarbons.',
    extractedKeyRules: [
      'Permit-to-work mandatory for hot work within 35 feet of wellbore or hydrocarbon vessels.',
      'Acoustic or sensor inspection required for manifolds operating above 250 psi cyclic pressure.',
      'Personal H2S electronic monitors required for all personnel in designated Zone 1/2.'
    ],
    verificationHistory: [
      { date: '2026-06-22', action: 'Standard Endorsement', reviewer: 'Process Safety Committee', notes: 'Approved for automatic weighting in process safety prediction models.' }
    ]
  },
  {
    id: 'KNOW-005',
    source: 'International Labour Organization (ILO)',
    sourceAuthority: 'ILO Sectoral Advisory Body for Maritime Transport',
    title: 'Code of Practice on Safety and Health in Ports & Maritime Logistics',
    documentCode: 'ILO-OSH Port Code / Rev 2025',
    type: 'Technical Guidance',
    domain: 'Industry Knowledge',
    jurisdiction: 'International Maritime Ports',
    publicationDate: '2025-09-14',
    lastUpdated: '2026-05-19',
    revision: 'Revision 2025',
    reviewDate: '2027-09-14',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Vehicle Movement', 'Port Logistics', 'Pedestrian Separation', 'Night Operations'],
    applicableIndustries: ['Maritime', 'Oil & Gas', 'Manufacturing'],
    summary: 'International guidelines for vehicle-pedestrian segregation, quay crane buffer zones, and illumination minimums in industrial terminals.',
    extractedKeyRules: [
      'Pedestrian walkways must be physically protected by rigid bollards or barriers in heavy vehicle zones.',
      'Active container/material handling areas must maintain a minimum average illuminance of 50 lux.'
    ],
    verificationHistory: [
      { date: '2026-05-19', action: 'Ingested & Calibrated', reviewer: 'Logistics Safety Panel', notes: 'Used to calibrate Lagos Logistics Gate 2 risk scoring.' }
    ]
  },
  {
    id: 'KNOW-009',
    source: 'Energy Institute (EI)',
    sourceAuthority: 'Energy Institute Process Safety Committee',
    title: 'EI Model Code of Safe Practice Part 15: Area Classification for Installations Handling Flammable Fluids',
    documentCode: 'EI-15 Rev 5',
    type: 'Technical Guidance',
    domain: 'Industry Knowledge',
    jurisdiction: 'Global Energy Sector',
    publicationDate: '2025-04-12',
    lastUpdated: '2026-04-12',
    revision: '5th Edition Rev B',
    reviewDate: '2028-04-12',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Hazardous Area Classification', 'Flammable Fluids', 'Zone 0/1/2 Boundaries', 'ATEX/IECEx'],
    applicableIndustries: ['Energy', 'Oil & Gas', 'Manufacturing'],
    summary: 'Definitive engineering code for calculating hazardous release envelope radius and equipment protection levels across energy assets.',
    extractedKeyRules: [
      'Flange connections operating above 50 barg require 3.5m Zone 2 secondary envelope radius.',
      'Fixed combustible gas detectors must trigger auto-deluge or trip at 20% LEL threshold.'
    ],
    verificationHistory: [
      { date: '2026-04-12', action: 'Direct Integration', reviewer: 'Engr. Emeka Nwosu', notes: 'Applied to compression skid B gas monitoring alarms.' }
    ]
  },
  {
    id: 'KNOW-010',
    source: 'Mining & Metallurgical Safety Board (MMSB)',
    sourceAuthority: 'International Council on Mining and Metals (ICMM)',
    title: 'Critical Control Management in Surface Mining Haulage & Heavy Fleet Operations',
    documentCode: 'ICMM-CCM-MINING-2025',
    type: 'Industry Benchmark',
    domain: 'Industry Knowledge',
    jurisdiction: 'Global Mining & Quarrying',
    publicationDate: '2025-01-30',
    lastUpdated: '2026-02-14',
    revision: 'Standard 2025.1',
    reviewDate: '2027-01-30',
    verification: 'Verified',
    verificationStatus: 'Verified',
    reliability: 'Very High',
    freshness: 'Current',
    topics: ['Heavy Haulage', 'Fatigue Detection', 'Collision Avoidance', 'Berm Standards'],
    applicableIndustries: ['Mining', 'Construction', 'Manufacturing'],
    summary: 'Industry best practices for autonomous/manual haul truck collision avoidance, proximity radar, and haul road safety berm design.',
    extractedKeyRules: [
      'Safety berms must equal at least 50% of the largest tire diameter operating on haul roads.',
      'Proximity detection systems must initiate auto-braking when worker RFID transponder enters 15m radius.'
    ],
    verificationHistory: [
      { date: '2026-02-14', action: 'Benchmark Indexed', reviewer: 'Fleet Safety Committee', notes: 'Used as comparative model for Yard 4 mobile plant.' }
    ]
  },

  // 3. ORGANIZATION KNOWLEDGE (Private organization-specific: Policies, Procedures, Risk assessments, Incident reports, Lessons learned, Internal standards)
  {
    id: 'KNOW-006',
    source: 'Demo Energy & Engineering Ltd. (Private Internal)',
    sourceAuthority: 'Corporate HSE & Technical Assurance Board',
    title: 'SOP-HSE-042: Critical Lift Planning, Tandem Rigging & SIMOPS Execution Procedure',
    documentCode: 'DEE-SOP-LIFT-042-Rev6',
    type: 'Internal SOP',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Organization (Demo Energy & Engineering Ltd.)',
    publicationDate: '2026-02-10',
    lastUpdated: '2026-08-15',
    revision: 'Rev 6.0 (2026 Mandatory Release)',
    reviewDate: '2027-02-10',
    verification: 'Verified',
    verificationStatus: 'Audited',
    reliability: 'Very High',
    freshness: 'Current',
    organizationScope: 'Organization-scoped knowledge (Private Tenant Isolation)',
    topics: ['Lifting Operations', 'Tandem Lifts', 'Permit-to-Work', 'Tag Line Usage'],
    applicableIndustries: ['Oil & Gas', 'Engineering', 'Construction'],
    summary: 'Company-mandatory standard for lifts exceeding 10 tonnes, lifts over live piping, or tandem crane lifts.',
    extractedKeyRules: [
      'Lifts above 10 tonnes require Engineering Category 3 lift plan approved by Technical Director.',
      'Mandatory double synthetic tag line attachment on all loads >6 meters length.',
      'Wind speed limit strictly capped at 20 knots (10.2 m/s) for suspended loads with area >15 m².'
    ],
    verificationHistory: [
      { date: '2026-08-15', action: 'Internal Policy Verification', reviewer: 'Lead HSE Director', notes: 'Updated with mandatory QR code tag verification.' }
    ]
  },
  {
    id: 'KNOW-011',
    source: 'Demo Energy & Engineering Ltd. (Private Internal)',
    sourceAuthority: 'Corporate Health, Safety & Environment Committee',
    title: 'POL-HSE-001: Golden Safety Rules & Stop-Work Authority Directive',
    documentCode: 'DEE-POL-GOLDEN-2026',
    type: 'Policy',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Organization (Demo Energy & Engineering Ltd.)',
    publicationDate: '2026-01-05',
    lastUpdated: '2026-07-01',
    revision: 'Rev 4.0',
    reviewDate: '2027-01-05',
    verification: 'Verified',
    verificationStatus: 'Audited',
    reliability: 'Very High',
    freshness: 'Current',
    organizationScope: 'Organization-scoped knowledge (Private Tenant Isolation)',
    topics: ['Stop Work Authority', 'Golden Rules', 'Life Saving Controls', 'Accountability'],
    applicableIndustries: ['Oil & Gas', 'Construction', 'Energy', 'Maritime'],
    summary: '10 Mandatory Golden Rules covering Energy Isolation, Confined Space Entry, Lifting Operations, Working at Height, and Driving Safety.',
    extractedKeyRules: [
      '100% unconditional Stop-Work Authority granted to all employees and contractors without fear of reprisal.',
      'Bypassing a safety critical barrier without management written MOC constitutes immediate suspension.'
    ],
    verificationHistory: [
      { date: '2026-07-01', action: 'Annual Policy Attestation', reviewer: 'CEO & VP Operations', notes: 'Re-signed and deployed across all operating sites.' }
    ]
  },
  {
    id: 'KNOW-012',
    source: 'Demo Energy & Engineering Ltd. (Private Internal)',
    sourceAuthority: 'Operations Risk Assessment Working Group',
    title: 'HIRA-Y4-2026: Hazard Identification & Risk Assessment for Yard 4 Heavy Fabrication Pad',
    documentCode: 'DEE-HIRA-Y4-0826',
    type: 'Risk Assessment',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Organization (Demo Energy & Engineering Ltd.)',
    publicationDate: '2026-06-15',
    lastUpdated: '2026-08-20',
    revision: 'Rev 2.1 (Turnaround Update)',
    reviewDate: '2026-12-15',
    verification: 'Verified',
    verificationStatus: 'Audited',
    reliability: 'Very High',
    freshness: 'Recently Updated',
    organizationScope: 'Organization-scoped knowledge (Private Tenant Isolation)',
    topics: ['Yard 4 Staging', 'Crane Walkways', 'SIMOPS', 'Welding Bays'],
    applicableIndustries: ['Oil & Gas', 'Construction', 'Engineering'],
    summary: 'Comprehensive quantitative risk baseline assessing dropped objects, simultaneous operations (SIMOPS), and heavy transporter traffic in Yard 4.',
    extractedKeyRules: [
      'Max ground load rating on Yard 4 Pad B is 180 kN/m²; outrigger mats mandatory for all crane setups.',
      'SIMOPS exclusion radius of 25m required around active hydrotesting operations.'
    ],
    verificationHistory: [
      { date: '2026-08-20', action: 'HIRA Review & Audit', reviewer: 'Marcus Adebayo', notes: 'Integrated into continuous yard precursor anomaly detector.' }
    ]
  },
  {
    id: 'KNOW-013',
    source: 'Demo Energy & Engineering Ltd. (Private Internal)',
    sourceAuthority: 'Major Incident Investigation Board',
    title: 'INC-2025-084-LL: Lessons Learned from Q4 2025 Spreader Beam Near-Miss at Berth 2',
    documentCode: 'DEE-LL-2025-084',
    type: 'Incident Report',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Organization (Demo Energy & Engineering Ltd.)',
    publicationDate: '2025-11-28',
    lastUpdated: '2026-01-10',
    revision: 'Final Investigation Report',
    reviewDate: '2026-11-28',
    verification: 'Verified',
    verificationStatus: 'Audited',
    reliability: 'High',
    freshness: 'Current',
    organizationScope: 'Organization-scoped knowledge (Private Tenant Isolation)',
    topics: ['Near Miss Investigation', 'Root Cause Analysis', 'Spreader Beam Tagging', 'Lifting Gear'],
    applicableIndustries: ['Oil & Gas', 'Maritime', 'Construction'],
    summary: 'Comprehensive investigation into uncertified spreader beam deployed during barge loading. Corrective actions mandated centralized digital gear passports.',
    extractedKeyRules: [
      'Rigging storekeeper must perform daily physical scan against digital asset registry before issuing gear.',
      'Quarantine lockers must be fitted with dual-custody physical padlocks.'
    ],
    verificationHistory: [
      { date: '2026-01-10', action: 'CAPA Verification Closed', reviewer: 'HSE Assurance Director', notes: 'Historical failure mode linked to Recurring Risk Detection Module.' }
    ]
  },
  {
    id: 'KNOW-014',
    source: 'Demo Energy & Engineering Ltd. (Private Internal)',
    sourceAuthority: 'Electrical Engineering Standards Committee',
    title: 'STD-ELEC-018: Standard for Temporary Electrical Installations & Generator Grounding (Draft 2024)',
    documentCode: 'DEE-STD-ELEC-018-2024',
    type: 'Internal Standard',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Organization (Demo Energy & Engineering Ltd.)',
    publicationDate: '2024-04-10',
    lastUpdated: '2024-04-10',
    revision: 'Rev 1.0 (Archived)',
    reviewDate: '2025-04-10',
    verification: 'Flagged',
    verificationStatus: 'Flagged',
    reliability: 'Moderate',
    freshness: 'Review Required',
    organizationScope: 'Organization-scoped knowledge (Private Tenant Isolation)',
    topics: ['Temporary Power', 'Earth Resistance', 'RCD Testing', 'Generator Skids'],
    applicableIndustries: ['Engineering', 'Construction'],
    summary: 'Legacy internal specification for site portable generators. Earth electrode test criteria requires harmonization with IEEE 81 2026 revision.',
    extractedKeyRules: [
      'Earth rod resistance must not exceed 10 ohms prior to energization.',
      'RCD sensitivity must be tested weekly at 30mA threshold.'
    ],
    verificationHistory: [
      { date: '2026-08-01', action: 'Flagged for Review', reviewer: 'SIE Compliance Bot', notes: 'Review overdue by >400 days. Flagged in Knowledge Center.' }
    ]
  }
];

export const INTERVENTIONS: InterventionItem[] = [
  {
    id: 'INT-LIFT-2026-01',
    title: 'Targeted Lifting Safety Campaign & Rigging Integrity Reset',
    targetRiskId: 'RISK-LIFT-01',
    targetRiskCategory: 'Lifting Operations',
    priority: 'Immediate',
    reason: 'Elevated lifting risk detected (78% probability) with 14 observations and 3 overdue gear inspections.',
    status: 'Active',
    dateRecommended: '2026-08-28',
    assignee: 'Marcus Adebayo (Operations Superintendent)',
    deadline: '2026-09-10',
    recommendedActions: [
      { id: 1, title: 'Conduct Focused Lifting Inspection Campaign', description: 'Inspect 100% of rigging lofts in Yard 4 and Pier 2; quarantine un-tagged slings immediately.', assignedRole: 'Lifting Superintendent', completed: true },
      { id: 2, title: 'Mandatory Supervisor Toolbox Talk', description: 'Deliver interactive briefing on tag line discipline, load stability, and wind gust thresholds.', assignedRole: 'Area HSE Supervisors', completed: true },
      { id: 3, title: 'Review & Re-approve High-tonnage Lifting Plans', description: 'Audit all pending >10t lift plans against SOP-HSE-042 Rev 6 before crane mobilization.', assignedRole: 'Senior Rigging Engineer', completed: false },
      { id: 4, title: 'Verify Crane Operator & Rigger Competency Passports', description: 'Audit contractor personnel cards against LMS database; suspend non-verified riggers.', assignedRole: 'Competency Lead', completed: false },
      { id: 5, title: 'Close 3 Overdue Rigging Corrective Actions', description: 'Expedite third-party NDT certification for spreader beams SB-401 and SB-402.', assignedRole: 'Maintenance Lead', completed: false }
    ],
    expectedIndicators: [
      { metric: 'Observation Frequency', expectedShift: '↓ 25% within 14 days' },
      { metric: 'Rigging Control Compliance', expectedShift: '↑ 20% in field audits' },
      { metric: 'Near-Miss Frequency', expectedShift: '↓ 40% over 30 days' }
    ],
    outcomeData: {
      baselineRisk: 78,
      currentRisk: 51,
      observationShift: '-24%',
      complianceShift: '+18%',
      nearMissShift: '-33%',
      verdict: 'Likely Effective',
      confidence: 76,
      evaluationPeriod: 'Post-intervention Day 18 Evaluation',
      expertAssessments: [
        {
          id: 'EXP-01',
          expertName: 'Capt. Tunde Bakare',
          role: 'Offshore Marine & Lifting Specialist',
          date: '2026-08-30',
          rating: 'Effective',
          comments: 'Quarantining the uncertified spreader beams in Yard 4 immediately stopped the unsafe rigging practices. Recommend keeping the weekly supervisor audits active for 60 more days.'
        }
      ]
    }
  },
  {
    id: 'INT-VEH-2026-02',
    title: 'Nocturnal Logistics Separation & Gate 2 Lighting Overhaul',
    targetRiskId: 'RISK-VEH-02',
    targetRiskCategory: 'Vehicle Movement',
    priority: 'High',
    reason: '61% risk score driven by flatbed night transfers and lighting degradation at Gate 2 buffer.',
    status: 'Recommended',
    dateRecommended: '2026-08-29',
    assignee: 'Emeka Nwosu (Logistics Base Manager)',
    deadline: '2026-09-08',
    recommendedActions: [
      { id: 1, title: 'Mobilize 2 High-Output Solar Mobile Light Towers', description: 'Deploy immediate auxiliary lighting (min 60 lux) at Gate 2 truck maneuvering area.', assignedRole: 'Facilities Maintenance' },
      { id: 2, title: 'Establish Dedicated Pedestrian Interlocking Corridors', description: 'Install water-filled barrier walkway separating foot traffic from trailer reversing path.', assignedRole: 'Civil Works Team' },
      { id: 3, title: 'Enforce Dedicated Reversing Spotters for Night Lifts', description: 'Mandate reflective-vest spotter with illuminated wands for every flatbed reversing motion.', assignedRole: 'Logistics Supervisor' }
    ],
    expectedIndicators: [
      { metric: 'Illuminance Level', expectedShift: '↑ to >65 Lux' },
      { metric: 'Pedestrian Barrier Non-compliance', expectedShift: '↓ 80%' },
      { metric: 'Telematics Harsh Braking Events', expectedShift: '↓ 50%' }
    ]
  },
  {
    id: 'INT-PS-2026-03',
    title: 'Compression Train B Flange Integrity & Acoustic Surveillance Protocol',
    targetRiskId: 'RISK-PS-03',
    targetRiskCategory: 'Process Safety',
    priority: 'Immediate',
    reason: 'Acoustic resonance spikes (142 Hz) and 40ppm sniffing trace on high-pressure gas header.',
    status: 'Active',
    dateRecommended: '2026-08-27',
    assignee: 'Dr. Fatima Bello (Process Integrity Superintendent)',
    deadline: '2026-09-03',
    recommendedActions: [
      { id: 1, title: 'Execute Hot Controlled Flange Torque Verification', description: 'Re-torque flange B-104 bolts using calibrated hydraulic tensioning equipment.', assignedRole: 'Mechanical Integrity Team', completed: true },
      { id: 2, title: 'Install Continuous Optical Gas Imaging (OGI) Surveillance Camera', description: 'Mount temporary FLIR infrared gas detection camera focused on Train B manifold.', assignedRole: 'Instrumentation Team', completed: true },
      { id: 3, title: 'Expedite Spiral Wound Gasket Supply for Train B Skid', description: 'Air freight replacement 600# Inconel gaskets for scheduled short shutdown.', assignedRole: 'Procurement Specialist', completed: false }
    ],
    expectedIndicators: [
      { metric: 'Acoustic Micro-leak Amplitude', expectedShift: '↓ 85%' },
      { metric: 'Sniffer ppm reading', expectedShift: '0 ppm (ND)' },
      { metric: 'Predictive Loss-of-Containment Risk', expectedShift: '↓ 69% to <15%' }
    ]
  }
];

export const DATA_SOURCES: DataIngestionSource[] = [
  {
    id: 'SRC-01',
    name: 'Safelytic Core HSE Database',
    type: 'Safelytic Core',
    connected: true,
    recordsProcessed: 142850,
    lastSync: '2 minutes ago',
    dataQualityScore: 98,
    syncFrequency: 'Real-time WebSocket / Change Data Capture',
    statusText: 'Synchronizing Live Events'
  },
  {
    id: 'SRC-02',
    name: 'Enterprise SAP / Oracle ERP',
    type: 'Enterprise ERP',
    connected: true,
    recordsProcessed: 89400,
    lastSync: '14 minutes ago',
    dataQualityScore: 95,
    syncFrequency: 'Every 15 minutes via REST API',
    statusText: 'Work Orders & Hours Worked Synced'
  },
  {
    id: 'SRC-03',
    name: 'Field Inspection & Audit Spreadsheets',
    type: 'Excel / CSV',
    connected: true,
    recordsProcessed: 31200,
    lastSync: '1 hour ago',
    dataQualityScore: 89,
    syncFrequency: 'Automated SFTP / S3 Bucket Ingestion',
    statusText: 'Validated with schema checks'
  },
  {
    id: 'SRC-04',
    name: 'Legacy Intelex / Enablon EHS Connector',
    type: 'External EHS',
    connected: true,
    recordsProcessed: 48900,
    lastSync: '35 minutes ago',
    dataQualityScore: 92,
    syncFrequency: 'Hourly Batch Sync',
    statusText: 'Historical Incident Sync Active'
  },
  {
    id: 'SRC-05',
    name: 'Field IoT Telemetry (Crane Sensors & Gas Detectors)',
    type: 'IoT Telemetry',
    connected: true,
    recordsProcessed: 1240000,
    lastSync: '5 seconds ago',
    dataQualityScore: 96,
    syncFrequency: 'Streaming MQTT / Kafka Topic',
    statusText: 'Active Stream: 420 msgs/sec'
  },
  {
    id: 'SRC-06',
    name: 'Workforce Competency LMS API',
    type: 'REST Webhook API',
    connected: true,
    recordsProcessed: 18450,
    lastSync: '20 minutes ago',
    dataQualityScore: 97,
    syncFrequency: 'Event Webhook on Training Completion',
    statusText: 'Certifications & Passports Live'
  }
];

export const SAFETY_DATA_METRICS = {
  dataQualityScore: 94,
  incidentsCount: 38,
  nearMissesCount: 142,
  observationsCount: 1284,
  inspectionsCount: 412,
  auditsCount: 64,
  trainingRecordsCount: 3950,
  correctiveActionsTotal: 342,
  correctiveActionsOverdue: 14,
  permitsActive: 87
};

export const LEARNING_ACTIVITY_TIMELINE: LearningPipelineItem[] = [
  {
    id: 'LRN-101',
    timestamp: '2026-08-30 16:45',
    category: 'Expert Feedback',
    title: 'Expert Feedback Ingested: Lifting Spreader Beam Quarantine',
    description: 'Capt. Tunde Bakare confirmed lifting intervention effectiveness; model increased weight of rigging gear overdue inspection factor by +12%.',
    impactWeightDelta: '+12% Factor Weight',
    systemEffect: 'Higher sensitivity to unverified rigging equipment in Yard 4.'
  },
  {
    id: 'LRN-102',
    timestamp: '2026-08-29 11:20',
    category: 'Intervention Outcome',
    title: 'Closed-Loop Outcome Evaluated: Lifting Campaign Day 18',
    description: 'Post-intervention data shows 24% reduction in lifting observations and 18% improvement in field tag-line compliance.',
    impactWeightDelta: '+0.14 Model Confidence',
    systemEffect: 'Validated predictive accuracy of multi-crane SIMOPS causal model.'
  },
  {
    id: 'LRN-103',
    timestamp: '2026-08-28 09:15',
    category: 'Knowledge Ingested',
    title: 'New Verified Standard Ingested: HSE UK L113 Rev 2026',
    description: 'Updated LOLER statutory rules ingested and mapped to 4 active offshore and fabrication risk models.',
    impactWeightDelta: '46 Rules Added',
    systemEffect: 'Updated baseline compliance checklists for crane certifications.'
  },
  {
    id: 'LRN-104',
    timestamp: '2026-08-26 14:00',
    category: 'Validated Prediction',
    title: 'Prediction Validated: Gate 2 Vehicle Reversing Risk',
    description: 'Logistics near-miss NM-208 confirmed SIE prediction of unlit staging area hazard. Model precision score increased to 88%.',
    impactWeightDelta: '+4.2% Precision',
    systemEffect: 'Increased early-warning threshold trigger for night shift telematics.'
  }
];

export const KNOWLEDGE_INGESTION_ITEMS: KnowledgeIngestionItem[] = [
  {
    id: 'KNOW-ING-01',
    title: 'OSHA 29 CFR 1926 Subpart CC: Cranes & Derricks in Construction',
    category: 'Regulators',
    sourceAuthority: 'Occupational Safety and Health Administration (OSHA)',
    processedDate: '2026-08-30 08:30',
    verificationStatus: 'Verified',
    itemsExtracted: 142,
    summary: 'Statutory requirements for rigging inspection, ground conditions, ground slope tolerances, and dedicated spotters.',
    isSimulated: true
  },
  {
    id: 'KNOW-ING-02',
    title: 'HSE UK L113: Safe Use of Lifting Equipment (LOLER 1998 ACOP 2026 Rev)',
    category: 'Regulators',
    sourceAuthority: 'Health and Safety Executive (HSE UK)',
    processedDate: '2026-08-28 09:15',
    verificationStatus: 'Verified',
    itemsExtracted: 89,
    summary: 'Approved Code of Practice for thorough examination intervals, rigging certification, and load stability derating.',
    isSimulated: true
  },
  {
    id: 'KNOW-ING-03',
    title: 'NIOSH Rigging & Precursor Dynamics in High-Tonnage Tandem Lifts',
    category: 'Research',
    sourceAuthority: 'National Institute for Occupational Safety and Health (NIOSH)',
    processedDate: '2026-08-27 14:20',
    verificationStatus: 'Verified',
    itemsExtracted: 38,
    summary: 'Empirical data on sling angle tension compounding and blind spot collision probabilities during multi-crane lifts.',
    isSimulated: true
  },
  {
    id: 'KNOW-ING-04',
    title: 'API Recommended Practice 54: Occupational Safety for Oil & Gas Well Operations',
    category: 'Industry Sources',
    sourceAuthority: 'American Petroleum Institute (API)',
    processedDate: '2026-08-26 11:00',
    verificationStatus: 'Verified',
    itemsExtracted: 112,
    summary: 'Industry consensus standards for tubular handling, high-pressure line barriers, and offshore mast inspection regimes.',
    isSimulated: true
  },
  {
    id: 'KNOW-ING-05',
    title: 'IMCA Safety Flash 2026-04: Synthetic Round Sling UV & Chemical Degradation',
    category: 'Safety Alerts',
    sourceAuthority: 'International Marine Contractors Association (IMCA)',
    processedDate: '2026-08-25 16:40',
    verificationStatus: 'Verified',
    itemsExtracted: 12,
    summary: 'Global safety alert highlighting accelerated fiber failure in tropical maritime environments with sunlight exposure.',
    isSimulated: true
  },
  {
    id: 'KNOW-ING-06',
    title: 'Safelytic Global Golden Rules: Heavy Lifts, SIMOPS & Confined Space SOP Rev 5',
    category: 'Organization Documents',
    sourceAuthority: 'Corporate HSE & Operations Assurance Board',
    processedDate: '2026-08-29 10:15',
    verificationStatus: 'Audited',
    itemsExtracted: 58,
    summary: 'Internal mandatory barrier requirements, stop-work authority thresholds, and 100% pre-lift tag line mandate.',
    isSimulated: true
  }
];

export const PREDICTIVE_MODEL_MODULES: PredictiveModelModule[] = [
  {
    id: 'MOD-01',
    name: 'Emerging-Risk Detection',
    tagline: 'Bayesian precursor surveillance before incidents occur',
    description: 'Continuously synthesizes leading multi-stream indicators (near misses, safety observations, permit overrides, contractor turnover) to identify statistical risk elevation before incidents materialize.',
    inputDataTypes: ['Safety Observations (1,284)', 'Near-Miss Logs (142)', 'PTW Active Permits (87)', 'Rigging Defect Logs (24)'],
    algorithmType: 'Hierarchical Bayesian Network & Random Forest Ensemble',
    improvementMetric: 'Area Under ROC Curve (AUC-ROC)',
    currentAccuracy: '91.8% AUC-ROC (Precision: 88.4%)',
    lastCalibrated: '2026-08-30 (Automated Batch Calibration)',
    recalibrationMechanism: 'Markov Chain Monte Carlo (MCMC) Bayesian Prior Update'
  },
  {
    id: 'MOD-02',
    name: 'Anomaly Detection',
    tagline: 'Multivariable outlier identification in sensor & operational streams',
    description: 'Detects subtle sensor irregularities, crane harmonic vibration spikes, or sudden statistical drops in hazard reporting frequency from specific subcontractors.',
    inputDataTypes: ['IoT Crane Telematics (420 msgs/s)', 'Acoustic Sniffing Sensors (142 Hz)', 'Shift Reporting Ratios', 'LMS Passport Compliance'],
    algorithmType: 'Isolation Forest & Gaussian Mixture Models (GMM)',
    improvementMetric: 'Outlier Recall / False Positive Rate',
    currentAccuracy: '94.2% Recall (0.8% False Positive Rate)',
    lastCalibrated: '2026-08-31 06:00 (Daily Cycle)',
    recalibrationMechanism: 'Covariance Matrix Recalibration & Dynamic Sigma Thresholding'
  },
  {
    id: 'MOD-03',
    name: 'Trend Forecasting',
    tagline: 'Precursor velocity and 30/60/90-day trajectory modeling',
    description: 'Projects hazard escalation slope and exposure trajectories across yards, offshore facilities, and operational activity disciplines.',
    inputDataTypes: ['Historical 3-Year Incident Series', 'Daily Precursor Counts', 'Production Milestones', 'Man-hour Density'],
    algorithmType: 'Prophet Decomposition & Auto-Regressive Moving Average (ARIMA)',
    improvementMetric: 'Mean Absolute Percentage Error (MAPE)',
    currentAccuracy: '89.6% Directional Accuracy (MAPE: 6.4%)',
    lastCalibrated: '2026-08-29 (Weekly Cycle)',
    recalibrationMechanism: 'Time-Series Residual Error Minimization & Drift Compensation'
  },
  {
    id: 'MOD-04',
    name: 'Recurring-Risk Detection',
    tagline: 'Causal graph matching of chronic failure modes across historical cycles',
    description: 'Identifies systemic recurring patterns where past CAPA actions failed to eliminate underlying organizational failure roots.',
    inputDataTypes: ['Historical Audit Findings (64)', 'Overdue CAPA Records (14)', 'Repeat Observation Codes', 'Root Cause Taxonomies'],
    algorithmType: 'Graph Neural Subgraph Matching & Association Rule Mining',
    improvementMetric: 'Pattern Retrieval Recall & Specificity',
    currentAccuracy: '93.1% Chronic Pattern Recall',
    lastCalibrated: '2026-08-28 (Bi-weekly Audit Cycle)',
    recalibrationMechanism: 'Graph Topology Weight Adjustment & Association Confidence Thresholds'
  }
];

export const EXPERT_FEEDBACK_LEDGER: ExpertFeedbackItem[] = [
  {
    id: 'FB-801',
    expertName: 'Dr. Alistair Vance',
    role: 'Group HSE Assurance Director, CMIOSH',
    actionType: 'Confirming Prediction',
    targetRiskId: 'RISK-LIFT-01',
    targetRiskTitle: 'Elevated Risk in Heavy Crane & Rigging Operations',
    date: '2026-08-30 16:45',
    notes: 'Field walkabout in Yard 4 confirmed high subcontractor turnover (18%) and unverified spreader beams. Model sensitivity correctly identified developing precursor surge.',
    status: 'Applied to Model',
    adjustment: '+12% Weight to Overdue Rigging Inspection Factor',
    isSimulated: true
  },
  {
    id: 'FB-802',
    expertName: 'Dr. Fatima Bello',
    role: 'Process Integrity Superintendent, CEng',
    actionType: 'Correcting Prediction',
    targetRiskId: 'RISK-PS-03',
    targetRiskTitle: 'Compression Train B Flange Integrity & Micro-leak Risk',
    date: '2026-08-29 14:10',
    notes: 'Adjusted loss-of-containment probability from 69% to 48% following temporary containment clamping and ultrasonic bolt verification on Train B skid.',
    status: 'Applied to Model',
    adjustment: '-21% Probability Prior Updated with Physical Mitigation Factor',
    isSimulated: true
  },
  {
    id: 'FB-803',
    expertName: 'Capt. Tunde Bakare',
    role: 'Marine & Logistics Operations Lead',
    actionType: 'Challenging Assumption',
    targetRiskId: 'RISK-VEH-02',
    targetRiskTitle: 'Vehicle-Pedestrian Interface at Gate 2 Logistics Buffer',
    date: '2026-08-28 11:30',
    notes: 'Challenged model assumption that Gate 2 congestion is solely night-shift related; observation data shows peak hazard window begins at 17:30 dusk transition.',
    status: 'Applied to Model',
    adjustment: 'Extended Twilight Time Window Filter in Spatial Anomaly Detector',
    isSimulated: true
  },
  {
    id: 'FB-804',
    expertName: 'Engr. Emeka Nwosu',
    role: 'Lagos Base Operations Manager',
    actionType: 'Rating Recommendation',
    targetRiskId: 'RISK-LIFT-01',
    targetRiskTitle: 'Elevated Risk in Heavy Crane & Rigging Operations',
    date: '2026-08-27 09:20',
    notes: 'Prescribed 100% pre-lift tag-line mandate and spreader beam quarantine were highly practical and executed immediately with zero operational downtime.',
    rating: 4.9,
    status: 'Verified',
    adjustment: 'Promoted Intervention Template to Gold Standard in Prescriptive Engine',
    isSimulated: true
  }
];

export const OUTCOME_LEARNING_CASES: OutcomeLearningRecord[] = [
  {
    id: 'OUT-CASE-01',
    riskId: 'RISK-LIFT-01',
    riskTitle: 'Elevated Risk in Heavy Crane & Rigging Operations (Yard 4)',
    prediction: '78% Dropped Load Probability (+14% 30-Day Precursor Surge in Yard 4)',
    intervention: 'Quarantine of uncertified spreader beams, 100% tag-line enforcement, and mandatory rigger verification',
    outcome: '24% drop in lifting non-conformances, 18% improvement in field tag-line compliance, 0 dropped objects in 30 days',
    effectiveness: '92% (Highly Effective)',
    modelEvaluation: '+0.14 Model Confidence Recalibration; Causal link between overdue gear inspections and drop precursors confirmed',
    date: '2026-08-29',
    status: 'Evaluation Completed',
    isSimulated: true
  },
  {
    id: 'OUT-CASE-02',
    riskId: 'RISK-VEH-02',
    riskTitle: 'Vehicle-Pedestrian Interface at Gate 2 Logistics Buffer',
    prediction: '61% Collision Potential at Nocturnal Heavy Flatbed Transfer Corridor',
    intervention: 'Mobilization of 2 mobile solar light towers (min 65 lux) and interlocking water-filled pedestrian barrier',
    outcome: '78% drop in unauthorized walkway breaches, illuminance raised from 18 to 72 lux',
    effectiveness: '89% (Likely Effective)',
    modelEvaluation: '+0.11 Spatial Weight Precision; Verified illuminance as primary precursor modulator',
    date: '2026-08-27',
    status: 'Evaluation Completed',
    isSimulated: true
  },
  {
    id: 'OUT-CASE-03',
    riskId: 'RISK-PS-03',
    riskTitle: 'Compression Train B Gas Flange Integrity & Acoustic Sniffing Trace',
    prediction: '69% Micro-Leak & Loss-of-Containment Vulnerability (Acoustic Resonance at 142 Hz)',
    intervention: 'Hot controlled torque verification on B-104 bolts & continuous FLIR optical gas imaging camera',
    outcome: 'Acoustic resonance amplitude dropped 85%, sniffer reading returned to 0 ppm',
    effectiveness: '96% (Highly Effective)',
    modelEvaluation: '+0.18 Acoustic Sensor Model Calibration; Validated high-frequency acoustic monitoring as early warning',
    date: '2026-08-28',
    status: 'Evaluation Completed',
    isSimulated: true
  }
];

export const GOVERNANCE_LOGS: GovernanceLog[] = [
  { id: 'GOV-8901', timestamp: '2026-08-31 07:12:00', actor: 'System (SIE Pipeline)', event: 'Zero-Knowledge Tenant Isolation Check', resource: 'Tenant ORG-ENG-4921-NG', securityDomain: 'Tenant Isolation', status: 'Success' },
  { id: 'GOV-8902', timestamp: '2026-08-31 06:45:22', actor: 'Dr. Alistair Vance (HSE Director)', event: 'Approved Verified Knowledge Source: HSE UK LOLER', resource: 'KNOW-001', securityDomain: 'Source Governance', status: 'Audited' },
  { id: 'GOV-8903', timestamp: '2026-08-31 05:30:11', actor: 'API Gateway (Key: sie_live_...48)', event: 'ERP Work Order Ingestion (89 records)', resource: 'SAP Bridge', securityDomain: 'Data Access', status: 'Success' },
  { id: 'GOV-8904', timestamp: '2026-08-31 04:15:08', actor: 'System (Security Daemon)', event: 'AES-256 GCM Rest Encryption Verification', resource: 'All Firestore & Blob Stores', securityDomain: 'Encryption', status: 'Protected' },
  { id: 'GOV-8905', timestamp: '2026-08-30 22:10:44', actor: 'System (AI Boundary Guard)', event: 'Outbound AI Payload Sanitization (Zero PII leak)', resource: 'Inference Gateway', securityDomain: 'External AI Access', status: 'Protected' }
];

export const SITES_LIST = [
  { id: 'lagos', name: 'Lagos Operations', type: 'Offshore Logistics & Fabrication Yard', riskScore: 78, highRisksCount: 3 },
  { id: 'portharcourt', name: 'Port Harcourt Project', type: 'Drilling & Flowstation Facility', riskScore: 64, highRisksCount: 1 },
  { id: 'abuja', name: 'Abuja Engineering Centre', type: 'Design & Project Management HQ', riskScore: 32, highRisksCount: 0 }
];

export const NOTIFICATIONS = [
  {
    id: 'NOTIF-01',
    title: 'Critical Watchpoint: Lifting Risk Surge (+14%)',
    category: 'Risk Alert' as const,
    message: 'SIE detected elevated lifting exposure at Yard 4 driven by 14 new observations and 3 overdue gear certifications.',
    timestamp: '10m ago',
    severity: 'Critical' as const,
    isRead: false,
    relatedRiskId: 'RISK-LIFT-01'
  },
  {
    id: 'NOTIF-02',
    title: 'Intervention Required: Compression Train B Flange',
    category: 'Intervention' as const,
    message: 'Acoustic resonance (142 Hz) on high-pressure gas manifold requires immediate controlled torque check.',
    timestamp: '42m ago',
    severity: 'High' as const,
    isRead: false,
    relatedRiskId: 'RISK-PS-03'
  },
  {
    id: 'NOTIF-03',
    title: 'New Knowledge Ingested: HSE UK L113 Rev 2026',
    category: 'Knowledge Update' as const,
    message: 'Statutory rules on LOLER 1998 synchronized and indexed into 4 active risk models.',
    timestamp: '2h ago',
    severity: 'Info' as const,
    isRead: true
  },
  {
    id: 'NOTIF-04',
    title: 'IoT Sensor Stream: 1.24M records processed',
    category: 'Data Stream' as const,
    message: 'Crane telematics and atmospheric monitors streaming at 420 msgs/sec with 98% quality grade.',
    timestamp: '4h ago',
    severity: 'Info' as const,
    isRead: true
  }
];

export const INITIAL_CHAT_MESSAGES = [
  {
    id: 'MSG-01',
    sender: 'assistant' as const,
    text: `### Active Intelligence Briefing: Lagos Operations

The causal synthesis engine has evaluated operational indicators across Yard 4 and Pier 2:

- **Lifting Operations Precursor Surge (Risk Score: 78% / High)**: +14% 30-day upward trajectory in rigging non-conformances, correlated with high subcontractor turnover (18%) and 3 overdue gear inspections.
- **Process Containment Alert (Risk Score: 69% / High)**: Acoustic micro-vibration harmonic (142 Hz) identified on Gas Compression Train B header flange.
- **Immediate Recommended Action**: Maintain quarantine on uninspected spreader beams and execute scheduled hydraulic bolt torque checks.`,
    timestamp: '08:30 AM',
    intelligenceContext: {
      orgRecords: 24,
      externalKnowledgeSources: 6,
      historicalAnalysisDays: 90,
      predictiveModelsCount: 3
    },
    evidenceUsed: {
      organizationEvidence: [
        '14 proactive observation logs (OBS-1021, OBS-1044)',
        '1 high-potential near-miss report (NM-203: load swing during wind shear)',
        '3 overdue rigging certification tickets (CAPA-4912, CAPA-4918)'
      ],
      externalKnowledge: [
        'HSE UK L113 (LOLER 1998 Regulation 8 & 9 Approved Code of Practice)',
        'OSHA 1926 Subpart CC (Cranes & Derricks in Construction)',
        'API 570 5th Ed (Piping Inspection Code § 7.3 Flange Torquing)'
      ],
      analyticalResults: [
        'Bayesian Causal Directed Acyclic Graph (DAG) convergence score: 0.88',
        '+14% 30-day precursor surge index exceeding statistical control baseline',
        '95% confidence interval [71% - 84%] on 30-day dropped object probability'
      ]
    },
    relatedRiskId: 'RISK-LIFT-01',
    citations: [
      { id: 'OBS-1021', title: 'Tag line absence on 12-ton turbine casing lift', type: 'Observation', severity: 'High', date: '12 Aug 2026', details: 'Tag line not utilized during load alignment near live manifold.' },
      { id: 'HSE-L113', title: 'HSE Safe Use of Lifting Equipment L113', type: 'Regulation', severity: 'Regulatory', date: '2026', details: 'Statutory guidance on LOLER 1998 Regulation 8: Organization of lifting operations.' }
    ]
  }
];

export const API_ENDPOINTS = [
  {
    path: '/api/v1/observations',
    method: 'POST' as const,
    description: 'Ingest proactive safety observations, hazard cards, unsafe conditions, and positive safety behaviors from any field tool or mobile app.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "Intelex_Mobile_App",
      timestamp: "2026-08-31T08:30:00Z",
      location: { site: "Lagos Operations", zone: "Yard 4 Fabrication Line" },
      observationType: "Unsafe Condition",
      category: "Lifting Operations",
      hazardDescription: "Synthetic sling showing UV degradation stored outdoors without protective cover.",
      severity: "Medium",
      observerRole: "Rigging Supervisor",
      actionTakenImmediate: "Sling quarantined pending NDT inspector test."
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "ingested",
      observationId: "OBS-2026-9812",
      canonicalMapping: "Lifting.Precursor.GearDegradation",
      precursorSurgeTriggered: true,
      riskModelUpdated: "RISK-LIFT-01",
      computedLatencyMs: 24
    }, null, 2)
  },
  {
    path: '/api/v1/incidents',
    method: 'POST' as const,
    description: 'Ingest near misses, first-aid events, lost time injuries (LTIs), or environmental spills from any enterprise EHS platform.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "SAP_EHSM",
      incidentId: "INC-2026-041",
      type: "Near Miss",
      category: "Vehicle Movement",
      dateTime: "2026-08-30T21:45:00Z",
      site: "Lagos Operations",
      location: "Gate 2 Logistics Buffer",
      description: "Flatbed trailer reversed within 1.5m of pedestrian walkway in low illumination zone.",
      potentialSeverity: "High (SIF Precursor)",
      actualSeverity: "Minor",
      contributingFactors: ["Poor Lighting (<20 lux)", "Lack of Dedicated Spotter", "Fatigue Transition Window"]
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "ingested_and_classified",
      incidentRef: "INC-2026-041",
      canonicalClassification: "SIF_Precursor.Vehicle_Pedestrian_Interface",
      causalGraphMatched: "CR-VEH-LOGISTICS-02",
      triggeredEarlyWarning: true,
      affectedRiskIds: ["RISK-VEH-02"]
    }, null, 2)
  },
  {
    path: '/api/v1/inspections',
    method: 'POST' as const,
    description: 'Ingest statutory audit findings, thorough examinations, crane certs, and checklist non-conformances.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "Cority_Audit_Engine",
      inspectionType: "Statutory Thorough Examination (LOLER)",
      assetId: "CRANE-50T-TEREX-04",
      auditor: "Lloyds Register NDT Inspector",
      date: "2026-08-31",
      status: "Failed Non-Conformance",
      findings: [
        { item: "Spreader Beam SB-401", defect: "Missing 6-month proof load stamp", severity: "Critical" }
      ]
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "ingested",
      inspectionRecordId: "INSP-8831",
      assetQuarantineFlagged: true,
      regulatoryViolationDetected: "HSE UK / L113 Regulation 9",
      riskScoreDelta: "+18% in Yard 4 Lifting Operations"
    }, null, 2)
  },
  {
    path: '/api/v1/training',
    method: 'POST' as const,
    description: 'Ingest worker competency certifications, LMS course completions, and safety passport expiry events.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "Workday_Learning_LMS",
      workerId: "EMP-4912",
      name: "Tariq Ibrahim",
      role: "Slinger / Rigger Grade II",
      contractorCompany: "Gulf Offshore Services Ltd",
      competencyCode: "RIG-ADV-02",
      certificationDate: "2026-08-15",
      expiryDate: "2028-08-15",
      passGrade: 94
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "competency_indexed",
      workerRef: "EMP-4912",
      verifiedSkills: ["Tandem Rigging", "LOLER Compliant Slings", "Tag Line Discipline"],
      activePermitAuthorized: true
    }, null, 2)
  },
  {
    path: '/api/v1/operational-data',
    method: 'POST' as const,
    description: 'Ingest live operational telemetry: man-hours worked, active permits-to-work (PTW), crane load cell sensors, and gas detectors.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "Maximo_CMMS_and_IoT_Gateway",
      telemetryType: "Combined Operational Telemetry",
      activeWorkOrders: 42,
      activeHotWorkPermits: 6,
      siteManHoursWorkedToday: 3840,
      sensorTelemetry: [
        { sensorId: "GAS-SNIF-B104", readingPpm: 40, gas: "CH4 Hydrocarbon", zone: "Compression Train B" },
        { sensorId: "CRANE-LOAD-01", currentLoadTons: 38.4, ratedCapTons: 50.0, windSpeedKnots: 19.2 }
      ]
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "telemetry_streamed",
      recordsIngested: 48,
      anomalyDetected: true,
      anomalyAlert: "Acoustic Resonance & 40ppm Trace at Compression Train B Flange",
      alertDispatchedTo: ["RISK-PS-03", "InterventionEngine"]
    }, null, 2)
  },
  {
    path: '/api/v1/knowledge',
    method: 'POST' as const,
    description: 'Ingest private organization SOPs, site risk assessments (HIRAs), lessons learned, and internal safety standards.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      sourceSystem: "SharePoint_Engineering_DMS",
      documentCode: "DEE-SOP-LIFT-042-Rev6",
      title: "Critical Lift Planning, Tandem Rigging & SIMOPS Execution Procedure",
      type: "Internal SOP",
      revision: "Rev 6.0",
      contentRawText: "All tandem crane lifts exceeding 20 tonnes require dual-operator radio synchronization and 100% synthetic sling inspection before rigging..."
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "knowledge_vectorized",
      documentId: "KNOW-006",
      extractedRulesCount: 14,
      tenantIsolationGuaranteed: "Private AES-256 Tenant Sandbox",
      indexedToRiskDomains: ["Lifting Operations", "Engineering SIMOPS"]
    }, null, 2)
  },
  {
    path: '/api/v1/intelligence',
    method: 'GET' as const,
    description: 'Retrieve real-time holistic safety intelligence scores, site risk distributions, and systemic exposure indices.',
    sampleRequest: '// GET query: ?tenantId=ORG-ENG-4921-NG&site=Lagos%20Operations&timeframe=30d',
    sampleResponse: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      site: "Lagos Operations",
      intelligenceScore: 78,
      riskLevel: "Elevated",
      activeEmergingRisks: 3,
      topWatchpoints: [
        { category: "Lifting Operations", probability: 78, trend: "+14% 30-Day Surge", zone: "Yard 4" },
        { category: "Vehicle Movement", probability: 61, trend: "Dusk/Night Peak", zone: "Gate 2 Buffer" },
        { category: "Process Safety", probability: 48, trend: "Acoustic Flange Trace", zone: "Compression Skid B" }
      ],
      systemReliabilityGrade: "High (94.2%)",
      computedAt: "2026-08-31T08:35:00Z"
    }, null, 2)
  },
  {
    path: '/api/v1/predictions',
    method: 'GET' as const,
    description: 'Retrieve predictive risk forecasts, precursor anomaly trajectories, and Bayesian causal graphs across all operating assets.',
    sampleRequest: '// GET query: ?category=Lifting%20Operations&lookaheadDays=30&includeDrivers=true',
    sampleResponse: JSON.stringify({
      riskId: "RISK-LIFT-01",
      category: "Lifting Operations",
      probability: 78,
      confidence: 82,
      trajectory: "Increasing",
      precursorVelocity: "+14% per 30d",
      causalDrivers: [
        { driver: "Overdue Rigging Gear Inspections", contribution: "34%" },
        { driver: "Subcontractor Rigger Turnover", contribution: "28%" },
        { driver: "Fabrication Yard SIMOPS Congestion", contribution: "22%" }
      ],
      associatedStandards: ["HSE UK L113", "OSHA 1926 Subpart CC", "DEE-SOP-LIFT-042"]
    }, null, 2)
  },
  {
    path: '/api/v1/recommendations',
    method: 'GET' as const,
    description: 'Retrieve prescriptive, actionable safety interventions ranked by quantified risk reduction efficacy.',
    sampleRequest: '// GET query: ?riskId=RISK-LIFT-01&priority=Immediate',
    sampleResponse: JSON.stringify({
      interventionId: "INT-LIFT-2026-01",
      title: "Targeted Lifting Safety Campaign & Rigging Integrity Reset",
      targetRisk: "RISK-LIFT-01 (78% Prob)",
      expectedRiskReduction: "↓ 27% within 14 days",
      actionItems: [
        { step: 1, action: "Quarantine uncertified spreader beams in Yard 4 and Pier 2", owner: "Rigging Superintendent" },
        { step: 2, action: "Supervisor Toolbox Talk on tag-line discipline and wind gust thresholds", owner: "Area HSE Lead" },
        { step: 3, action: "Audit 3rd-party rigger competency passports against LMS registry", owner: "HR Competency Lead" }
      ]
    }, null, 2)
  },
  {
    path: '/api/v1/feedback',
    method: 'POST' as const,
    description: 'Submit human expert oversight reviews or post-intervention empirical outcomes for closed-loop Bayesian model weight calibration.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      interventionId: "INT-LIFT-2026-01",
      expertAuditor: "Capt. Tunde Bakare (Marine & Rigging Specialist)",
      actionType: "Confirming Prediction",
      expertRating: "Highly Effective",
      observedMetrics: {
        liftingObservationReduction: "-24%",
        tagLineComplianceShift: "+18%",
        droppedObjectsInPeriod: 0
      },
      expertNotes: "Quarantining uncertified spreader beams stopped the unsafe rigging habit. Recommend maintaining weekly audits."
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "feedback_logged_and_recalibrated",
      modelConfidenceDelta: "+0.14",
      factorRecalibrated: "Overdue Rigging Gear Inspection Weight (+12%)",
      nextAuditCycle: "2026-09-07"
    }, null, 2)
  }
];

export const MANAGEMENT_ATTENTION_ITEMS: ManagementAttentionItem[] = [
  {
    id: 'ATTN-01',
    title: 'High Lifting Risk Trajectory in Yard 4 & Pier 2',
    scope: 'Lagos Operations • Yard 4 & Pier 2',
    category: 'Lifting Operations',
    severity: 'Critical',
    trend: '+14% 30-Day Precursor Surge',
    trendDirection: 'Increasing',
    owner: 'Marine Ops Director & Rigging Supt.',
    recommendedAction: 'Mandate 100% pre-lift rigging inspection & halt tandem lifts in Yard 4 until lift-plan re-validation.',
    dueDate: '2026-09-02',
    urgency: 'Within 48h'
  },
  {
    id: 'ATTN-02',
    title: 'Repeated Corrective-Action Failure on Rigging Gear',
    scope: 'Fabrication Yard 4 • Maintenance Dept',
    category: 'Audit Assurance',
    severity: 'High',
    trend: 'Chronic (3 Cycles Overdue / 12 Days)',
    trendDirection: 'Chronic',
    owner: 'Site HSE Lead & Maintenance Supt.',
    recommendedAction: 'Escalate 3 overdue rigging gear recertification CAPAs to Plant VP; enforce daily quarantine lockout.',
    dueDate: '2026-09-03',
    urgency: 'Within 72h'
  },
  {
    id: 'ATTN-03',
    title: 'Competency Gap in High-Risk Heavy Lifting Activity',
    scope: 'Subcontractor Rigger Pool • Berth 5 & Pier 2',
    category: 'Competency & Training',
    severity: 'High',
    trend: 'Accelerating (+18% Contractor Turnover)',
    trendDirection: 'Emerging',
    owner: 'Contractor Safety Manager & HR Lead',
    recommendedAction: 'Institute mandatory hands-on verification before issuing high-tonnage rigging permits to 3rd-party crews.',
    dueDate: '2026-09-03',
    urgency: 'Within 48h'
  },
  {
    id: 'ATTN-04',
    title: 'Declining Inspection Effectiveness in PTW & Confined Spaces',
    scope: 'Process Line & Confined Spaces',
    category: 'Inspection Assurance',
    severity: 'Moderate',
    trend: 'Deteriorating (-22% Hazard Catch Rate)',
    trendDirection: 'Decreasing',
    owner: 'Quality & HSE Assurance Director',
    recommendedAction: 'Deploy joint leadership peer-walks to recalibrate supervisor PTW & hazard detection sensitivity.',
    dueDate: '2026-09-05',
    urgency: 'Within 5 Days'
  },
  {
    id: 'ATTN-05',
    title: 'Emerging Contractor SIMOPS Congestion & Interface Risk',
    scope: 'Terminal Area B & Yard 4 Fabrication Line',
    category: 'Contractor Management',
    severity: 'High',
    trend: 'Emerging (+28% Multi-Trade Congestion)',
    trendDirection: 'Increasing',
    owner: 'Project Operations Director',
    recommendedAction: 'Establish daily SIMOPS deconfliction matrix and dedicate senior spotters across multi-trade zones.',
    dueDate: '2026-09-02',
    urgency: 'Within 48h'
  }
];


