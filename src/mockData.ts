import { EmergingRisk, KnowledgeDocument, InterventionItem, DataIngestionSource, LearningPipelineItem, GovernanceLog } from './types';

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
        id: 'OBS-1021',
        type: 'Observation',
        title: 'Tag line not utilized on 12-ton turbine casing lift',
        severity: 'High',
        date: '12 Aug 2026',
        location: 'Pier 2 - Heavy Berth',
        details: 'Subcontractor crew guided 12t suspended turbine casing using direct hand contact on load edge rather than approved fiber tag lines.',
        reporterRole: 'Senior HSE Officer',
        status: 'Open'
      },
      {
        id: 'OBS-1044',
        type: 'Observation',
        title: 'Unsafe sling angle exceeding 60-degree safe envelope',
        severity: 'Medium',
        date: '18 Aug 2026',
        location: 'Yard 4 Staging Pad',
        details: 'Two-leg wire rope bridle rigged at improper spread angle, reducing safe working load (SWL) by estimated 25%.',
        reporterRole: 'Rigging Superintendent',
        status: 'In Remediation'
      },
      {
        id: 'NM-203',
        type: 'Near Miss',
        title: 'Uncontrolled load swing near fuel manifold during gust',
        severity: 'High',
        date: '22 Aug 2026',
        location: 'Lagos Main Fabrication Hall',
        details: 'Sudden wind gust caused 8t pipe spool to oscillate within 1.2m of pressurized nitrogen header. Lift stopped via emergency whistle.',
        reporterRole: 'Crane Operator Level II',
        status: 'Overdue'
      },
      {
        id: 'ACT-884',
        type: 'Audit Finding',
        title: 'Master Rigging Register lacking current color-coding check',
        severity: 'Medium',
        date: '25 Aug 2026',
        location: 'Central Rigging Loft',
        details: 'Quarterly color tag changeover not systematically applied to 18 wire slings in field circulation.',
        reporterRole: 'Lead Quality Auditor',
        status: 'Overdue'
      }
    ],
    externalEvidence: [
      {
        id: 'EXT-HSE-LIFT',
        publisher: 'HSE UK (Health and Safety Executive)',
        documentTitle: 'LOLER 1998 Approved Code of Practice & Rigging Failure Causation Analysis',
        code: 'HSE L113 / 2026 Rev',
        publicationDate: '2026',
        topic: 'Lifting Equipment Inspection & Pre-use Controls',
        reliability: 'Very High',
        jurisdiction: 'United Kingdom / Global Best Practice',
        keyExcerpt: 'Over 68% of industrial rigging incidents originate from unverified sling geometry and unrectified pre-use wear during surges in operational tempo.'
      },
      {
        id: 'EXT-OSHA-1926',
        publisher: 'OSHA (Occupational Safety and Health Admin)',
        documentTitle: 'Cranes and Derricks in Construction Standard: SIMOPS and Ground Stability',
        code: '29 CFR 1926.1400',
        publicationDate: '2025',
        topic: 'Simultaneous Operations & Ground Bearing Capacity',
        reliability: 'High',
        jurisdiction: 'United States',
        keyExcerpt: 'Simultaneous material transfers within crane swing radii multiply incident likelihood by a factor of 3.4 when spotter communication is non-dedicated.'
      },
      {
        id: 'EXT-IMCA-LR001',
        publisher: 'IMCA (International Marine Contractors Assoc)',
        documentTitle: 'Guidance on the Management of Lifting Operations in High-Tempo Ports',
        code: 'IMCA LR 001 / Rev 4',
        publicationDate: '2026',
        topic: 'Contractor Competency & Blind Lift Controls',
        reliability: 'Very High',
        jurisdiction: 'International Maritime & Energy',
        keyExcerpt: 'A rapid intake of temporary rigging personnel requires mandatory supervisor-led task safety briefings for all lifts exceeding 5 tonnes.'
      }
    ],
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
      { id: 'OBS-1102', type: 'Observation', title: 'Worker crossing unlit flatbed reversing lane', severity: 'High', date: '21 Aug 2026', location: 'Gate 2 Buffer Zone', details: 'Technician on foot bypassed safety walkway into active blind spot of reversing 30t tractor-trailer.', reporterRole: 'Logistics Supervisor', status: 'In Remediation' },
      { id: 'NM-208', type: 'Near Miss', title: 'Forklift near-collision with pipe flatbed corner', severity: 'Medium', date: '24 Aug 2026', location: 'Pipe Staging West', details: 'Operator swerved to avoid unchocked pallet in dark zone.', reporterRole: 'Forklift Driver', status: 'Closed' }
    ],
    externalEvidence: [
      { id: 'EXT-NIOSH-VEH', publisher: 'NIOSH', documentTitle: 'Preventing Worker Injuries and Deaths from Mobile Equipment Backover', code: 'NIOSH Pub 2025-118', publicationDate: '2025', topic: 'Internal Traffic Control Plans', reliability: 'High', jurisdiction: 'United States', keyExcerpt: 'Physical separation of foot traffic and dedicated marshaling reduces dark-shift mobile equipment incidents by up to 83%.' }
    ],
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
      { id: 'INS-409', type: 'Inspection Defect', title: 'Flange B-104 weeping traces detected via soap bubble test', severity: 'High', date: '23 Aug 2026', location: 'Train B Skid', details: 'Trace bubble formation on bottom 6 o-clock bolt segment. Hydrocarbon sniffer detected 40ppm background trace.', reporterRole: 'Integrity Engineer', status: 'Open' }
    ],
    externalEvidence: [
      { id: 'EXT-API-570', publisher: 'American Petroleum Institute (API)', documentTitle: 'Piping Inspection Code: In-service Inspection, Rating, Repair, and Alteration', code: 'API 570 5th Ed', publicationDate: '2026', topic: 'Piping Integrity & Flange Leakage Control', reliability: 'Very High', jurisdiction: 'Global', keyExcerpt: 'Flange joint relaxation under cyclic temperature transitions mandates re-torque within 72 hours of initial acoustic vibration alerts.' }
    ],
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
      { id: 'OBS-1055', type: 'Observation', title: 'Painter unclipped while traversing scaffold ledger', severity: 'High', date: '19 Aug 2026', location: 'Tank 103 Roof Perimeter', details: 'Worker unhooked both shock-absorbing lanyards simultaneously to navigate around structural ladder.', reporterRole: 'HSE Safety Auditor', status: 'Closed' }
    ],
    externalEvidence: [
      { id: 'EXT-OSHA-1926-502', publisher: 'OSHA', documentTitle: 'Fall Protection Systems Criteria and Practices', code: '29 CFR 1926.502', publicationDate: '2025', topic: '100% Tie-Off & Anchorage Strength', reliability: 'Very High', jurisdiction: 'United States', keyExcerpt: 'Continuous tie-off requires redundant twin-tail lanyards or dual self-retracting lifelines whenever moving across un-decked frames.' }
    ],
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
      { id: 'AUD-302', type: 'Permit Exception', title: 'Permit-to-Work gas test stamp missing at 14:00 check', severity: 'Medium', date: '14 Aug 2026', location: 'TK-202 Manway', details: 'Authorized gas tester was called to Tank 101, leaving 90-minute monitoring void.', reporterRole: 'Permit Coordinator', status: 'Closed' }
    ],
    externalEvidence: [
      { id: 'EXT-HSE-INDG258', publisher: 'HSE UK', documentTitle: 'Safe Work in Confined Spaces: Confined Spaces Regulations 1997', code: 'INDG258 Rev 4', publicationDate: '2026', topic: 'Continuous Atmospheric Monitoring', reliability: 'Very High', jurisdiction: 'United Kingdom', keyExcerpt: 'Continuous monitoring with aspirated gas detection is mandatory when volatile hydrocarbon deposits are subject to mechanical agitation.' }
    ],
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
      { id: 'OBS-1088', type: 'Observation', title: 'Contractor pipefitters working hot work zone without fire watch assigned', severity: 'High', date: '24 Aug 2026', location: 'Yard 4 Welding Bay', details: 'Contractor commenced torch cutting without dedicated fire watch posted with 9kg dry powder extinguisher.', reporterRole: 'Area Authority', status: 'Open' }
    ],
    externalEvidence: [
      { id: 'EXT-ILO-OSH2001', publisher: 'International Labour Organization (ILO)', documentTitle: 'Guidelines on Occupational Safety and Health Management Systems: Contractor Safety', code: 'ILO-OSH 2001 Sec 3.10', publicationDate: '2025', topic: 'Contractor Oversight & Co-employment Safety', reliability: 'Very High', jurisdiction: 'International', keyExcerpt: 'Contractor incident rates correlate directly with supervisory ratio thresholds falling below 1 qualified supervisor per 10 workers.' }
    ],
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
      { id: 'AUD-310', type: 'Audit Finding', title: 'MCC Substation 3: Isolation log missing second-person witness check', severity: 'Medium', date: '08 Aug 2026', location: 'Substation 3', details: 'Electrical isolator operated breaker without recorded second-person witness verification.', reporterRole: 'Senior Electrical Engineer', status: 'Closed' }
    ],
    externalEvidence: [
      { id: 'EXT-NFPA-70E', publisher: 'NFPA', documentTitle: 'Standard for Electrical Safety in the Workplace: Article 120 Establishing an Electrically Safe Work Condition', code: 'NFPA 70E / 2026', publicationDate: '2026', topic: 'Zero Energy State & Test Before Touch', reliability: 'Very High', jurisdiction: 'United States / Global', keyExcerpt: 'Test-before-touch with an adequately rated voltage detector is the definitive requirement for establishing electrically safe work conditions.' }
    ],
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
    mainDriver: 'Face shield usage improved following introduction of auto-darkening grinding hoods.',
    drivers: [
      '94% compliance observed during latest HSE walkabout',
      'Dust extraction filter change completed on schedule'
    ],
    status: 'Monitored',
    orgRecordsCount: 8,
    externalSourcesCount: 2,
    modelsUsedCount: 1,
    summary: 'PPE compliance has improved markedly following equipment upgrades; risk continues on a downward trajectory.',
    causalChain: [
      { step: 1, title: 'Equipment Upgrade', description: 'New ventilated grinding helmets distributed.', metricChange: '+18% Compliance' },
      { step: 2, title: 'Positive Reinforcement Walkabout', description: 'HSE recognitions for compliant crews.', metricChange: 'Risk Down (-8%)' }
    ],
    contributingFactors: [
      { name: 'Ergonomic Helmet Fit', percentage: 60, impact: 'Low', description: 'Workers prefer new lightweight air-fed helmets.' },
      { name: 'Consumable Stock Availability', percentage: 40, impact: 'Low', description: 'Adequate visor replacement stock in tool crib.' }
    ],
    organizationEvidence: [
      { id: 'OBS-0980', type: 'Observation', title: 'Worker noted using safety glasses without secondary face shield', severity: 'Low', date: '04 Aug 2026', location: 'Bay 2', details: 'Operator coached and provided new full-face shield.', reporterRole: 'Safety Warden', status: 'Closed' }
    ],
    externalEvidence: [
      { id: 'EXT-ANSI-Z87', publisher: 'ANSI / ISEA', documentTitle: 'Occupational and Educational Personal Eye and Face Protection Devices', code: 'ANSI/ISEA Z87.1-2025', publicationDate: '2025', topic: 'Impact & Splash Protection', reliability: 'High', jurisdiction: 'United States', keyExcerpt: 'High-speed rotary grinding requires secondary face protection over primary impact-rated spectacles at all times.' }
    ],
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
  {
    id: 'KNOW-001',
    source: 'Health and Safety Executive (HSE)',
    title: 'LOLER 1998: Lifting Operations and Lifting Equipment Regulations Safe Work Guidance',
    documentCode: 'HSE UK / L113 / 2026 Ed',
    type: 'Regulatory Standard',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United Kingdom / Europe',
    publicationDate: '2026-01-15',
    lastUpdated: '2026-08-10',
    verification: 'Verified',
    reliability: 'Very High',
    topics: ['Lifting Operations', 'Equipment Certification', 'Safe Working Load (SWL)', 'LOLER'],
    applicableIndustries: ['Oil & Gas', 'Engineering', 'Construction', 'Maritime'],
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
    title: '29 CFR 1926 Subpart CC: Cranes and Derricks in Construction Standard',
    documentCode: 'OSHA 1926.1400-1442',
    type: 'Regulatory Standard',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United States',
    publicationDate: '2025-11-20',
    lastUpdated: '2026-07-18',
    verification: 'Verified',
    reliability: 'Very High',
    topics: ['Crane Safety', 'Ground Bearing Capacity', 'Signal Person Qualification', 'Power Line Proximity'],
    applicableIndustries: ['Construction', 'Engineering', 'Oil & Gas'],
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
    id: 'KNOW-003',
    source: 'American Petroleum Institute (API)',
    title: 'API RP 54: Recommended Practice for Occupational Safety for Oil and Gas Well Drilling and Servicing Operations',
    documentCode: 'API RP 54 4th Edition',
    type: 'Industry Benchmark',
    domain: 'Industry Knowledge',
    jurisdiction: 'Global',
    publicationDate: '2025-06-10',
    lastUpdated: '2026-06-22',
    verification: 'Verified',
    reliability: 'Very High',
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
    id: 'KNOW-004',
    source: 'National Institute for Occupational Safety and Health (NIOSH)',
    title: 'Criteria for a Recommended Standard: Occupational Exposure in Confined Spaces',
    documentCode: 'NIOSH Pub 80-106 / 2026 Re-evaluation',
    type: 'Research Paper',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United States',
    publicationDate: '2026-03-01',
    lastUpdated: '2026-08-01',
    verification: 'Verified',
    reliability: 'High',
    topics: ['Confined Space', 'Toxic Atmosphere', 'Ventilation Dynamics', 'Rescue Protocols'],
    applicableIndustries: ['Oil & Gas', 'Chemical', 'Maritime', 'Mining'],
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
    id: 'KNOW-005',
    source: 'International Labour Organization (ILO)',
    title: 'Code of Practice on Safety and Health in Ports & Logistics',
    documentCode: 'ILO-OSH Port Code / Rev 2025',
    type: 'Technical Guidance',
    domain: 'Industry Knowledge',
    jurisdiction: 'International',
    publicationDate: '2025-09-14',
    lastUpdated: '2026-05-19',
    verification: 'Verified',
    reliability: 'Very High',
    topics: ['Vehicle Movement', 'Port Logistics', 'Pedestrian Separation', 'Night Operations'],
    applicableIndustries: ['Maritime', 'Logistics', 'Energy'],
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
    id: 'KNOW-006',
    source: 'Demo Energy & Engineering Ltd. (Internal)',
    title: 'SOP-HSE-042: Critical Lift Planning, Tandem Rigging & SIMOPS Execution Procedure',
    documentCode: 'DEE-SOP-LIFT-042-Rev6',
    type: 'Internal SOP',
    domain: 'Organization Knowledge',
    jurisdiction: 'Internal Company Standard',
    publicationDate: '2026-02-10',
    lastUpdated: '2026-08-15',
    verification: 'Verified',
    reliability: 'Very High',
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
    id: 'KNOW-007',
    source: 'Health and Safety Executive (HSE)',
    title: 'Guidance on Scaffolding and Temporary Access Structures: Advanced Fall Arrest Anchor Testing',
    documentCode: 'HSE UK / CIS10 / Draft 2026',
    type: 'Technical Guidance',
    domain: 'Global Safety Knowledge',
    jurisdiction: 'United Kingdom',
    publicationDate: '2026-08-20',
    lastUpdated: '2026-08-28',
    verification: 'Pending Review',
    reliability: 'High',
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
    text: `Welcome to **Safelytic Intelligence Engine (SIE)**. I am your evidence-grounded Safety Intelligence Co-Pilot.

I synthesize:
1. **Verified Statutory Safety Knowledge** (OSHA, HSE UK, NIOSH, API, ILO)
2. **Organization Operational Data** (Observations, near misses, audits, training records)
3. **Causal Reasoning Models** (Bayesian predictive risk networks)
4. **Historical Incident Analogues & Intervention Outcomes**

How can I assist your safety intelligence assessment today?`,
    timestamp: '09:00 AM'
  }
];

