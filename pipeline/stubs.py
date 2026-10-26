"""DRY_RUN·테스트용 스텁 LLM. 네트워크를 쓰지 않는다.

스텁은 블로그 프로필 기준(길이·구조·금지 표현)을 통과하는 응답을 돌려준다. 프롬프트로 언어를 가려 한국어 블로그에는
한국어 글을, 영어 블로그(프롬프트에 'Topic:' 줄이 있거나 주제 확장 지시문에 'JSON array of strings'가 있는 경우)에는 영어 글을 낸다.
"""
import json
import re

_BODY = """<p>하루를 보내다 보면 {topic} 같은 고민이 불쑥 올라올 때가 있어요. 거창한 계획보다는 오늘 바로 해볼 수 있는 작은 행동 하나가 훨씬 오래 갑니다. 이 글에서는 부담 없이 시작할 수 있는 방법만 골라 정리했어요.</p>
<h3>1. 먼저 지금 상태를 가볍게 확인하기</h3>
<p>무언가를 바꾸기 전에 오늘 컨디션과 일정을 한 줄로 적어 보세요. 길게 쓸 필요는 없습니다. 현재 상황을 알고 나면 어떤 방법이 지금의 나에게 맞는지 고르기 훨씬 쉬워집니다. 휴대폰 메모장이면 충분해요.</p>
<h3>2. 시간을 정하고 아주 작게 시작하기</h3>
<p>처음부터 오래 하려고 하면 금방 지칩니다. 5분 정도만 하겠다고 정해 두면 시작하는 마음의 부담이 줄어들어요. 타이머를 맞춰 두고 끝나면 미련 없이 멈추는 것도 좋은 방법입니다. 오늘 해냈다는 경험이 내일의 시작을 쉽게 만들어 줍니다.</p>
<h3>3. 주변 환경을 조금만 바꿔 보기</h3>
<p>의지만으로 습관을 만들기는 어렵습니다. 자주 쓰는 물건의 위치를 바꾸거나, 눈에 잘 띄는 곳에 필요한 도구를 두면 행동이 자연스럽게 따라와요. 책상 위나 침대 옆처럼 하루에 여러 번 보는 곳을 활용해 보세요.</p>
<h3>4. 잘 안 된 날에도 기록은 이어가기</h3>
<p>하루 빠졌다고 처음부터 다시 시작할 필요는 없어요. 체크 표시가 한 칸 비어도 괜찮습니다. 중요한 것은 다시 돌아오는 것이고, 일주일 단위로 돌아보면 생각보다 많이 해냈다는 걸 알게 될 거예요.</p>
<h3>5. 일주일에 한 번 돌아보며 조절하기</h3>
<p>일주일에 한 번, 어떤 방법이 잘 맞았는지 가볍게 돌아보세요. 잘 맞는 것은 남기고 부담스러운 것은 과감히 빼도 괜찮습니다. 나에게 맞게 조금씩 고쳐 가는 것이 오래 가는 가장 쉬운 비결이에요.</p>
<h3>오늘부터 해볼 체크리스트</h3>
<ul>
<li>오늘 컨디션을 한 줄로 적어 보기</li>
<li>5분 타이머를 맞추고 한 가지만 해 보기</li>
<li>필요한 물건을 눈에 잘 띄는 곳에 두기</li>
<li>하루가 끝나기 전에 체크 표시 남기기</li>
</ul>
<p>처음부터 완벽하게 하려고 하지 말고, 오늘 하나만 시도해 보세요. 여러분은 요즘 어떤 작은 습관을 시도하고 계신가요?</p>"""


def stub_post(topic):
    title = f"{topic}, 오늘 바로 해볼 4가지"
    return f"제목: {title}\n라벨: 생활습관, 루틴, 일상\n내용:\n" + _BODY.format(topic=topic)


