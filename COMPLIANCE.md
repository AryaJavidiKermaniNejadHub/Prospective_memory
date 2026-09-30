# Smith & Bayen (2006) compliance check

**Read this first.** I could **not** obtain the full text of Smith & Bayen (2006, JEP:LMC 32(3), 623–635; APA-paywalled, PMC copy blocked).
I verified only the abstract plus what (a) Millisecond's technical manual, (b) later papers by the same lab and others that describe the
paradigm or say they reused the 2006 materials, report. Everything marked ❓ must be checked against the PDF (Method sections, esp. p. 625–627).
Sources: **[M]** Millisecond manual; **[S]** secondary papers (PMC2856082; PMC4113409; Smith, Horn & Bayen 2012); **[P]** the 2006 paper itself (NOT accessed).

| Element | Original S&B 2006 | Our implementation | Match? |
|---|---|---|---|
| Ongoing task | Judge whether a word's *colour* matches one of several coloured squares [S: PMC2856082 describes it for S&B 2004/2006] | 4 squares → coloured word; Y/N on word colour | ✅ (secondary) |
| Number of colours per trial | ❓ not verified (a 2012 lab paper varied 2/4/6 colours) | 4 squares, 5-colour palette [M] | ❓ |
| PM task | Learn several target words; press a designated key when one appears [S] | 6 targets, extra key Z | ✅ (secondary) |
| Number of targets / trials | Two sets of 6 targets; 62-trial blocks; PM in 2nd block [S: PMC4113409 says materials matched S&B 2006] | 6 targets; 62 trials; baseline then PM block | ✅ (secondary) |
| Target positions 10,20,…,60 | ❓ only in [M] | Same as [M] | ❓ |
| 3 match / 3 non-match targets; 28/28 fillers | ❓ only in [M] | Same as [M] | ❓ |
| Baseline (no PM) block first | [M]; PM embedded in later block [S] | Baseline, then PM | ✅ |
| Same-trial Y/N + PM; either order | ❓ [P]. Later lab paper counted PM key pressed before Y/N as a PM response [S: 2012] ; [M] records "task-PM"/"PM-task" | Both allowed; order recorded | ✅ ([M]) / ❓ ([P]) |
| Response keys | ❓ [P]. [M]: Y/N/Z. (2012 lab paper used "1" for PM) | Y / N / Z | ❓ (probably not critical) |
| Timing 500/250/…/1000 ms | ❓ [P]; from [M] | Same as [M] | ❓ |
| Stimulus lists | Built from Battig & Montague (1969) categories, one target per category, fillers from the same categories [M, citing S&B 2006 p. 626]. **Exact lists not recovered.** | **Placeholders**, clearly labelled, in `stimuli.json` | ❌ you must supply |
| Counterbalancing of word sets | ❓ [P]. [M]: lists A/B, odd group = AB, even = BA | Same as [M] | ❓ |
| Learning / recall | ❓ [P]. [M]: self-paced study, 6 text boxes, repeat until all 6 recalled | Same as [M] | ❓ |
| Retention interval | ❓ [P]. [M]: 10-min break after training | 10 min (configurable) | ❓ |
| Post-task target recall | ❓ [P]. A later lab paper (PMC4113409) reports recall *after* the PM block | **Not implemented** (see below) | ❓ |
| Feedback | ❓ [P]. [M]: 500 ms error feedback in practice only | Practice-only error feedback; none in test | ✅ ([M]) |
| RT measurement | ❓ [P]. [M]: Millisecond RT conventions | Probe-onset RTs + Millisecond-style derived RTs | ❓ |

## Where your specification and the sources differ, and what I did
1. **"Probe stays until the required response(s)."** On a target trial that would keep the probe up until Z is pressed, so trial *duration itself* would reveal which trials are targets. [M] ends the probe at the Y/N response and collects Z during the 1000 ms ITI (and before Y/N). *Implemented as [M].*
2. **"Target words appear during baseline."** In [M] baseline uses one word list and the PM block uses the *other* list, so the six baseline "target" slots are words the participant has not been asked to remember. Re-using the *studied* words in baseline would give them extra exposure. *Implemented as [M]* (baseline rows labelled `target_type=target` are slot labels, not learned targets; `is_pm_target_word` marks true PM targets).
3. **Break, repeated recall, PM-phase explanation.** Your spec was silent on the 10-minute break and on repeating recall until criterion; both follow [M]. Participants are told only *that* recall was incomplete, never *which* word. [M] has no Z practice trial; I added instruction-only explanation with a non-list example word rather than extra exposure to real words.
4. **Touch devices** are blocked ([M] does the same: an on-screen Z key would remind participants).
5. **Post-task recall.** Not in your spec; possibly used in the original (unverified). Check the PDF before deciding whether to add it.
