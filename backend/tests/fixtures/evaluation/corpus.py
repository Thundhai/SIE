"""Synthetic safety-knowledge evaluation corpus — milestone spec item 19.

Entirely synthetic and non-confidential: generic, textbook-level safety
statements written for this repository, not sourced from or resembling
any real organization's procedures, any specific regulation's exact
text, or any copyrighted material. Six topics, matching the milestone's
own example list, ~4-5 short chunks each (28 total, within the
milestone's 15-30 target range).

Used by:
  * tests/evaluation/test_recall_at_k.py — the Recall@K evaluation
    harness (milestone item 20/21), a PostgreSQL-integration test.
  * tests/test_retrieval_service.py — general retrieval behavior tests
    that want realistic, topically-distinct content.

Each entry becomes one `KnowledgeChunk` under its own synthetic
`KnowledgeDocument`/`KnowledgeSource` — see
tests/evaluation/conftest.py::seed_evaluation_corpus for how these are
loaded into the database and embedded.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusChunk:
    topic: str
    section_title: str
    text: str


CORPUS: list[CorpusChunk] = [
    # --- Working at Height -------------------------------------------------
    CorpusChunk(
        "working_at_height",
        "Fall Protection",
        "Workers must wear a full-body harness with a shock-absorbing lanyard "
        "whenever working at height above 1.8 metres where no other fall "
        "protection is in place.",
    ),
    CorpusChunk(
        "working_at_height",
        "Anchor Points",
        "Anchor points for fall arrest equipment must be rated to at least "
        "22 kilonewtons and inspected before each use by a competent person.",
    ),
    CorpusChunk(
        "working_at_height",
        "Guardrails",
        "Where practicable, guardrails, toe boards, and edge protection should "
        "be installed on any elevated platform before work at height begins.",
    ),
    CorpusChunk(
        "working_at_height",
        "Ladders",
        "Ladders used for access at height must be secured at the top and "
        "bottom, extend at least one metre above the landing point, and be "
        "inspected for damage before use.",
    ),
    CorpusChunk(
        "working_at_height",
        "Weather Conditions",
        "Work at height should be suspended in high wind, heavy rain, or "
        "icy conditions that could affect footing or the stability of "
        "access equipment.",
    ),
    # --- Lifting Operations --------------------------------------------------
    CorpusChunk(
        "lifting_operations",
        "Lift Planning",
        "Before any lifting operation, a competent person must prepare a lift "
        "plan identifying the load weight, the crane's safe working load, and "
        "the intended lift path.",
    ),
    CorpusChunk(
        "lifting_operations",
        "Rigging Inspection",
        "Slings, shackles, and other rigging equipment must be visually "
        "inspected for wear, deformation, or damage before every lift and "
        "removed from service if any defect is found.",
    ),
    CorpusChunk(
        "lifting_operations",
        "Exclusion Zones",
        "An exclusion zone must be established and maintained beneath and "
        "around the load path of any lifting operation, with no personnel "
        "permitted to stand under a suspended load.",
    ),
    CorpusChunk(
        "lifting_operations",
        "Crane Operator Certification",
        "Only a certified, competent crane operator may operate lifting "
        "equipment above a specified capacity, and certification must be "
        "verified before each shift.",
    ),
    CorpusChunk(
        "lifting_operations",
        "Load Weight Verification",
        "The actual weight of the load should be verified against documentation "
        "or calculated before lifting, since an underestimated load is a common "
        "cause of lifting incidents.",
    ),
    # --- Permit to Work --------------------------------------------------------
    CorpusChunk(
        "permit_to_work",
        "Permit Authorization",
        "A permit to work must be authorized by a competent person before "
        "high-risk activities such as hot work, excavation, or confined "
        "space entry begin.",
    ),
    CorpusChunk(
        "permit_to_work",
        "Permit Scope",
        "Each permit to work specifies the exact task, location, time window, "
        "and precautions required, and is not valid for any work outside "
        "that defined scope.",
    ),
    CorpusChunk(
        "permit_to_work",
        "Permit Closure",
        "On completion of the task, the permit to work must be formally "
        "closed out and the work area returned to a safe condition before "
        "the permit is cancelled.",
    ),
    CorpusChunk(
        "permit_to_work",
        "Concurrent Permits",
        "Where multiple permits to work are active in the same area at the "
        "same time, the site controller must review them together for "
        "conflicting hazards before authorizing either.",
    ),
    # --- Personal Protective Equipment ------------------------------------------
    CorpusChunk(
        "ppe",
        "Minimum PPE Requirements",
        "All personnel entering an active work area must wear, at minimum, "
        "a hard hat, safety glasses, high-visibility clothing, and "
        "steel-toed boots.",
    ),
    CorpusChunk(
        "ppe",
        "Respiratory Protection",
        "Where airborne contaminants exceed exposure limits, an appropriate "
        "respirator must be selected, fit-tested, and worn correctly for "
        "the specific hazard present.",
    ),
    CorpusChunk(
        "ppe",
        "PPE Inspection and Replacement",
        "Personal protective equipment must be inspected before each use "
        "and replaced immediately if damaged, as damaged PPE can fail to "
        "provide the protection it was rated for.",
    ),
    CorpusChunk(
        "ppe",
        "Hearing Protection",
        "In areas where noise levels exceed the designated threshold, "
        "hearing protection such as earplugs or earmuffs is mandatory for "
        "anyone entering the area.",
    ),
    # --- Confined Spaces ---------------------------------------------------
    CorpusChunk(
        "confined_spaces",
        "Atmospheric Testing",
        "Before entry into a confined space, the atmosphere must be tested "
        "for oxygen levels, flammable gases, and toxic contaminants, and "
        "retested periodically throughout the entry.",
    ),
    CorpusChunk(
        "confined_spaces",
        "Standby Attendant",
        "A trained standby attendant must remain at the entrance of a "
        "confined space at all times while anyone is working inside, "
        "maintaining continuous communication with entrants.",
    ),
    CorpusChunk(
        "confined_spaces",
        "Rescue Equipment",
        "Rescue equipment appropriate to the confined space, such as a "
        "harness and retrieval line, must be in place and ready before "
        "entry is authorized.",
    ),
    CorpusChunk(
        "confined_spaces",
        "Ventilation",
        "Mechanical ventilation should be used to maintain a safe "
        "atmosphere inside a confined space whenever natural airflow is "
        "insufficient.",
    ),
    CorpusChunk(
        "confined_spaces",
        "Entry Log",
        "An entry log recording the name and entry/exit time of every "
        "person who enters a confined space must be maintained by the "
        "standby attendant.",
    ),
    # --- Emergency Response --------------------------------------------------
    CorpusChunk(
        "emergency_response",
        "Fire Evacuation",
        "On hearing a fire alarm, all personnel must stop work immediately, "
        "evacuate via the nearest marked exit, and proceed to the "
        "designated assembly point.",
    ),
    CorpusChunk(
        "emergency_response",
        "First Aid Response",
        "A trained first aider should be contacted immediately for any "
        "injury, and the incident scene should be preserved for "
        "investigation once the injured person is safe.",
    ),
    CorpusChunk(
        "emergency_response",
        "Emergency Contacts",
        "Emergency contact numbers for site security, first aid, and "
        "external emergency services must be posted at every entrance and "
        "known to all site personnel.",
    ),
    CorpusChunk(
        "emergency_response",
        "Spill Response",
        "A chemical spill must be contained using the site's spill kit "
        "where safe to do so, and the area evacuated and reported "
        "immediately if the substance or quantity is unknown.",
    ),
    CorpusChunk(
        "emergency_response",
        "Assembly Point Roll Call",
        "At the assembly point, the site warden must conduct a roll call "
        "against the site attendance register to confirm everyone has "
        "evacuated safely.",
    ),
]

TOPICS: list[str] = sorted({chunk.topic for chunk in CORPUS})
