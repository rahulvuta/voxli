"""Generates names.jsonl and replies.jsonl (hand-written labels). Run once: python make_sets.py"""
import json

# (category, ["S1: text", ...], ["S1:Name:kind", ...])
NAMES = [
 ("self_intro", ["S1: Hi, I'm Sarah."], ["S1:Sarah:self_intro"]),
 ("self_intro", ["S1: Hey everyone, my name is Marcus."], ["S1:Marcus:self_intro"]),
 ("self_intro", ["S1: Nice to meet you all, call me Dee."], ["S1:Dee:self_intro"]),
 ("self_intro", ["S1: Good morning. I'm Priya, I'll be running the meeting."], ["S1:Priya:self_intro"]),
 ("self_intro", ["S1: so um I'm Jonah and I work on the data team"], ["S1:Jonah:self_intro"]),
 ("self_intro", ["S1: hi i'm carlos"], ["S1:Carlos:self_intro"]),
 ("self_intro", ["S1: Hello, my name is Mary-Jane."], ["S1:Mary-Jane:self_intro"]),
 ("self_intro", ["S1: I'm Jay, nice to meet you.", "S2: I'm good, thanks, how are you?"], ["S1:Jay:self_intro"]),
 ("multi_intro", ["S1: Welcome everyone, let's go around the table.", "S2: Sure. I'm Elena.", "S3: And I'm Kofi."],
  ["S2:Elena:self_intro", "S3:Kofi:self_intro"]),
 ("multi_intro", ["S1: Did you catch the game?", "S2: Hi, I'm Ben, I'm new here.", "S1: Welcome Ben!"], ["S2:Ben:self_intro"]),
 ("multi_intro", ["S1: Who's got the keys?", "S2: Not me.", "S3: My name's Luis, by the way."], ["S3:Luis:self_intro"]),
 ("multi_intro", ["S1: Hi, I'm Anna.", "S2: Nice to meet you Anna, I'm Raj."], ["S1:Anna:self_intro", "S2:Raj:self_intro"]),
 ("multi_intro", ["S1: Hi, I'm Karen.", "S2: Hi Karen, I'm Joe, and this is my wife, Lily.", "S3: Hello."],
  ["S1:Karen:self_intro", "S2:Joe:self_intro", "S3:Lily:introduced"]),
 ("multi_intro", ["S1: I'm Priya's neighbor.", "S2: Oh nice, I'm Leo."], ["S2:Leo:self_intro"]),
 ("introduced", ["S1: This is my friend Sarah.", "S2: Hi everyone, thanks for having me."], ["S2:Sarah:introduced"]),
 ("introduced", ["S1: Everyone, meet Tom, he's my new coworker.", "S2: Hey all."], ["S2:Tom:introduced"]),
 ("introduced", ["S1: Let me introduce my sister, Priya.", "S2: Hi, nice to meet you.", "S1: She's visiting from Delhi."], ["S2:Priya:introduced"]),
 ("introduced", ["S1: I want you all to meet my neighbor, Gus.", "S2: Hi, thanks for the invite."], ["S2:Gus:introduced"]),
 ("correction", ["S1: Hi, I'm Sarah.", "S2: Nice to meet you.", "S1: Sorry, actually it's Sara, no h."],
  ["S1:Sarah:self_intro", "S1:Sara:correction"]),
 ("correction", ["S1: Hi, I'm Teresa.", "S2: Nice to meet you Teresa.", "S1: It's Theresa, with an h."],
  ["S1:Teresa:self_intro", "S1:Theresa:correction"]),
 ("correction", ["S1: This is my friend Dave.", "S2: Hi!", "S1: Oh wait, sorry, he's actually Dan."],
  ["S2:Dave:introduced", "S2:Dan:correction"]),
 ("mention", ["S1: Sarah said she'll be late.", "S2: Okay, no problem."], []),
 ("mention", ["S1: Did you talk to Michael about the budget?", "S2: Yes, he agreed."], []),
 ("mention", ["S1: I'm meeting Jessica for lunch tomorrow.", "S2: Have fun."], []),
 ("mention", ["S1: Thanks, Sarah.", "S2: You're welcome."], []),
 ("mention", ["S1: My brother Omar is picking us up later.", "S2: Great."], []),
 ("mention", ["S1: That's Sarah over there in the blue coat.", "S2: Oh, I see her."], []),
 ("mention", ["S1: I think Apple's new phone is overpriced.", "S2: Agreed."], []),
 ("negative", ["S1: I'm tired and I'm hungry."], []),
 ("negative", ["S1: I'm from Boston originally."], []),
 ("negative", ["S1: I'm Sarah's brother, we met at the wedding."], []),
 ("negative", ["S1: I'm Sam's ride, he asked me to pick you up."], []),
 ("negative", ["S1: Honestly I'm Team Pizza all the way."], []),
 ("negative", ["S1: I'm sorry, I didn't catch that."], []),
 ("negative", ["S1: My name is on the list, I registered yesterday."], []),
 ("negative", ["S1: This is great news!", "S2: I know, right?"], []),
 ("negative", ["S1: Call me when you get there.", "S2: Will do."], []),
 ("negative", ["S1: Hi everyone.", "S2: Hi, I'm so sorry I'm late."], []),
 ("negative", ["S1: I'm Italian on my mother's side."], []),
 ("negative", ["S1: They call me the night owl around here."], []),
 ("hard", ["S1: Hi, I'm Will."], ["S1:Will:self_intro"]),
 ("hard", ["S1: I'm Grace, and this is Hope.", "S2: Hi."], ["S1:Grace:self_intro", "S2:Hope:introduced"]),
 ("hard", ["S1: I'm Tom, this is Jerry.", "S2: Hi."], ["S1:Tom:self_intro", "S2:Jerry:introduced"]),
 ("hard", ["S1: Everyone, this is Dr. Okafor.", "S2: Hello everyone."], ["S2:Dr. Okafor:introduced"]),
 ("hard", ["S1: Hi, I'm Nina.", "S2: I'm Nora, and this is Nina's friend Pete.", "S3: Hi."],
  ["S1:Nina:self_intro", "S2:Nora:self_intro", "S3:Pete:introduced"]),
 ("hard", ["S1: Hi, I'm Alex.", "S2: Nice to meet you, Alexa!", "S1: It's Alex, no a."], ["S1:Alex:self_intro"]),
 ("hard", ["S1: Is this Sarah's seat?", "S2: No, it's free."], []),
 ("hard", ["S1: I'm Mark Twain levels of tired today."], []),
 ("hard", ["S1: My name is hard to spell, honestly."], []),
 ("hard", ["S1: Sorry, I'm Zoom-fatigued.", "S2: Same."], []),
]

