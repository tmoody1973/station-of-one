# Style reference: a daily public-radio headlines podcast

Notes written Nov 26, 2026 from one episode of *The Headlines* (The New York Times, Nov 25, 2026),
which Tarik pointed to as a reference. These are observations in our own words, used to shape the
writer prompt. The transcript itself is not stored here (it is The Times' copyrighted text), and
nothing about the show's name, voice or sound is copied: Station of One keeps its own identity.

## Running order
- Open: show name, host name, the date, then "here's what we're covering" and straight into the lead.
- Lead: the weightiest story, often in two parts, with a reporter's voice.
- Middle: two or three varied stories, introduced with plain connectives ("Meanwhile,").
- Kicker: a light, consumer or human story last, introduced with "And finally,".
- Sign-off: a fixed closing line, then credits.

## Inside each story
1. The host sets the scene in one or two plain sentences.
2. A short clip: an official, a person affected, or the reporter.
3. The host paraphrases the reporter or source: "[name] says that…", "according to prosecutors…",
   "in a statement, the agency said…".
4. One closing sentence on where things stand or what happens next.

## Sentences
- Short and plain. Past tense for events, present tense for who says what.
- Technical terms are explained in a clause the first time ("so-called X, a strategy to…").
- Numbers stay simple and are rounded when that's clearer.

## What we took, and what we did not
- Took: scene-setting first sentence, attribution phrasing, inline explanations, closing "where it
  stands" line, "And finally," for the last story. These are in `station/steps/write.py` (`SYSTEM`,
  `messages_for`).
- Did not take: music beds between stories (decision 001 keeps a sting only), named staff reporters
  (our reporter voice is synthetic and attributes to where things were posted), the show's wording.
