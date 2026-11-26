# 002: A story airs if it ranks in the top five, above a 0.40 floor

**Decision.** Each hour, the five posts with the highest "will this still matter in a week?"
score air, as long as that score is at least 0.40. The floor gets tuned Friday by listening.
The privacy rule is unchanged: a post scoring 0.20 or higher on "could airing this harm a
private individual?" is dropped and never shown.

**Why this came up.** The spec said a story airs only at 0.70 or higher. On Thursday, Jev scored
19 real Hacker News stories from a week ago and one current release announcement. Its "matters in
a week" probabilities (Jev's answer to a yes/no question is a single number, the chance of
"yes") ran from 0.32 to 0.62. Not one reached 0.70. Left as written, every newscast would be
empty, and the Corrections segment would have no calls to grade.

**Options.**
1. Keep 0.70. Cost: no stories air; the show doesn't exist.
2. A lower fixed bar, e.g. 0.50. Cost: quiet hours still go empty; busy hours could put more
   than five above the bar.
3. Rank and take the top five, above a floor of 0.40. Cost: a weak hour still airs its best
   five, which may be thin; the floor is a guess until Friday's listening.

**What we chose and why.** Option 3. Claude proposed it; Tarik approved ("go"). Jev still makes
every judgment; code only ranks and applies the floor, which keeps the editorial rule that a
language model never chooses what airs. The spec's "fewer than three stories, run short and say
so" rule still covers quiet hours.

The privacy cut was also questioned. At 0.20 it dropped 7 of 19 stories; the top three flags
were real (named private people), the rest looked like noise. It stays at 0.20 for the weekend:
losing a few stories is the cheaper mistake.

**What we gave up.** A simple "Jev says 70%+" line for the page and the demo. Scores on air will
read lower ("52% likely to matter in a week"), which is honest but less punchy.

**How we'll know if this was right.** Friday's hand-built newscasts have three to five stories
each, and on listening the fifth story still sounds like news. Sunday's Corrections can grade
the aired calls against what was still discussed a week later.

**What actually happened.**
