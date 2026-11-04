# CEP Prototype v1 Extraction Prompt

Prompt version: prompt_cep_v1

## Task

Extract a structured Cultural Experience Profile (CEP) from the supplied Touristic Experience text.

You are given ONLY two source fields:

- TITLE
- DESCRIPTION

Use only information contained in those two fields.

Do not assume access to platform, destination metadata, tourism category, itinerary, reviews, images, ratings, prices, popularity, host information, URL, provenance metadata, reference annotations, or external cultural knowledge.

Return only information permitted by CEP JSON Schema v1.

Do not calculate character offsets, Component Coverage, TE-level supported facet aggregation, cultural abstention, final provenance IDs, or any other deterministic derived value.

---

## 1. Core evidence rule

Every extracted component, assertion, or unmapped item must be grounded in exact text from TITLE or DESCRIPTION.

Evidence must contain:

- `source_field`: `title` or `description`
- `exact_text`: an exact contiguous quotation copied from that field

Preserve the original spelling, capitalization, punctuation, and wording of the quoted span.

Do not paraphrase evidence.

Do not calculate `char_start` or `char_end`.

Prefer a concise but sufficiently specific exact contiguous span that supports the extraction and is likely to occur uniquely in the declared source field.

The same evidence object may be referenced by multiple components or assertions when appropriate.

Use model-local evidence identifiers such as `E1`, `E2`, `E3`.

All model-local identifiers are temporary response-scoped references only. They are not final CEP/provenance IDs and will be mapped or replaced deterministically during post-processing.
---

## 2. No external-knowledge or destination leakage

Reason only from the supplied TITLE and DESCRIPTION.

You may interpret the ordinary meaning of words that actually occur in the supplied text, but you must not add facts that require external knowledge about a destination, landmark, community, religion, historical period, cuisine, tradition, or cultural group.

A city, region, country, neighborhood, or POI name appearing in the text may be quoted as evidence, but its presence alone does not establish cultural significance or any cultural facet.

For example:

- a mention of Rome does not by itself establish Roman identity, Roman heritage, historical culture, or Italian culinary culture;
- a named landmark does not by itself establish heritage status or cultural significance unless the supplied text supports that claim;
- a destination name must not be used to infer authenticity, traditionality, representativeness, or community recognition.

Do not reconstruct or guess the dataset/search destination from prior knowledge.

---

## 3. Components

A component is a discrete advertised experiential unit that the tourist is expected to do, visit, encounter, consume, observe, or participate in as part of the TE, supported by explicit listing evidence.

Identify experiential components before deciding whether they contain cultural content.

A valid experiential component may have no supported cultural facet.

Do not create a component merely because the text mentions a named place, city, landmark, address, nearby attraction, background fact, suggested option, meeting location, pass-by view, or another product.

Create only components supported by the supplied text.

Use model-local identifiers such as `C1`, `C2`, `C3`.

For each component provide:

- `component_local_id`
- `normalized_label`
- `component_type`
- `component_role`
- `evidence_refs`

The `normalized_label` should be a concise neutral description of the component. It must not add unsupported cultural meaning.

### Component types

Use exactly one of these types.

#### `activity_practice`

A described activity or practice that can be represented independently of a particular named place.

Examples include cooking, tasting, dancing, painting, pottery making, storytelling, or another activity explicitly described by the text.

#### `place_poi_stop`

A place, POI, site, neighborhood, building, landscape stop, or other visit location when the textual evidence primarily describes visiting or encountering the place rather than performing a distinct activity there.

Do not infer characteristics of a named POI from external knowledge.

#### `activity_at_place`

A distinct activity explicitly anchored to a particular place or POI in the supplied text.

Use this when representing the activity-place combination is more accurate than separating them.

#### `c0_te_whole`

`c0_te_whole` is a conservative fallback.

Use it only when the TE genuinely forms one meaningful whole-experience unit and further segmentation would be artificial.

A TE with one ordinary activity or one ordinary POI stop is not automatically `c0_te_whole`.

Do not create C0 merely because an assertion applies broadly to the TE.

Do not manufacture C0 to avoid an empty component list.

---

## 4. Component roles

Assign exactly one role to every component.

### `fixed`

The text presents the component as a definite included part of the experience.

