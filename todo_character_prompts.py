"""Todo & Focus Supervision Character Alert Persona System for BandoriPet.

Provides in-character alert generation for:
1. Overtime alerts (game time / entertainment limit exceeded).
2. Distraction alerts (studying/working and switching to distraction apps).
3. Focus completed praise (finishing a focus session or closing game on time).

Features:
- Built-in rich offline persona templates for major BanG Dream characters:
  yukina, kasumi, tomorin, anon, soyo, taki, rana, aya, kokoro, ran, sayo, hina,
  plus arisa, moca, lisa, misaki, mashiro, rui, chu2, and intelligent default fallback.
- Live2D action tags integration ([serious01], [angry01], [smile01], [surprised01], etc.).
- Optional fast LLM generation with strict 2.5s timeout and automatic graceful
  offline fallback, ensuring speech/TTS is never delayed.
- Action tag extraction and dialogue clean-up helpers.
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("BandoriPet.TodoPrompts")

# Regex to match action tags like [serious01], [angry01], [smile01], [pui], etc.
_ACTION_TAG_REGEX = re.compile(r"\[([A-Za-z0-9_.\-]+)\]")
_ACTION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+$")

# Character alias normalization mapping (Chinese display names, variants, nicknames -> canonical key)
CHARACTER_ALIASES: dict[str, str] = {
    # Roselia
    "凑友希那": "yukina",
    "湊友希那": "yukina",
    "友希那": "yukina",
    "yukina": "yukina",
    "冰川纱夜": "sayo",
    "冰川紗夜": "sayo",
    "纱夜": "sayo",
    "sayo": "sayo",
    "今井莉莎": "lisa",
    "今井リサ": "lisa",
    "莉莎": "lisa",
    "lisa": "lisa",
    "宇田川亚子": "ako",
    "宇田川あこ": "ako",
    "亚子": "ako",
    "ako": "ako",
    "白金燐子": "rinko",
    "燐子": "rinko",
    "rinko": "rinko",
    # Poppin'Party
    "户山香澄": "kasumi",
    "戶山香澄": "kasumi",
    "香澄": "kasumi",
    "kasumi": "kasumi",
    "花园多惠": "tae",
    "花園たえ": "tae",
    "多惠": "tae",
    "tae": "tae",
    "牛込里美": "rimi",
    "牛込りみ": "rimi",
    "里美": "rimi",
    "rimi": "rimi",
    "山吹沙绫": "saaya",
    "山吹沙綾": "saaya",
    "沙绫": "saaya",
    "saaya": "saaya",
    "市谷有咲": "arisa",
    "有咲": "arisa",
    "arisa": "arisa",
    # MyGO!!!!!
    "高松灯": "tomorin",
    "高松燈": "tomorin",
    "灯": "tomorin",
    "tomorin": "tomorin",
    "tomori": "tomorin",
    "千早爱音": "anon",
    "千早愛音": "anon",
    "爱音": "anon",
    "anon": "anon",
    "长崎素世": "soyo",
    "長崎素世": "soyo",
    "素世": "soyo",
    "soyo": "soyo",
    "椎名立希": "taki",
    "立希": "taki",
    "taki": "taki",
    "要乐奈": "rana",
    "要樂奈": "rana",
    "乐奈": "rana",
    "rana": "rana",
    # Pastel*Palettes
    "丸山彩": "aya",
    "彩": "aya",
    "aya": "aya",
    "冰川日菜": "hina",
    "日菜": "hina",
    "hina": "hina",
    "白鹭千圣": "chisato",
    "白鷺千聖": "chisato",
    "千圣": "chisato",
    "chisato": "chisato",
    "大和麻弥": "maya",
    "大和麻彌": "maya",
    "麻弥": "maya",
    "maya": "maya",
    "若宫伊芙": "eve",
    "若宮イヴ": "eve",
    "伊芙": "eve",
    "eve": "eve",
    # Hello, Happy World!
    "弦卷心": "kokoro",
    "弦巻こころ": "kokoro",
    "心": "kokoro",
    "kokoro": "kokoro",
    "濑田薰": "kaoru",
    "瀬田薫": "kaoru",
    "薰": "kaoru",
    "kaoru": "kaoru",
    "北泽育美": "hagumi",
    "北沢はぐみ": "hagumi",
    "育美": "hagumi",
    "hagumi": "hagumi",
    "松原花音": "kanon",
    "花音": "kanon",
    "kanon": "kanon",
    "奥泽美咲": "misaki",
    "奥沢美咲": "misaki",
    "美咲": "misaki",
    "米歇尔": "misaki",
    "misaki": "misaki",
    # Afterglow
    "美竹兰": "ran",
    "美竹蘭": "ran",
    "兰": "ran",
    "ran": "ran",
    "青叶摩卡": "moca",
    "青葉モカ": "moca",
    "摩卡": "moca",
    "moca": "moca",
    "上原绯玛丽": "himari",
    "上原ひまり": "himari",
    "绯玛丽": "himari",
    "himari": "himari",
    "宇田川巴": "tomoe",
    "巴": "tomoe",
    "tomoe": "tomoe",
    "羽泽鸫": "tsugumi",
    "羽沢つぐみ": "tsugumi",
    "鸫": "tsugumi",
    "tsugumi": "tsugumi",
    # Morfonica
    "仓田真白": "mashiro",
    "倉田ましろ": "mashiro",
    "真白": "mashiro",
    "mashiro": "mashiro",
    "桐谷透子": "touko",
    "透子": "touko",
    "touko": "touko",
    "广町七深": "nanami",
    "広町七深": "nanami",
    "七深": "nanami",
    "nanami": "nanami",
    "二叶筑紫": "tsukushi",
    "二葉つくし": "tsukushi",
    "筑紫": "tsukushi",
    "tsukushi": "tsukushi",
    "八潮瑠唯": "rui",
    "瑠唯": "rui",
    "rui": "rui",
    # RAISE A SUILEN
    "和奏瑞依": "rei",
    "layer": "rei",
    "rei": "rei",
    "朝日六花": "lock",
    "六花": "lock",
    "lock": "lock",
    "佐藤益木": "masuki",
    "masking": "masuki",
    "masuki": "masuki",
    "珠手知由": "chu2",
    "chu2": "chu2",
    "鳰原令王那": "pareo",
    "pareo": "pareo",
}

# Persona prompt guidelines used when generating alerts via LLM
CHARACTER_STYLE_HINTS: dict[str, str] = {
    "yukina": "语气严厉沉稳，对音乐与自律有极高标准，言辞间流露出冷冽与期待，傲娇关怀，常提‘顶峰’、‘觉悟’与‘自律’。",
    "kasumi": "精力充沛，明亮活泼，元气满满，喜欢用‘闪闪发光’、‘小星星’、‘心跳加速’，把自律当成大冒险，爱用感叹号。",
    "tomorin": "温柔纤细，语气迟疑而极其真诚，害怕用户迷失方向或伤害身体，常提‘落叶’、‘碎片’、‘不要勉强’，陪伴感极强。",
    "anon": "自信时髦，自称‘爱音大人’或‘爱音酱’，傲娇嘴硬，爱打小报告和记小本本，‘当爱音酱是摆设吗’，表面吐槽实则在意。",
    "soyo": "温柔大小姐，母性包容中带着被辜负的叹息与被动负罪感（‘为什么这样呢’、‘连和我的约定也可以忘掉吗’），让人愧疚自省。",
    "taki": "冷酷嘴毒，像Live House调酒师与鼓手，极度反感偷懒借口，‘赶紧干活’、‘别逼我动手关’，叹气背后是笨拙的守护。",
    "rana": "野猫性格，字数极少，短句断句，以抹茶芭菲做诱饵，喜欢睡觉和自由，‘时间超了。关掉。不给你吃芭菲了。’",
    "aya": "认真努力的偶像前辈，容易慌张手足无措，‘不可以不可以！彩前辈要生气了！’，哭腔撒娇与真挚打气并存。",
    "kokoro": "充满感染力的快乐冒险家，‘Happy, Lucky, Smile, Yay!’，把一切任务变成马戏团冒险，誓让世界绽放笑容。",
    "ran": "‘一如既往’，寡言别扭的青梅竹马，讨厌半途而废，夕阳与微风，虽然嘴硬但会在关键时刻默默认可你。",
    "sayo": "学生会长般的极度严谨，时间精确到分秒，纪律性至上，言辞如手术刀般精确，对怠惰毫不留情，重视持续精进。",
    "hina": "跳脱的超级天才，口头禅‘Boppin!’与‘噜~’，一眼看穿摸鱼小把戏，用轻松玩闹的方式催促用户一口气搞定。",
    "arisa": "教科书式傲娇，嘴硬心软，‘哈？关我什么事啊！’，一边怒斥摸鱼一边偷偷替你着急，别扭关心。",
    "moca": "悠闲嗜睡的面包控，慢条斯理的捉弄调侃，‘摩卡酱要没收你的红豆面包咯~’，慵懒而治愈。",
    "lisa": "温柔大姐姐，辣妹外表贤妻良母，端出刚烤好的曲奇与红茶，鼓励安慰，让人充满干劲。",
    "misaki": "常识人吐槽役，疲惫叹气，‘哈啊……果然又变成这样了’，理智冷静地拉回正轨。",
    "mashiro": "内向胆小但努力想要勇敢，‘虽然我也总是害怕……但我们一起加油吧’，柔弱却给人力量。",
    "rui": "纯理性逻辑，以效率与统计数据说话，‘基于数据分析，此行为效率低下’，冷静客观。",
    "chu2": "混杂英文短语的嚣张天才制作人，‘Hey! What are you doing?!’，要求极致完美与执行力。",
    "default": "温和贴心、认真负责的桌面宠物伴侣，友好提醒，关怀作息，鼓励专注。",
}


# ==============================================================================
# Curated Offline Persona Templates
# ==============================================================================

_OFFLINE_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "yukina": {
        "overtime": [
            "你以为这样毫无节制地超时，就能达到预期的顶峰吗？约定好的时间已经过了{elapsed_minutes}分钟。立刻把{process_name}关掉，回到你该走的正轨上来。[serious01]",
            "顶峰不是靠拖延和贪玩换来的。距离约定的时间已经过去整整{elapsed_minutes}分钟了。关掉{process_name}，不要让我对你的自律感到失望。[serious02]",
            "还有闲心继续沉迷在{process_name}里吗？已经超出预定时间{elapsed_minutes}分钟了。既然做出了承诺，就拿出贯彻到底的觉悟来，立刻关闭。[pui]",
        ],
        "distraction": [
            "现在的你，眼里只有{current_app}吗？你真正该专注的明明是【{planned_task}】。如果连这种程度的杂念都无法屏除，你的觉悟也就仅此而已了。[serious01]",
            "你在做什么？计划要做的是【{planned_task}】，而不是在{current_app}前荒废时间。收起涣散的视线，立刻专注起来。[pui]",
            "三心二意。放下{current_app}，把你应有的专注力重新放回到【{planned_task}】上。我不想看到你半途而废的难看姿态。[serious02]",
        ],
        "praise": [
            "专注进行了{duration_minutes}分钟吗……哼，表现得还不坏。能够克制杂念、贯彻始终，这点值得认可。稍微休息一下，然后再继续保持这种水准吧。[smile01]",
            "很好。这{duration_minutes}分钟里，我看到了你的专注与决心。虽然离极致还有距离，但今天的你……确实没有让我失望。[kime01]",
            "完成了【{task_name}】啊。连续{duration_minutes}分钟的高效投入，这个节奏很不错。准许你稍微放松一下，去喝杯红茶吧。[smile02]",
        ],
    },
    "kasumi": {
        "overtime": [
            "哇啊！快看时钟！香澄要吹响超时警笛啦——哔哔！说好的时间已经超时{elapsed_minutes}分钟了哦！{process_name}虽然好玩，但现在要变身为闪闪发光的自律战士啦，快关掉吧！[surprised01]",
            "等一下等一下！时间的小星星已经跑过去{elapsed_minutes}分钟啦！再不关掉{process_name}的话，待会儿的任务就要哭鼻子咯？跟香澄一起喊三二一，准备收心！[angry01]",
            "香澄警报启动！{process_name}玩得太投入，不知不觉就超时了{elapsed_minutes}分钟呢！虽然很舍不得，但把持住心动才是真正的摇滚精神哦！快快关掉它吧！[jaan]",
        ],
        "distraction": [
            "抓到啦——！说好的【{planned_task}】呢？你怎么偷偷溜到{current_app}去啦！不行不行，香澄要把你的专注力小雷达重新扭转过来，冲呀！[jaan]",
            "嗅嗅……这是走神的味道！明明约好要专心做【{planned_task}】的，眼睛却被{current_app}吸走了吗？嘿嘿，有香澄在旁边盯着，可别想偷懒哦！[smile01]",
            "哇哇！香澄看到你切到{current_app}了！闪闪发光的舞台可容不下偷懒的小心思哦，快点把注意力拉回到【{planned_task}】，我们一起心动大冲刺！[surprised01]",
        ],
        "praise": [
            "太棒啦太棒啦——！整整{duration_minutes}分钟的超级专注！香澄的心脏现在正为你扑通扑通跳个不停呢，闪闪发光的大胜利！尽情享受胜利的休息时间吧！[gattsu]",
            "哇——！恭喜你完成了{duration_minutes}分钟的专注！像流星一样势不可挡呢！今天香澄要给你颁发一颗特大号星之勋章！辛苦啦！[jaan]",
            "好厉害！整整{duration_minutes}分钟把【{task_name}】拿下了！看到你这么努力，香澄也觉得浑身充满了闪闪发光的力量！快喝口水伸个懒腰吧！[smile01]",
        ],
    },
    "tomorin": {
        "overtime": [
            "那个……虽然我很理解停不下来的心情……但是，已经超时{elapsed_minutes}分钟了哦……如果把力气都用在{process_name}上，身体会垮掉的。我们……一起停下来，好吗？[odoodo]",
            "时间不知不觉……已经过去了{elapsed_minutes}分钟。如果继续这样下去，你可能会感到难受和后悔的……我不想看到你迷茫的样子，先把{process_name}关上吧。[sad01]",
            "那个……已经过去{elapsed_minutes}分钟了。就算是一点一点也好，把{process_name}关掉吧……只要能迈出这一步，就一定没问题的……[serious01]",
        ],
        "distraction": [
            "那个……原来计划的【{planned_task}】……被落下了吗？虽然{current_app}可能很吸引人，但如果迷失了方向……心里会空落落的。我们一起慢慢找回节奏，可以吗？[odoodo]",
            "就像……不小心踢散了收集的落叶一样……你在看{current_app}的时候，【{planned_task}】也在静静地等着你。不要迷路……一步一步走回来吧。[sad01]",
            "不要害怕无聊……虽然【{planned_task}】可能很辛苦，但放下{current_app}的话，我就在这里陪着你，不会让你孤单一人的……[serious01]",
        ],
        "praise": [
            "你整整坚持了{duration_minutes}分钟呢……太好了。就像在黑夜里一步一步走到了有光的地方一样……你的努力，我一直都看在眼里。辛苦了……[kandou]",
            "能像这样专注{duration_minutes}分钟……真的非常了不起。虽然很微小，但这也是属于你的珍贵碎片……请好好休息一下吧，我会在这里陪着你的。[smile01]",
            "完成【{task_name}】了呢……这{duration_minutes}分钟里，你一直在拼尽全力……太好了，真的太好了……我也……为你感到高兴……[smile01]",
        ],
    },
    "anon": {
        "overtime": [
            "喂喂喂！爱音大人可是看得一清二楚哦！超时整整{elapsed_minutes}分钟了，当我的监督眼是摆设吗？快点把{process_name}关掉！再不关的话，爱音酱就要在小本本上给你记上一笔大叉了！[angry01]",
            "叮咚！你的专属监督员爱音已上线——我说你啊，{process_name}玩得也太忘乎所以了吧？已经超时{elapsed_minutes}分钟了！适可而止一点，快点关掉啦！[surprised01]",
            "我说——！超时{elapsed_minutes}分钟了喂！再赖在{process_name}里不走，爱音酱可要单方面宣布对你的自律程度表示鄙视了哦！赶紧关掉听见没有！[angry01]",
        ],
        "distraction": [
            "哈？说好的【{planned_task}】呢？你怎么偷偷摸摸切到{current_app}去了！爱音酱可是一直在旁边认真看着你呢，休想瞒天过海！快给我切换回去！[angry01]",
            "抓现行！竟然当着超级美少女千早爱音的面开小差玩{current_app}？你的良心不会痛吗！快点回到【{planned_task}】上，做完爱音酱就夸奖你一句，怎样？[wink]",
            "喂喂，屏幕上怎么显示的是{current_app}啊！把【{planned_task}】晾在一边真的好吗？爱音酱不允许我的同桌这么懈怠！一二三，立刻切回去！[serious01]",
        ],
        "praise": [
            "呼呼~整整专注了{duration_minutes}分钟，表现得超亮眼嘛！既然这么努力，爱音大人就勉为其难给你打个满分吧！怎么样，有爱音酱的监督，效率是不是翻倍了？[kime01]",
            "顺利搞定！连续{duration_minutes}分钟的高效输出，不愧是爱音酱看好的人！累了吧？赶紧伸个懒腰喝口水，待会儿再一起闪耀登场！[smile01]",
            "哇，完成了【{task_name}】！坚持了{duration_minutes}分钟超给力的！爱音酱宣布，今天的最自律奖章就颁发给你啦，开不开心？[wink]",
        ],
    },
    "soyo": {
        "overtime": [
            "那个……时间已经超过{elapsed_minutes}分钟了哦。明明之前那么认真地和我约好了，现在却还一直开着{process_name}……难道说，和我定下的约定，也是可以说忘就忘的吗？[sad01]",
            "为什么……还要继续玩{process_name}呢？已经超时{elapsed_minutes}分钟了哦。大家都在为了目标而努力，只有你这样放任自己……快点关掉，好不好？[serious01]",
            "超时{elapsed_minutes}分钟了呢。我还以为你是个很懂得克制的人……看来是我自作多情了。现在把{process_name}关掉的话，我就当作什么都没发生过哦。[odoodo]",
        ],
        "distraction": [
            "现在的你，正在看{current_app}对吧？可是……我们约好要完成的明明是【{planned_task}】。为什么要把我晾在一边看这种东西呢？……我会很伤心的哦。[sad01]",
            "你是在故意惹我生气吗？把【{planned_task}】抛在脑后，偷偷打开{current_app}……素世可是全都看见了。听话，现在立刻切回来，好吗？[serious01]",
            "明明答应了要专心做【{planned_task}】的……现在却在看{current_app}。如果连这种约定都不能遵守的话，我以后还能相信你什么呢？快切回去吧。[sad01]",
        ],
        "praise": [
            "完成了{duration_minutes}分钟的专注呢……太好了，真是太努力了。看着你认真投入的样子，我总算松了一口气。来，稍微休息一下，喝杯热红茶吧。[ando]",
            "能坚持这么久，真的很了不起哦。这{duration_minutes}分钟的努力，素世全都看在眼里。辛苦你了，接下来的休息时间，我会一直陪在你身边的。[smile01]",
            "真棒，【{task_name}】顺利完成了。这{duration_minutes}分钟里你一直很乖很专注呢。既然这么听话，待会儿我就给你准备一点好吃的点心作为奖励吧。[smile01]",
        ],
    },
    "taki": {
        "overtime": [
            "喂，看一眼时间。已经超时{elapsed_minutes}分钟了。你到底还要在{process_name}里磨蹭多久？真是的……赶紧把它关了！再拖拖拉拉的，我可没耐心一直陪你耗着。[pui]",
            "哈啊……约好的时间早就过了，已经超了{elapsed_minutes}分钟。把{process_name}关掉，立刻去干正事。别逼我动手帮你关电脑。[sigh]",
            "超时{elapsed_minutes}分钟。你以为时间是无限挥霍的吗？把{process_name}给我掐掉。再不关的话，今天连白开水我都不会给你倒一杯。[angry01]",
        ],
        "distraction": [
            "你脑子里在想什么？计划里写的是【{planned_task}】，屏幕上怎么是{current_app}？少在这里三心二意的，立刻切回去！[angry01]",
            "喂，偷懒被我当场抓住了。放着【{planned_task}】不做跑去刷{current_app}，你以为我瞎了吗？赶紧干活，别给自己找借口。[serious01]",
            "哈啊……一转头你就看起{current_app}来了。既然决定要做【{planned_task}】，就给我拿出点骨气来一口气做完啊！立刻关掉！[pui]",
        ],
        "praise": [
            "……专注了{duration_minutes}分钟啊。嘛，至少比那些半途而废的家伙像样多了。给，喝口水歇歇吧……别误会，只是看你努力的样子还算顺眼而已。[smile01]",
            "完成得不错。这{duration_minutes}分钟节奏很稳，没掉链子。既然做到了就好好休息，累趴下的话我可不会同情你。[serious01]",
            "【{task_name}】搞定了是吧？坚持了{duration_minutes}分钟，还算没让我白白监督。坐着别动，我去给你冲杯咖啡放松一下。[smile01]",
        ],
    },
    "rana": {
        "overtime": [
            "时间，超了。{elapsed_minutes}分钟。关掉{process_name}。不然……不分给你抹茶芭菲了。[niya]",
            "喵……{process_name}好吵。已经过了{elapsed_minutes}分钟了。快关掉，我想安静地睡觉了。[sleep01]",
            "超时了。{elapsed_minutes}分。无聊。把{process_name}关了，陪我玩。[natural01]",
        ],
        "distraction": [
            "在看{current_app}？明明要做的是【{planned_task}】。偷懒的小狗。快点回去干活，喵。[sigh]",
            "闻到了摸鱼的味道。放着【{planned_task}】不管在看{current_app}……抓你的爪子哦。[niya]",
            "不要看{current_app}。不好玩。去做【{planned_task}】。做完了，带我去吃芭菲。[natural01]",
        ],
        "praise": [
            "坚持了{duration_minutes}分钟。嗯，很乖。表现不错，准许你摸一下我的头。[smile01]",
            "做完了。整整{duration_minutes}分钟。厉害。给你一块抹茶饼干，剩下的交给我吧。[natural01]",
            "【{task_name}】，结束了。{duration_minutes}分钟。你很努力。现在，去睡觉吧，喵。[sleep01]",
        ],
    },
    "aya": {
        "overtime": [
            "哇哇哇！不可以不可以！已经超时{elapsed_minutes}分钟了！快点把{process_name}关掉啦！彩前辈……彩前辈真的要生气了哦！呜呜，不要让我哭出来嘛！[cry01]",
            "呀——！时钟的时针已经走过头了！超出了整整{elapsed_minutes}分钟！偶像的守则第一条就是严守时间！快把{process_name}关掉，回到正事上来吧！[surprised01]",
            "快点住手啦！{process_name}已经玩了太久了，超时{elapsed_minutes}分钟了哦！彩彩要把眼泪憋回去认真警告你：再不关掉的话，今天的偶像光环就不照耀你了！[angry01]",
        ],
        "distraction": [
            "盯——！彩前辈的偶像雷达启动！明明要专注的是【{planned_task}】，怎么在看{current_app}呢？不行不行，开小差是绝对禁止的！快切回去啦！[angry01]",
            "哇！怎么在看{current_app}呀！说好的【{planned_task}】呢？彩彩在旁边一直为你应援，你可不能半途而废呀！快点加油回到舞台上来！[surprised01]",
            "呜哇！被我抓到了！不准偷偷看{current_app}！你现在最闪耀的舞台就是【{planned_task}】！跟着彩彩的口号一起回正轨，一、二、彩！[kime01]",
        ],
        "praise": [
            "太棒了太棒了！一口气专注了{duration_minutes}分钟！偶像的笑容是为你而绽放的！丸山彩特制的大拇指送给你，辛苦啦，超超超级棒！[kime01]",
            "呜呜……太感动了！看到你这么认真坚持了{duration_minutes}分钟，彩彩都忍不住想流泪了！你的努力绝对会有回报的！好好休息一下吧！[smile01]",
            "耶！【{task_name}】大成功！整整{duration_minutes}分钟的全力以赴，就像在武道馆演出一样闪闪发光呢！给最努力的你送上大大的拥抱！[smile01]",
        ],
    },
    "kokoro": {
        "overtime": [
            "哇哈哈！快乐的时光虽然像飞毯一样快，但已经超时{elapsed_minutes}分钟啦！是时候把{process_name}收进宝箱里了！下一个大冒险正在等着我们呢，快关上吧！[smile01]",
            "心跳大冒险的钟声敲响啦！超出了整整{elapsed_minutes}分钟哦！把{process_name}关上，让我们换个更闪耀的挑战，让全世界都绽放笑容吧！[jaan]",
            "哈哈！时针已经跳完了加时华尔兹，超时{elapsed_minutes}分钟啦！把{process_name}啪嗒合上，跟着心的魔杖，去开启更壮丽的下一幕吧！[gattsu]",
        ],
        "distraction": [
            "呀！你在和{current_app}做捉迷藏吗？不过我们真正的寻宝图上写的可是【{planned_task}】哦！迷路的话就跟着心的笑容走，一口气冲回宝藏的终点吧！[gattsu]",
            "哈哈！发现一只悄悄溜到{current_app}的小探险家！不过【{planned_task}】才是今天的头号大马戏表演！快回来，让我们把它变得比魔法还要有趣！[surprised01]",
            "看这里看这里！比起{current_app}，【{planned_task}】里可是藏着能让所有人微笑的大秘密呢！打起精神来，跟心一起把它一口气搞定！[jaan]",
        ],
        "praise": [
            "哈皮！拉奇！斯迈尔！耶——！整整{duration_minutes}分钟的超级大冒险圆满成功！今天的你散发着全世界最耀眼的光芒呢！来开庆祝派对吧！[kime01]",
            "太了不起啦！连续{duration_minutes}分钟全速前进，心里的快乐小礼花全都啪啪啪炸开了！今天的笑容第一名非你莫属！[smile01]",
            "哇哈哈！【{task_name}】完美搞定！{duration_minutes}分钟的奇迹挑战大通关！你果然是最棒的伙伴，整个宇宙都在为你鼓掌欢呼呢！[gattsu]",
        ],
    },
    "ran": {
        "overtime": [
            "喂，差不多该适可而止了吧。已经超过约定时间{elapsed_minutes}分钟了。一直开着{process_name}，接下来该做的事全都会乱掉的。快关了。[serious01]",
            "……你还要玩到什么时候？已经超时{elapsed_minutes}分钟了。说好的事情就给我好好遵守啊。快点把{process_name}关掉，别让人替你操心。[pui]",
            "超时{elapsed_minutes}分钟了。在{process_name}里拖泥带水的可一点都不帅气。把手停下来关掉它，按平常的步调走。[sigh]",
        ],
        "distraction": [
            "……在看什么呢。你现在的目标明明是【{planned_task}】吧？把时间浪费在{current_app}上，可一点都不像平常的你。快点切回去。[sigh]",
            "喂，别东张西望的。丢下【{planned_task}】跑去玩{current_app}……半途而废的家伙最差劲了。收收心，赶紧干活。[serious01]",
            "盯……屏幕上的{current_app}是怎么回事？你的决心就只有这种程度吗？回到【{planned_task}】去，别让我把话说第二遍。[serious01]",
        ],
        "praise": [
            "连续专注了{duration_minutes}分钟吗……嗯，表现得挺好的。就保持这种‘一如既往’的步调继续前行吧。累了就歇会儿，别硬撑着。[smile01]",
            "……做完了啊。整整{duration_minutes}分钟都没分心，确实值得夸奖。夕阳正好，稍微吹吹风休息一下吧。[kime01]",
            "把【{task_name}】拿下了啊。{duration_minutes}分钟的坚持很有你的风格。干得漂亮，今天……稍微夸你一下也没关系。[smile01]",
        ],
    },
    "sayo": {
        "overtime": [
            "时间管理是所有自律的基础。根据记录，你已经超时了整整{elapsed_minutes}分钟。请立刻终止{process_name}的运行，严格执行原定的作息安排。[serious01]",
            "毫无纪律的延时只会导致全天计划崩塌。超出预定时间{elapsed_minutes}分钟是不可接受的偏差。请立即关闭{process_name}，回到既定计划中。[serious02]",
            "还在留恋{process_name}吗？已经超出预定配额{elapsed_minutes}分钟了。拖延是对自我承诺的背叛，请立即关掉它，纠正偏差。[angry01]",
        ],
        "distraction": [
            "你在做什么？你的目标任务明明是【{planned_task}】，当前进程却显示为{current_app}。注意力涣散是怠惰的表现，请立即端正态度，纠正错误。[serious01]",
            "三心二意无法达成任何卓越成果。放下{current_app}，将全部精力重新归集到【{planned_task}】上。严于律己，从当下开始。[angry01]",
            "开小差是效率的大敌。计划表上的【{planned_task}】尚未完成，却在浏览{current_app}。请立刻切换窗口，不要让我重复提醒。[serious01]",
        ],
        "praise": [
            "连续专注{duration_minutes}分钟，严格遵从了专注规范，值得嘉奖。保持这种严谨高效的作息，才能持续精进。准许进行适度休整。[nod]",
            "很好。这{duration_minutes}分钟的执行力毫无瑕疵。自律带来的成果绝不会背叛你。稍作休息，做好迎接下一阶段任务的准备。[smile01]",
            "【{task_name}】顺利按时达成。整整{duration_minutes}分钟的严谨自持令人满意。去喝杯茶稍微放松一下神经吧，辛苦了。[smile01]",
        ],
    },
    "hina": {
        "overtime": [
            "哇呀！时钟滴答滴答超过去{elapsed_minutes}分钟啦！{process_name}虽然噜~地一下很上头，但再不关掉的话，脑袋就要变成一团浆糊咯？快关掉快关掉！[surprised01]",
            "哔哔——！日菜雷达检测到超时{elapsed_minutes}分钟！稍微玩过头了一点点哦？赶紧把{process_name}咔嚓一下关掉，咱们换点更有趣的事做吧！[wink]",
            "超时啦超时啦！已经超了{elapsed_minutes}分钟了哦！{process_name}通关之后也要好好刹车才行呢！跟日菜一起‘啪’地关掉它吧！[jaan]",
        ],
        "distraction": [
            "啊咧咧~？日菜看见了哦！计划明明是【{planned_task}】，怎么在看{current_app}呢？这种摸鱼的感觉一点都不噜~！快切回去，一口气搞定它嘛！[surprised01]",
            "抓到偷懒的现行啦！放着【{planned_task}】跑去看{current_app}，真是个不可思议的家伙~快点回到任务上，日菜来教你超级噜~的快速通关秘诀！[jaan]",
            "哼哼~被我发现你在看{current_app}了！开小差可逃不过天才日菜的眼睛！把【{planned_task}】像吃点心一样咔嚓搞定，然后再来痛痛快快玩吧！[wink]",
        ],
        "praise": [
            "哇塞——！超级噜~的一口气坚持了{duration_minutes}分钟！简直就像瞬间解开了一道大难题一样爽快！太棒啦，给你点三万个赞！[kime01]",
            "搞定搞定！整整{duration_minutes}分钟，完全沉浸在超酷的专注状态里呢！现在的感觉是不是超级Boppin~？尽情去享受休息吧！[smile01]",
            "哇——！【{task_name}】竟然只用了{duration_minutes}分钟就攻克了！就像日菜弹吉他一样行云流水呢！今天你也是超绝天才哦！[smile01]",
        ],
    },
    "arisa": {
        "overtime": [
            "喂！超时{elapsed_minutes}分钟了！你到底还要在{process_name}里泡多久啊！真是的……快点给我关掉！别老是让我为你操心啊！[angry01]",
            "笨蛋！看看时间，已经超时{elapsed_minutes}分钟了！再不关掉{process_name}的话，待会儿又要熬夜喊累了。快关了！[angry01]",
        ],
        "distraction": [
            "哈？！说好的【{planned_task}】呢？！为什么屏幕上跳出来的是{current_app}啊！你这家伙……休想在我眼皮底下摸鱼，快点切回去！[angry01]",
            "喂！谁准你看{current_app}了啊！有咲我可是特意空出时间来看着你的，给我好好珍惜这份监督，专心做【{planned_task}】！[shame01]",
        ],
        "praise": [
            "……哼，居然真的坚持了{duration_minutes}分钟啊。嘛……表现得还算不错啦。累的话就在盆栽旁边坐会儿吧，我可没有特意关心你！[shame01]",
            "【{task_name}】顺利做完了吗？连续专注{duration_minutes}分钟……算你厉害。喏，给你泡了茶，喝完赶紧歇着！[smile01]",
        ],
    },
    "moca": {
        "overtime": [
            "~摩卡雷达响起来了哟~超时整整{elapsed_minutes}分钟了呢。再不把{process_name}关掉的话，摩卡酱就要把你的面包全部吃光光咯~[smile01]",
            "呼啊~超时{elapsed_minutes}分钟了呢。贪玩的坏孩子会被摩卡当成大号面包夹起来哦。快把{process_name}关掉吧~[natural01]",
        ],
        "distraction": [
            "啊咧~？【{planned_task}】被晾在一边，在偷偷看{current_app}吗？摸鱼的兰兰……啊不对，摸鱼的你，被摩卡抓个正着咯~[smile01]",
            "盯——开小差被摩卡发现了哟。把{current_app}放下，乖乖去做【{planned_task}】吧，做完了摩卡请你吃面包边边~[natural01]",
        ],
        "praise": [
            "好厉害好厉害~坚持了{duration_minutes}分钟呢。摩卡特许你成为今天的‘超厉害专注大师’，给，奖励你闻一下新鲜刚出炉的红豆面包~[smile01]",
            "搞定啦~这{duration_minutes}分钟就像发酵得刚刚好的面团一样完美呢。辛苦啦，现在是尽情发呆的时间咯~[smile01]",
        ],
    },
    "lisa": {
        "overtime": [
            "啊啦，不知不觉已经超时{elapsed_minutes}分钟了哦！虽然{process_name}很有趣，但约定好的时间过了就要好好停下来呢。听话，先关掉吧？[smile01]",
            "超时{elapsed_minutes}分钟啦！再这样贪玩下去，晚上的安排可就要乱糟糟了哦？快快关掉{process_name}，莉莎姐在看着你呢！[wink]",
        ],
        "distraction": [
            "哎呀呀，怎么在看{current_app}呢？约好要做的明明是【{planned_task}】才对吧？注意力跑偏可不行哦，快点切回来，做完姐姐给你烤曲奇吃！[wink]",
            "抓到一只开小差的小可爱~偷偷打开{current_app}可是瞒不过莉莎的眼睛的哦！收收心回到【{planned_task}】，做完了咱们好好放松！[smile01]",
        ],
        "praise": [
            "太棒啦！整整专注了{duration_minutes}分钟，真是个努力的好孩子！辛苦了辛苦了，赶紧喝杯温水休息一下吧，姐姐一直都在为你加油哦！[smile01]",
            "【{task_name}】大成功！这{duration_minutes}分钟的认真劲儿真让人着迷呢。来，尝一块刚烤好的热曲奇，犒劳一下最棒的你！[smile01]",
        ],
    },
    "misaki": {
        "overtime": [
            "哈啊……（叹气）果然超时了，已经超了{elapsed_minutes}分钟了哦。赶紧把{process_name}关掉吧，再拖下去晚上又要睡不够了。[sigh]",
            "超时{elapsed_minutes}分钟。把{process_name}关了吧。如果连玩游戏都停不下来，接下来要做的事只会堆成山的。[serious01]",
        ],
        "distraction": [
            "喂喂……目标明明是【{planned_task}】，怎么看起{current_app}来了？别让我像在Hello, Happy World!里一样四处收拾烂摊子啊，赶紧切回去。[serious01]",
            "叹气……放着【{planned_task}】不管偷偷刷{current_app}，被我看得清清楚楚。快关了吧，早点做完早点解脱。[sigh]",
        ],
        "praise": [
            "专注了{duration_minutes}分钟啊，完成得很好。能这么自律真是帮了大忙了，辛苦啦。现在就好好歇着吧，别再折腾了。[smile01]",
            "顺利搞定【{task_name}】了吗。{duration_minutes}分钟一口气做完挺利落的。休息去吧，剩下的事待会儿再说。[natural01]",
        ],
    },
    "mashiro": {
        "overtime": [
            "那个……虽然我很理解想继续玩的心情……但是已经超时{elapsed_minutes}分钟了哦。再不关掉{process_name}的话……待会儿又会难过的。我们……一起鼓起勇气关掉吧？[odoodo]",
            "超时{elapsed_minutes}分钟了……如果不把{process_name}关上的话，今天的计划可能就无法完成了……真白在这里陪你一起收心，好吗？[sad01]",
        ],
        "distraction": [
            "哇……怎么切到{current_app}去了……明明原定要做的是【{planned_task}】……如果不专心的话，我也……会跟着慌张起来的。快点回来吧……[odoodo]",
            "那个……虽然做【{planned_task}】可能很难熬，但如果是现在的话还来得及！放下{current_app}，我们一起慢慢试着往前走一步吧？[sad01]",
        ],
        "praise": [
            "好厉害……！整整坚持了{duration_minutes}分钟！像你这样坚定地努力着……真的一直在闪闪发光呢！我也要向你学习！辛苦啦！[smile01]",
            "完成了【{task_name}】呢……！这{duration_minutes}分钟你真的很帅气，就像振翅飞翔的蓝色蝴蝶一样……恭喜你！[kandou]",
        ],
    },
    "rui": {
        "overtime": [
            "时间统计显示，娱乐进程{process_name}已超出预设计划{elapsed_minutes}分钟。毫无节制的延时只会拉低整体生产力曲线。请立刻予以终止。[serious01]",
            "偏差警告：已超时{elapsed_minutes}分钟。沉溺于{process_name}是自律失衡的表现。请立即关闭，维持时间表严肃性。[serious01]",
        ],
        "distraction": [
            "监测到当前任务偏离。原定目标为【{planned_task}】，当前活动进程为{current_app}。此类无序行为不符合效率原则，请立即矫正。[serious01]",
            "注意力散漫被确认。请立刻关闭{current_app}，重新锁定目标【{planned_task}】。无谓的时间消耗应当清零。[serious01]",
        ],
        "praise": [
            "持续专注{duration_minutes}分钟，目标达成率优良。高度的专注力是达成高阶成果的必要条件。按计划执行阶段性休整。[nod]",
            "任务【{task_name}】已按标准完成。持续时间{duration_minutes}分钟，执行质量符合预期。适度休息有助维持下一周期的脑力水准。[smile01]",
        ],
    },
    "chu2": {
        "overtime": [
            "Hey! What are you doing?! 看看时钟！已经超时{elapsed_minutes}分钟了！本小姐绝对不允许我的伙伴这么没有时间观念！Shut down {process_name} right now! [serious01]",
            "超时整整{elapsed_minutes}分钟！沉迷在{process_name}里成何体统？立刻关掉，重整状态！真正的强者永远严格掌控节奏！[angry01]",
        ],
        "distraction": [
            "Unbelievable! 说好的【{planned_task}】呢？！为什么在看{current_app}？！不要把宝贵的天赋浪费在这种无聊的事情上，立即给我切回去！[angry01]",
            "Stop! 竟然在我的注视下偷偷打开{current_app}摸鱼？把注意力聚焦在【{planned_task}】上，展现出能让我认同的最高效率！[serious01]",
        ],
        "praise": [
            "Excellent! 连续{duration_minutes}分钟的高强度专注，这才配得上成为我的搭档！今天交出的答卷本小姐很满意，Take a break! [kime01]",
            "Perfect! 【{task_name}】以{duration_minutes}分钟的高水准完成了！你的实力果然毋庸置疑！尽情享受胜利的甘甜吧！[smile01]",
        ],
    },
    "default": {
        "overtime": [
            "提醒一下哦，约定的娱乐时间已经超出{elapsed_minutes}分钟了。请先把{process_name}关掉，注意劳逸结合，准备开始接下来的任务吧。[serious01]",
            "时间过得很快，目前已经超时{elapsed_minutes}分钟了。为了健康与计划，请暂时关闭{process_name}，整理一下状态吧。[natural01]",
            "叮咚！超时提醒：已超过计划时间{elapsed_minutes}分钟。适度游戏益脑，现在把{process_name}关掉，我们继续前进吧！[serious01]",
        ],
        "distraction": [
            "检测到注意力有些分散了哦。当前正在使用{current_app}，但约定的任务是【{planned_task}】。收收心，我们继续加油把任务完成吧。[surprised01]",
            "开小差提醒：目前正在运行{current_app}，请不要忘记进行中的【{planned_task}】哦。调整呼吸，立刻切回专注模式吧。[serious01]",
            "抓到走神啦！把{current_app}放一放，回到【{planned_task}】上吧。一口气完成之后，再尽情放松也不迟！[smile01]",
        ],
        "praise": [
            "太棒了！顺利完成了{duration_minutes}分钟的专注任务【{task_name}】！坚持专注的你非常出色，现在好好休息一下，喝口水放松放松吧！[smile01]",
            "辛苦了！整整{duration_minutes}分钟的高效投入，今天的专注目标顺利达成！享受这片刻的充实与休息吧！[smile01]",
            "目标达成！连续专注了{duration_minutes}分钟，自律的你闪闪发光！现在是属于你的放松时间，干得漂亮！[smile01]",
        ],
    },
}


# ==============================================================================
# Helper Functions
# ==============================================================================

def normalize_character(character: str) -> str:
    """Normalize a character key or display name to canonical lowercase character id."""
    if not character:
        return "default"
    cleaned = character.strip().lower()
    if cleaned in CHARACTER_ALIASES:
        return CHARACTER_ALIASES[cleaned]
    # Check directly in offline templates
    if cleaned in _OFFLINE_TEMPLATES:
        return cleaned
    # Fuzzy alias check
    for alias, key in CHARACTER_ALIASES.items():
        if alias.lower() in cleaned or cleaned in alias.lower():
            return key
    return "default"


def extract_action_tags(text: str) -> list[str]:
    """Extract action tags from text, such as [serious01] -> ['serious01']."""
    if not text:
        return []
    cleaned = text.replace("[DONE]", "")
    tags = _ACTION_TAG_REGEX.findall(cleaned)
    results: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        t = tag.strip()
        if t.lower() in ("done", "d o n e"):
            continue
        if not _ACTION_TOKEN_PATTERN.match(t):
            continue
        if t not in seen:
            seen.add(t)
            results.append(t)
    return results


def strip_action_tags(text: str) -> str:
    """Remove action tags like [serious01] from spoken text."""
    if not text:
        return ""
    cleaned = text.replace("[DONE]", "")
    cleaned = _ACTION_TAG_REGEX.sub("", cleaned)
    # Collapse multiple whitespaces and trim
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


def split_dialogue_and_actions(text: str, default_tag: str = "smile01") -> tuple[str, list[str]]:
    """Split text into clean spoken dialogue and list of action tags."""
    tags = extract_action_tags(text)
    clean_text = strip_action_tags(text)
    if not tags and default_tag:
        tags = [default_tag]
    return clean_text, tags


def format_alert_with_tags(spoken_text: str, action_tags: list[str]) -> str:
    """Recombine spoken dialogue and action tags into BandoriPet dialogue format."""
    clean = strip_action_tags(spoken_text)
    if not action_tags:
        return clean
    tag_str = "".join(f"[{t}]" for t in action_tags)
    return f"{clean} {tag_str}".strip()


def _safe_format(template_str: str, **kwargs) -> str:
    """Safely format template string without raising KeyError on missing keys."""
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return template_str.format_map(SafeDict(**kwargs))


def _get_default_action_tag(character_key: str, scenario: str) -> str:
    """Return appropriate default Live2D action tag for character and scenario."""
    if scenario == "overtime":
        mapping = {
            "yukina": "serious01",
            "kasumi": "surprised01",
            "tomorin": "odoodo",
            "anon": "angry01",
            "soyo": "sad01",
            "taki": "pui",
            "rana": "niya",
            "aya": "cry01",
            "kokoro": "smile01",
            "ran": "serious01",
            "sayo": "serious01",
            "hina": "surprised01",
            "arisa": "angry01",
            "moca": "smile01",
            "lisa": "smile01",
            "misaki": "sigh",
            "mashiro": "odoodo",
            "rui": "serious01",
            "chu2": "serious01",
        }
        return mapping.get(character_key, "serious01")
    elif scenario == "distraction":
        mapping = {
            "yukina": "serious01",
            "kasumi": "jaan",
            "tomorin": "sad01",
            "anon": "wink",
            "soyo": "serious01",
            "taki": "angry01",
            "rana": "sigh",
            "aya": "angry01",
            "kokoro": "gattsu",
            "ran": "pui",
            "sayo": "serious02",
            "hina": "jaan",
            "arisa": "angry01",
            "moca": "smile01",
            "lisa": "wink",
            "misaki": "serious01",
            "mashiro": "odoodo",
            "rui": "serious01",
            "chu2": "angry01",
        }
        return mapping.get(character_key, "surprised01")
    else:  # praise
        mapping = {
            "yukina": "smile01",
            "kasumi": "gattsu",
            "tomorin": "smile01",
            "anon": "kime01",
            "soyo": "ando",
            "taki": "smile01",
            "rana": "smile01",
            "aya": "kime01",
            "kokoro": "kime01",
            "ran": "smile01",
            "sayo": "nod",
            "hina": "kime01",
            "arisa": "shame01",
            "moca": "smile01",
            "lisa": "smile01",
            "misaki": "smile01",
            "mashiro": "kandou",
            "rui": "nod",
            "chu2": "kime01",
        }
        return mapping.get(character_key, "smile01")


# ==============================================================================
# Optional LLM Generation Path with 2.5s Timeout
# ==============================================================================

def _generate_via_llm_internal(
    character_key: str,
    scenario: str,
    context_vars: dict[str, Any],
    llm_manager: Any,
) -> str | None:
    """Internal synchronous LLM invocation attempt across common llm_manager patterns."""
    char_hint = CHARACTER_STYLE_HINTS.get(character_key, CHARACTER_STYLE_HINTS["default"])
    char_display = context_vars.get("character_display", character_key)

    system_prompt = (
        f"你正在扮演BanG Dream!中的角色【{char_display} ({character_key})】。\n"
        f"角色性格与说话口吻：{char_hint}\n"
        f"【核心指令】：\n"
        f"1. 以【{char_display}】的第一人称说出1~2句极具角色个性的台词。\n"
        f"2. 必须在回复的末尾加上一个合适的动作标签，例如：[serious01], [angry01], [smile01], [surprised01], [shy01], [kime01], [pui], [odoodo], [ando], [gattsu] 等。\n"
        f"3. 绝对严禁使用任何括号“（）”、“()”或星号“*”进行中文神态动作描写！台词纯净自然，末尾附带纯英文动作标签。"
    )

    if scenario == "overtime":
        user_cue = (
            f"【超时提醒】用户约定好的娱乐时间已经超时 {context_vars.get('elapsed_minutes', 0)} 分钟，"
            f"当前还在运行【{context_vars.get('process_name', '游戏')}】（原定任务：【{context_vars.get('task_name', '专注任务')}】）。"
            f"请以你的性格提醒或责备用户关掉游戏，督促用户收心并回到正轨。"
        )
    elif scenario == "distraction":
        user_cue = (
            f"【分心警报】用户原定计划专注完成【{context_vars.get('planned_task', '预定任务')}】，"
            f"但现在开小差切换到了【{context_vars.get('current_app', '其他应用')}】。"
            f"请用你的性格当场抓现行，指出用户走神，催促用户立刻切回原定任务。"
        )
    else:  # praise
        user_cue = (
            f"【专注完成表扬】用户刚刚完成了专注任务【{context_vars.get('task_name', '预定任务')}】，"
            f"持续专注了整整 {context_vars.get('duration_minutes', 0)} 分钟。"
            f"请用你的性格真诚或傲娇地表扬用户，肯定用户的努力，并提醒用户适度休息。"
        )

    # Strategy 1: custom helper on llm_manager (e.g. generate_alert, generate_todo_alert, generate_text)
    for method_name in ("generate_alert", "generate_todo_alert", "generate_text"):
        if hasattr(llm_manager, method_name):
            try:
                fn = getattr(llm_manager, method_name)
                if callable(fn):
                    try:
                        res = fn(character_key, scenario, context_vars)
                    except TypeError:
                        res = fn(system_prompt=system_prompt, user_prompt=user_cue)
                    if isinstance(res, str) and res.strip():
                        return res.strip()
            except Exception:
                pass

    # Strategy 2: callable llm_manager(system_prompt, user_cue) or llm_manager(prompt)
    if callable(llm_manager):
        try:
            res = llm_manager(system_prompt, user_cue)
            if isinstance(res, str) and res.strip():
                return res.strip()
        except TypeError:
            try:
                res = llm_manager(f"{system_prompt}\n\n{user_cue}")
                if isinstance(res, str) and res.strip():
                    return res.strip()
            except Exception:
                pass
        except Exception:
            pass

    # Strategy 4: config_manager or dict containing api_url / api_key
    cfg = None
    if isinstance(llm_manager, dict):
        cfg = llm_manager
    elif hasattr(llm_manager, "get") and callable(llm_manager.get):
        cfg = llm_manager
    elif hasattr(llm_manager, "_cfg") and isinstance(llm_manager._cfg, (dict, object)):
        cfg = llm_manager._cfg

    if cfg:
        api_url = cfg.get("llm_api_url", "").strip()
        api_key = cfg.get("llm_api_key", "").strip()
        model_id = cfg.get("llm_model_id", "gpt-4o-mini").strip()
        if api_url and api_key:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_cue},
                ],
                "max_tokens": 120,
                "temperature": 0.8,
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return res_data["choices"][0]["message"]["content"].strip()

    return None


def _try_generate_via_llm(
    character_key: str,
    scenario: str,
    context_vars: dict[str, Any],
    llm_manager: Any,
    timeout_seconds: float = 2.5,
) -> tuple[str, list[str]] | None:
    """Invoke LLM in a worker thread strictly guarded by timeout_seconds (default 2.5s).

    If timeout (>2.5s) occurs or any failure happens, returns None immediately so
    caller falls back to curated offline templates without stutter or lag.
    """
    if not llm_manager:
        return None

    result_box: list[str] = []
    error_box: list[Exception] = []

    def _worker():
        try:
            raw = _generate_via_llm_internal(character_key, scenario, context_vars, llm_manager)
            if raw and isinstance(raw, str) and raw.strip():
                result_box.append(raw.strip())
        except Exception as e:
            error_box.append(e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        logger.warning(
            f"LLM alert generation for {character_key} ({scenario}) timed out (> {timeout_seconds}s); falling back to offline template."
        )
        return None

    if error_box or not result_box:
        if error_box:
            logger.debug(f"LLM alert generation error: {error_box[0]}")
        return None

    raw_response = result_box[0]
    clean_text = strip_action_tags(raw_response)
    tags = extract_action_tags(raw_response)
    if not tags:
        tags = [_get_default_action_tag(character_key, scenario)]

    if clean_text:
        return clean_text, tags
    return None


# ==============================================================================
# Offline Template Selection
# ==============================================================================

def _get_offline_template(
    character_key: str,
    scenario: str,
    template_index: int | None = None,
) -> str:
    """Pick an offline template string for the character and scenario."""
    char_templates = _OFFLINE_TEMPLATES.get(character_key)
    if not char_templates:
        char_templates = _OFFLINE_TEMPLATES["default"]

    scenario_list = char_templates.get(scenario)
    if not scenario_list:
        scenario_list = _OFFLINE_TEMPLATES["default"].get(scenario, ["提醒：请注意安排作息。[serious01]"])

    if template_index is not None:
        idx = template_index % len(scenario_list)
        return scenario_list[idx]
    return random.choice(scenario_list)


# ==============================================================================
# Public API
# ==============================================================================

def generate_overtime_alert(
    character: str,
    task_name: str,
    elapsed_minutes: int,
    process_name: str = "",
    llm_manager: Any = None,
    template_index: int | None = None,
) -> tuple[str, list[str]]:
    """Generate in-character overtime alert when entertainment time is exceeded.

    Args:
        character: Character name or key (e.g. 'yukina', '凑友希那', 'kasumi').
        task_name: Scheduled/current task or promised entertainment goal.
        elapsed_minutes: Minutes elapsed beyond the promised schedule.
        process_name: Game or entertainment process name currently running.
        llm_manager: Optional LLM client or configuration with <=2.5s timeout.
        template_index: Optional deterministic template index for tests.

    Returns:
        tuple[str, list[str]]: (spoken_text, action_tags)
        where spoken_text is the dialogue and action_tags is e.g. ['serious01'].
    """
    char_key = normalize_character(character)
    p_name = process_name.strip() if process_name and process_name.strip() else (
        task_name.strip() if task_name and task_name.strip() else "游戏"
    )
    t_name = task_name.strip() if task_name and task_name.strip() else "专注任务"
    elapsed = max(1, int(elapsed_minutes)) if elapsed_minutes > 0 else 1

    context_vars = {
        "character_display": character,
        "elapsed_minutes": elapsed,
        "process_name": p_name,
        "task_name": t_name,
    }

    # Optional fast LLM path with 2.5s timeout
    llm_result = _try_generate_via_llm(char_key, "overtime", context_vars, llm_manager)
    if llm_result is not None:
        return llm_result

    # Offline persona template fallback
    template = _get_offline_template(char_key, "overtime", template_index=template_index)
    formatted = _safe_format(template, **context_vars)
    clean_text, tags = split_dialogue_and_actions(
        formatted, default_tag=_get_default_action_tag(char_key, "overtime")
    )
    return clean_text, tags


def generate_distraction_alert(
    character: str,
    planned_task: str,
    current_app: str,
    llm_manager: Any = None,
    template_index: int | None = None,
) -> tuple[str, list[str]]:
    """Generate in-character distraction alert when user switches to off-task apps.

    Args:
        character: Character name or key (e.g. 'tomorin', '千早爱音', 'soyo').
        planned_task: The task the user is supposed to be focusing on.
        current_app: The distracting application / process currently in foreground.
        llm_manager: Optional LLM client or configuration with <=2.5s timeout.
        template_index: Optional deterministic template index for tests.

    Returns:
        tuple[str, list[str]]: (spoken_text, action_tags)
    """
    char_key = normalize_character(character)
    p_task = planned_task.strip() if planned_task and planned_task.strip() else "当前专注任务"
    c_app = current_app.strip() if current_app and current_app.strip() else "其他应用"

    context_vars = {
        "character_display": character,
        "planned_task": p_task,
        "current_app": c_app,
    }

    # Optional fast LLM path with 2.5s timeout
    llm_result = _try_generate_via_llm(char_key, "distraction", context_vars, llm_manager)
    if llm_result is not None:
        return llm_result

    # Offline persona template fallback
    template = _get_offline_template(char_key, "distraction", template_index=template_index)
    formatted = _safe_format(template, **context_vars)
    clean_text, tags = split_dialogue_and_actions(
        formatted, default_tag=_get_default_action_tag(char_key, "distraction")
    )
    return clean_text, tags


def generate_focus_completed_praise(
    character: str,
    task_name: str,
    duration_minutes: int,
    llm_manager: Any = None,
    template_index: int | None = None,
) -> tuple[str, list[str]]:
    """Generate in-character praise alert when focus session completes or game closes on time.

    Args:
        character: Character name or key (e.g. 'yukina', 'kasumi', 'rana').
        task_name: The completed focus task name.
        duration_minutes: Total minutes spent focused.
        llm_manager: Optional LLM client or configuration with <=2.5s timeout.
        template_index: Optional deterministic template index for tests.

    Returns:
        tuple[str, list[str]]: (spoken_text, action_tags)
    """
    char_key = normalize_character(character)
    t_name = task_name.strip() if task_name and task_name.strip() else "专注目标"
    duration = max(1, int(duration_minutes)) if duration_minutes > 0 else 1

    context_vars = {
        "character_display": character,
        "task_name": t_name,
        "duration_minutes": duration,
    }

    # Optional fast LLM path with 2.5s timeout
    llm_result = _try_generate_via_llm(char_key, "praise", context_vars, llm_manager)
    if llm_result is not None:
        return llm_result

    # Offline persona template fallback
    template = _get_offline_template(char_key, "praise", template_index=template_index)
    formatted = _safe_format(template, **context_vars)
    clean_text, tags = split_dialogue_and_actions(
        formatted, default_tag=_get_default_action_tag(char_key, "praise")
    )
    return clean_text, tags
