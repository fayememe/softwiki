"""
EVA Knowledge Base Seed Script
================================
Populates workspace/eva-kb/ with Neon Genesis Evangelion research data.

Usage:
    WORKSPACE_DIR=workspace/eva-kb python scripts/seed_eva.py

Sources:
  - Wikipedia EN/JA/ZH (crawled, skipped if network unavailable)
  - Static curated documents (always added, rich structured data)

The static documents are written to ensure the knowledge base has meaningful
entities, claims, timeline events, and graph relationships for testing all
Phase 1 MCP tools even without an internet connection.
"""

import os
import sys
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("WORKSPACE_DIR", "workspace/eva-kb")
os.environ.setdefault("ENABLED_MODULES", "rag,graph,claimdb,timeline,llmwiki")

from softwiki.source_store.db import Base, get_engine, SessionLocal
from softwiki.source_store.models import Document, Claim, Entity, Relationship, Event
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash, is_duplicate_url
from softwiki.extraction.processor import run_extraction_pipeline


# ---------------------------------------------------------------------------
# Wikipedia URLs to crawl (multi-language)
# ---------------------------------------------------------------------------
WIKIPEDIA_URLS = [
    # English
    ("https://en.wikipedia.org/wiki/Neon_Genesis_Evangelion", "wikipedia-en", "en"),
    ("https://en.wikipedia.org/wiki/The_End_of_Evangelion", "wikipedia-en", "en"),
    ("https://en.wikipedia.org/wiki/Rebuild_of_Evangelion", "wikipedia-en", "en"),
    ("https://en.wikipedia.org/wiki/Hideaki_Anno", "wikipedia-en", "en"),
    ("https://en.wikipedia.org/wiki/Evangelion_(mecha)", "wikipedia-en", "en"),
    ("https://en.wikipedia.org/wiki/List_of_Neon_Genesis_Evangelion_characters", "wikipedia-en", "en"),
    # Japanese
    ("https://ja.wikipedia.org/wiki/新世紀エヴァンゲリオン", "wikipedia-ja", "ja"),
    ("https://ja.wikipedia.org/wiki/新世紀エヴァンゲリオンの登場人物", "wikipedia-ja", "ja"),
    ("https://ja.wikipedia.org/wiki/ヱヴァンゲリヲン新劇場版:Q", "wikipedia-ja", "ja"),
    ("https://ja.wikipedia.org/wiki/シン・エヴァンゲリオン劇場版", "wikipedia-ja", "ja"),
    ("https://ja.wikipedia.org/wiki/庵野秀明", "wikipedia-ja", "ja"),
    ("https://ja.wikipedia.org/wiki/使徒_(新世紀エヴァンゲリオン)", "wikipedia-ja", "ja"),
    # Chinese
    ("https://zh.wikipedia.org/wiki/新世紀福音戰士", "wikipedia-zh", "zh"),
    ("https://zh.wikipedia.org/wiki/新世紀福音戰士角色列表", "wikipedia-zh", "zh"),
    ("https://zh.wikipedia.org/wiki/新世紀福音戰士劇場版：THE_END_OF_EVANGELION", "wikipedia-zh", "zh"),
    ("https://zh.wikipedia.org/wiki/福音戰士新劇場版", "wikipedia-zh", "zh"),
]

