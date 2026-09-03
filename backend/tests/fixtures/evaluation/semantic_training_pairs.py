"""Synthetic paraphrase-pair training data — SIE Milestone 21: Real
Semantic Embedding & Retrieval Productionization v0.1, item 5/11.

Used only by `scripts/train_local_semantic_model.py` to train a small,
genuinely real (not hashing/TF-IDF/handcrafted) local sentence-embedding
model from scratch, offline — see that script's own module docstring for
why this exists and what it is (and is not) evidence of.

Entirely synthetic, non-confidential, generic safety-domain text, covering
the same six topics as `tests/fixtures/evaluation/corpus.py` (so the
trained model's vocabulary has real, varied exposure to each topic's
concepts) but written with deliberately varied phrasing — **not** copied
from `corpus.py`, and **not** the same sentences used in
`tests/fixtures/evaluation/hard_paraphrase_queries.py` (that file is the
held-out evaluation set; training on it directly would make any recall
result measured against it meaningless — memorization, not
generalization).

Each entry is an (anchor, positive) pair: two different phrasings of the
same underlying statement, trained with a contrastive objective
(`MultipleNegativesRankingLoss`) so the model learns "these two texts
mean approximately the same thing" from many such pairs across many
topics, rather than from any single hand-tuned similarity score.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParaphrasePair:
    anchor: str
    positive: str
    topic: str


TRAINING_PAIRS: list[ParaphrasePair] = [
    # --- working_at_height ---------------------------------------------------
    ParaphrasePair(
        "Workers must wear a full-body harness with a shock-absorbing lanyard "
        "whenever working above 1.8 metres.",
        "Anyone working higher than 1.8 metres off the ground needs to be "
        "clipped into a harness and lanyard.",
        "working_at_height",
    ),
    ParaphrasePair(
        "Anchor points for fall arrest equipment must be rated to at least "
        "22 kilonewtons.",
        "The point you tie off to needs a strength rating of at least 22 kN.",
        "working_at_height",
    ),
    ParaphrasePair(
        "Guardrails and edge protection should be installed on elevated "
        "platforms before work at height begins.",
        "Put up rails and edge barriers on raised platforms before anyone "
        "starts working up there.",
        "working_at_height",
    ),
    ParaphrasePair(
        "Ladders used for access must be secured at the top and bottom before use.",
        "Make sure a ladder is fastened at both ends before climbing it.",
        "working_at_height",
    ),
    ParaphrasePair(
        "Work at height should be suspended in high wind or icy conditions.",
        "Stop working up high if it's very windy or the surfaces are icy.",
        "working_at_height",
    ),
    ParaphrasePair(
        "A competent person must inspect fall protection equipment before each use.",
        "Someone qualified needs to check the fall-arrest gear every time before it's used.",
        "working_at_height",
    ),
    # --- lifting_operations ----------------------------------------------------
    ParaphrasePair(
        "A competent person must prepare a lift plan before any lifting operation.",
        "Before you lift anything, a qualified person has to draw up a plan for it.",
        "lifting_operations",
    ),
    ParaphrasePair(
        "Slings and shackles must be visually inspected for damage before every lift.",
        "Check rigging gear like slings and shackles for wear each time before hoisting a load.",
        "lifting_operations",
    ),
    ParaphrasePair(
        "No personnel are permitted to stand beneath a suspended load.",
        "Nobody should walk or stand underneath something that's being hoisted overhead.",
        "lifting_operations",
    ),
    ParaphrasePair(
        "Only a certified operator may operate a crane above a specified capacity.",
        "You need proper certification to run a crane once it's above a certain lifting capacity.",
        "lifting_operations",
    ),
    ParaphrasePair(
        "The actual weight of a load should be verified before lifting it.",
        "Double-check how much something really weighs before trying to hoist it.",
        "lifting_operations",
    ),
    ParaphrasePair(
        "An exclusion zone must be maintained around the load path of a lifting operation.",
        "Keep a cleared-out area around wherever a crane's load is going to travel.",
        "lifting_operations",
    ),
    # --- permit_to_work ----------------------------------------------------------
    ParaphrasePair(
        "A permit to work must be authorized before high-risk activities such as hot "
        "work or excavation begin.",
        "Dangerous jobs like welding or digging need sign-off before they can start.",
        "permit_to_work",
    ),
    ParaphrasePair(
        "Each permit specifies the exact task, location, and time window it covers.",
        "The paperwork lays out precisely what job, where, and when it's valid for.",
        "permit_to_work",
    ),
    ParaphrasePair(
        "On completion, the permit must be formally closed out and the area made safe.",
        "Once the job's done, the authorization has to be officially closed and the "
        "area left in a safe state.",
        "permit_to_work",
    ),
    ParaphrasePair(
        "Multiple permits active in the same area must be reviewed together for "
        "conflicting hazards.",
        "If more than one job is happening in the same spot at once, someone needs "
        "to check they don't create dangers for each other.",
        "permit_to_work",
    ),
    ParaphrasePair(
        "Only a competent person can authorize a permit to work.",
        "Sign-off on this kind of paperwork can only come from someone qualified to give it.",
        "permit_to_work",
    ),
    ParaphrasePair(
        "A permit is not valid for any work outside its defined scope.",
        "The authorization doesn't cover anything beyond exactly what it describes.",
        "permit_to_work",
    ),
    # --- ppe ------------------------------------------------------------------------
    ParaphrasePair(
        "All personnel entering an active work area must wear a hard hat, safety "
        "glasses, and steel-toed boots.",
        "Anyone going into the work zone needs a helmet, eye protection, and "
        "protective footwear on.",
        "ppe",
    ),
    ParaphrasePair(
        "Where airborne contaminants exceed exposure limits, a fit-tested respirator "
        "must be worn.",
        "If the air quality is bad enough, people need a properly fitted breathing "
        "mask before entering.",
        "ppe",
    ),
    ParaphrasePair(
        "Damaged protective equipment must be replaced immediately.",
        "Swap out any safety gear right away if it's been damaged.",
        "ppe",
    ),
    ParaphrasePair(
        "Hearing protection is mandatory where noise levels exceed the designated threshold.",
        "You have to wear ear protection once the noise gets loud enough on site.",
        "ppe",
    ),
    ParaphrasePair(
        "Protective equipment must be inspected before each use.",
        "Check your safety gear over before you put it on every time.",
        "ppe",
    ),
    ParaphrasePair(
        "High-visibility clothing is required for anyone in an active work area.",
        "You need to be wearing bright, reflective clothing anywhere work is going on.",
        "ppe",
    ),
    # --- confined_spaces -------------------------------------------------------------
    ParaphrasePair(
        "The atmosphere inside a confined space must be tested before entry.",
        "Check the air inside an enclosed space before anyone goes in.",
        "confined_spaces",
    ),
    ParaphrasePair(
        "A trained standby attendant must remain at the entrance while anyone is "
        "working inside.",
        "Someone qualified needs to stay watching the entryway the whole time a "
        "colleague is inside.",
        "confined_spaces",
    ),
    ParaphrasePair(
        "Rescue equipment must be ready before entry into a confined space is authorized.",
        "Have retrieval gear set up and ready before letting anyone go into an "
        "enclosed area.",
        "confined_spaces",
    ),
    ParaphrasePair(
        "Mechanical ventilation should be used when natural airflow is insufficient.",
        "Bring in a fan or blower if there isn't enough natural air movement inside.",
        "confined_spaces",
    ),
    ParaphrasePair(
        "An entry log recording every person's entry and exit time must be kept.",
        "Keep a written record of exactly who went in and out, and when.",
        "confined_spaces",
    ),
    ParaphrasePair(
        "The atmosphere must be retested periodically throughout an entry.",
        "Keep re-checking the air quality the whole time someone is inside.",
        "confined_spaces",
    ),
    # --- emergency_response -----------------------------------------------------------
    ParaphrasePair(
        "On hearing a fire alarm, personnel must evacuate to the designated assembly point.",
        "If the fire alarm goes off, everyone needs to leave and gather at the "
        "meeting spot outside.",
        "emergency_response",
    ),
    ParaphrasePair(
        "A trained first aider should be contacted immediately for any injury.",
        "Get someone with first-aid training right away if anyone gets hurt.",
        "emergency_response",
    ),
    ParaphrasePair(
        "Emergency contact numbers must be posted at every entrance.",
        "Phone numbers for emergencies should be displayed near every doorway.",
        "emergency_response",
    ),
    ParaphrasePair(
        "A chemical spill must be contained using the site's spill kit where safe to do so.",
        "If something hazardous leaks out, use the on-site cleanup kit to control "
        "it, if it's safe.",
        "emergency_response",
    ),
    ParaphrasePair(
        "The area should be evacuated if the spilled substance is unknown.",
        "Clear the area out if nobody knows exactly what liquid has leaked.",
        "emergency_response",
    ),
    ParaphrasePair(
        "A roll call must be conducted at the assembly point to confirm everyone "
        "has evacuated.",
        "Count heads at the meeting point to make sure nobody's been left behind.",
        "emergency_response",
    ),
]