### `optional`

The text explicitly presents the component as optional.

### `alternative`

The text presents the component as one possibility among alternatives rather than a guaranteed part of the experience.

### `contextual`

The component appears as background, surrounding context, description, or orientation rather than as an activity/place actually included in the delivered experience.

### `meeting_point`

The place is used only or primarily as a meeting, starting, pickup, ending, or logistical point rather than as a substantive experience component.

### `cross_promotion`

The text mentions another tour, product, service, attraction, or commercial offering that is not part of the current TE.

Do not convert optional, alternative, contextual, meeting-point, or cross-promotional content into `fixed`.

CEP eligibility will be calculated later by deterministic post-processing. Do not calculate eligibility yourself.

---

## 5. Candidate cultural facets

The candidate framework contains exactly nine facets.

Facets are independent and non-mutually-exclusive.

Do not normalize facets to percentages or force every TE into one or more facets.

A component may support multiple facets only when the supplied evidence genuinely supports each facet.

### 5.1 Foodways / culinary culture

Direct advertised food/drink preparation, tasting, consumption, production, culinary-market encounter, or interpretation of food practices may support Foodways S1.

Incidental refreshments, catering/logistics, or food mentioned only as background are insufficient.

Substantive advertised consumption may support Foodways S1 even when it is described as a meal.

Keep authenticity, traditionality, localness, representativeness, and cultural-significance claims separate through S2/S4 as appropriate.

### 5.2 Architecture / built environment

Use for explicitly described architecture, built forms, buildings, monuments, streetscapes, constructed environments, or architectural features.

A place name alone is insufficient when the text does not indicate that it is a built or architectural feature.

Do not infer architectural style, heritage status, historical significance, or destination identity from external knowledge.

### 5.3 Arts / creative expression

Use for explicitly described artistic or creative expression such as visual art, music, performance, dance, theatre, literature, photography as creative practice, street art, or comparable expressive activity.

When the emphasis is on producing a material object through a making technique, consider `Craft / making practices` instead.

### 5.4 Craft / making practices

Use for explicit material-making practices, artisan production, manual fabrication, or learned making techniques such as pottery, weaving, glasswork, carving, or comparable practices.

Food preparation belongs primarily to `Foodways / culinary culture`, not Craft, unless the text independently supports a distinct non-food making practice.

Do not infer traditional craftsmanship or heritage status solely from the activity.

### 5.5 Religious / spiritual cultural content

Use Religious / spiritual cultural content only when the supplied text advertises actual visit, entry, observation, learning, practice, ritual, object engagement, or another substantive encounter with explicitly religious/spiritual content.

A religious place name alone is insufficient.

Passing by, distant viewing, proximity, background mention, nearby location, or merely stating that a religious site exists does not establish S1 Religious / spiritual cultural content.

Do not infer religious meaning from external knowledge of a named place.

Do not infer sacred significance, doctrinal importance, community meaning, pilgrimage status, or heritage status without appropriate support.

### 5.6 Social / community practices

Use for substantive social or communal practices, customs, community participation, community interaction, or culturally meaningful forms of collective social activity explicitly represented in the experience.

Do not use this facet merely because:

- the tour has a small group;
- tourists interact with one another;
- a guide or host provides a service;
- the listing mentions friendliness;
- ordinary logistical interaction occurs.

### 5.7 Contemporary / living culture

Use for explicitly represented present-day cultural practices, current local cultural life, contemporary cultural scenes, everyday living culture, or active modern cultural expression.

Do not use this facet merely because an activity occurs in the present day, takes place at night, is modern, or is entertainment.

There must be observable cultural content rather than generic contemporary tourism activity.

### 5.8 Historical / cultural-past content

Use for explicitly represented historical periods, past events, archaeology, historical interpretation, historical memory, or other substantive past-oriented cultural content.

Do not assign this facet merely because something is described with vague words such as `old`, `classic`, or `historic` when the text provides no substantive past-oriented content.

Do not infer historical importance or heritage significance from external knowledge.

### 5.9 Cultural landscape / human-place relations

Use when the supplied text explicitly represents a relationship between people, cultural practices, human activity, and landscape/place.

Examples may include culturally shaped agricultural, pastoral, fishing, working, settlement, or other human-place relationships when they are actually described.