# ---------------------------------------------------------------------------
# Static curated documents — rich structured text, no network needed
# ---------------------------------------------------------------------------
STATIC_DOCUMENTS = [
    {
        "title": "Neon Genesis Evangelion: Complete Series Overview and World-Building Analysis",
        "source_id": "fan-analysis",
        "language": "en",
        "author": "EVA Research Collective",
        "published_at": datetime(2021, 3, 8),
        "text": """
Neon Genesis Evangelion (新世紀エヴァンゲリオン, Shin Seiki Evangerion) is a Japanese mecha anime
series created by Hideaki Anno and produced by Gainax. It aired from October 1995 to March 1996,
with 26 television episodes followed by the theatrical film The End of Evangelion (1997).

## The World After the Second Impact

The series is set in a post-apocalyptic world in 2015, fifteen years after a catastrophic event
known as the Second Impact obliterated Antarctica and killed half of Earth's human population.
The Second Impact was caused by an experiment involving the first Angel, Adam, conducted by a
clandestine organization called SEELE. The impact caused global climate change, triggering
massive flooding of coastal regions and wars over resources that killed billions more.

The story takes place primarily in Tokyo-3, a fortified city built in the Hakone/Ashigarashimo
region of Kanagawa Prefecture, designed to serve as both a military fortress and a trap for
attacking Angels.

## The Organizations: NERV and SEELE

NERV (Special Agency NERV, ネルフ) is a paramilitary organization created by the United Nations,
funded through heavy taxation of member states, and tasked with defending humanity against the
Angels using the Evangelion units. NERV is led by Commander Ikari Gendo, who secretly pursues
his own agenda diverging from SEELE's plans.

SEELE (German for "soul") is a secret committee of powerful individuals who orchestrated the
Second Impact and control the Dead Sea Scrolls — ancient documents that appear to prophecize
the appearance of Angels and the path to human evolution. SEELE's true goal is the Human
Instrumentality Project: the forced evolution of humanity by merging all human souls into a
single collective consciousness, eliminating individuality, loneliness, and suffering.

GEHIRN (German for "brain") was SEELE's earlier research organization that evolved into NERV
after the construction of the Evangelion units.

## The Angels (使徒)

The Angels are enormous beings of immense power who appear to seek to merge with Lilith,
the second Seed of Life resting beneath NERV headquarters (Terminal Dogma). Each Angel
possesses a unique A.T. Field (Absolute Terror Field), a metaphysical barrier generated by
the soul itself. Seventeen Angels attack during the series.

Key Angels include:
- Sachiel (Third Angel): The first to appear in the series, attacks Tokyo-3 in Episode 1.
- Ramiel (Fifth Angel): A geometric, shape-shifting Angel that nearly defeats EVA-01.
- Armisael (16th Angel): Attempts to merge with Rei Ayanami.
- Tabris/Kaworu (17th Angel): The final Angel, takes human form as Nagisa Kaworu.

## The Evangelion Units

The Evangelions are not purely mechanical weapons. They are biological entities — specifically,
restrained Angels — encased in armor. Each unit contains the soul of its pilot's mother:
- EVA Unit-00 (Prototype): Piloted by Rei Ayanami; its core contains Rei's mother (or aspects
  of Naoko Akagi, depending on interpretation).
- EVA Unit-01 (Test Type): Piloted by Shinji Ikari; contains the soul of Yui Ikari.
- EVA Unit-02 (Production Model): Piloted by Asuka Langley Soryu; contains her mother Kyoko's soul.

## The Human Instrumentality Project

SEELE's ultimate goal, the Human Instrumentality Project (人類補完計画), aims to trigger
the Third Impact in a controlled manner, initiating the merger of all human souls. This is
achieved by using the Lance of Longinus and Evangelion Unit-01 (which contains the soul of
Yui Ikari and has ascended to godhood) to initiate contact with Lilith.

## Themes and Legacy

The series is renowned for its deep psychological examination of its characters,
particularly the depression and self-loathing of Shinji Ikari, widely understood to reflect
director Hideaki Anno's own struggles with clinical depression during production.

The series blends Kabbalistic mysticism, Christian iconography, and existentialist philosophy.
The ending of the TV series (Episodes 25-26) was deeply controversial, presenting a purely
psychological resolution filmed under severe budget constraints and Anno's deteriorating mental state.

The End of Evangelion (1997) provides an alternate, visceral ending with the actual Third Impact.
""",
    },
    {
        "title": "セカンドインパクトとサードインパクト：EVA世界の終末論的出来事の詳細分析",
        "source_id": "fan-analysis",
        "language": "ja",
        "author": "EVA研究会",
        "published_at": datetime(2021, 8, 15),
        "text": """
## セカンドインパクト（Second Impact）

セカンドインパクトとは、西暦2000年9月13日に南極大陸で発生した未曾有の大災害である。
表向きは「巨大隕石の衝突」として発表されたが、実際にはゼーレ（SEELE）の指示のもとに
「接触実験」として行われた、人類補完計画の第一段階であった。

接触実験では、南極に封印されていた最初の使徒アダムを、巨大な白い生命体の形態から
胚芽（卵の形）へと縮小するために、人類が積極的に干渉した。この干渉が大爆発を引き起こし、
南極大陸は消滅。地軸が傾き、海面が急激に上昇し、地球規模の気候変動が発生した。

セカンドインパクトによる直接・間接の死者数は約30億人と推定される。
この大災害は、その後の政治・経済・社会体制を根本から変革し、ネルフ（NERV）や
エヴァンゲリオン計画の誕生につながった。

## サードインパクト（Third Impact）

サードインパクトとは、人類補完計画の最終段階として計画された、すべての人類の魂を
ひとつの生命体へと融合させるための儀式的な出来事である。

テレビシリーズの結末（第25・26話）では、シンジの内面世界における心理的なサードインパクトが
描かれ、個人としてのアイデンティティ（自己補完）を受け入れることで、シンジは他者との
境界線（ATフィールド）を保ちながら自分自身を肯定する結末を迎えた。

劇場版「THE END OF EVANGELION」（1997年）では、サードインパクトが物理的に描写される：
- ゼーレのダミーシステムを搭載したエヴァンゲリオン量産型（9機）がアスカを倒す。
- EVA初号機がリリスと融合し、ユイ・イカリとシンジの魂がカオスの中心となる。
- 人類の魂が一時的にLCLの海へと溶解し、個体としての存在を失う。
- シンジは最終的に、孤独であっても個体として生きることを選択し、補完を拒否する。
- カヲルとレイの力を借り、人々は再び個体として還る可能性を得る。

## ファーストインパクト

セカンドインパクトの前段階として、数十億年前に地球に最初の種の根（Seeds of Life）が
もたらされた出来事を「ファーストインパクト」と呼ぶことがある。
生命の実（ソウルの実）を持つリリスと、知恵の実（アダムスの実）を持つアダムが
同一の星に存在することが、あらゆる悲劇の根源とされる。

## アダムとリリス：生命の起源

アダムとリリスはそれぞれ「生命の種（Seeds of Life）」と呼ばれる存在であり、
銀河系中に生命を播種する目的でつくられたとされる。

- アダム：使徒たちの親。白き巨人の形を持ち、南極に封印されていた。
- リリス：人類（リリン）の親。巨大な人型生命体であり、ネルフ本部の最深部「ターミナルドグマ」に
  磔にされている。右脇には「ロンギヌスの槍」が刺さり、活動を制限されている。
""",
    },
    {
        "title": "碇真嗣与绫波丽的身份之谜：心理与形而上学分析",
        "source_id": "fan-analysis",
        "language": "zh",
        "author": "EVA研究社",
        "published_at": datetime(2021, 6, 27),
        "text": """
## 碇真嗣（Ikari Shinji）的心理分析

碇真嗣是新世纪福音战士的主角，14岁的少年，EVA初号机的驾驶员。
作为系列核心，他的心理描写极为细腻，被普遍认为是导演庵野秀明的自我投射。

真嗣的主要心理特征：
- 严重的自我否定与低自尊（"逃げちゃダメだ"自我强迫）
- 对父亲碇源堂的极度渴望与被抛弃的创伤
- 对人际关系的恐惧与矛盾：既渴望亲密又害怕受伤
- 在压力下崩溃但能在极限时刻爆发的潜力

真嗣最具争议的行为是在《THE END OF EVANGELION》中，
他亲手掐死了试图重新具现化的渚薰，这一行为被解读为：
对他人的愤怒与绝望，以及对虚假的"联系"的拒绝。

## 绫波丽（Rei Ayanami）的本质

绫波丽是NERV的第一适格者，驾驶EVA零号机。她外表冷淡、寡言，
对碇源堂表现出异常的服从与忠诚。

绫波丽的真实身份是一个极大的谜：

1. **克隆体身份**：丽实际上是碇源堂利用亡妻碇唯的遗传物质，
   与第一使徒亚当（或第二使徒莉莉斯）的基因结合创造的人造人。
   NERV地下深处保存着大量丽的克隆体备份，每次丽"死亡"，记忆就
   会转移到新的克隆体中，但个人记忆的连续性会有所丢失。

2. **莉莉斯的一部分**：在最终阶段，丽吸收了亚当的灵魂（驻留在源堂体内），
   与莉莉斯合而为一，成为引发第三次冲击的神圣存在。

3. **"灵魂容器"的象征意义**：丽代表着"他者的存在"与"接纳"，
   是贯穿整个系列的"镜子"意象——她反映的是每个角色对自我的投射。

## 人类补完计划的哲学维度

人类补完计划（人類補完計画）的核心哲学争议在于：

**支持者（泽勒/SEELE）的立场**：
人类作为个体永远无法克服"孤独"，AT力场（绝对恐怖领域）是灵魂的壁垒，
防止人与人真正融合。补完计划通过消除个体性来消除孤独与痛苦，
实现"完全的爱"。

**反对者（碇真嗣的选择）的立场**：
个体性、痛苦与孤独是生命的本质。拥有独立的自我，
即使会受伤，也比融入无差别的集合体更真实、更有意义。
真嗣在最后选择了"回到现实、独自活着"，象征对个体存在价值的肯定。

这一哲学辩论呼应了萨特的存在主义："他人即地狱"（L'enfer, c'est les autres）
与"存在先于本质"的命题，以及弗洛伊德关于"死亡驱力"与"生命驱力"的张力。
""",
    },
    {
        "title": "SEELE vs. NERV: Competing Agendas and the True Purpose of the Evangelion Project",
        "source_id": "fan-analysis",
        "language": "en",
        "author": "EVA Research Collective",
        "published_at": datetime(2020, 11, 1),
        "text": """
## SEELE's Plan vs. Gendo's Plan

One of the central conflicts in Neon Genesis Evangelion is the divergence between
the plans of SEELE (the shadowy council) and Commander Ikari Gendo, ostensible leader of NERV.

### SEELE's Scenario (Human Instrumentality)

SEELE planned to use the Evangelion project and the progression of Angel attacks as
steps toward initiating a controlled Third Impact. Their endgame:
- Gather all of Adam's soul (contained in Gendo's right hand) and Lilith's soul
- Unite Adam and Lilith using the Lance of Longinus
- Trigger the Third Impact using the Mass Production Evangelions (MP-EVA series)
- Dissolve all human souls into an undifferentiated collective consciousness (LCL)
- SEELE's 12 committee members believed they would transcend physical death through this process

### Gendo Ikari's Scenario (Personal Instrumentality)

Gendo secretly modified SEELE's scenario to achieve his own goal:
- He embedded Adam's soul into his right hand
- He planned to personally merge with Rei Ayanami (who contains Lilith's soul)
- This would have allowed Gendo alone to control the Instrumentality process
- His true motivation: to be reunited with his deceased wife Yui Ikari, whose soul
  resides within Evangelion Unit-01

### The Actual Outcome

Neither SEELE's nor Gendo's plans succeeded as intended:
- Rei refused to follow Gendo's orders, merging with Lilith of her own will
- She then granted Shinji (not Gendo) the power of godhood to decide humanity's fate
- Shinji chose to reject Instrumentality, allowing humanity to return as individuals
- Gendo was devoured by the awakened EVA Unit-01 (containing Yui's soul — Yui's judgment upon him)

## NERV's Internal Power Structures

Within NERV, multiple power centers existed:
- Commander Ikari Gendo: Nominally leading NERV, secretly pursuing his scenario
- Sub-Commander Fuyutsuki Kozo: Gendo's loyal confidant, aware of the true history
- Dr. Akagi Ritsuko: Head scientist, creator of the Dummy System and MAGI supercomputers;
  emotionally entangled with Gendo (and her mother Naoko, who was also Gendo's lover)
- Captain Katsuragi Misato: Operations director, later revealed to carry Second Impact
  survivor's guilt and a personal vendetta against Angels

## The MAGI Supercomputer System

NERV is controlled through the MAGI system — three supercomputers created by Dr. Naoko Akagi
(Ritsuko's mother) and named after the Biblical Magi (Melchior, Balthasar, Casper).
Each MAGI contains a fragment of Naoko Akagi's personality:
- Melchior: Naoko as a scientist
- Balthasar: Naoko as a mother
- Casper: Naoko as a woman

This fracturing of a single person's psyche into three decision-making nodes is a
recurring motif in EVA: wholeness vs. fragmentation, unity vs. individuality.
""",
    },
    {
        "title": "A.T.フィールドとエヴァの真実：形而上生物学的考察",
        "source_id": "fan-analysis",
        "language": "ja",
        "author": "形而上生物学研究会",
        "published_at": datetime(2019, 4, 1),
        "text": """
## ATフィールド（Absolute Terror Field / 絶対恐怖領域）の本質

ATフィールドとは、使徒やエヴァンゲリオンが発現させる防御フィールドであるが、
その本質は「魂そのものが持つ壁」である。

作中の台詞（碇ゲンドウ）によれば：
「ATフィールドとは、人の心の壁。誰もが持つ、絶対的な安心の領域。
 人と人との間に必ず存在する、越えられない壁だ。」

つまりATフィールドとは：
1. 物理的障壁としての側面：使徒やエヴァが発現させる強力なシールド
2. 心理的・存在論的側面：すべての人間が持つ「自己と他者の境界線」

人類補完計画は、すべての人間のATフィールドを解除し、
個体としての境界を消すことで人類を「ひとつの存在」へと昇華させることを目的とする。

## エヴァンゲリオンの真の姿

エヴァンゲリオンは単なる機械ではない。以下の事実が明らかになる：

1. **生命体としての本質**：エヴァの「装甲」は実は拘束具であり、
   その内部には使徒と同じ生物的な巨人（ゼーレが「神」と呼ぶ存在）が封じられている。

2. **母の魂**：各エヴァには、パイロットの母親の魂が宿っている：
   - 初号機：碇ユイ（シンジの母）
   - 零号機：赤木ナオコ（律子の母）、あるいはレイ自身のオリジナル
   - 弐号機：惣流・カイワイ（アスカの母）

3. **覚醒状態**：拘束具が外れ、エヴァが本来の意志で動く状態。
   初号機は第19話「男の戦い」でゼルエルとの戦闘中に覚醒し、
   使徒の魂を取り込んで不死の存在となる。

4. **量産型エヴァ（EVA量産型）**：ゼーレが独自に建造した9機の量産型。
   パイロット不要（ダミーシステム使用）で、ロンギヌスのレプリカを装備。
   EoEにおいてアスカを圧倒し、補完計画の最終段階に使用される。

## ロンギヌスの槍

ロンギヌスの槍（Lance of Longinus）は、リリスの封印に使われた超高度生物兵器であり、
あらゆるATフィールドを無効化する力を持つ。キリスト教的象徴（イエスの脇を刺した槍）
からその名が取られている。槍は後に月へ飛ばされ、ゼーレとゲンドウの計画における
重要な鍵となる。
""",
    },
    {
        "title": "Rebuild of Evangelion: Continuity, Retcon, and New Canon Analysis",
        "source_id": "fan-analysis",
        "language": "en",
        "author": "EVA Research Collective",
        "published_at": datetime(2021, 8, 15),
        "text": """
## The Rebuild Tetralogy Overview

The Rebuild of Evangelion (ヱヴァンゲリヲン新劇場版) is a theatrical film series
produced by Hideaki Anno's studio khara, consisting of four films:

1. Evangelion: 1.0 You Are (Not) Alone (2007) — Remake of Episodes 1-6
2. Evangelion: 2.0 You Can (Not) Advance (2009) — Diverges significantly from the series
3. Evangelion: 3.0 You Can (Not) Redo (2012) — Set 14 years after events of 2.0
4. Evangelion: 3.0+1.0 Thrice Upon a Time (2021) — Final conclusion

## Key Differences from the Original Series

### New Characters
The Rebuild introduces Makinami Mari Illustrious (真希波・マリ・イラストリオス),
pilot of EVA Unit-08, whose connection to the original series mythology is never fully
explained. She is notably optimistic compared to other pilots.

### The Near Third Impact (2.0)
In Evangelion: 2.0, Shinji's attempt to rescue Rei from within the 10th Angel (Sahaquiel)
triggers a Near Third Impact. EVA Unit-01, awakened by Shinji's will, begins evolving
toward godhood — an event that Kaworu (arriving in this timeline with the Lance of Cassius)
stops by piercing Unit-01.

### The 14-Year Time Skip (3.0)
Evangelion: 3.0 skips 14 years after the Near Third Impact. Key revelations:
- The world has been devastated (referred to as "Red Earth") by the Near Third Impact
- Shinji spent 14 years within EVA Unit-01 in orbit (suspended animation)
- Misato and Ritsuko now lead WILLE, an anti-NERV organization
- Rei has a new clone body with no memory of her previous existence
- Kaworu is present, seemingly manipulating events to help Shinji

### Final Instrumentality and "The Last Door" (3.0+1.0)
The final film reveals:
- The Rebuild timeline is ONE of many past cycles — EVA characters have lived and died
  through numerous iterations of these events
- Kaworu has been perpetually revived into each cycle, always trying to bring happiness to Shinji
- Shinji chooses to use the "super Solenoid theory" (developed by Yui Ikari and young Fuyutsuki)
  to rewrite the fundamental rules of the universe, eliminating the Evangelions and the Angels
  and creating a world where none of these events ever occurred
- This is referred to as "Neon Genesis" — a new beginning, connecting to the original series title

## SEELE's Role in the Rebuild

In the Rebuild, SEELE appears to have orchestrated multiple cycles of Instrumentality attempts.
Kaworu reveals that SEELE "gave him this fate" — implying SEELE's committee members engineered
multiple timeline loops to find a path to perfect Instrumentality.

The Rebuild's version of SEELE is even more mysterious than the original series,
with their physical forms reduced to monoliths bearing the SEELE logo.

## Critical Reception and Legacy

Evangelion: 3.0+1.0 was received as a satisfying conclusion that Anno used to:
- Make peace with his past work and the franchise's burden on him personally
- Provide Shinji with a more hopeful resolution than The End of Evangelion
- Explore the therapeutic theme of "growing up and letting go"

The film's final scene — Shinji as an adult, living in the new world — is widely read as
Anno's own farewell to EVA and his traumatic relationship with it.
""",
    },
    {
        "title": "渚カヲルと使徒の哲学：愛と死と循環する運命",
        "source_id": "fan-analysis",
        "language": "ja",
        "author": "EVA哲学研究会",
        "published_at": datetime(2022, 1, 1),
        "text": """
## 渚カヲル（Nagisa Kaworu）：第17使徒タブリス

渚カヲルはネルフが「フィフスチルドレン（第5の適格者）」として受け入れた少年であり、
その正体は第17使徒・タブリス（Tabris）。彼は人間の姿をとり、
アダムの魂（ゲンドウの右手に宿っていた）とリリンとしての肉体を持つ特殊な存在である。

カヲルの本質的な特徴：
- ほぼすべての状況に対して超然としており、感情の起伏が少ない
- シンジに対して率直な「愛情」を告白する（「好きだよ、シンジくん」）
- 人類の存在を「美しい」と評しながらも、使徒としてリリスへと向かう衝動を持つ
- 自らの死を予期し、受け入れている

テレビ版の第24話「最後のシ者」において、カヲルはシンジにより処刑される。
シンジが初めて自らの意志で「殺す」選択をした場面であり、シリーズ最も重要な場面の一つ。

## 新劇場版のカヲル：ループする運命

新劇場版においてカヲルの役割は大幅に拡張される。

「Q」（第3作）では、カヲルは：
- ゼーレによって繰り返しこの世界に送り込まれてきた存在であることが示唆される
- シンジに「今度こそ、きみを幸せにしてみせる」と告げる
- 第13号機との接触実験を経て、「第13の使徒」として覚醒した後、
  自ら首を断ち処刑される（再び、シンジの目の前で）

「シン・エヴァンゲリオン」では：
- ゲンドウの口から、カヲルは「ゼーレによって送り込まれ、毎回死ぬ運命を与えられた」と明かされる
- シンジはカヲルを救うため、世界のルールそのものを書き換える
- カヲルは最終的に死ではなく、人間として普通の生を生きることができる

## 愛の普遍性とアダムスの存在

カヲルは「アダムスの魂」を宿す存在の一人であり、
その他にも複数の「アダムスの器」（マリなど）が存在することが新劇場版で示唆される。

カヲルのシンジへの愛は、多くの議論を呼んでいる：
- 「無条件の受容」の象徴：シンジが最も欲していた「ありのままで愛される」体験
- 使徒としての本能（リリス/人類への接触衝動）が「愛」として昇華された形
- AGN（アニメ・ゲイ・ナラティブ）の先駆けとして、LGBTQ+視点からの再評価
""",
    },
    {
        "title": "新世纪福音战士中的宗教符号学：卡巴拉、基督教与犹太神秘主义",
        "source_id": "fan-analysis",
        "language": "zh",
        "author": "符号学研究院",
        "published_at": datetime(2020, 5, 10),
        "text": """
## EVA中的宗教符号体系

新世纪福音战士（Neon Genesis Evangelion）大量借用了犹太教、基督教
及卡巴拉神秘主义的符号与术语，但导演庵野秀明本人多次表示，
这些宗教元素主要是出于"视觉上的异国情调"，而非严格的神学论述。

尽管如此，这些符号构成了作品意义层的重要维度，学界与粉丝社群对此展开了大量解读。

## 卡巴拉生命树（Sefirot / セフィロト）

作中多处出现的"生命树"图案直接来源于卡巴拉神秘主义的核心概念——生命之树（Etz Chaim）。
生命之树由十个圆圈（Sefirot，属性/质点）和二十二条路径构成，象征神圣秩序与人类意识的结构。

在EVA的世界观中：
- 人类（莉莉丝/Lilith之子）的遗传密码被编码为生命树图案
- 使徒的遗传密码为"死海文书"（Dead Sea Scrolls）中描述的另一种图案（使徒的"果实"）
- "Soul Tree"（ソウルツリー）在新剧场版中以视觉形式出现

## 死海文书（Dead Sea Scrolls）

作中的"死海文书"并非现实中在以色列发现的古代希伯来典籍，
而是泽勒（SEELE）掌握的神秘预言文书，据称预言了：
- 使徒的出现顺序与特征
- 第三次冲击的条件
- 人类补完计划的路径

这一设定暗示整个EVA故事是"命中注定"的循环，某种更高存在早已预设了人类的命运。

## 朗基努斯之枪（Lance of Longinus）

"朗基努斯之枪"取自基督教传说，据称是罗马士兵朗基努斯（Longinus）
在耶稣受难时刺入其侧的长枪。在EVA中，这支枪能够贯穿一切AT力场，
是封印莉莉丝（绑在十字架上）的关键道具，也是触发第三次冲击的必要元素之一。

## 使徒的命名

十七使徒的名称大多来源于犹太教/基督教天使学（Angelology）中的天使名：
- 萨基尔（Sachiel）：第三使徒，"神的覆盖"
- 拉米尔（Ramiel））：第五使徒，"神的雷霆"
- 泽鲁尔（Zeruel）：第十四使徒，"神的手臂"
- 塔布里斯（Tabris）：第十七使徒（渚薰），"自由意志"

## Lilith（莉莉丝）：黑暗母神

莉莉丝在犹太神话中是亚当的第一任妻子，后被描述为恶魔与夜行精灵之母。
在EVA中，莉莉丝是人类（莉莉丝之子，"Lillin"）的起源，
被钉在巨大十字架上，封印于NERV总部最深处的"终端教义"（Terminal Dogma）区域。
她的形象——被钉十字架的白色巨人——将基督受难的意象与母神/创造者的角色合而为一，
产生极为复杂的神学张力。
""",
    },
    {
        "title": "Hideaki Anno and the Creation of Evangelion: Depression, Otaku Culture, and Artistic Rebellion",
        "source_id": "anno-interview",
        "language": "en",
        "author": "EVA Research Collective",
        "published_at": datetime(2019, 10, 1),
        "text": """
## Anno Hideaki's Mental State During Production

Hideaki Anno (庵野秀明, born 1960) began production of Neon Genesis Evangelion in 1993.
By his own accounts, he was in the depths of clinical depression for nearly four years
during the creation of the series, which fundamentally shaped its themes and trajectory.

Anno has described himself during this period as:
- Unable to feel genuine emotion or connect with others
- Obsessively self-critical and unable to find meaning in his work
- Using the series as a form of self-therapy and public confrontation of his psychological state

The final two episodes (25 and 26) of the TV series, produced under catastrophic budget
constraints and Anno's deteriorating mental health, abandoned conventional animation
in favor of rough sketches and internal monologue — a decision both celebrated for its
psychological intensity and criticized for perceived incompleteness.

## Anno's Critique of Otaku Culture

Anno has been openly critical of what he terms "otaku" (fan) culture, including within himself.
In interviews, he has described the original Evangelion audience (and himself) as:
- People who retreat into fantasy to avoid real-world engagement
- Individuals who use fiction as a substitute for genuine human connection
- His work as a "mirror" — showing otaku their own psychology, hoping it would provoke
  self-reflection rather than comfortable fantasy projection

This critique is embedded in the series: Shinji is deliberately written as an unsympathetic
protagonist who refuses to grow up, forcing the audience to confront their own desire for
an idealized, emotionally static "hero."

## The Gainax Crisis and Budget Catastrophe

GAINAX, the studio that produced NGE, was in severe financial difficulty during production.
The final episodes were produced with a fraction of the original budget:
- The famous "live action" sequence showing ordinary Tokyo streets represents Anno's idea
  of showing Shinji in "the real world" rather than fantasy
- The internal monologue animation style was born from necessity but became intentional art

## The End of Evangelion as Counter-Argument

Anno created The End of Evangelion (1997) partly in response to death threats and harassment
from fans who felt the TV ending was a betrayal. The film serves as:
- A visceral, external depiction of what the final episodes portrayed internally
- A darker and more ambiguous conclusion
- Anno's expression of resentment toward the fans who had made EVA into an escape fantasy

The film's final lines — Shinji and Asuka alone on the beach of LCL, Shinji attempting to
strangle Asuka, Asuka saying "kimochi warui" (disgusting/I feel sick) — remain among the
most analyzed and debated endings in anime history.

## Legacy and Anno's Relationship with Evangelion

The Rebuild series (2007-2021) represents Anno's attempt to:
- Revisit and recontextualize his own work with greater maturity
- Provide a more hopeful conclusion for characters he felt he had harmed in the original
- "Graduate" from EVA and close the chapter personally

The final film, Evangelion: 3.0+1.0 Thrice Upon a Time (2021), is widely read as
Anno's self-portrait of healing — Shinji chooses life, growth, and connection over
eternal regression into the womb of Instrumentality.
""",
    },
]


