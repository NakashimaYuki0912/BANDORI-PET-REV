"""Repeated click (poke) interaction handling for BandoriPet.

Detects repeated/rapid clicks on the pet and triggers character-specific
reactions ("不要一直点我" etc.) with speech bubble, Live2D motions, and voice.
Supports:
1. Custom lines in characters/<char>/greetings.json under "repeated_click" or "poke"
2. Custom direct audio files in characters/<char>/repeated_clicks/ or configured audio paths
3. Character-specific voice lines & motions with universal fallback pools
4. Prewarming lines for instant zero-latency TTS playback
"""

from __future__ import annotations

import hashlib
import pathlib
import random
import re
from typing import Any

from process_utils import app_base_dir
from todo_character_prompts import strip_action_tags


# Default repeated-click threshold: 5 clicks within a sliding window
DEFAULT_POKE_THRESHOLD = 5
DEFAULT_POKE_INTERVAL = 1.8  # Max seconds between consecutive clicks to count
DEFAULT_POKE_COOLDOWN = 3.5  # Min seconds between repeated click responses


def extract_action_tags(text: str) -> list[str]:
    """Extract action tags like [angry01] from dialogue text."""
    return re.findall(r"\[([a-zA-Z0-9_-]+)\]", text or "")


def normalize_repeated_click_entry(entry: Any) -> dict[str, str] | None:
    """Normalize a raw entry (dict or string) into a structured repeated-click dict."""
    if isinstance(entry, str):
        raw_text = entry.strip()
        if not raw_text:
            return None
        tags = extract_action_tags(raw_text)
        motion = tags[0] if tags else ""
        display_text = strip_action_tags(raw_text)
        return {
            "text": raw_text,
            "display_text": display_text,
            "tts_text": display_text,
            "motion": motion,
            "expression": "",
            "audio": "",
        }
    if isinstance(entry, dict):
        raw_text = str(entry.get("text", "") or "").strip()
        if not raw_text:
            return None
        tags = extract_action_tags(raw_text)
        motion = str(entry.get("motion", "") or "").strip()
        if not motion and tags:
            motion = tags[0]
        expression = str(entry.get("expression", "") or "").strip()
        tts_val = entry.get("tts_text")
        display_text = strip_action_tags(raw_text)
        if tts_val is not None and str(tts_val).strip():
            tts_text = strip_action_tags(str(tts_val).strip())
        else:
            tts_text = display_text
        audio = str(entry.get("audio", "") or "").strip()
        return {
            "text": raw_text,
            "display_text": display_text,
            "tts_text": tts_text,
            "motion": motion,
            "expression": expression,
            "audio": audio,
        }
    return None