export const API_ENDPOINTS = [
  {
    path: '/api/v1/risks/predict',
    method: 'POST' as const,
    description: 'Trigger real-time causal risk prediction for an operational location or activity.',
    sampleRequest: JSON.stringify({
      tenantId: "ORG-ENG-4921-NG",
      site: "Lagos Operations",
      discipline: "Lifting Operations",
      lookaheadDays: 30,
      includeEvidence: true
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "success",
      prediction: {
        riskId: "RISK-LIFT-01",
        probability: 78,
        confidence: 82,
        trajectory: "Increasing",
        trendPercentage: 14,
        primaryDrivers: [
          "Rigging Gear Certification Delays (34%)",
          "Contractor Competency Variation (28%)",
          "SIMOPS Ground Congestion (22%)"
        ],
        citations: [
          { type: "Internal", ref: "OBS-1021", score: 0.94 },
          { type: "External", ref: "HSE-L113", score: 0.98 }
        ]
      },
      computedAt: "2026-08-31T07:15:00Z"
    }, null, 2)
  },
  {
    path: '/api/v1/intelligence/overview',
    method: 'GET' as const,
    description: 'Retrieve executive safety intelligence scores and top emerging risks.',
    sampleRequest: '// GET query: ?site=Lagos%20Operations&timeframe=30d',
    sampleResponse: JSON.stringify({
      overallSafetyIntelligence: 78,
      emergingRisksCount: 6,
      criticalActionsOpen: 14,
      trainingGaps: 8,
      riskTrendDelta: "+12%"
    }, null, 2)
  },
  {
    path: '/api/v1/knowledge/query',
    method: 'POST' as const,
    description: 'Query verified international standards and company SOPs by semantic vector.',
    sampleRequest: JSON.stringify({
      query: "flange bolt torque ASME PCC-1 protocol",
      jurisdiction: "Global",
      maxResults: 3
    }, null, 2),
    sampleResponse: JSON.stringify({
      results: [
        {
          code: "API 570 5th Ed",
          publisher: "API",
          relevance: 0.96,
          excerpt: "Flange joint relaxation under cyclic temperature mandates torque inspection within 72 hours."
        }
      ]
    }, null, 2)
  },
  {
    path: '/api/v1/interventions/generate',
    method: 'POST' as const,
    description: 'Generate prescriptive safety interventions targeted at emerging risk drivers.',
    sampleRequest: JSON.stringify({
      riskId: "RISK-LIFT-01",
      operatingZone: "Yard 4",
      priority: "Immediate"
    }, null, 2),
    sampleResponse: JSON.stringify({
      interventionId: "INT-LIFT-2026-01",
      title: "Targeted Lifting Safety Campaign",
      prescribedActions: 5,
      expectedRiskReduction: "27%"
    }, null, 2)
  },
  {
    path: '/api/v1/feedback/outcome',
    method: 'POST' as const,
    description: 'Submit post-intervention telemetry and human expert evaluation for closed-loop Bayesian weight calibration.',
    sampleRequest: JSON.stringify({
      interventionId: "INT-LIFT-2026-01",
      expertRating: "Effective",
      observedObservationShift: "-24%",
      notes: "Quarantine of uncertified spreader beams resolved Yard 4 defects."
    }, null, 2),
    sampleResponse: JSON.stringify({
      status: "recalibrated",
      modelWeightDelta: "+0.14 confidence",
      nextCalibrationCycle: "2026-09-07"
    }, null, 2)
  }
];