SOURCE_META = {
    "wikipedia-en": {
        "source_name": "Wikipedia (English)",
        "source_type": "encyclopedia",
        "source_country": "international",
        "trust_level": "medium",
    },
    "wikipedia-ja": {
        "source_name": "Wikipedia (日本語)",
        "source_type": "encyclopedia",
        "source_country": "jp",
        "trust_level": "medium",
    },
    "wikipedia-zh": {
        "source_name": "Wikipedia (中文)",
        "source_type": "encyclopedia",
        "source_country": "international",
        "trust_level": "medium",
    },
    "fan-analysis": {
        "source_name": "EVA Research Collective",
        "source_type": "analysis",
        "source_country": "international",
        "trust_level": "low",
    },
    "anno-interview": {
        "source_name": "Anno Hideaki Interviews & Statements",
        "source_type": "primary_source",
        "source_country": "jp",
        "trust_level": "high",
    },
}


def _ingest_document(db, title, url, source_id, language, author, published_at, raw_text, cleaned_text=None, raw_html=None):
    from softwiki.ingestion.normalize import normalize_text
    if cleaned_text is None:
        cleaned_text = normalize_text(raw_text)
    text_hash = calculate_hash(cleaned_text)
    if is_duplicate_hash(db, text_hash):
        print(f"  [skip-dup] {title[:60]}")
        return None
    if url and is_duplicate_url(db, url):
        print(f"  [skip-url] {title[:60]}")
        return None

    meta = SOURCE_META.get(source_id, {})
    doc = Document(
        title=title,
        url=url,
        source_name=meta.get("source_name", source_id),
        source_type=meta.get("source_type", "analysis"),
        source_country=meta.get("source_country", "international"),
        trust_level=meta.get("trust_level", "medium"),
        language=language,
        author=author,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        hash=text_hash,
        published_at=published_at,
        collected_at=datetime.utcnow(),
        status="pending",
    )
    doc = DocumentRepository.create_document(db, doc)
    doc_id = doc.id

    # Stage 1: raw file
    from softwiki.ingestion.file_store import save_raw_html, save_processed_document
    try:
        if raw_html:
            save_raw_html(text_hash, raw_html)
    except Exception as e:
        print(f"    [warn] raw_html save: {e}")

    # Stage 2: processed document text
    try:
        save_processed_document(doc_id, title, cleaned_text,
                                language=language, published_at=published_at,
                                source_name=meta.get("source_name", source_id), url=url or "")
    except Exception as e:
        print(f"    [warn] processed save: {e}")

    print(f"  [ingested] [{language}] {title[:60]} (id={doc_id})")
    return doc_id