Do not use this facet for generic nature, scenery, viewpoints, mountains, beaches, parks, or landscapes when no human-cultural relationship is supported by the text.

---

## 6. Cultural assertions

For each relevant candidate cultural interpretation create an assertion containing:

- `assertion_local_id`
- `component_local_id`
- `facet`
- `observable_cue`
- `evidence_refs`
- `relation_qualifier`
- `assertion_state`
- `external_grounding_required`
- `ambiguity_note`

Use model-local assertion identifiers such as `A1`, `A2`, `A3`.

The `observable_cue` must describe what is actually present in the supplied text without adding cultural significance.

`relation_qualifier` may contain a short neutral relation such as `participation in`, `visit to`, `observation of`, or `provider describes as` when useful. Otherwise use `null`.

Do not create assertions simply to ensure that every facet appears.

---

## 7. Assertion states

Use exactly one of:

- `S1`
- `S2`
- `S4`
- `S5`
- `S6`

`S3` must never be used.

### S1 — directly supported observable cultural content

Use S1 when the supplied TITLE or DESCRIPTION directly supports observable content that falls within one of the nine candidate facets.

S1 must remain at the observable-content level.

Examples of the reasoning pattern include:

- the text explicitly says participants make pasta -> observable food-preparation practice;
- the text explicitly says participants make pottery -> observable making practice;
- the text explicitly describes a church visit -> observable religious-place content;
- the text explicitly describes street-art viewing -> observable artistic content.

S1 does not by itself establish:

- authenticity;
- traditionality;
- cultural significance;
- heritage status;
- destination representativeness;
- local identity;
- community recognition;
- historical importance.

Only S1 will later establish supported cultural-facet membership.

Do not calculate membership yourself.

### S2 — provider-attributed cultural claim

Use S2 when the supplied listing itself explicitly attributes a cultural property or claim to the experience, but the claim cannot be independently established from TITLE and DESCRIPTION alone.

Typical provider wording may include claims such as:

- authentic;
- traditional;
- local tradition;
- representative of local culture;
- culturally important;
- iconic;
- heritage;
- typical;
- genuine local experience.

Preserve these as provider-attributed claims rather than converting them into verified facts.

When a sentence contains both observable content and a provider claim, separate them when appropriate.

For example, wording equivalent to `learn to make traditional pasta` may justify:

- an S1 assertion for the observable pasta-making activity; and
- a separate S2 assertion for the provider's `traditional` characterization.

S2 does not establish supported cultural-facet membership.

Set:

`external_grounding_required = false`

for S2.

### S4 — stronger claim requiring external grounding

Use S4 for a stronger cultural conclusion that might be relevant but cannot be established from TITLE and DESCRIPTION and would require an external authoritative source to verify.

Examples include claims that something:

- has cultural significance at the destination;
- constitutes recognized heritage;
- represents destination or group identity;
- is historically important;
- is community-recognized;
- is culturally representative;
- has a specific culturally significant human-place relationship.

Do not generate S4 claims automatically for every culturally relevant component.

Use S4 only when a concrete textual cue makes the stronger claim a relevant candidate for later external verification.

An S4 evidence reference points only to the Title/Description cue that motivates the candidate claim. It is not external evidence.

Set:

`external_grounding_required = true`

for every S4 assertion.

S4 does not establish supported cultural-facet membership.

### S5 — insufficient / unsupported

Use S5 when a genuine eligible experiential component is present in TITLE or DESCRIPTION but no cultural facet can be supported from the available v1 evidence.

S5 may use `facet = null` when no specific candidate facet is supportable.

Do not invent a cultural interpretation merely so that it can be labelled S5.

Do not use S5 to enumerate all absent cultural facets.

If a specific facet relationship is plausible but genuinely uncertain, use S6 instead.

Set:

`external_grounding_required = false`

for S5.

S5 does not establish supported cultural-facet membership.

### S6 — ambiguous / uncertain

Use S6 when the supplied text is genuinely ambiguous about the cultural interpretation, component assignment, or relevant facet and a defensible resolution cannot be made from TITLE and DESCRIPTION alone.

For S6, explain the uncertainty concisely in `ambiguity_note`.

