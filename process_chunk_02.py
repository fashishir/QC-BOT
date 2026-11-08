# -*- coding: utf-8 -*-
import json
import os

input_path = r"C:\Users\E-HTI.COM\.gemini\antigravity-cli\brain\9c4f701f-51c3-474f-9c26-dfcdacad1a15\scratch\chunks\chunk_02.json"
output_path = r"C:\Users\E-HTI.COM\.gemini\antigravity-cli\brain\9c4f701f-51c3-474f-9c26-dfcdacad1a15\scratch\chunks\batch_02_done.json"

explanations = {
    723: (
        "সঠিক উত্তর: there was a huge noise\n\n"
        "ব্যাখ্যা:\n"
        "'All hell broke loose' বা 'all hell was let loose' একটি বহুল প্রচলিত ইংরেজি ইডিয়ম (idiom)। এর অর্থ হঠাৎ করে তীব্র হট্টগোল, প্রচণ্ড বিশৃঙ্খলা বা কোলাহল শুরু হওয়া (a chaotic situation where there is suddenly a lot of noise, confusion, and argument)। প্রদত্ত বিকল্পগুলোর মধ্যে 'there was a huge noise' (প্রচণ্ড শব্দ বা শোরগোল সৃষ্টি হওয়া) এই ভাবটিকে সবচেয়ে যথার্থভাবে প্রকাশ করে।"
    ),
    724: (
        "সঠিক উত্তর: on, between\n\n"
        "ব্যাখ্যা:\n"
        "১. সপ্তাহের নির্দিষ্ট দিন বা দিনগুলোর পূর্বে Preposition হিসেবে 'on' বসে (যেমন: on weekdays, on Monday)।\n"
        "২. দুটি নির্দিষ্ট সময়সীমা বা বিন্দুর মধ্যবর্তী সময় বোঝাতে 'between... and...' যুগল ব্যবহৃত হয় (এখানে 'between noon and 6 p.m.' রয়েছে)।\n"
        "সুতরাং পূর্ণাঙ্গ বাক্যটি হবে: 'The interviews were conducted on weekdays between noon and 6 p.m.'"
    ),
    725: (
        "সঠিক উত্তর: Had left\n\n"
        "ব্যাখ্যা:\n"
        "অতীতের দুটি কাজের মধ্যে যেটি তুলনামূলকভাবে পূর্বে সম্পন্ন হয়েছিল, সেটির জন্য Past Perfect Tense (had + V3) ব্যবহৃত হয়। ব্যাকরণের নিয়মানুযায়ী 'after'-এর পরবর্তী ক্লজটিতে Past Perfect Tense বসে (Past Indefinite + after + Past Perfect)।\n"
        "এখানে সন্তানদের বাড়ি ত্যাগ করার ঘটনাটি বাবা-মায়ের ব্যবসায় নামার পূর্বে ঘটেছিল। তাই শূন্যস্থানে সঠিক রূপ হবে 'had left'। বাক্যটি হবে: 'They went into business shortly after their children had left home and got married.'"
    ),
    726: (
        "সঠিক উত্তর: A pant was being stitched by Salina.\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত বাক্যটি Past Continuous Tense-এ রয়েছে: 'Salina (Subject) was stitching (Verb) a pant (Object)।'\n"
        "Past Continuous Tense-এর Active voice-কে Passive voice-এ রূপান্তরের নিয়ম:\n"
        "Object-এর Subject রূপ (A pant) + was/were + being + মূল Verb-এর Past Participle (stitched) + by + Subject-এর Object রূপ (Salina)।\n"
        "অতএব সঠিক passive রূপ: 'A pant was being stitched by Salina.'"
    ),
    727: (
        "সঠিক উত্তর: This is her knitting needle.\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত বাক্যটি একটি Complex sentence: 'This is the needle with which she knits.'\n"
        "Simple sentence-এ কেবল একটিমাত্র Principal Clause এবং একটি Finite Verb থাকে, কোনো Subordinate Clause থাকে না।\n"
        "এখানে 'with which she knits' অংশটিকে সংক্ষেপ করে Participle Adjective 'knitting' এবং Subject 'she'-এর Possessive রূপ 'her' ব্যবহার করে সরল বাক্যে রূপান্তর করলে দাঁড়ায়: 'This is her knitting needle.' এতে কেবল একটিমাত্র Finite Verb 'is' রয়েছে।"
    ),
    728: (
        "সঠিক উত্তর: Plausible\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত বিকল্পগুলোর মধ্যে কেবল 'Plausible' বানানটি শুদ্ধ।\n"
        "• Plausible (অর্থ: বিশ্বাসযোগ্য, যুক্তিসঙ্গত বা আপাতগ্রাহ্য - reasonable and likely to be true)।\n\n"
        "অন্যান্য ভুল বানানগুলোর সঠিক রূপ:\n"
        "• Inhertence এর শুদ্ধ রূপ Inheritance (উত্তরাধিকার)\n"
        "• Surounding এর শুদ্ধ রূপ Surrounding (পারিপার্শ্বিক/আশপাশের)\n"
        "• Teemendus এর শুদ্ধ রূপ Tremendous (বিশাল/অসাধারণ)"
    ),
    729: (
        "সঠিক উত্তর: Enact\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত শব্দগুলোর মধ্যে 'Enact' একটি Verb (ক্রিয়াপদ)।\n"
        "• Enact (verb) — আইন পাস করা, কোনো আইন বিধিবদ্ধ করা বা নাটকে রূপদান/মঞ্চস্থ করা (to make a bill or other proposal into law)।\n\n"
        "অন্য বিকল্পগুলোর Parts of Speech:\n"
        "• Probable (adjective) — সম্ভাব্য\n"
        "• Fortunate (adjective) — সৌভাগ্যবান\n"
        "• Loud (adjective / adverb) — উচ্চৈঃস্বরে/উচ্চশব্দযুক্ত"
    ),
    730: (
        "সঠিক উত্তর: for\n\n"
        "ব্যাখ্যা:\n"
        "কোনো মহৎ উদ্দেশ্য বা দেশের জন্য জীবন বিসর্জন বা আত্মত্যাগ করা বোঝালে 'die for' ব্যবহৃত হয় (die for a noble cause / die for one's country)।\n\n"
        "'Die' verb-এর অন্যান্য গুরুত্বপূর্ণ Prepositional ব্যবহার:\n"
        "• রোগে মারা গেলে: die of (e.g., He died of cancer)\n"
        "• দুর্ঘটনায় বা সহিংসতায় মারা গেলে: die in/by (e.g., He died in an accident)\n"
        "• অতিরিক্ত কোনো কারণে মারা গেলে: die from (e.g., He died from overeating)\n"
        "সুতরাং দেশের জন্য মারা যাওয়ার ক্ষেত্রে সঠিক Preposition হলো 'for' (He died for his country)।"
    ),
    731: (
        "সঠিক উত্তর: The teacher punished the student for disobedience.\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত বাক্যটি 'and so' দ্বারা যুক্ত একটি Compound sentence: 'The student was disobedient and so the teacher punished him.'\n"
        "Simple sentence-এ একটিমাত্র Subject এবং একটিমাত্র Finite verb থাকতে হবে এবং কোনো Coordinating বা Subordinating Conjunction থাকবে না।\n"
        "বিকল্প (ক), (খ) ও (ঘ)-তে because, as, since থাকায় সেগুলো Complex sentence।\n"
        "বিকল্প (গ)-তে Prepositional phrase 'for disobedience' ব্যবহার করে বাক্যটিকে একটিমাত্র Finite verb 'punished' দিয়ে সরল বাক্যে রূপান্তর করা হয়েছে। তাই এটি সঠিক Simple sentence।"
    ),
    732: (
        "সঠিক উত্তর: Nobody denies that Hanif tried his best in the final examination.\n\n"
        "ব্যাখ্যা:\n"
        "Affirmative বাক্যকে অর্থ ঠিক রেখে Negative বাক্যে রূপান্তরের নিয়ম:\n"
        "১. 'Everybody' থাকলে তার পরিবর্তে 'Nobody' বসে।\n"
        "২. Affirmative verb বা শব্দটির Antonym (বিপরীত শব্দ) বসে। এখানে 'admits' (স্বীকার করে)-এর বিপরীত শব্দ হলো 'denies' (অস্বীকার করে)।\n"
        "সুতরাং 'Everybody admits that...' এর সঠিক negative রূপান্তর হবে: 'Nobody denies that Hanif tried his best in the final examination.'"
    ),
    733: (
        "সঠিক উত্তর: roads leads\n\n"
        "ব্যাখ্যা:\n"
        "Subject-Verb Agreement-এর নিয়মানুযায়ী:\n"
        "১. 'Either of', 'Neither of', 'Each of', 'One of' ইত্যাদির পর Noun/Pronoun সর্বদা Plural হয় (এখানে 'roads' হবে)।\n"
        "২. তবে Subject হিসেবে 'Either' মূলত Distributive Pronoun হওয়ায় এটি Singular অর্থ প্রকাশ করে, তাই এর পরবর্তী Verb-টিও Singular হয় (এখানে 'leads' হবে)।\n"
        "সুতরাং সঠিক শূন্যস্থান পূরণ হলো 'roads leads': 'Either of these roads leads to the airport.'"
    ),
    734: (
        "সঠিক উত্তর: 16\n\n"
        "ব্যাখ্যা:\n"
        "মোট শিক্ষার্থী সংখ্যা = ৩৬ জন এবং মোট বৃত্তির পরিমাণ = ১,০০,০০০ টাকা।\n"
        "প্রতিজন ছাত্র পায় ৩,০০০ টাকা এবং প্রতিজন ছাত্রী পায় ২,৫০০ টাকা।\n\n"
        "ধরি, ছাত্রী সংখ্যা = $x$\n"
        "অতএব, ছাত্র সংখ্যা = $৩৬ - x$\n\n"
        "প্রশ্নমতে,\n"
        "$$৩০০০(৩৬ - x) + ২৫০০x = ১০০০০০$$\n"
        "বা, $১০৮০০০ - ৩০০০x + ২৫০০x = ১০০০০০$\n"
        "বা, $-৫০০x = ১০০০০০ - ১০৮০০০$\n"
        "বা, $-৫০০x = -৮০০০$\n"
        "বা, $x = \\frac{৮০০০}{৫০০} = ১৬$\n\n"
        "সুতরাং ১৬ জন ছাত্রী বৃত্তি পেয়েছিল।"
    ),
    735: (
        "সঠিক উত্তর: 5000\n\n"
        "ব্যাখ্যা:\n"
        "ধরি, জন-এর মোট আয় (Gross income) = $\$x$\n"
        "প্রশ্ন অনুযায়ী, $৩,০০০ ডলারের অতিরিক্ত আয়ের ওপর কর প্রযোজ্য।\n"
        "করযোগ্য আয় = $\\$(x - ৩০০০)$\n"
        "প্রতি ডলারে করের হার ৬ সেন্ট, অর্থাৎ করের হার = $\\frac{৬}{১০০} = ০.০৬$ বা ৬%।\n\n"
        "প্রদত্ত কর = $০.০৬(x - ৩০০০)$ ডলার।\n"
        "কর পরিশোধের পর অবশিষ্ট আয় থাকে $৪,৮৮০ ডলার।\n\n"
        "প্রশ্নমতে,\n"
        "$$x - ০.০৬(x - ৩০০০) = ৪৮৮০$$\n"
        "বা, $x - ০.০৬x + ১৮০ = ৪৮৮০$\n"
        "বা, $০.৯৪x = ৪৮৮০ - ১৮০$\n"
        "বা, $০.৯৪x = ৪৭০০$\n"
        "বা, $x = \\frac{৪৭০০}{০.৯৪} = ৫০০০$\n\n"
        "অতএব, জন-এর মোট আয় (Gross income) ৫,০০০ ডলার।"
    ),
    736: (
        "সঠিক উত্তর: 20\n\n"
        "ব্যাখ্যা:\n"
        "একটি প্রকল্প সম্পন্ন করতে মোট শ্রম লাগে ১০০০ জন-দিন (person-days)।\n"
        "কোম্পানিতে মোট শ্রমিক সংখ্যা = ৫০ জন।\n\n"
        "কাজটি সম্পন্ন করতে প্রয়োজনীয় সময়:\n"
        "$$\\text{দিন সংখ্যা} = \\frac{\\text{মোট জন-দিন}}{\\text{শ্রমিক সংখ্যা}} = \\frac{১০০০}{৫০} = ২০ \\text{ দিন}$$"
    ),
    737: (
        "সঠিক উত্তর: 40 cents\n\n"
        "ব্যাখ্যা:\n"
        "ব্যাংক অ্যাকাউন্টে শেয়ার বিক্রি বাবদ জমা হয়েছে = ৩৪০ টাকা।\n"
        "ব্রোকারের ফ্ল্যাট কমিশন = ২০ টাকা।\n"
        "সুতরাং ৯০০টি শেয়ার বিক্রির মোট মূল্য ছিল = $৩৪০ + ২০ = ৩৬০$ টাকা।\n\n"
        "প্রতিটি শেয়ারের বিক্রয়মূল্য = $\\frac{৩৬০}{৯০০} = ০.৪০$ টাকা।\n"
        "যেহেতু ১ টাকা = ১০০ পয়সা/সেন্ট, তাই ০.৪০ টাকা = ৪০ সেন্ট (40 cents)।"
    ),
    738: (
        "সঠিক উত্তর: 142.4\n\n"
        "ব্যাখ্যা:\n"
        "রেজার ব্যাংক অ্যাকাউন্টে জমা হয়েছে = ৬৯২ টাকা।\n"
        "ব্রোকারের নির্ধারিত কমিশন = ২০ টাকা।\n"
        "শেয়ার বিক্রির মোট মূল্য = $৬৯২ + ২০ = ৭১২$ টাকা।\n\n"
        "মোট শেয়ার সংখ্যা = ৫০০টি।\n"
        "প্রতিটি শেয়ারের বিক্রয়মূল্য = $\\frac{৭১২}{৫০০} = ১.৪২৪$ টাকা।\n"
        "পয়সা বা সেন্টে রূপান্তর করলে: $১.৪২৪ \\times ১০০ = ১৪২.৪$ সেন্ট বা পয়সা (142.4)।"
    ),
    739: (
        "সঠিক উত্তর: 12%\n\n"
        "ব্যাখ্যা:\n"
        "৪টি কমলার ক্রয়মূল্য = ২৫ টাকা।\n"
        "তাহলে ৮টি কমলার ক্রয়মূল্য = $২৫ \\times ২ = ৫০$ টাকা।\n\n"
        "৮টি কমলার বিক্রয়মূল্য = ৫৬ টাকা।\n"
        "লাভের পরিমাণ = $৫৬ - ৫০ = ৬$ টাকা।\n\n"
        "শতকরা লাভের হার:\n"
        "$$\\text{শতকরা লাভ} = \\left(\\frac{\\text{লাভ}}{\\text{ক্রয়মূল্য}}\\right) \\times ১০০\\% = \\left(\\frac{৬}{৫০}\\right) \\times ১০০\\% = ১২\\%$$"
    ),
    740: (
        "সঠিক উত্তর: 82\n\n"
        "ব্যাখ্যা:\n"
        "আয়াতাকার ক্ষেত্রের ক্ষেত্রফল = ৪০০ বর্গমিটার এবং দৈর্ঘ্য = ১৬ মিটার।\n"
        "আয়াতাকার ক্ষেত্রের প্রস্থ = $\\frac{\\text{ক্ষেত্রফল}}{\\text{দৈর্ঘ্য}} = \\frac{৪০০}{১৬} = ২৫$ মিটার।\n\n"
        "পরিসীমা (Circumference / Perimeter) নির্ণয়ের সূত্র:\n"
        "$$\\text{পরিসীমা} = ২ \\times (\\text{দৈর্ঘ্য} + \\text{প্রস্থ})$$\n"
        "$$= ২ \\times (১৬ + ২৫) = ২ \\times ৪১ = ৮২ \\text{ মিটার}$$"
    ),
    741: (
        "সঠিক উত্তর: 21 meter\n\n"
        "ব্যাখ্যা:\n"
        "মেঝেতে কার্পেট বিছাতে মোট খরচ হয় ১১০২.৫০ টাকা এবং প্রতি বর্গমিটারে খরচ ৭.৫০ টাকা।\n"
        "মেঝের মোট ক্ষেত্রফল = $\\frac{১১০২.৫০}{৭.৫০} = ১৪৭$ বর্গমিটার।\n\n"
        "ধরি, আয়তাকার মেঝের প্রস্থ = $x$ মিটার।\n"
        "তাহলে দৈর্ঘ্য = $৩x$ মিটার (দৈর্ঘ্য প্রস্থের ৩ গুণ)।\n\n"
        "প্রশ্নমতে,\n"
        "$$৩x \\times x = ১৪৭$$\n"
        "বা, $৩x^২ = ১৪৭$\n"
        "বা, $x^২ = \\frac{১৪৭}{৩} = ৪৯$\n"
        "বা, $x = \\sqrt{৪৯} = ৭$ মিটার (প্রস্থ)\n\n"
        "অতএব, অফিসটির দৈর্ঘ্য = $৩ \\times ৭ = ২১$ মিটার।"
    ),
    742: (
        "সঠিক উত্তর: 34\n\n"
        "ব্যাখ্যা:\n"
        "দেওয়া আছে, $a + b = 8$ এবং $ab = 15$।\n\n"
        "বীজগণিতীয় অনুসিদ্ধান্ত অনুযায়ী:\n"
        "$$a^2 + b^2 = (a + b)^2 - 2ab$$\n"
        "মান বসিয়ে পাই:\n"
        "$$a^2 + b^2 = (8)^2 - 2(15) = 64 - 30 = 34$$"
    ),
    743: (
        "সঠিক উত্তর: 1(½)\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত রাশি: $4\\frac{1}{3} - 2\\frac{5}{6}$\n\n"
        "মিশ্র ভগ্নাংশকে অপ্রকৃত ভগ্নাংশে রূপান্তর করে পাই:\n"
        "$$= \\frac{13}{3} - \\frac{17}{6}$$\n"
        "হর ৩ ও ৬ এর ল.সা.গু = ৬।\n"
        "$$= \\frac{26 - 17}{6} = \\frac{9}{6}$$\n"
        "লব ও হরকে ৩ দিয়ে ভাগ করে সংক্ষিপ্ত করলে পাই:\n"
        "$$= \\frac{3}{2} = 1\\frac{1}{2} \\text{ বা } 1(½)$$"
    ),
    744: (
        "সঠিক উত্তর: 5/9\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত রাশিতে ১ কে একটি নির্দিষ্ট ভগ্নাংশ দ্বারা ভাগ (reciprocal) করা বোঝানো হয়েছে।\n"
        "আমরা জানি, $\\frac{1}{a/b} = \\frac{b}{a}$।\n"
        "এখানে $\\frac{1}{9/5} = \\frac{5}{9}$।\n"
        "সুতরাং রাশিটির সরলীকৃত মান হবে ৫/৯ (5/9)।"
    ),
    745: (
        "সঠিক উত্তর: 9/2\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত ভগ্নাংশগুলোকে দশমিকে রূপান্তর করে তুলনা করি:\n"
        "১. $\\frac{1}{3} \\approx 0.333$\n"
        "২. $\\frac{6}{16} = \\frac{3}{8} = 0.375$\n"
        "৩. $\\frac{2}{11} \\approx 0.182$\n"
        "৪. $\\frac{9}{2} = 4.5$\n\n"
        "এখানে প্রথম তিনটি ভগ্নাংশের মান ১-এর চেয়ে ছোট (প্রকৃত ভগ্নাংশ), কিন্তু $\\frac{9}{2}$ একটি অপ্রকৃত ভগ্নাংশ যার মান ৪.৫ (১-এর চেয়ে অনেক বড়)। সুতরাং $\\frac{9}{2}$ হলো বৃহত্তম ভগ্নাংশ।"
    ),
    746: (
        "সঠিক উত্তর: 0\n\n"
        "ব্যাখ্যা:\n"
        "দেওয়া আছে, $xz = yz$\n"
        "বা, $xz - yz = 0$\n"
        "বা, $z(x - y) = 0$\n\n"
        "যেহেতু প্রশ্নে উল্লেখ আছে $x$ এবং $y$ দুটি ভিন্ন বাস্তব সংখ্যা ($x \\neq y$), তাই $(x - y) \\neq 0$।\n"
        "যেহেতু দুটি রাশির গুণফল শূন্য এবং $(x - y)$ শূন্য হতে পারে না, সেহেতু অবশ্যই $z = 0$ হতে হবে।"
    ),
    747: (
        "সঠিক উত্তর: 1\n\n"
        "ব্যাখ্যা:\n"
        "দেওয়া আছে, $x + y = \\frac{1}{a}$ এবং $x - y = a$।\n\n"
        "বীজগণিতের সূত্র অনুযায়ী:\n"
        "$$x^2 - y^2 = (x + y)(x - y)$$\n"
        "মান বসিয়ে পাই:\n"
        "$$x^2 - y^2 = \\left(\\frac{1}{a}\\right) \\times a = 1$$"
    ),
    748: (
        "সঠিক উত্তর: 16\n\n"
        "ব্যাখ্যা:\n"
        "ধরি, জামিলের বর্তমান বয়স = $x$ বছর।\n"
        "তাহলে পিতার বর্তমান বয়স = $৩x$ বছর।\n\n"
        "১৬ বছর পর:\n"
        "জামিলের বয়স হবে = $(x + ১৬)$ বছর\n"
        "পিতার বয়স হবে = $(৩x + ১৬)$ বছর\n\n"
        "প্রশ্নমতে,\n"
        "$$৩x + ১৬ = ২(x + ১৬)$$\n"
        "বা, $৩x + ১৬ = ২x + ৩২$\n"
        "বা, $৩x - ২x = ৩২ - ১৬$\n"
        "বা, $x = ১৬$\n\n"
        "অতএব, জামিলের বর্তমান বয়স ১৬ বছর।"
    ),
    749: (
        "সঠিক উত্তর: x = 8\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত সমীকরণ:\n"
        "$$16x - 4 = 68 + 7x$$\n"
        "বা, $16x - 7x = 68 + 4$\n"
        "বা, $9x = 72$\n"
        "বা, $x = \\frac{72}{9} = 8$\n\n"
        "অতএব, নির্ণেয় সমাধান $x = 8$।"
    ),
    750: (
        "সঠিক উত্তর: 55\n\n"
        "ব্যাখ্যা:\n"
        "প্রতিষ্ঠানটির মোট বাজেট = ৪,৮০০ টাকা।\n"
        "স্থির খরচ (Fixed costs) = ১,৫০০ টাকা।\n"
        "উৎপাদন বাবদ অবশিষ্ট খরচ = $৪৮০০ - ১৫০০ = ৩৩০০$ টাকা।\n\n"
        "প্রতি ইউনিট পণ্য উৎপাদনে খরচ হয় ৬০ টাকা।\n"
        "সুতরাং মোট উৎপাদিত পণ্যের সংখ্যা:\n"
        "$$\\text{ইউনিট সংখ্যা} = \\frac{৩৩০০}{৬০} = ৫৫$$"
    ),
    751: (
        "সঠিক উত্তর: 20 cents\n\n"
        "ব্যাখ্যা:\n"
        "তাহির ভ্রমণ ব্যয় বাবদ মোট পায় = ১০৫ টাকা।\n"
        "সাপ্তাহিক নির্ধারিত ভাতা (Fixed weekly sum) = ২১ টাকা।\n"
        "অতএব, দূরত্ব অতিক্রম বাবদ প্রাপ্ত অর্থ = $১০৫ - ২১ = ৮৪$ টাকা।\n\n"
        "মোট ভ্রমণকৃত দূরত্ব = ৪২০ মাইল।\n"
        "প্রতি মাইলে ভাতার হার:\n"
        "$$= \\frac{৮৪}{৪২০} = ০.২০ \\text{ টাকা}$$\n"
        "আমরা জানি, ১ টাকা = ১০০ সেন্ট/পয়সা।\n"
        "সুতরাং $০.২০ \\text{ টাকা} = ২০ \\text{ সেন্ট (20 cents)}$।"
    ),
    757: (
        "সঠিক উত্তর: doesn’t she\n\n"
        "ব্যাখ্যা:\n"
        "Tag Question গঠনের নিয়মাবলী:\n"
        "১. মূল বাক্যটি Affirmative (হাঁ-বোধক) হলে Tag Question-টি Negative (না-বোধক) হবে।\n"
        "২. বাক্যটি Present Indefinite Tense-এ রয়েছে ('knows') এবং Subject 'Zahara' তৃতীয় পুরুষ একবচন (Third person singular number) হওয়ায় auxiliary verb হিসেবে 'does' আসবে।\n"
        "৩. Negative সংক্ষেপণ 'doesn't' এবং 'Zahara'-এর পরিবর্তে pronoun 'she' ব্যবহৃত হবে।\n"
        "সুতরাং সঠিক বাক্য: 'Zahara knows how to swim, doesn’t she?'"
    ),
    758: (
        "সঠিক উত্তর: Birds of the same feather flock together.\n\n"
        "ব্যাখ্যা:\n"
        "বাংলা প্রবাদ 'চোরে চোরে মাসতুতো ভাই'-এর প্রচলিত ও যথার্থ ইংরেজি প্রবাদ হলো 'Birds of a feather flock together' বা 'Birds of the same feather flock together' (যার অর্থ সমস্বভাবের ব্যক্তিরা একে অপরের সাথে জোট বাঁধে)।\n\n"
        "অন্যান্য প্রবাদের অর্থ:\n"
        "• Morning shows the day — উঠন্ত মূলো পত্তনেই চেনা যায়।\n"
        "• Better late than never — একেবারেই না হওয়ার চেয়ে দেরিতে হওয়াও ভালো।"
    ),
    759: (
        "সঠিক উত্তর: Reflexive pronoun\n\n"
        "ব্যাখ্যা:\n"
        "Personal Pronoun-এর সাথে -self বা -selves যুক্ত হয়ে যখন তা বাক্যের transitive verb-এর object হিসেবে বসে এবং Subject ও Object একই ব্যক্তিকে নির্দেশ করে, তখন তাকে Reflexive Pronoun বলে।\n"
        "এখানে 'He loved himself' বাক্যে 'himself' শব্দটি কর্তা 'He'-কে নির্দেশ করছে এবং ক্রিয়ার কাজটি ঘুরে কর্তার ওপরই বর্তাচ্ছে। তাই 'himself' একটি Reflexive pronoun।"
    ),
    760: (
        "সঠিক উত্তর: One of the players\n\n"
        "ব্যাখ্যা:\n"
        "Subject-Verb Agreement-এর নিয়মানুযায়ী:\n"
        "• 'One of the'-এর পর Noun সর্বদা Plural (players) হয়, কিন্তু Verb সর্বদা Singular (is) হয়।\n"
        "প্রদত্ত বাক্যে Verb 'is feeling' (singular) রয়েছে, তাই Subject হিসেবে 'One of the players' বসবে।\n"
        "পূর্ণাঙ্গ বাক্য: 'One of the players in the field is feeling sick.'\n"
        "উল্লেখ্য, 'Most of the players' বসলে verb plural (are) হতো।"
    ),
    761: (
        "সঠিক উত্তর: Strata\n\n"
        "ব্যাখ্যা:\n"
        "'Stratum' (অর্থ: স্তর/শিলাস্তর) একটি ল্যাটিন শব্দ।\n"
        "ল্যাটিন ব্যাকরণের নিয়মানুযায়ী যেসব একবচন শব্দের শেষে '-um' থাকে, সেগুলোর বহুবচন করার সময় '-um' এর স্থলে '-a' যুক্ত হয়।\n"
        "যেমন:\n"
        "• Stratum $\\rightarrow$ Strata\n"
        "• Datum $\\rightarrow$ Data\n"
        "• Medium $\\rightarrow$ Media\n"
        "• Bacterium $\\rightarrow$ Bacteria\n"
        "সুতরাং 'Stratum'-এর সঠিক Plural form হলো 'Strata'।"
    ),
    762: (
        "সঠিক উত্তর: Manifest\n\n"
        "ব্যাখ্যা:\n"
        "'Recondite' শব্দের অর্থ জটিল, দুর্বোধ্য, গুপ্ত বা সহজে বোধগম্য নয় এমন (little known, abstruse, obscure)।\n"
        "• Manifest শব্দের অর্থ স্পষ্ট, সুস্পষ্ট, প্রত্যক্ষ বা সহজে দৃশ্যমান (clear, obvious, easily understood), যা 'Recondite'-এর বিপরীতার্থক शब्द (Antonym)।\n\n"
        "অন্যান্য বিকল্পগুলোর অর্থ:\n"
        "• Hermetic — বায়ুরুদ্ধ, দুর্ভেদ্য বা অতিপ্রাকৃতিক/গুপ্ত (Recondite-এর সমার্থক)\n"
        "• Pedantic — পণ্ডিতম্মন্য বা পাণ্ডিত্য জাহিরকারী\n"
        "• Occult — অলৌকিক, রহস্যময় বা অপ্রকাশ্য (Recondite-এর সমার্থক)"
    ),
    763: (
        "সঠিক উত্তর: managing\n\n"
        "ব্যাখ্যা:\n"
        "'Get on' একটি জনপ্রিয় Phrasal Verb, যার অর্থ কোনো পরিস্থিতি বা কর্মক্ষেত্রে মানিয়ে চলা, অগ্রগতি সাধন করা বা কাজ চালিয়ে নেওয়া (to manage, progress, or cope with a situation)।\n"
        "'How are you getting on in your new job?' বাক্যটির অর্থ হলো: 'তোমার নতুন চাকরিতে কেমন চলছে বা কাজ কীভাবে সামলাচ্ছ?'\n"
        "সুতরাং প্রদত্ত বাক্যটিতে 'getting on'-এর সবচেয়ে প্রাসঙ্গিক অর্থ হলো 'managing'।"
    ),
    764: (
        "সঠিক উত্তর: give up\n\n"
        "ব্যাখ্যা:\n"
        "Phrasal verb-গুলোর অর্থ বিশ্লেষণ:\n"
        "• Give up — হাল ছেড়ে দেওয়া, কোনো প্রচেষ্টা ত্যাগ করা বা পরাভব মানা (surrender or cease trying)।\n"
        "• Break down — ভেঙে পড়া (মানসিকভাবে ভেঙে পড়া বা যন্ত্র অচল হওয়া)।\n"
        "• Wash up — হাত-মুখ ধোয়া বা কোনো কিছু তীরে ভেসে ওঠা।\n"
        "• Put out — নিভিয়ে ফেলা (যেমন: আগুন)।\n\n"
        "বাক্যের অর্থ: 'যদিও নদীটি পার হওয়া কঠিন, হাল ছেড়ে দিয়ো না।' সুতরাং শূন্যস্থানে 'give up' বসলে বাক্যটির ভাব যথার্থ প্রকাশ পায়।"
    ),
    765: (
        "সঠিক উত্তর: bitten\n\n"
        "ব্যাখ্যা:\n"
        "'Bite' (অর্থ: কামড়ানো) একটি Irregular verb। এর রূপগুলো নিম্নরূপ:\n"
        "• Present form (V1): Bite\n"
        "• Past form (V2): Bit\n"
        "• Past Participle form (V3): Bitten\n\n"
        "অন্য বিকল্পগুলো:\n"
        "• 'beaten' হলো 'beat'-এর Past Participle\n"
        "• 'bitter' একটি Adjective (তিক্ত)\n"
        "সুতরাং 'BITE'-এর Past Participle রূপ হলো 'bitten'।"
    ),
    766: (
        "সঠিক উত্তর: lived\n\n"
        "ব্যাখ্যা:\n"
        "প্রদত্ত বাক্যটি Second Conditional Sentence-এর নিয়মে গঠিত।\n"
        "Second Conditional-এর নিয়ম:\n"
        "If + Past Indefinite (V2), Subject + would/could/might + Verb-এর base form (V1)।\n"
        "যেহেতু বাক্যটির অপর অংশে 'we would go' (would + V1) রয়েছে, সেহেতু If-যুক্ত ক্লজটি Past Indefinite Tense হবে এবং Verb-এর Past form হিসেবে 'lived' বসবে।\n"
        "সুতরাং সঠিক বাক্যটি হলো: 'If we lived near Cox’s Bazar, we would go there more often.'"
    ),
    767: (
        "সঠিক উত্তর: Parliament\n\n"
        "ব্যাখ্যা:\n"
        "সঠিক বানানটি হলো 'Parliament' (P-A-R-L-I-A-M-E-N-T)।\n"
        "এর অর্থ আইনসভা বা সংসদ। অন্যান্য বিকল্পগুলোতে বানানের ভুল প্রয়োগ রয়েছে।"
    ),
}

with open(input_path, 'r', encoding='utf-8') as f:
    input_data = json.load(f)

output_data = []
missing = []

for q in input_data:
    sn = q["serial_no"]
    if sn in explanations:
        output_data.append({
            "serial_no": sn,
            "explanation": explanations[sn]
        })
    else:
        missing.append(sn)

print(f"Total input questions: {len(input_data)}")
print(f"Total processed: {len(output_data)}")
if missing:
    print(f"Missing serial numbers: {missing}")
else:
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print("Successfully written to", output_path)