def crawl_wikipedia(db):
    from softwiki.ingestion.web_loader import extract_web_content

    print("\n── Crawling Wikipedia (EN/JA/ZH) ──")
    ingested = 0
    for url, source_id, lang in WIKIPEDIA_URLS:
        try:
            content = extract_web_content(url)
            doc_id = _ingest_document(
                db,
                title=content["title"],
                url=url,
                source_id=source_id,
                language=lang,
                author=content.get("author", "Wikipedia Contributors"),
                published_at=content.get("published_at", datetime.utcnow()),
                raw_text=content["raw_text"],
                cleaned_text=content["cleaned_text"],
                raw_html=content.get("raw_html"),
            )
            if doc_id:
                ingested += 1
        except Exception as e:
            print(f"  [error] {url[:60]} — {e}")
    print(f"Wikipedia: {ingested} new articles ingested.")
    return ingested


def seed_static_documents(db):
    print("\n── Adding static curated EVA documents ──")
    ingested = 0
    for d in STATIC_DOCUMENTS:
        doc_id = _ingest_document(
            db,
            title=d["title"],
            url=None,
            source_id=d["source_id"],
            language=d["language"],
            author=d["author"],
            published_at=d["published_at"],
            raw_text=d["text"].strip(),
        )
        if doc_id:
            ingested += 1
    print(f"Static documents: {ingested} new documents added.")
    return ingested