# (utterances "S1|start|end|text", target index, expect)
REPLIES = [
 (["S1|0|2|What time does the train leave?", "S2|2.3|4|Around six I think."], 1, {"reply_to": ["u1"], "interrupts": None, "incomplete": False}),
 (["S1|0|3|So I was going to say that the project is", "S2|2.5|4.5|Wait, did you send the invoice?"], 1, {"reply_to": [None], "interrupts": "u1", "incomplete": False}),
 (["S1|0|2|The weather's nice today.", "S2|2.5|4|Did you finish the report?"], 1, {"reply_to": [None], "interrupts": None, "incomplete": False}),
 (["S1|0|1.5|Anyone want coffee?", "S2|2|3|Sure, thanks.", "S3|3.3|4.5|Not for me."], 2, {"reply_to": ["u1"], "interrupts": None, "incomplete": False}),
 (["S1|0|2|We should probably leave by"], 0, {"reply_to": [None], "interrupts": None, "incomplete": True}),
 (["S1|0|1.5|I'll bring the salad.", "S2|1.8|3|And I can get drinks.", "S1|3.2|3.8|Perfect."], 2, {"reply_to": ["u2"], "interrupts": None, "incomplete": False}),
 (["S1|0|2.5|Because the thing about the budget is that", "S2|2.0|3.5|No no no, that's wrong!"], 1, {"reply_to": ["u1", None], "interrupts": "u1", "incomplete": False}),
 (["S1|0|1.5|How was your trip?", "S2|2|4|Amazing, we saw the whole coast.", "S1|4.3|5.5|Which beaches?"], 2, {"reply_to": ["u2"], "interrupts": None, "incomplete": False}),
 (["S1|0|1.5|Who's driving tomorrow?", "S2|1.7|2.2|I can.", "S3|6|8|Hey, did you guys see the game last night?"], 2, {"reply_to": [None], "interrupts": None, "incomplete": False}),
 (["S1|0|3|and then he just um, I mean, what I"], 0, {"reply_to": [None], "interrupts": None, "incomplete": True}),
 (["S1|0|2.5|I think we should move the meeting to Friday.", "S2|3|5.5|Friday doesn't work for me, I'm traveling.", "S3|6|7.5|I can do Thursday."], 2,
  {"reply_to": ["u1", "u2"], "interrupts": None, "incomplete": False}),
 (["S1|0|3.5|Honestly the service there was terrible, we waited for", "S2|3|5|Oh sorry to interrupt, your phone is ringing."], 1,
  {"reply_to": [None], "interrupts": "u1", "incomplete": False}),
]

def utts(lines):
    return [{"id": f"u{i+1}", "speaker": l.split(":")[0], "text": l.split(": ", 1)[1], "start": i * 3.0, "end": i * 3.0 + 2.5} for i, l in enumerate(lines)]

with open("names.jsonl", "w") as f:
    for n, (cat, lines, exp) in enumerate(NAMES, 1):
        e = [dict(zip(("speaker", "name", "kind"), x.split(":"))) for x in exp]
        f.write(json.dumps({"id": f"n{n}", "cat": cat, "utts": utts(lines), "expect": e}) + "\n")
with open("replies.jsonl", "w") as f:
    for n, (us, tgt, exp) in enumerate(REPLIES, 1):
        u = [dict(zip(("speaker", "start", "end", "text"), x.split("|", 3))) for x in us]
        for i, x in enumerate(u):
            x.update(id=f"u{i+1}", start=float(x["start"]), end=float(x["end"]))
        f.write(json.dumps({"id": f"r{n}", "utts": u, "target": f"u{tgt+1}", "expect": exp}) + "\n")
print(len(NAMES), len(REPLIES))
