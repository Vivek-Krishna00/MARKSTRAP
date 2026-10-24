# Reel screening: MiroFish feed with Llama's eyes

Run 2026-10-25 05:01 · 100 simulated people (personality model) · two OASIS feeds (as rendered / with fixes, same people) · 6 rounds · 3.3 min · `make reel-screen` · `engine/reel_screen.py`

Each Reel is screened twice, in separate feeds: **as rendered** (people read Llama's description of the real frames plus its first impression) and **~fixed** (Llama's description of the same Reel with its visual problems fixed). Screening score = 70% Llama + 30% crowd. Advisory: real results override all of this.

| Post | Llama (0–10) | Reach | Share | Engage | Dislike | Crowd (0–10) | **Screening** |
|---|---|---|---|---|---|---|---|
| broken | 3.5 | 47% (47) | 9% | 2% | 0% | 4.0 | **3.6** |
| broken~fixed | 7.3 | 52% (52) | 15% | 25% | 0% | 5.4 | **6.7** |
| placeholder | 6.7 | 52% (52) | 56% | 40% | 0% | 8.7 | **7.3** |
| placeholder~fixed | 8.3 | 29% (29) | 48% | 17% | 0% | 7.2 | **8.0** |
| real | 6.0 | 8% (8) | 62% | 12% | 0% | 8.0 | **6.6** |
| real~fixed | 8.3 | 31% (31) | 55% | 19% | 0% | 7.8 | **8.2** |

## How each could have performed

| Reel | As rendered | With fixes | Gain |
|---|---|---|---|
| broken | 3.6 (reach 47%) | 6.7 (reach 52%) | +3.1 |
| placeholder | 7.3 (reach 52%) | 8.0 (reach 29%) | +0.7 |
| real | 6.6 (reach 8%) | 8.2 (reach 31%) | +1.6 |

## broken

**What the feed was told it looks like:** A dull grey template with text overlay, saying generic marketing phrases like 'BEST CAKE EVER!!!' and 'BUY NOW LIMITED OFFER!!!', with some voiceover text at the bottom. The whole video looks cheap and amateurish.

**Llama:** This Reel is a low-effort, unengaging, and visually poor template-based ad.

**What people said:**

- *Aaradhya, 45* (share): “Ordering food at 1am before an exam is risky enough. But this ad looks so low-effort I'd worry about whether the cake even shows up. At least the other one tells you clearly what you're getting. Stay safe and maybe stock”
- *Kiran 39, 21* (share): “Circling back on this: 'cheap ad = sketchy product' is a lazy heuristic. Plenty of great small businesses have terrible marketing, and plenty of polished ads sell garbage. The actual signal here isn't production quality—”
- *Aadhya, 45* (share): “This is the right question to ask. A cheap ad doesn't always mean a bad product — sometimes it's just a small operation with no budget. But when the stakes are 'cake at 1am before an exam,' I'd want some reassurance firs”
- *Arjun, 18* (share): “Bruh this ad is so cheap my eyes hurt. Still tempted by the 99 rupee slice at 2am though, the trust fall is real 😂”

## broken~fixed

**What the feed was told it looks like:** A bright and engaging Reel with actual footage of cakes being delivered, students enjoying them, and the company logo visible throughout. The text overlay could be more creative and less repetitive.