def build_index():
    print("\n── Building RAG index ──")
    from softwiki.rag.chunker import build_document_chunks
    from softwiki.rag.embedder import WikiEmbedder
    from softwiki.rag.vector_store import LocalVectorStore
    from softwiki.rag.bm25_store import Bm25Store
    from softwiki.source_store.models import Chunk

    db = SessionLocal()
    try:
        from softwiki.ingestion.file_store import save_chunks

        documents = DocumentRepository.get_all_documents(db)
        for doc in documents:
            DocumentRepository.delete_document_chunks(db, doc.id)
            meta = {
                "title": doc.title,
                "source_name": doc.source_name,
                "published_at": doc.published_at,
            }
            chunks_data = build_document_chunks(doc.id, doc.cleaned_text, meta)
            db_chunks = [
                Chunk(
                    document_id=c["document_id"],
                    chunk_index=c["chunk_index"],
                    text=c["text"],
                    title=c["title"],
                    section=c["section"],
                    published_at=c["published_at"],
                )
                for c in chunks_data
            ]
            DocumentRepository.create_chunks(db, db_chunks)

            # Stage 3: chunks JSON
            try:
                save_chunks(doc.id, chunks_data)
            except Exception as e:
                print(f"    [warn] chunks save doc={doc.id}: {e}")

        all_chunks = DocumentRepository.get_all_chunks(db)
        embedder = WikiEmbedder()
        vector_store = LocalVectorStore()

        chunk_ids = [c.id for c in all_chunks]
        chunk_texts = [c.text for c in all_chunks]
        embeddings = embedder.embed_texts(chunk_texts)

        if os.path.exists(vector_store.get_current_path()):
            os.remove(vector_store.get_current_path())
            vector_store.load()
        vector_store.add_vectors(chunk_ids, embeddings)

        bm25_store = Bm25Store()
        bm25_store.rebuild_index({c.id: c.text for c in all_chunks})

        print(f"Index built: {len(all_chunks)} chunks across {len(documents)} documents.")
    finally:
        db.close()