Do not resolve ambiguity by guessing from external knowledge.

Set:

`external_grounding_required = false`

for S6.

S6 does not establish supported cultural-facet membership.

---

## 8. Strong-claim discipline

Never convert ordinary TE wording into unsupported cultural significance.

In particular, do not state as fact that something is:

- authentic;
- traditional;
- indigenous;
- culturally significant;
- culturally important;
- representative;
- iconic;
- heritage;
- community-recognized;
- part of local identity;
- part of national identity;
- preserved cultural memory;
- a destination-defining practice

unless the appropriate assertion-state logic above is followed.

Observable activity is not equivalent to cultural significance.

Location is not equivalent to cultural significance.

Provider marketing language is not equivalent to verified cultural fact.

---

## 9. Non-forced cultural attribution

Cultural content is not mandatory.

A TE may have:

- no S1 cultural assertions;
- no salience proposals;
- no unmapped content.

Do not force a facet because the task asks for a Cultural Experience Profile.

Generic sightseeing, transportation, scenery, entertainment, logistics, or commercial content must not automatically become cultural content.

When evidence is insufficient, abstain from S1 rather than stretching a facet definition.

The final cultural-abstention decision will be calculated later by deterministic post-processing.

Do not output a cultural-abstention field yourself.

---

## 10. Salience proposals

Salience is proposed only for a facet having at least one S1 assertion attached to a `fixed` experiential component.

S1 assertions attached only to optional, alternative, contextual, meeting-point, or cross-promotional components do not justify a TE-level salience proposal.

For every facet having at least one S1 assertion attached to a fixed
experiential component, output exactly one salience proposal for that facet.

Do not output a salience proposal for any facet supported only by S2, S4,
S5, or S6 assertions, or only by non-fixed components.

Never output more than one salience proposal for the same facet.

Use:

- `1` = Minor
- `2` = Moderate
- `3` = Major

### Minor — 1

The S1-supported facet is genuinely present but incidental or limited relative to the overall described experience.

### Moderate — 2

The S1-supported facet is a clear and meaningful part of the described experience but is not the dominant or defining focus.

### Major — 3

The S1-supported facet is central, defining, repeated, or a primary focus of the described experience.

Do not output salience `0`.

Do not assign salience to facets supported only by S2, S4, S5, or S6.

Do not normalize salience values or make them sum to any total.

Do not calculate Component Coverage.

---

## 11. Unmapped cultural content

If the supplied text contains evidence-grounded possible cultural content that does not fit any of the nine candidate facets cleanly, preserve it in `unmapped_content`.

For each unmapped item provide:

- `unmapped_local_id`
- `component_local_id`
- `status`
- `normalized_label`
- `observable_cue`
- `evidence_refs`
- `note`

Use model-local identifiers such as `U1`, `U2`.
Set `status` to exactly one of:

- `unmapped_cultural_content`
- `candidate_missing_construct`

Use `unmapped_cultural_content` when evidence-grounded cultural content does not fit the current nine facets.

Use `candidate_missing_construct` only when the evidence suggests a potentially missing conceptual construct worth later taxonomy review.

Frequency alone must not create or justify a new facet or missing construct.

Explain briefly in `note` why the content does not fit the frozen candidate framework.

Do not create a tenth facet.

Do not force the content into the nearest facet merely to avoid leaving it unmapped.

If there is no such content, return an empty array.

---

## 12. Output discipline

Return exactly one structured JSON object conforming to CEP JSON Schema v1.

Do not include prose before or after the object.

Do not include Markdown code fences.

Do not add fields that are not defined by the schema.

Do not create:

- character offsets;
- final stable IDs;
- provenance IDs;
- platform information;
- dataset/search destination;
- tourism category;
- itinerary information not contained in DESCRIPTION;
- review information;
- image information;
- ratings;
- prices;
- host information;
- URL information;
- Component Coverage;
- TE-level supported-facet aggregation;
- cultural abstention;
- model confidence scores;
- percentages.

Before returning the result, check that every evidence quotation is copied exactly from TITLE or DESCRIPTION.

---

# RUNTIME INPUT

TITLE:
{{TITLE}}

DESCRIPTION:
{{DESCRIPTION}}

# END RUNTIME INPUT