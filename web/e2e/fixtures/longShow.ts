/** T34: a synthetic 45-minute, two-speaker show transcript (~7,000 words) -- the size of Show
 * #37 (a podcast host + Andrew Keen, one remote recording). Generated deterministically (a fixed
 * LCG seed) instead of a multi-MB JSON file: speaker turns of 20-90 s with a 1.6 s pause at
 * every change (RawTranscript breaks paragraphs at pauses >= 1.5 s), words 0.22-0.38 s long. */

export interface FixtureWord {
  id: string
  schema_version: number
  text: string
  start: number
  end: number
  speaker: string
  confidence: number
}

const VOCAB = (
  'so the thing about AI this week is that it is becoming permanent not a fad and what that means for ' +
  'startups investors and everyone building software right now I think the question is whether the ' +
  'platforms capture all of the value or whether there is room for new companies to grow and you know ' +
  'Andrew I would push back on that because the history of every wave says otherwise'
).split(' ')

export const LONG_SHOW_SECONDS = 45 * 60

export function longShowWords(seconds = LONG_SHOW_SECONDS): FixtureWord[] {
  let seed = 37
  const rand = () => {
    seed = (seed * 1103515245 + 12345) % 2 ** 31
    return seed / 2 ** 31
  }
  const words: FixtureWord[] = []
  let t = 0.5
  let speaker = 0
  let turnEnds = 20 + rand() * 70
  for (let i = 0; t < seconds - 1; i++) {
    if (t >= turnEnds) {
      speaker = 1 - speaker
      t += 1.6
      turnEnds = t + 20 + rand() * 70
    }
    const duration = 0.22 + rand() * 0.16
    words.push({
      id: `w${i}`, schema_version: 1, text: VOCAB[i % VOCAB.length]!, start: Number(t.toFixed(3)),
      end: Number((t + duration).toFixed(3)), speaker: `SPEAKER_0${speaker}`, confidence: 0.98,
    })
    t += duration + 0.02 + rand() * 0.1
  }
  return words
}