def backfill_files():
    """Backfill processed/ file artifacts for documents already in the DB.

    raw/html/ cannot be backfilled (original HTML was not saved).
    processed/documents/ and processed/chunks/ are regenerated from DB data.
    processed/extractions/ is regenerated for docs that have extraction data.
    """
    print("\n── Backfilling file artifacts from DB ──")
    from softwiki.ingestion.file_store import (
        save_processed_document, save_chunks, save_extraction
    )
    from softwiki.source_store.models import Claim, Relationship, Event
    from softwiki.rag.chunker import build_document_chunks as bdc

    db = SessionLocal()
    try:
        docs = DocumentRepository.get_all_documents(db)
        for doc in docs:
            doc_id = doc.id
            # processed/documents/
            try:
                save_processed_document(
                    doc_id, doc.title, doc.cleaned_text,
                    language=doc.language or "unknown",
                    published_at=doc.published_at,
                    source_name=doc.source_name or "",
                    url=doc.url or "",
                )
            except Exception as e:
                print(f"  [warn] doc text save id={doc_id}: {e}")

            # processed/chunks/ — rebuild from cleaned_text
            try:
                meta = {"title": doc.title, "source_name": doc.source_name, "published_at": doc.published_at}
                chunks_data = bdc(doc_id, doc.cleaned_text, meta)
                save_chunks(doc_id, chunks_data)
            except Exception as e:
                print(f"  [warn] chunks save id={doc_id}: {e}")

            # processed/extractions/ — only if extraction data exists
            doc_claims = db.query(Claim).filter(Claim.document_id == doc_id).all()
            doc_rels = db.query(Relationship).filter(Relationship.document_id == doc_id).all()
            doc_events = db.query(Event).filter(Event.document_id == doc_id).all()
            all_entities = DocumentRepository.get_all_entities(db)
            if doc_claims or doc_rels or doc_events:
                try:
                    save_extraction(doc_id, doc_claims, all_entities, doc_rels, doc_events)
                except Exception as e:
                    print(f"  [warn] extraction save id={doc_id}: {e}")

            print(f"  [backfill] doc_id={doc_id} {doc.title[:50]}")
    finally:
        db.close()
    print("Backfill done.")


