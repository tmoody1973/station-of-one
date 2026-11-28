# 014 — Voice breaks: a host per station, cited facts, voice between songs

**Decision** — Rhythm Lab and ONE Jazz each get their own synthetic host (Gemini's Algieba and Sulafat, chosen by Tarik by ear). Every few songs the host back-announces what played, gives one fact that cites a source, says where the agent found the record and teases what's next. A fact without a link is cut, and Jev checks every script against its facts. In the listener's player the host and the news play between blocks of songs, never over one.

**Why this came up** — Plan C played the stations as songs only and skipped the slots the program director reserves for IDs, breaks and news, so the stations sounded like a playlist, not radio. The music PRD's "Voice breaks and news" section asks for a host who adds something true between songs. Getting it wrong means a host who says false things about real artists on air, or station audio playing over a song (Apple's terms forbid it).

**Options**
1. **Facts from Perplexity's web search, with the station's own facts as a fallback.** Richer breaks (producers, players, where it was recorded), each fact linked. Cost: a new connector, about $1–2 a day, and a third party's answers to check.
2. **Only the station's own facts** (Apple Music's album and year, the post where the record was found). Free, already linked. Cost: plainer breaks that repeat the same kinds of fact.
3. **No facts: back-announces only.** Nothing can be wrong. Cost: a host with nothing to say.

**What we chose and why** — Option 1. Tarik chose Perplexity (Nov 27, 9 pm) and a host per station. Claude built the station's own facts first, so breaks work and cite sources before Perplexity is connected, and keep working when it fails. Jev, not the writer, judges whether a script went beyond its facts: at 0.85 or more the script is replaced by a plain back-announce. The plan said 0.3; a rehearsal cut every break, and a calibration (check 24) found Jev scores faithful scripts about 0.7 and scripts with a wrong year, album or place about 0.97.

**What we gave up**
- The hosts' voices can't be chosen by accent. Our Gemini connector only reaches Gemini's 30 built-in voices: Google's voice library and designed voices are refused ("endpoint is not supported by the Google Gemini connector"). ONE Jazz's host reads with British English as its language setting; whether it sounds British is a matter of ear.
- Breaks are only as good as their facts. Until Perplexity is connected, most songs have just their album and year, so many breaks sound alike.
- Real break lengths differ from the slots the schedule planned, so a listener's player drifts a few seconds from the clock each hour.
- About $1.25 a day of Gemini voicing for both stations around the clock, whether or not anyone is listening.

**How we'll know if this was right** — After two days: no break states something its cited sources don't (Tarik spot-checks 20 breaks against their links); Jev cuts fewer than one script in five; no listener report of our audio over a song; the voicing step's notes show fewer than 5% of spoken items unvoiced.

**What actually happened** —