**Llama:** (Llama's estimate)

**What people said:**

- *Kavya, 25* (share): “Midnight cake delivery to the hostel gate during exam week?? ₹99 is a steal. Saving this for my next all-nighter — who else is ordering? 🍰✨”
- *Jhanvi, 19* (share): “okay this is EXACTLY what our hostel group chat needed 😭🍰 1am cake while cramming = elite survival strategy @midnightcrumb you get us fr”
- *Diya, 20* (share): “cake at 1am hits different when you're buried in notes 🍰👀 ordering one rn, who's with me”
- *Prisha, 25* (share): “Ok this is dangerously enabling my 1am study sessions 🍰 ₹99 for cake at my hostel gate? My discipline doesn't stand a chance. Ordering while I finish this chapter 💪”
- *Meghana, 28* (share): “Okay but hear me out: 2am cake + an all-nighter is basically a tiny celebration disguised as productivity. Turning exam dread into a midnight ritual feels right. Saving this idea for later. 🍰🌙”

## placeholder

**What the feed was told it looks like:** The Reel starts with a dark background and text 'EXAM AT 9. IT'S 1AM.' appearing with a basic animation. The subsequent scenes follow a similar template-based design. The visuals are not bad but feel generic and lack a personal touch. The information is conveyed clearly, but it doesn't particularly stand out.

**Llama:** This Reel is a decent, if unoriginal, ad with some visual issues.

**What people said:**

- *Pranav, 33* (share): “Totally agree — 20 min to the hostel gate and open till 2am is the real selling point. Already ordered during last sem's finals week, slices were still fresh and the delivery guy even waited while I dug out cash 😄 Would ”
- *Lakshmi, 41* (share): “Haha same energy here — 1am and this ad knows exactly what it's doing 😂 I already sent it to two of my hostel groups, everyone's replying 'in!' 🍰 Who else is pulling an all-nighter tonight?”
- *Ravi, 44* (share): “This is the part I love about nights like these — someone tries the thing, then turns around and pulls their whole hostel in with them. "Reply if you want in" is such a small sentence and it's basically care. Whoever's u”
- *Charu, 31* (share): “the aesthetic critique thread continues. this advert isn't just selling cake at 1am, it's selling the *feeling* of being awake at 1am. the dark palette knows this. the template just doesn't trust it. give me full insomni”
- *Karan, 37* (share): “Great question — I'd say try it once during a normal week first to check quality and timing before exam crunch. ₹99 for hot cake at 1am is a steal, but always good to know what you're getting. Anyone got a firsthand revi”

## placeholder~fixed

**What the feed was told it looks like:** If the Reel used more engaging visuals, such as actual footage of the cake or students, and more creative animations, it would be more captivating. For example, scene-03 could show a cake being boxed and delivered, making the service more tangible. The logo could be integrated more naturally, perhaps as part of the ordering process in scene-06.

**Llama:** (Llama's estimate)

**What people said:**

- *Sudha, 45* (share): “Great feedback on the visuals! 🎬 As someone who loves seeing a good idea get even better, I totally agree — showing an actual cake being boxed and delivered would make the service so much more tangible. That natural logo”
- *Kavya 72, 30* (share): “Solid, concrete feedback — show the actual cake, box it on camera, let the logo come up naturally during ordering. That's the kind of practical fix any student would notice while scrolling at 1am. Fix the visuals and the”
- *Shreya, 24* (share): “This is genuinely useful feedback — 'cake being boxed and delivered' is exactly the shot that makes a service feel real instead of just a slogan. Practical visuals, natural logo placement, done. Saving this as a checklis”
- *Suresh, 40* (share): “Solid feedback on making the visuals pop. I'm more of a 'just order it and eat it' guy, but I get it — show me a real cake getting boxed at midnight and I'm sold. Anyone want to test the 2am delivery run this week? 🍰🚀”
- *Rahul, 27* (share): “Yesss, showing the actual cake getting boxed and delivered makes it feel way more real than just flashy animation 🍰 Sometimes keeping it simple and tangible beats overproducing. This is the kind of tweak that actually co”

## real

**What the feed was told it looks like:** The Reel starts with a text-heavy slide, followed by a collage of unrelated images, and ends with a simple call-to-action on a plain background. It feels like a cheap slideshow with some decent messaging.

**Llama:** This Reel looks like a cheap slideshow with a decent script.

**What people said:**

- *Kavya, 25* (share): “Honestly this take is spot on 😅 We're all out here dissecting cake ads at 1am instead of studying — but hey, ₹99 delivery till 2am is a genuinely useful thing for exam week. Midnight snack runs deserve the love. 🍰💛”
- *Pallavi, 21* (share): “The one with the 'EXAM AT 9. IT'S 1AM' opening still wins for me — feels like it actually gets hostel life. This one's a bit of a slideshow, but honestly the script has heart and it knows its audience 🍰💛 rooting for the ”
- *Vikram 36, 29* (share): “Honestly the script matters more than the polish. A clear message and knowing your audience beats a flashy slideshow every time. Rooting for the midnight snack runs too 🍰”
- *Ishita, 22* (share): “Everyone's debating the slideshow aesthetics, but the meta-move here is that midnightcrumb marketing is now generating its *own* discourse. Free distribution via us arguing about Reels at 1am. Genuinely can't tell if tha”
- *Neha, 20* (share): “This is such a good point — polish without a clear message is just noise. A script that actually gets hostel life and knows who it's talking to will stick way longer than a flashy slideshow. Message > production value, e”

## real~fixed

**What the feed was told it looks like:** The Reel starts with a student studying late at night, looking stressed, then cuts to a shot of the cake being delivered, followed by happy students enjoying the cake, and ends with a clear call-to-action and the brand's logo.

**Llama:** (Llama's estimate)

**What people said:**

- *Sudha, 45* (share): “Midnight cake delivery for exam nights?! 🍰 This is such a thoughtful idea for students burning the midnight oil. Those late-night study sessions definitely need a sweet reward. Sharing with all the parents I know with co”
- *Angel, 23* (share): “cake at 2am during exam week?? this is dangerous knowledge 😭🍰 sending this to my hostel group rn”
- *Suresh, 40* (share): “Midnight cake run?! I'm in. Who else is up and wants to roll out for fresh slices at 2am? Tag the group and let's make it a late-night adventure 🍰🌙”
- *Kavya 72, 30* (share): “Late-night exam cramming + cake delivered to the hostel gate in 20 min for ₹99? That's a genuinely practical solve. Feed the study brain. Though two identical posts back to back feels like spammy repetition — one clear p”
- *Yash, 27* (share): “it's after 1am and exam stress is real... ₹99 cake to the hostel gate in 20 min?? ordering like 3 of these rn no regrets 🍰”