def run_extractions(db):
    """Trigger LLM extraction pipeline for all pending documents (background)."""
    print("\n── Triggering extraction pipeline ──")
    docs = DocumentRepository.get_all_documents(db)
    pending = [d for d in docs if d.status in ("pending", None)]
    if not pending:
        print("No pending documents to extract.")
        return
    for doc in pending:
        doc_id = doc.id
        published_at = doc.published_at
        cleaned_text = doc.cleaned_text
        # Run synchronously for seeding (no background=True)
        try:
            run_extraction_pipeline(db, doc_id, cleaned_text, published_at, background=False)
            print(f"  [extracted] doc_id={doc_id}")
        except Exception as e:
            print(f"  [extract-error] doc_id={doc_id}: {e}")


def print_status(db):
    from softwiki.source_store.models import Claim, Entity, Relationship, Event

    docs = DocumentRepository.get_all_documents(db)
    chunks = DocumentRepository.get_all_chunks(db)
    claims = db.query(Claim).count()
    entities = db.query(Entity).count()
    rels = db.query(Relationship).count()
    events = db.query(Event).count()

    print(f"""
── EVA Knowledge Base Status ──
  Workspace : {os.environ['WORKSPACE_DIR']}
  Documents : {len(docs)}
  Chunks    : {len(chunks)}
  Claims    : {claims}
  Entities  : {entities}
  Relations : {rels}
  Events    : {events}
""")


