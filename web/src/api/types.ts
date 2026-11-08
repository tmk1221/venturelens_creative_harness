import type { components } from './schema'

// Thin aliases over generated OpenAPI schema types, so the rest of the app never spells out
// `components['schemas']['X']`. No hand-written shapes -- every field here traces to a real
// pydantic model on the server.
export type Cut = components['schemas']['Cut']
export type Passage = components['schemas']['Passage']
export type Span = components['schemas']['Span']
export type Section = components['schemas']['Section']
export type Trim = components['schemas']['Trim']
export type WordAnchor = components['schemas']['WordAnchor']
export type Word = components['schemas']['WordOut']
export type Rational = components['schemas']['Rational']
export type TimelineSegment = components['schemas']['TimelineSegmentOut']
export type SwapCandidate = components['schemas']['SwapCandidateOut']
export type Suggestion = components['schemas']['SuggestionOut']
// T13b: the automated "Suggest visuals" pass -- distinct from `Suggestion` above (older
// filler/silence removal suggestions).
export type VisualSuggestion = components['schemas']['VisualSuggestionOut']
export type AcceptSuggestionResult = components['schemas']['AcceptSuggestionOut']
export type AcceptAllResult = components['schemas']['AcceptAllOut']
export type EditReport = components['schemas']['EditReportOut']
export type CutOpResult = components['schemas']['CutOpResult']
export type CutSummary = components['schemas']['CutSummaryOut']
export type ProjectRef = components['schemas']['ProjectRef']
export type Project = components['schemas']['Project']
// T33: one row of `GET /api/brand-kits` (the shell's kit picker).
export type BrandKit = components['schemas']['BrandKitOut']
export type BrandPage = components['schemas']['BrandPageOut']
export type Shoot = components['schemas']['Shoot']
export type Source = components['schemas']['Source']
export type SyncGroup = components['schemas']['SyncGroup']
export type QueueJob = Record<string, unknown>
export type DecisionRow = components['schemas']['DecisionRowOut']
export type Decisions = components['schemas']['DecisionsOut']
export type Consent = components['schemas']['ConsentOut']
// T34: a new project from local recordings (`POST /api/projects/new`) and the Ingest page.
export type NewProjectRequest = components['schemas']['NewProjectRequest']
export type Library = components['schemas']['LibraryOut']
export type Company = components['schemas']['CompanyOut']
export type NewProjectResult = components['schemas']['NewProjectOut']
export type IngestStatus = components['schemas']['IngestStatusOut']
export type IngestSource = components['schemas']['IngestSourceOut']
export type IngestJob = components['schemas']['IngestJobOut']
export type OpenEditorResult = components['schemas']['OpenEditorOut']
// T35: a paid transcription (estimate -> one-click budget -> queued job) and speaker names.
export type TranscribeEstimate = components['schemas']['TranscribeEstimateOut']
export type TranscribeJob = components['schemas']['TranscribeJobOut']
export type Speakers = components['schemas']['SpeakersOut']
export type Speaker = components['schemas']['SpeakerOut']