_BODY_EN = """<p>Some days the plan is simple: {topic}. You do not need a perfect setup or a free afternoon to try it. A few small steps, repeated at a calm pace, tend to do more than one big burst of effort. This post collects easy ideas you can start today with things you already have at home.</p>
<h3>1. Start by noticing where your day gets bumpy</h3>
<p>Before changing anything, take one minute to jot down the part of your day that feels the most rushed or the most draining. It can be as short as a single line on your phone. Seeing the pattern in plain words makes it easier to pick a small change that fits your real schedule instead of an imaginary one. Many people find that the bumpy moment is the same every day, which makes it simple to plan around.</p>
<h3>2. Pick one tiny action and attach it to something you already do</h3>
<p>New habits stick better when they ride along with an existing routine. Stretch while the kettle heats up, review your plan while your coffee cools, or tidy one shelf while a video call loads. Because the cue is already part of your day, you do not have to remember anything extra. Keep the action so small that it feels almost silly, since small steps are easy to repeat on a busy day.</p>
<h3>3. Make the helpful choice the easy choice</h3>
<p>Your surroundings quietly shape what you do. Put a water bottle where you can see it, leave your walking shoes by the door, or keep a notebook on your pillow. Likewise, move the things that pull you off track a little further away. A minute of setup on a calm evening can save a lot of effort when the next morning arrives.</p>
<h3>4. Give yourself a time box</h3>
<p>Telling yourself that you will do something for just five or ten minutes takes the pressure off. Set a timer, begin, and stop when it rings, even if you feel like doing more. Finishing on time builds trust with yourself, and that trust makes it easier to begin again tomorrow. If you do feel like continuing, that is a pleasant bonus rather than a requirement.</p>
<h3>5. Review once a week and adjust without guilt</h3>
<p>Once a week, look back at what worked and what felt like a chore. Keep the pieces you enjoyed, drop the ones that did not fit, and try a slightly different version next week. A missed day is just information, not a failure. The goal is a routine that feels friendly enough to keep, and it is perfectly fine for that routine to change as your life changes.</p>
<h3>A short checklist to try today</h3>
<ul>
<li>Write one line about the busiest part of your day</li>
<li>Choose one tiny action and link it to something you already do</li>
<li>Set out anything you will need before you go to bed</li>
<li>Use a five-minute timer and stop when it rings</li>
<li>Pick a day this week for a quick review</li>
</ul>
<p>Start with just one idea from this list and see how it feels. Every small, friendly step counts, and you can always make it a little bigger later. Which of these ideas are you most likely to try first?</p>"""


def stub_post_en(topic):
    title = topic.strip().rstrip(".!? ")
    title = title[:1].upper() + title[1:]
    if len(title) <= 45:
        title += ": 4 easy ideas"
    return f"Title: {title}\nLabels: habits, routine, lifestyle\nContent:\n" + _BODY_EN.format(topic=topic.strip().rstrip(".!? "))


def stub_llm(prompt):
    """(prompt) -> (text, 'stub'). 주제 확장 요청이면 JSON 배열, 아니면 글 한 편. 한국어·영어 프롬프트를 둘 다 알아본다."""
    if "JSON 문자열 배열" in prompt:
        return json.dumps(["출근 전 10분 가볍게 몸 깨우는 아침 루틴", "저녁 식사 후 15분 가볍게 걷는 습관 만들기",
                           "주말 오후를 편안하게 보내는 간단한 정리 루틴"], ensure_ascii=False), "stub"
    if "JSON array of strings" in prompt:
        return json.dumps(["A ten-minute evening walk to unwind after work", "A simple Sunday reset for a calmer week",
                           "Easy desk breaks to keep your afternoons light"]), "stub"
    english = re.search(r"^Topic:\s*(.+)$", prompt, re.M)
    if english:
        return stub_post_en(english.group(1).strip()), "stub"
    match = re.search(r"주제:\s*(.+)", prompt)
    topic = match.group(1).strip() if match else "생활 속 작은 습관"
    return stub_post(topic), "stub"