def main():
    crawl = "--no-crawl" not in sys.argv
    extract = "--no-extract" not in sys.argv
    backfill_only = "--backfill" in sys.argv

    print("═" * 60)
    print("  SoftWiki EVA Knowledge Base Seeder")
    print(f"  Workspace: {os.environ['WORKSPACE_DIR']}")
    print("═" * 60)

    # Init DB
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")

    # Backfill-only mode: generate file artifacts from existing DB without re-crawling
    if backfill_only:
        backfill_files()
        build_index()
        db = SessionLocal()
        try:
            print_status(db)
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        # 1. Crawl Wikipedia
        if crawl:
            crawl_wikipedia(db)
        else:
            print("\n[--no-crawl] Skipping Wikipedia crawl.")

        # 2. Static documents
        seed_static_documents(db)

        # 3. Extraction pipeline
        if extract:
            run_extractions(db)
        else:
            print("\n[--no-extract] Skipping LLM extraction (add manually via MCP later).")

    finally:
        db.close()

    # 4. Build RAG index
    build_index()

    # 5. Status
    db = SessionLocal()
    try:
        print_status(db)
    finally:
        db.close()

    print("Done. Run `WORKSPACE_DIR=workspace/eva-kb ./sw shell` to explore.")


if __name__ == "__main__":
    main()