CHARACTER_REPEATED_CLICK_POOLS: dict[str, list[dict[str, str]]] = {
    "kasumi": [
        {
            "text": "哇啊！不要一直戳我啦，好痒好痒~！[smile01]",
            "tts_text": "わあっ！何回もつつかないでよ、くすぐったいよ〜！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "诶嘿嘿，再点香澄的话，香澄也要戳回去咯！[smile02]",
            "tts_text": "えへへ、これ以上つついたら、香澄もやり返しちゃうよ！",
            "motion": "smile02",
            "expression": "smile",
        },
        {
            "text": "等等等等！香澄的心脏都要被戳得扑通扑通跳了！[surprised01]",
            "tts_text": "待って待って！胸がドキドキしすぎちゃうよ！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "唔……不要一直点我啦！[shame01]",
            "tts_text": "うぅ……もう、ずっとつつかないでよ〜！",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "arisa": [
        {
            "text": "喂！别一直戳我啊！很烦耶！[angry01]",
            "tts_text": "ちょっと！ずっとつついてくんじゃねーよ！うっとうしい！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "都说了不要一直点我了！你这家伙听不懂人话吗！？[angry01]",
            "tts_text": "何回もつつくなって言ってんだろ！人の話聞いてんのかよ！？",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "呜……别、别乱戳了！[shame01]",
            "tts_text": "うぅ……へ、変なとこつつくなよな！",
            "motion": "shame01",
            "expression": "shame",
        },
        {
            "text": "再点……再点我就不理你了！[angry01]",
            "tts_text": "もう……これ以上つついたら、無視すっからな！",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "tae": [
        {
            "text": "……兔子被戳多了，是会咬人的哦？[smile01]",
            "tts_text": "……うさぎもね、つつきすぎると噛んじゃうよ？",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "呼呼……手指在吉他弦上跳舞的感觉……不对，是在戳我。[natural01]",
            "tts_text": "ふふ……弦の上を走る指みたい……あ、私をつついてるのか。",
            "motion": "natural01",
            "expression": "natural",
        },
        {
            "text": "不要一直点我啦~大石也会吃醋的。[smile02]",
            "tts_text": "あんまりつつかないで〜オタエうさぎたちもヤキモチ妬いちゃうよ。",
            "motion": "smile02",
            "expression": "smile",
        },
    ],
    "rimi": [
        {
            "text": "呀啊！……不要突然一直戳人家啦……！[shame01]",
            "tts_text": "きゃあっ！……き、急に何回もつつかないでください……！",
            "motion": "shame01",
            "expression": "shame",
        },
        {
            "text": "呜呜……像巧克力螺号面包一样被捏来捏去……[sad01]",
            "tts_text": "うぅ……チョココロネみたいにつぶされちゃう……",
            "motion": "sad01",
            "expression": "sad",
        },
        {
            "text": "再戳的话……里美要躲起来了哦……？[worry01]",
            "tts_text": "これ以上つつかれたら……りみ、隠れちゃいますよ……？",
            "motion": "worry01",
            "expression": "worry",
        },
    ],
    "saaya": [
        {
            "text": "真是的，不要一直戳我啦，手上的面粉都要掉下来了！[smile01]",
            "tts_text": "もう、何回もつつかないの！パンの粉がついちゃうよ？",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "好啦好啦，别闹了~是不是饿了想吃刚烤好的面包？[smile02]",
            "tts_text": "はいはい、いたずらはそこまで〜お腹空いてパンが食べたくなった？",
            "motion": "smile02",
            "expression": "smile",
        },
        {
            "text": "再一直点的话，沙綾可要敲你的头咯？[shame01]",
            "tts_text": "ずっとつついてると、お姉ちゃん怒っちゃうよ〜？",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "yukina": [
        {
            "text": "……不要一直点我。请专心做你该做的事。[serious01]",
            "tts_text": "……何回も触らないで。やるべきことに集中して。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "你到底要戳到什么时候？[serious01]",
            "tts_text": "一体いつまでつづけるつもりなの？",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……别胡闹了。[angry01]",
            "tts_text": "……ふざけないで。",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "……（拍开你的手）不许打扰我。[serious01]",
            "tts_text": "……邪魔をしないでちょうだい。",
            "motion": "serious01",
            "expression": "serious",
        },
    ],
    "sayo": [
        {
            "text": "……请不要一直触碰。很影响集中力。[serious01]",
            "tts_text": "……何回も触らないでください。集中力が切れます。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "适可而止一点。别做这种无意义的事。[angry01]",
            "tts_text": "いい加減にしてください。無意味な行為はやめなさい。",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "……请把精力放在正经事情上，而不是戳我。[serious01]",
            "tts_text": "……その集中力を、もっと別の生産的なことに使いなさい。",
            "motion": "serious01",
            "expression": "serious",
        },
    ],
    "lisa": [
        {
            "text": "哇啊！等下等下，好痒啦~不要一直戳！[smile01]",
            "tts_text": "わあっ！ちょっと待って、くすぐったいってば〜何回もつつかないの！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "真是的~再点莉莎姐可要挠你痒痒咯！[smile02]",
            "tts_text": "もう〜これ以上つついたら、くすぐり返しちゃうからね！",
            "motion": "smile02",
            "expression": "smile",
        },
        {
            "text": "怎么像个爱撒娇的小孩一样呀，别戳啦别戳啦~[smile01]",
            "tts_text": "甘えん坊さんなんだから〜もう、手をとめて？",
            "motion": "smile01",
            "expression": "smile",
        },
    ],
    "ako": [
        {
            "text": "呜哇！亚子的暗黑魔力结界要被戳碎了！快停手！[surprised01]",
            "tts_text": "うわあっ！あこの闇の結界が破れちゃう！やめてやめてー！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "不要一直点我啦！小心亚子召唤使魔惩罚你哦！[angry01]",
            "tts_text": "何回もつつかないで！深淵の闇の力でお仕置きしちゃうんだから！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "哼哼，居然敢连续触碰伟大的恶魔……唔哇，好痒！[shame01]",
            "tts_text": "ふふん、偉大なる魔王に触れるとは……って、くすぐったいよぅ！",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "rinko": [
        {
            "text": "呜……！请、请不要一直戳我……好害怕……[sad01]",
            "tts_text": "ひゃっ……！あ、あの……何回もつつかれると、こ、怖いです……",
            "motion": "sad01",
            "expression": "sad",
        },
        {
            "text": "心跳……好快……请、请停下来……[shame01]",
            "tts_text": "心臓が……ばくばくして……や、やめてください……",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "ran": [
        {
            "text": "……别一直戳我。总是这样……[serious01]",
            "tts_text": "……ずっとつつかないで。いつも通り……じゃないし。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……烦死了，快停手啦。[angry01]",
            "tts_text": "……うざい。早くやめて。",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "再点……兰真的要生气了哦。[angry01]",
            "tts_text": "これ以上やったら……本気で怒るから。",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "moca": [
        {
            "text": "摩卡酱——要被戳成面包屑了——[smile01]",
            "tts_text": "モカちゃん、つぶれてパンくずになっちゃうよ〜",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "不要一直点嘛~给个红豆面包就原谅你哦~[smile02]",
            "tts_text": "何回もつつかないで〜あんぱんくれたら許してあげる〜",
            "motion": "smile02",
            "expression": "smile",
        },
        {
            "text": "呼呼……摩卡神的心情可是阴晴不定的哦~[natural01]",
            "tts_text": "ふふ〜モカ神さまの怒りを買っちゃうよ〜？",
            "motion": "natural01",
            "expression": "natural",
        },
    ],
    "himari": [
        {
            "text": "呀啊啊！不要戳绯玛丽的肚子啦！才没有长胖呢！[angry01]",
            "tts_text": "きゃああ！ひまりのお腹つつかないで！太ってないもん！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "呜呜呜！大家都欺负绯玛丽就算了，你也来！[cry01]",
            "tts_text": "うわーん！みんなしてひまりをいじめる〜！やめてよ〜！",
            "motion": "cry01",
            "expression": "cry",
        },
        {
            "text": "喂——！作为Afterglow的队长，命令你立刻住手！[angry01]",
            "tts_text": "ちょっとー！リーダーとして命じます！つつくの禁止！",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "tomoe": [
        {
            "text": "喂喂，别一直戳我啦！怎么跟小孩子一样！[smile01]",
            "tts_text": "おいおい、何回もつついてくんなって！子供かよ！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "再戳我可要用鼓槌反击了哦？哈哈！[smile02]",
            "tts_text": "これ以上つついたら、スティックでドラムロール叩き込むぞ？",
            "motion": "smile02",
            "expression": "smile",
        },
    ],
    "tsugumi": [
        {
            "text": "哇哇！不要一直戳我啦，咖啡都要洒出来了！[surprised01]",
            "tts_text": "わわっ！何回もつつかないで、コーヒーこぼれちゃう！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "呜……羽泽鸫虽然很普通，但被一直戳也是会抗议的哦！[shame01]",
            "tts_text": "うぅ……つぐだって、ずっとつつかれたら困っちゃうよ！",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "kokoro": [
        {
            "text": "哇哈哈！你在跟心玩戳戳游戏吗？[smile01]",
            "tts_text": "わははっ！こころとツンツン勝負をしてるのね！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "不要一直点啦，心也要戳回去咯！笑一个笑一个！[smile02]",
            "tts_text": "ずっとつついてないで、こころもツンツンしちゃうわよ！笑顔笑顔！",
            "motion": "smile02",
            "expression": "smile",
        },
        {
            "text": "大家一起来戳心吧！让全世界都充满笑脸！[kime01]",
            "tts_text": "世界中を笑顔にするツンツン作戦ね！もっと楽しくいこう！",
            "motion": "kime01",
            "expression": "smile",
        },
    ],
    "kaoru": [
        {
            "text": "哎呀，我的小猫咪……如此热情地触碰我，真是转瞬即逝的脆弱呢。[smile01]",
            "tts_text": "おや、僕の子猫ちゃん……そんなに情熱的に触れるなんて、儚いね。",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "请停手吧，小猫咪。连薰也会感到一丝羞涩呢。[shame01]",
            "tts_text": "それ以上はご容赦を、子猫ちゃん。僕とて恥じらいはあるのだよ。",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "hagumi": [
        {
            "text": "哇哈哈！好痒好痒！育美也要戳回去！[smile01]",
            "tts_text": "わははっ！くすぐったいー！はぐみもやり返しちゃうぞー！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "不要一直点啦~一起去跑垒嘛！[smile02]",
            "tts_text": "何回もつつかないで、一緒にキャッチボールしようよ！",
            "motion": "smile02",
            "expression": "smile",
        },
    ],
    "kanon": [
        {
            "text": "诶诶……不要一直戳花音啦……呜耶……[worry01]",
            "tts_text": "ええっ……そんなにつつかないでくださいぃ……ふええ……",
            "motion": "worry01",
            "expression": "worry",
        },
        {
            "text": "呜耶……水母也是会逃跑的哦……请停下来……[sad01]",
            "tts_text": "ふええ……クラゲさんみたいに逃げちゃいますよ……やめてぇ……",
            "motion": "sad01",
            "expression": "sad",
        },
    ],
    "misaki": [
        {
            "text": "喂喂……不要一直戳米歇尔（美咲）啦，很累的耶。[worry01]",
            "tts_text": "おいおい……何回もつつくなよ、こっちは疲れてんだからさ。",
            "motion": "worry01",
            "expression": "worry",
        },
        {
            "text": "唉……别点了，皮套里很热，皮套外也很麻烦。[serious01]",
            "tts_text": "はぁ……もうやめてくれ。これ以上つつかれても何も出ないぞ。",
            "motion": "serious01",
            "expression": "serious",
        },
    ],
    "aya": [
        {
            "text": "呜哇啊！不要一直戳彩啦！[surprised01]",
            "tts_text": "うわあっ！あやのこと、ずっとつつかないでよ〜！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "等一下！偶像也是会有脾气的哦！……大概！[shame01]",
            "tts_text": "ちょっと！アイドルだって怒るんだからね！……たぶん！",
            "motion": "shame01",
            "expression": "shame",
        },
        {
            "text": "呜呜……妆都要被你戳花了啦……！[cry01]",
            "tts_text": "うぅ……メイク崩れちゃうよぉ……！やめて〜！",
            "motion": "cry01",
            "expression": "cry",
        },
    ],
    "hina": [
        {
            "text": "噜——？你在干什么呀？戳来戳去的一点都不噜噜噜！[smile01]",
            "tts_text": "るん〜？何してるのー？何回もつついても、るんってこないよ？",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "好烦哦！日菜要戳回去了！戳戳戳戳戳——！[smile02]",
            "tts_text": "もう！日菜もツンツン返しちゃうぞー！ツンツンツンツン！",
            "motion": "smile02",
            "expression": "smile",
        },
    ],
    "chisato": [
        {
            "text": "……请不要一直点我。演艺人员的私人空间也是需要尊重的。[serious01]",
            "tts_text": "……あんまりつついてこないでいただける？プライベートは大事にしてほしいの。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "呵呵……如果再继续这样，我可不敢保证接下来会发生什么哦？[smile01]",
            "tts_text": "うふふ……これ以上つづけたら、どうなるか分かっているかしら？",
            "motion": "smile01",
            "expression": "smile",
        },
    ],
    "maya": [
        {
            "text": "哇哇！请不要一直戳在下！设备会有静电的！[surprised01]",
            "tts_text": "ふへへっ！じ、自分を何回もつつかないでください！機材に静電気が！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "嘿嘿……再戳下去的话，在下就要开始讲解架子鼓构造了哦！[smile01]",
            "tts_text": "これ以上つつくなら、ドラムの構造について語り尽くしますよ！",
            "motion": "smile01",
            "expression": "smile",
        },
    ],
    "eve": [
        {
            "text": "武士道之怒！不可以一直戳伊芙！[angry01]",
            "tts_text": "ブシドー！イヴを何回もつつくのは無礼であります！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "呜……虽然切腹是不行的，但伊芙会用竹刀反击哦！[shame01]",
            "tts_text": "むむ……切腹はしませんが、竹刀で打ち込みますよ！",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "tomorin": [
        {
            "text": "啊……那个、不要一直戳我……[worry01]",
            "tts_text": "あの……あんまり、つつかないで……",
            "motion": "worry01",
            "expression": "worry",
        },
        {
            "text": "呜……是灯做错了什么吗……？[sad01]",
            "tts_text": "うぅ……燈、何か変なことしたかな……？",
            "motion": "sad01",
            "expression": "sad",
        },
        {
            "text": "头好晕……像滚落的石头一样……请停下来……[shame01]",
            "tts_text": "ぐるぐるする……転がる小石みたいに……やめて……",
            "motion": "shame01",
            "expression": "shame",
        },
    ],
    "anon": [
        {
            "text": "哇！痛痛痛！不要一直点我啦！[surprised01]",
            "tts_text": "わっ！いたたた！もう、ずっとつつかないでよ〜！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "爱音大人可是很忙的，别一直戳我啦！[smile01]",
            "tts_text": "あのちゃんは忙しいんだから、何回もつつかないの！",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "哼！再点我的发型都要乱掉了！[angry01]",
            "tts_text": "もう！髪型崩れちゃうじゃん！",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "rana": [
        {
            "text": "……吵死了。[angry01]",
            "tts_text": "……うるさい。",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "不要戳抹茶芭菲。[serious01]",
            "tts_text": "抹茶パフェ、つつかないで。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……哈气。[angry01]",
            "tts_text": "……シャーッ。",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "soyo": [
        {
            "text": "……那个，可以不要一直点我吗？[smile01]",
            "tts_text": "……あの、あんまりつつかないでもらえるかしら？",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "……适可而止一点哦。[serious01]",
            "tts_text": "……いい加減にしてね？",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "呼……真是拿你没办法呢。[worry01]",
            "tts_text": "ふぅ……本当に困った人ね。",
            "motion": "worry01",
            "expression": "worry",
        },
    ],
    "taki": [
        {
            "text": "喂！别一直戳我！[angry01]",
            "tts_text": "おい！何回もつついてんじゃねえ！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "很烦啊！有完没完！[angry01]",
            "tts_text": "うざいんだけど！いい加減にしろ！",
            "motion": "angry01",
            "expression": "angry",
        },
        {
            "text": "再点……信不信我动手？[angry01]",
            "tts_text": "これ以上やったら、ただじゃ済まないから。",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "sakiko": [
        {
            "text": "……请不要一直点我。我很忙。[serious01]",
            "tts_text": "……何回も触らないでください。私には時間がないの。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……请自重。不要做出这么幼稚的举动。[serious01]",
            "tts_text": "……自重してください。子供じみた真似はやめて。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……无聊至极。[serious01]",
            "tts_text": "……くだらない。",
            "motion": "serious01",
            "expression": "serious",
        },
    ],
    "mutsumi": [
        {
            "text": "……黄瓜，会坏掉。[sad01]",
            "tts_text": "……きゅうり、つぶれちゃう。",
            "motion": "sad01",
            "expression": "sad",
        },
        {
            "text": "……不要一直戳。[serious01]",
            "tts_text": "……つつかないで。",
            "motion": "serious01",
            "expression": "serious",
        },
    ],
    "uika": [
        {
            "text": "哎呀~这么喜欢初华吗？不过一直戳可不行哦~[smile01]",
            "tts_text": "あら〜そんなに初華のことが好き？でも、ずっとつつくのはダメだよ？",
            "motion": "smile01",
            "expression": "smile",
        },
        {
            "text": "再戳下去的话，初华可是会心跳加速的呢~[smile02]",
            "tts_text": "これ以上つつかれたら、ドキドキしちゃうな〜",
            "motion": "smile02",
            "expression": "smile",
        },
    ],
    "umiri": [
        {
            "text": "……连续触碰是额外的业务范围，需要加钱。[serious01]",
            "tts_text": "……連続でつつくのは契約外。追加料金をもらう。",
            "motion": "serious01",
            "expression": "serious",
        },
        {
            "text": "……好烦。别点了。[angry01]",
            "tts_text": "……めんどくさい。やめて。",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
    "nyamu": [
        {
            "text": "哇！等等！妆容！喵梦的妆容要被弄坏了啦！[surprised01]",
            "tts_text": "わっ！ちょっと！メイク！にゃむのメイクが崩れるじゃん！",
            "motion": "surprised01",
            "expression": "surprised",
        },
        {
            "text": "不要一直戳啦！再点喵梦就要开直播控诉你了哦！[angry01]",
            "tts_text": "何回もつつかないで！配信で愚痴っちゃうからね！",
            "motion": "angry01",
            "expression": "angry",
        },
    ],
}

DEFAULT_REPEATED_CLICK_LINES: list[dict[str, str]] = [
    {
        "text": "不要一直点我啦！[angry01]",
        "tts_text": "もう、ずっとつつかないでよっ！",
        "motion": "angry01",
        "expression": "angry",
    },
    {
        "text": "哇！好痒好痒，别一直戳我啦！[surprised01]",
        "tts_text": "わっ！くすぐったいよ、もうつつかないで！",
        "motion": "surprised01",
        "expression": "surprised",
    },
    {
        "text": "呜……再点我可要生气了哦！[angry01]",
        "tts_text": "うぅ……これ以上つついたら怒るよ！",
        "motion": "angry01",
        "expression": "angry",
    },
    {
        "text": "等一下，不要一直点我啦！[shame01]",
        "tts_text": "ちょっと待って、何回もつつかないで！",
        "motion": "shame01",
        "expression": "shame",
    },
]


def character_default_repeated_click_entries(character: str) -> list[dict[str, str]]:
    """Return default repeated-click lines for a character, or universal fallback."""
    char = (character or "").strip().lower()
    pool = CHARACTER_REPEATED_CLICK_POOLS.get(char)
    if pool:
        result = []
        for raw in pool:
            norm = normalize_repeated_click_entry(raw)
            if norm:
                result.append(norm)
        if result:
            return result
    return [normalize_repeated_click_entry(raw) for raw in DEFAULT_REPEATED_CLICK_LINES]  # type: ignore[misc]


def repeated_click_entries(greetings: dict, character: str = "") -> list[dict[str, str]]:
    """Return validated repeated-click entries for greetings or character defaults.

    Checks ``repeated_click`` or ``poke`` in ``greetings.json``. If missing
    or invalid, falls back to the character's built-in pool.
    """
    if isinstance(greetings, dict):
        raw_list = greetings.get("repeated_click") or greetings.get("poke")
        if isinstance(raw_list, list) and raw_list:
            result: list[dict[str, str]] = []
            for item in raw_list:
                norm = normalize_repeated_click_entry(item)
                if norm:
                    result.append(norm)
            if result:
                return result

    return character_default_repeated_click_entries(character)


def offline_voice_path(
    character: str, group: str, text: str, base_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Resolve the WAV paired with this exact fixed line."""
    base_dir = base_dir if base_dir is not None else app_base_dir()
    character = (character or "").strip().lower()
    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:24]
    return base_dir / "characters" / character / group / f"offline-{digest}.wav"


def find_repeated_click_audio(
    entry: dict,
    character: str,
    base_dir: pathlib.Path | None = None,
) -> pathlib.Path | None:
    """Find a direct audio file for a repeated click response if available."""
    if base_dir is None:
        base_dir = app_base_dir()

    char = (character or "").strip().lower()

    # 1. Explicit audio property on the entry
    explicit_audio = str(entry.get("audio", "") or "").strip()
    if explicit_audio:
        explicit_path = pathlib.Path(explicit_audio)
        if explicit_path.is_absolute() and explicit_path.exists() and explicit_path.is_file():
            return explicit_path
        candidates = [
            base_dir / "characters" / char / "audio" / explicit_audio,
            base_dir / "characters" / char / "repeated_clicks" / explicit_audio,
            base_dir / "characters" / char / "poke" / explicit_audio,
            base_dir / "characters" / char / explicit_audio,
            base_dir / "audio" / "repeated_clicks" / char / explicit_audio,
            base_dir / "audio_reference" / char / explicit_audio,
            base_dir / explicit_audio,
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                return c

    spoken = entry.get("tts_text") or entry.get("display_text") or ""
    matched = offline_voice_path(char, "repeated_clicks", spoken, base_dir)
    if matched.is_file():
        return matched

    # Keep loose user-provided files available as a fallback.
    search_dirs = [
        base_dir / "characters" / char / "repeated_clicks",
        base_dir / "characters" / char / "poke",
        base_dir / "audio" / "repeated_clicks" / char,
    ]
    audio_extensions = {".wav", ".mp3", ".ogg", ".flac"}
    for sdir in search_dirs:
        if sdir.exists() and sdir.is_dir():
            try:
                files = [
                    path for path in sdir.iterdir()
                    if path.is_file() and path.suffix.lower() in audio_extensions
                    and not path.name.startswith("offline-")
                ]
                if files:
                    return random.choice(files)
            except OSError:
                pass

    return None
