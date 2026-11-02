# 무료 AI로 코드를 고칠 수 있는가 — 조사 보고서 (기준일 2026-11-02)

> 조사 에이전트(제가 쓰지 않은 AI)가 2026-11-02 에 공식 문서·약관·가격 페이지를 읽고 쓴 **보고서 원문**입니다. 운영자 요청(2026-11-02, 데스크톱 이전): "무료 AI 로 코드 수정이 가능한 모델을 찾고, 코드 수정 가능 모델과 알림·글쓰기용을 나눠 가이드하고, 안 되면 DeepSeek-Coder 를 쓸 생각". 읽기 쉬운 요약·규칙·결정 사항은 [`docs/AI_MODEL_GUIDE.md`](../AI_MODEL_GUIDE.md) 입니다. 이 원문의 표기(`[확인됨]`·`[부분 확인]`·`[확인 못 함]`)와 "내 계산/추정/의견"은 보고자의 것을 그대로 두었고, 한도·약관은 바뀌므로 월 1회 다시 확인합니다.

- 방법: 공급사 공식 문서·약관·가격 페이지를 오늘 직접 읽음. 확인일은 별도 표기가 없으면 전부 2026-11-02. 블로그·포럼은 [부분 확인]으로만 사용.
- 태그: [확인됨]=공식 페이지에서 직접 읽음 / [부분 확인]=일부만 읽음·2차 자료·문서끼리 불일치 / [확인 못 함]=읽지 못했거나 근거 없음. "내 계산/추정/의견"은 그대로 표기.
- 직접 써 보고 품질을 측정한 것은 하나도 없음. "문서상 가능"과 "실제로 잘 고침"은 다르다. SWE-bench 등 벤치마크 수치는 전부 벤더 자체 발표이며 독립 검증하지 못했다.
- 읽지 못한 페이지: geminicli.com 요금 페이지(502), openai.com·help.openai.com·one.google.com·microcenter.com(403), morphllm.com(429).
- 용어: 에이전트형 = AI가 파일을 직접 고치고 명령(테스트)까지 실행. 채팅/API형 = 글만 돌려주고 사람이 붙여 넣어야 함.

## 0. 결론 (먼저 읽기)
1. 올해 큰 무료 선택지가 닫혔다: Gemini CLI·Gemini Code Assist 개인 무료는 2026-06-18 종료(Antigravity로 이전), Qwen Code 무료 로그인은 2026-04-15 종료, Roo Code는 2026-05-15 보관(종료), Continue 저장소는 읽기 전용. 무료 한도·약관은 몇 달 단위로 바뀌므로 특정 도구에 작업 흐름을 묶지 말 것.
2. 지금 $0으로 "여러 파일 수정"을 문서상 지원하는 것: Google Jules(하루 15건), Google Antigravity(주간 한도, 수치 비공개), GitHub Copilot Free(수치 비공개), Amazon Q/Kiro(월 50), Mistral Vibe Free(수치 비공개). 무료 입력은 대부분 학습에 쓰일 수 있다(E절).
3. 16GB·내장 그래픽 PC의 로컬 모델은 에이전트식 코드 수정에 비추천(B절). 알림·요약 실험용으로만.
4. DeepSeek-Coder 폴백: 로컬 DeepSeek-Coder(2024년 모델)는 비추천. 공식 API(V4.1-Flash)는 품질 면에서 현실적이지만 무료가 아니고(월 약 $1~10, 내 계산) 서버가 중국이라 "조건부 사용"(C절).
5. 규칙 제안: 무료 AI는 T0·T1만 직접 수정, T2는 초안+다른 회사 AI 검토+CI+운영자 승인, T3는 직접 수정 금지(E절).
6. 무료만으로 신뢰도 높은 코드 수정은 보장할 수 없다. 소규모 T0/T1은 가능성이 있으나, 데스크톱 프로그램 신규 개발처럼 반복이 많은 작업은 무료 한도로 모자랄 가능성이 높다(내 추정). 가장 덜 나쁜 대안은 F절 3단계(선불 소액).

## A. 에이전트형 무료 경로 (파일 수정+명령 실행)
### A-1 한눈표
| 도구 | 지금 무료로 코드 수정 | 무료 한도(공식) | 무료 입력이 학습에 쓰임 | 난이도(내 판단) |
|---|---|---|---|---|
| Google Jules | 예(클라우드 VM, 브랜치 푸시) | 하루 15건·동시 3건 | 비공개 저장소는 아님 | 낮음 |
| Google Antigravity | 예(CLI·데스크톱 앱) | 주간 한도, 수치 비공개 | 예(설정 항목 있음) | 중 |
| GitHub Copilot Free | 예(VS Code 에이전트 모드, Copilot CLI) | 완성 월 2,000회, 나머지 비공개 | 예(2026-04-24~, 끌 수 있음) | 중 |
| Amazon Q Developer Free / Kiro Free | 예 | 에이전트 요청 월 50 / 월 50 크레딧 | Q: 옵트아웃 표기 / Kiro: 예(끌 수 있음) | 중 |
| Mistral Vibe Free | 예(CLI) | "limited coding sessions", 수치 비공개 | 예(끌 수 있음) | 높음 |
| Cline · OpenCode 무료 모델 | 예(모델은 수시 교체) | 기간 한정, 수치 없음 | 가능 | 중 |
| Cursor Free · Devin Desktop Free · Zed | 문서상 예, 수치 없음 | 비공개(Zed는 본인 키) | Cursor만 Privacy Mode 보장 | 중 |
| OpenAI Codex | Free는 데스크톱 앱만 명시 | 비공개 | 확인 못 함 | 중 |
| Gemini CLI · Code Assist 개인용 | 종료(2026-06-18) | — | — | — |
| Qwen Code 무료 로그인 | 종료(2026-04-15) | — | — | — |
| OpenRouter :free · Groq · Cerebras · NVIDIA · Cloudflare · Hugging Face | 아니오(모델 API, Aider/Cline에 연결해야 함) | A-2 참고 | 서비스별 상이 | 높음 |

### A-2 도구별 근거 (출처 URL, 확인일 11-02)
- **Google Antigravity**: 개인 $0, "기본 주간 한도"이며 수치 비공개, 용량에 따라 바뀔 수 있다고 명시. 무료에서 쓸 수 있는 Gemini 모델은 3.8 Flash뿐이고 Claude Sonnet/Opus 4.6·GPT-OSS-120b는 "2026-11-02 제거 예정" 표기(반영 여부 못 봄). Gemini 3.8 Flash의 Terminal-Bench 2.1 89.4%는 Google 모델카드 수치 → 병목은 성능보다 한도. 개인 계정은 "Interactions"를 Google 제품 개선에 사용하고 직원·계약자가 열람할 수 있으며, 설정에서 끌 수 있으나 텔레메트리를 꺼도 서비스 제공용 처리는 계속(포럼에선 끄기 효과 논쟁: https://discuss.ai.google.dev/t/antigravity-privacy/138277). 제3자 도구로 접속(예: OpenClaw+Antigravity OAuth)은 약관 위반·계정 정지 사유(§6). Windows 10 64비트+, App v2.28.2(설치 파일)·CLI v1.4.10(PowerShell 한 줄 설치 스크립트만 제공). 출처: https://antigravity.google/docs/plans · https://antigravity.google/docs/models · https://antigravity.google/terms · https://antigravity.google/download · https://antigravity.google/pricing · https://deepmind.google/models/model-cards/gemini-3-8-flash/ [확인됨]. 실제 한도 수치·한국 계정 이용 가능 여부·무료에서 테스트 실행 가능 여부 [확인 못 함]. 2차 자료: 유료 Pro에서도 올해 한도가 여러 번 줄었다는 보고 https://preuve.ai/blog/antigravity-review · https://dev.to/jovan_chan_9500711396d4e6/google-antigravity-20-review-2026-browser-subagent-20month-pro-and-the-quota-problem-6ob [부분 확인].
- **Gemini CLI · Code Assist 개인용**: 개인 무료·Google AI Pro/Ultra 로그인은 2026-06-18 종료(IDE 확장·CLI·GitHub 연동). 이후는 Code Assist Standard/Enterprise·유료 API 키만. 코드는 Apache-2.0으로 계속 공개. 종료 전 "분당 60·하루 1,000회"는 2차 요약뿐(공식 요금 페이지 https://geminicli.com/docs/resources/quota-and-pricing/ 은 502로 못 읽음, 문서 복사본 https://huggingface.co/datasets/LevelUp2x/adaptai/blob/main/projects/gemini-cli/docs/quota-and-pricing.md 는 검색 요약만). 무료 AI Studio 키로 계속 쓸 수 있는지 공식 답 없음(README는 키를 "model control or paid tier access"용으로 설명, 사용자 보고는 제한됨). https://github.com/google-gemini/gemini-cli · https://github.com/google-gemini/gemini-cli/discussions/27274 · https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals [확인됨]. 무료 키 사용 [확인 못 함].
- **Google Jules**: 무료 하루 15건(rolling 24h)·동시 3건, 문서 표기 모델 Gemini 2.5 Pro(실제 모델 못 봄), "한도는 조정할 수 있음" 명시. GitHub 저장소 권한 필요, VM에서 코드 복제·의존성 설치·수정, 계획 승인 후 시작, 완료 시 "Create branch"로 브랜치 푸시 → PR은 사람이 연다(main 직접 푸시 없음). 비공개 저장소는 학습에 쓰지 않는다고 명시(공개 저장소는 언급 없음), 18세 이상, 유료는 개인 @gmail만. https://jules.google/docs/usage-limits/ · https://jules.google/docs/faq/ · https://jules.google/docs/running-tasks/ [확인됨]. 테스트 실행은 "빌드·테스트가 되게 setup script" 언급뿐 [부분 확인].
- **GitHub Copilot Free**: 완성 월 2,000회. 에이전트 모드(VS Code 등)·Copilot CLI 포함이나 채팅·에이전트는 "Limited"(AI Credits 수치 미공개). 모델은 docs가 "Auto 선택만", 요금제 페이지는 Haiku 4.5·GPT-5 mini·Gemini 3.8 Flash 등 나열(둘이 불일치). 클라우드 코딩 에이전트(이슈 할당→PR)는 미포함. 2026-04-24부터 Free·Pro·Pro+ 상호작용 데이터(입력·코드 조각·파일명·저장소 구조)를 학습에 사용, Privacy 설정에서 거부 가능, 비공개 저장소 "저장 상태" 콘텐츠는 제외. https://docs.github.com/en/copilot/get-started/plans · https://github.com/features/copilot/plans · https://github.blog/news-insights/company-news/updates-to-github-copilot-interaction-data-usage-policy/ — 한도 [부분 확인], 학습 [확인됨].
- **Qwen Code / Qwen3-Coder**: CLI는 무료 오픈소스지만 호스팅 무료 로그인(Qwen OAuth)은 2026-04-15 종료. 이제 Alibaba 유료 Coding Plan·OpenRouter·본인 키·로컬. https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/ (2026-10-22 갱신본) [확인됨].
- **OpenAI Codex**: ChatGPT Free에 Codex 포함으로 표기되나 Free에서 명시된 면은 데스크톱 앱(GPT-6 Luna, "subject to rollout")뿐, CLI 무료 사용·한도 문서 없음. API 키는 종량제. 유료 Go $8·Plus $20·Pro $100~. 학습 정책 페이지는 403. https://learn.chatgpt.com/docs/pricing · https://learn.chatgpt.com/docs/cli [부분 확인], 학습 [확인 못 함].
- **Mistral (Devstral·Vibe)**: API의 Devstral 전 모델이 폐기 목록에 있음(마지막 Devstral 2 폐기일 2026-07-31, 대체 Mistral Medium 3.5). Devstral Small 2(24B) 가중치는 Apache 2.0, SWE-bench Verified 68.0%(HF 카드). Codestral 25.08(코드 완성용)은 라이선스 "Premier" 표기(오픈 가중치 아님). Vibe CLI(Apache-2.0)는 Mistral 계정/API 키로 로그인, Free "limited coding sessions"(수치 없음), Windows는 "작동하나 공식 지원은 UNIX". Mistral Studio 무료(Free mode)는 "입력·출력을 학습에 쓸 수 있음"이라 안내하고, Vibe는 기본적으로 학습에 쓰되 옵트아웃 가능. 한도는 로그인 후 콘솔에서만 표시(옵트아웃 토글이 관리자 화면에 있다는 말은 검색 요약 기준 2차 자료). https://docs.mistral.ai/getting-started/models/models_overview/ · https://mistral.ai/pricing · https://github.com/mistralai/mistral-vibe · https://help.mistral.ai/en/articles/347617-do-you-have-a-free-api-tier [확인됨]. 한도 [확인 못 함].
- **OpenRouter `:free`**: 무료 모델은 분당 20회, 하루 50회(누적 크레딧 구매 10 미만) 또는 1,000회(10 이상). 현재 무료 모델 16개, 코딩 특화는 Cohere North Mini Code·Recursive Flint 정도(과거 qwen3-coder:free 등은 목록에 없음). FAQ가 "프로덕션에 부적합"이라 밝힘. 제공자별 정책이 달라 무료/유료용 학습 허용 스위치가 따로 있고, `openrouter/free` 라우터는 자동 전환형이라 운영자의 "라우터 제외" 원칙에 해당. https://openrouter.ai/docs/api-reference/limits · https://openrouter.ai/collections/free-models · https://openrouter.ai/docs/faq · https://openrouter.ai/docs/guides/privacy/logging [확인됨].
- **Groq · Cerebras · NVIDIA · Cloudflare · Hugging Face (모델 API, 에이전트 아님)**: Groq gpt-oss-120b/20b 30 RPM·1K RPD·8K TPM·200K TPD(공식 표는 Developer 기준, 무료와 동일하다는 건 검색 요약 기준 2차 자료, 직접 열람 안 함) [부분 확인]; 추론 데이터 기본 비보관(오류·남용 점검용 최대 30일). Cerebras Free Trial gpt-oss-120b 5 RPM·1M TPD, $5 크레딧은 결제수단 인증 후 30일 만료. NVIDIA build.nvidia.com은 평가·프로토타입 전용이고 운영은 AI Enterprise 라이선스(40 RPM은 포럼 보고: https://forums.developer.nvidia.com/t/is-nim-free/369368). Cloudflare Workers AI는 하루 10,000 Neurons 무료, 고객 콘텐츠로 학습하지 않음. Hugging Face 무료 사용자는 월 크레딧 "None"(PRO $2). 분당 8K 토큰은 코드 에이전트 호출 1회에도 모자랄 수 있음(내 추정). https://console.groq.com/docs/rate-limits · https://console.groq.com/docs/your-data · https://inference-docs.cerebras.ai/support/rate-limits · https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317 · https://developers.cloudflare.com/workers-ai/platform/pricing/ · https://developers.cloudflare.com/workers-ai/platform/data-usage/ · https://huggingface.co/docs/inference-providers/pricing [확인됨].
- **Amazon Q Developer Free · Kiro Free**: Q는 에이전트 요청 월 50(IDE·CLI)·Java 변환 월 1,000줄이고 가격표에 데이터 수집 "옵트아웃 가능"만 표기(학습 문구는 못 읽음). Kiro Free는 월 50 크레딧(이월 없음), 무료 콘텐츠가 서비스 개선·모델 훈련에 쓰일 수 있고(옵트아웃 가능) 입력은 남용 탐지용 최대 60일 보관. https://aws.amazon.com/q/developer/pricing/ · https://kiro.dev/pricing/ · https://kiro.dev/docs/privacy-and-security/data-protection/ [확인됨].
- **Cursor · Devin Desktop(구 Windsurf) · Zed**: Cursor Free는 "limited agent requests"(수치 없음), Privacy Mode를 켜면 학습 미사용 보장. https://windsurf.com/ 은 https://devin.ai/desktop 으로 이동(리다이렉트 확인, 06-02 개명 날짜는 검색 요약 기준 2차 자료 https://digitalapplied.com/blog/windsurf-becomes-devin-desktop-ide-migration-2026 ), Devin Free는 "light quota to code with agents"(수치 없음). Zed Personal $0은 본인 API 키·외부 에이전트 사용(호스팅 모델은 Pro). https://cursor.com/pricing · https://devin.ai/pricing · https://zed.dev/pricing — 수치 [확인 못 함].
- **Cline · OpenCode 무료 모델**: Cline 무료 모델은 "기간 한정 회전 프로모션", 수치 없음, 계정 필요, "무료 모델 사용이 모델 개선에 쓰일 수 있음", ClinePass $9.99/월. OpenCode(MIT, Windows 앱)는 콘솔에 기간 한정 무료 모델(Big Pickle, GLM-5.3-Flash Free, DeepSeek V4.1 Flash Free 등)이 있고 OpenCode 클라이언트에서만 쓸 수 있으며, Big Pickle은 무료 기간 중 수집 데이터가 모델 개선에 쓰일 수 있고 Beam Free는 학습 미사용·30일 보관. https://docs.cline.bot/getting-started/free-models · https://opencode.ai/docs/zen/ [확인됨]. OpenCode 무료 모델에 결제정보가 필요한지 [확인 못 함].

### A-3 가이드용 구분표 (코드 수정 가능 vs 불가)
| 구분 | 도구·모델 | 쓰임 |
|---|---|---|
| 코드 수정 가능(에이전트형) | Jules, Antigravity, Copilot Free(VS Code), Amazon Q/Kiro, Mistral Vibe, Cline/OpenCode/Aider/Goose(+모델 연결) | 로컬 폴더를 쓰는 도구는 수정+테스트 실행, Jules는 클라우드 VM. T0·T1 한정(E절) |
| 수정 불가(채팅/API형) | AI Studio Gemini API 키, Cloudflare Workers AI, Groq, Cerebras, NVIDIA build, OpenRouter API, Hugging Face, Ollama·LM Studio 모델 단독 | 알림 문구, 한 줄 요약, 로그 설명, 주간 요약, 글 초안. 단 Aider/Cline에 "모델로 연결"하면 에이전트가 되며 한도·품질은 모델에 좌우 |

## B. 로컬(Ollama·LM Studio·llama.cpp) 오픈 가중치
| 모델 | 다운로드·라이선스 | 16GB RAM·내장 그래픽 PC | 비고 (출처는 표 아래 줄) |
|---|---|---|---|
| gpt-oss:20b | 14GB, Apache-2.0, 128K | 빠듯함(제작사는 "16GB 메모리에서 실행"이라 하나 Windows·컨텍스트 여유가 없음) | 21B/활성 3.6B. Aider 리더보드 gpt-oss-120b(high) 41.8%(2025-08, https://aider.chat/docs/leaderboards/), 20b 수치는 확인 못 함 |
| gemma4:12b · e4b | 7.7~8.0GB · 6.6~9.5GB, Apache-2.0(12B 카드) | 가능(느림) | 코딩 특화 아님, 알림·요약 후보. 한국어 명시 없음("35+ languages out of the box, 140+ pre-trained") |
| granite4.2:8b · ornith:9b | 5.3GB Apache-2.0 · 5.6GB MIT | 가능 | granite: IBM 발표 SWE-bench Verified 47.67(2차 인용), Ollama 도구 배지 없음. ornith: 제작사 주장만, 검증 못 함 |
| qwen3-coder:30b | 19GB(30.5B/활성 3.3B), Apache-2.0, 256K | 불가(메모리 부족) | 32GB급 필요(내 추정) |
| qwen3.8:27b · muse-glimmer:30b(Meta) | 18GB, Apache-2.0 | 불가 | Hashnode(2026-10-28)는 24~32GB 권장. glimmer SWE-bench Verified 76.0은 제작사 수치 |
| devstral-small-2:24b | 15GB, Apache-2.0 | 불가에 가까움 | SWE-bench Verified 65.8%(Ollama)/68.0%(HF) 제작사 수치, "RTX 4090 또는 32GB Mac" |
| deepseek-coder-v2:16b | 8.9GB, deepseek-license(상업 이용 가능 표기) | 가능 | 2024년 모델, Ollama "2년 전 업데이트". 16B/활성 2.4B MoE. 카드에 에이전트·도구 호출 언급 없음 |
| deepseek-r1:8b · 14b (R1 증류) | 5.2GB · 9.0GB, 가중치 MIT(기반 모델 라이선스는 태그별로 다름) | 8b 가능, 14b 빠듯 | Ollama "1년 전 업데이트". 추론용 증류 모델이며 에이전트 편집 성능 근거는 못 찾음 |
| gpt-oss:120b 65GB · qwen3-coder:480b 290GB · GLM-5.3(약 320B) · DeepSeek-V4-Flash(284B/활성 13B, MIT) · Kimi K3 | — | 불가 | 일반 PC 범위 밖. Ollama 요금표는 GLM·DeepSeek V4·Kimi를 클라우드 모델로 표기. Llama 계열 최신 코딩 모델은 확인 못 함 |
- 표 출처 [확인됨, 크기·라이선스는 해당 페이지 표기]: https://ollama.com/library/gpt-oss · https://ollama.com/library/gemma4 · https://ollama.com/library/granite4.2 · https://ollama.com/library/ornith · https://ollama.com/library/qwen3-coder · https://ollama.com/library/qwen3.8 · https://ollama.com/library/muse-glimmer · https://ollama.com/library/devstral-small-2 · https://ollama.com/library/deepseek-coder-v2 · https://ollama.com/library/glm-5.3-flash · https://ollama.com/library/deepseek-r1 · https://huggingface.co/openai/gpt-oss-20b · https://huggingface.co/google/gemma-4-12b-it · https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct · https://huggingface.co/Qwen/Qwen3.8-27B · https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512 · https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct · https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash. 2차 인용(SWE-bench 일부, 메모리 권장): https://hashnode.com/blog/best-local-llm-for-coding (2026-10-28) [부분 확인].
- 하드웨어: LM Studio 권장 RAM 16GB+·AVX2·전용 VRAM 4GB+(https://lmstudio.ai/docs/app/system-requirements). Ollama Windows는 10 22H2+·설치 4GB+(https://docs.ollama.com/windows). Ollama 기본 컨텍스트는 VRAM 24GiB 미만이면 4k인데 코딩 도구는 최소 64,000 토큰 권장(https://docs.ollama.com/context-length) → 14GB급 모델에 64K 컨텍스트를 16GB PC에서 주기는 어렵다(내 판단). [확인됨]
- 속도: Windows CPU 전용 실측은 못 찾음 [확인 못 함]. Mac mini M4 16GB에서 gpt-oss-20b 약 13~18토큰/초라는 보도(검색 요약, 원문 https://www.microcenter.com/site/mc-news/article/can-your-pc-run-gpt-oss-ai.aspx 은 403이라 직접 못 읽음)는 미확인이며 Windows CPU 수치도 아님. 내 PC 사양은 작업관리자 > 성능 탭(메모리, GPU 전용 메모리)에서 확인. 비개발자에게는 명령줄 도구(llama.cpp)보다 LM Studio(GUI)가 쉽다(의견).
- 프런트엔드(동작·유지 상태): Aider — Apache-2.0, `aider-install`, Python 3.10~3.12, 자동 커밋·테스트/린트 실행; PyPI 최신 0.86.2=2026-02-12, main 마지막 커밋 05-22(내가 본 시점) → 개발 속도 느려짐. Cline — Apache-2.0, VS Code 확장과 `npm i -g cline` CLI, Ollama/LM Studio 연결, RAM 16~32GB는 소형·양자화 모델 권장·"Compact Prompt" 안내.
- 프런트엔드(계속): OpenHands — MIT, Node+uv, 샌드박스는 Docker Desktop, Windows는 별도 가이드. Goose — Apache-2.0, Windows 데스크톱 앱, Ollama/OpenRouter 지원, Linux Foundation 소속. OpenCode — MIT, Windows 앱. 쓰지 말 것: Roo Code(2026-05-15 보관, 포크 ZooCode), Continue("no longer actively maintained"). https://github.com/Aider-AI/aider · https://pypi.org/project/aider-chat/ · https://docs.cline.bot/running-models-locally/overview · https://github.com/OpenHands/OpenHands · https://github.com/block/goose · https://github.com/RooCodeInc/Roo-Code · https://github.com/continuedev/continue [확인됨]
- 정직한 평가: Aider 공식 문서가 "Most local models are just barely capable of working with aider, so editing errors are probably unavoidable"(https://aider.chat/docs/troubleshooting/edit-errors.html)라고 적음 [확인됨]. Aider 리더보드(2025-11-20 갱신)에서 Qwen2.5-Coder-32B 16.4%, gemma-3-27b 4.9%, DeepSeek-V3.2-Exp(API) 74.2%로 격차가 큼(https://aider.chat/docs/leaderboards/) — 최신 소형 모델의 독립 측정치는 못 찾음 [확인 못 함]. 사양이 32GB RAM+12~16GB VRAM GPU(또는 32GB Mac)라면 Devstral Small 2·Qwen3.8-27B를 시험할 가치는 있으나 제작사 벤치마크일 뿐이다.
- Ollama 클라우드(원격 모델)는 요금표상 Pay-as-you-go $0=포함 크레딧 없음, Pro $20/월 → 무료 아님. 대신 프롬프트·응답을 학습에 쓰지 않는다고 명시 [확인됨: https://ollama.com/pricing · https://docs.ollama.com/cloud].

## C. DeepSeek
- 이름·유지: DeepSeek-Coder 저장소(1B~33B, 코드 MIT·모델은 별도 Model License)는 날짜 있는 업데이트 기록이 없음. 2024-09-05 DeepSeek-V2.5 공지에 "Chat과 Coder 모델을 합쳤다"고 적혀 있음 [확인됨: https://github.com/deepseek-ai/DeepSeek-Coder · https://api-docs.deepseek.com/news/news0905]. 이후 V3.x(2025), V4(2026-04-24), V4-Pro GA(08-13), V4.1-Flash(09-10·10-17)로 이어졌고 별도 "Coder" 신제품은 못 찾음 [부분 확인: https://api-docs.deepseek.com/updates].
- 현재 API 모델: `deepseek-flash`(V4.1-Flash-1017)와 `deepseek-v4-pro`(V4-Pro-0813), 컨텍스트 1M. 옛 이름 deepseek-chat/reasoner는 2026-07-24 중단 예정이었음(실제 중단 여부 못 봄). 라이선스: V4-Flash 가중치·저장소 MIT, 카드의 SWE-bench Verified 79는 V4-Flash 기준 벤더 수치(V4.1은 별도). [확인됨: https://api-docs.deepseek.com/quick_start/pricing · https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash]
| 가격(USD/1M 토큰, 비피크 / 피크) | 입력 캐시 적중 | 입력 미적중 | 출력 |
|---|---|---|---|
| deepseek-flash | 0.003 / 0.006 | 0.15 / 0.3 | 0.6 / 1.2 |
| deepseek-v4-pro | 0.022 / 0.044 | 0.66 / 1.32 | 1.98 / 3.96 |
- 피크 = UTC 월~금 01~04시·06~10시(한국시간 10~13시·15~19시, 내 환산), 그 밖은 절반 가격. 한도: 계정 단위 동시 요청 수만 공지(flash 2,500·pro 500), 일일 토큰 상한 언급 없음 [확인됨: https://api-docs.deepseek.com/quick_start/rate_limit].
- 무료 여부: 가입 무료 크레딧 액수는 공식 문서에서 못 찾음(가격 페이지엔 granted balance를 먼저 차감한다는 문구뿐) [확인 못 함]. 웹 채팅 무료는 2차 자료만(검색 요약 기준, 예: https://dev.to/hassann/how-to-use-deepseek-v4-for-free--4470 , 직접 열람 안 함) [부분 확인]. 최소 충전액·결제수단은 공식 확인 못 함(검색 요약 기준 2차: $2~5). API 키 필요: 예.
- 프라이버시: 개인정보 처리방침에 "서버는 중화인민공화국에 위치", 비식별화한 프롬프트를 모델 학습·개선에 쓸 수 있고 앱 설정에서 거부 가능 [확인됨: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html]. API(Open Platform) 약관은 DeepSeek의 학습 사용 여부를 명시하지 않음 [부분 확인]. 한국 개인정보보호위는 2025-02 신규 다운로드를 중단시켰고 2025-04-28 재개(보도: https://yahoo.com/news/deepseek-available-download-again-south-061600430.html) [부분 확인].
- 월 비용(내 계산): 가정 = 작업 1건에 모델 호출 10회, 호출당 입력 20k·출력 1.5k 토큰(건당 입력 200k·출력 15k). flash 피크가격 캐시 없이 약 $0.08/건, 캐시 70% 적중이면 약 $0.04/건, pro는 약 $0.14~0.32/건. 월 30건이면 flash $1~2.5, pro $4~10. 에이전트가 루프에 빠지면 몇 배 → 선불 잔액으로 상한을 건다.
- 연결: OpenAI형 `https://api.deepseek.com`, Anthropic형 `https://api.deepseek.com/anthropic`. Claude Code는 DeepSeek 공식 연동 목록에 있고 Aider·Cline은 DeepSeek 문서에 언급 없음(https://api-docs.deepseek.com/). Aider 문서는 "DeepSeek R1·V3가 잘 맞음"(https://aider.chat/docs/llms.html, 구 모델명 기준, V4 호환은 확인 못 함).
- 판단 = **조건부 사용**. 조건: (1) T0/T1만, (2) 공개 저장소 코드만·비밀/개인정보 절대 불가, (3) 공식 API+선불 소액($5 안팎), 웹 채팅 자동화 금지(DeepSeek 이용약관 3.5가 봇·스파이더 복제 금지), (4) 브랜치+PR+CI 유지. **로컬 DeepSeek-Coder-V2-Lite는 비추천**: 2024년 모델이고 에이전트용으로 학습됐다는 근거가 없으며 Aider 공식 경고가 그대로 적용됨.

## D. 코드 수정 외 용도 (알림·한 줄 요약·로그 설명·주간 요약·글 초안)
- Gemini API 무료(이미 쓰는 경로): 무료 대상 모델 ID(문서상 Stable) gemini-3.8-flash, gemini-3.6-flash, gemini-3.5-flash-lite, gemini-3.1-flash-lite, 입력·출력 "Free of charge". Gemma 4도 무료 전용 [확인됨: https://ai.google.dev/gemini-api/docs/pricing · https://ai.google.dev/gemini-api/docs/models].
- 한도: 공식 rate-limits 페이지는 모델별 숫자를 싣지 않고 "AI Studio에서 확인"만 안내 [확인됨: https://ai.google.dev/gemini-api/docs/rate-limits]. 블로그의 숫자(RPD 250~1,500 등, 검색 요약 기준 예: https://apidog.com/blog/gemini-api-free-tier/ 는 "Google이 모델별 한도 게시를 중단"이라고만 적음)는 서로 달라 쓰지 말 것 [부분 확인]. AI Studio 화면에서 직접 읽어 저장소 문서에 적어 둘 것.
- 일일 블로그 봇에 영향: (1) 2.5 계열은 2026-09-18부터 "과거에 실제 사용한 사용자"에게만 접근 허용, "until further notice" 제공 → 저장소가 gemini-2.5-* ID를 쓰면 3.x 이전 계획 필요(저장소는 직접 보지 않음) [확인됨: https://ai.google.dev/gemini-api/docs/changelog]. (2) 무료는 입력·출력이 제품 개선에 쓰이고 사람이 읽을 수 있으며 "민감·기밀·개인정보를 무료 서비스에 넣지 말 것"이 약관 문구 [확인됨: https://ai.google.dev/gemini-api/terms]. (3) 3.8·3.6 Flash 유료 단가는 2027-01-01 인상 공지(무료와 무관).
- 결제 계정 연결(선불 최소 $5)하면 학습에 쓰이지 않음. 3.5 Flash-Lite 유료 $0.30/$2.50(1M 토큰)이면 글 1편(입력 2k·출력 3k 토큰 가정)이 약 $0.01 미만(내 계산). "무료 원칙"을 깨므로 운영자 결정 사항 [확인됨: https://ai.google.dev/gemini-api/docs/billing · https://ai.google.dev/gemini-api/terms · https://ai.google.dev/gemini-api/docs/pricing].
- 다른 무료 후보: Cloudflare Workers AI(하루 10,000 Neurons, 학습 미사용; gpt-oss-20b는 입력 18,182·출력 27,273 Neurons/1M 토큰 → 하루 입력 약 55만 또는 출력 약 37만 토큰, 내 계산). Groq(A-2). 로컬 Ollama의 gemma4(PC가 켜져 있을 때만, GitHub Actions에서는 불가). 가장 안전하고 무료인 방법은 AI 없이 문장 템플릿.
- 한국어 품질: 소형 로컬·Gemini 모두 2026년 한국어 비교 자료를 신뢰할 만하게 못 찾음 [확인 못 함]. 이미 한국어 글을 쓰는 봇의 실제 결과가 가장 좋은 증거. 로컬 모델은 같은 문장 5개로 직접 시험.

## E. 위험과 규칙 (가이드에 넣을 것)
- 절대 보내지 말 것: API 키·토큰·비밀번호·`.env`, 개인정보(이름·메일·전화·주소·결제), 비공개 문서, 로그 원문. GitHub는 등록된 비밀을 로그에서 가리지만 큰 비밀 우회 방식은 가리지 않으므로 로그는 사람이 훑거나 가공한 뒤 전송 [확인됨: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions].
- 무료 입력이 학습·열람에 쓰이는가(근거 URL은 A-2·C·D절): Gemini API 무료=예, 사람 검토 가능 [확인됨]. Antigravity 개인=예(설정으로 선택 가능하다고 약관에 있으나 효과는 포럼 논쟁) [확인됨/부분]. Copilot Free=예(2026-04-24~, 거부 가능) [확인됨]. Mistral Studio Free=예, Vibe=기본 예·옵트아웃 가능 [확인됨]. Kiro Free=예(옵트아웃) [확인됨]. Cline·OpenCode 무료 모델=가능 [확인됨]. OpenRouter 무료=제공자별 [부분 확인]. DeepSeek=처리방침상 가능(서버 중국) [확인됨]. Jules=비공개 저장소는 아님 [확인됨]. Cloudflare=아님 [확인됨]. Groq=기본 비보관(학습 문구 못 찾음) [부분 확인]. ChatGPT/Codex Free·Cerebras=[확인 못 함]. 로컬 모델=PC 밖으로 안 나감(Ollama cloud 모델은 외부 전송).
- 자동화·약관: 채팅 웹 UI를 스크립트·매크로로 조작 금지(DeepSeek 이용약관 3.5(3)가 봇·스파이더 금지, Antigravity §6이 제3자 도구 접속 금지·계정 정지 사유) [확인됨: https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html · https://antigravity.google/terms]. 공식 API·공식 CLI/앱만 사용. 한 서비스 로그인을 다른 도구에 빌려 쓰지 말 것(Antigravity OAuth를 OpenCode/OpenClaw에 연결해 정지된 사례, 포럼·2차: https://discuss.ai.google.dev/t/antigravity-ban/135583) [부분 확인]. 한도 우회용 다중 계정·다중 프로젝트는 하지 말 것(Gemini API 약관에서 해당 문구는 못 찾았으나 제재 위험, 의견). `openrouter/free` 같은 자동 전환 라우터는 제외 원칙 유지.
- 안전 장치: 브랜치+PR+CI 유지. 에이전트를 돌릴 폴더에는 `.env`·키 파일이 없어야 하고 환경변수에도 토큰을 넣지 말 것. 도구는 "명령 실행 전 확인" 모드로, GitHub 연결은 특정 저장소 1개로 제한. 에이전트가 읽는 이슈·웹페이지·로그 속 지시문은 따르지 않도록 PR 검토에서 확인(프롬프트 주입 위험, 일반 지식). 회사 PC·회사 계정에서는 규정 확인 전 외부 무료 AI 로그인·코드 전송 금지(의견).
- 변경 속도: 올해만 Gemini CLI 무료 종료(06-18), Qwen OAuth 종료(04-15), Roo Code 종료(05-15), Devstral API 폐기, Gemini 2.5 접근 제한(09-18), Copilot 학습 정책 변경(04-24)이 있었음 → 월 1회 한도·약관 점검을 운영 절차에 넣을 것.
| T 등급(제안) | 무료 AI 권한 | 필요한 조건 |
|---|---|---|
| T0 문서·테스트 | 직접 수정 가능 | 브랜치+PR, CI 통과, 운영자가 변경 파일 목록(비밀·워크플로 파일 포함 여부) 확인 |
| T1 모듈·프롬프트 1개 | 직접 수정 가능 | 수정 범위를 지정 파일로 한정, 테스트 함께 추가, PR 설명에 변경 요약, CI 통과 |
| T2 워크플로·파이프라인 핵심 | 초안(diff)까지만 | CI 통과 + 다른 회사 AI의 읽기 전용 검토 1회 + 운영자 승인 |
| T3 | 직접 수정 금지(분석·설명까지) | 운영자 명시 승인 후 사람이 반영 |
- `.github/workflows/`·권한(permissions)·비밀 참조·배포 단계는 항상 T2 이상으로 취급한다(제안).

## F. 추천 구성 (싼 것·쉬운 것부터)
- 0단계 ($0, 지금): AI에 덜 의존하게 만들기. 알림은 템플릿, AI는 선택 기능. 현 Gemini 키는 글쓰기·요약 전용으로 두고 모델 ID 점검(D절). 한도 수치를 AI Studio에서 읽어 문서화.
- 1단계 ($0, 설치 없음): Jules로 T0/T1 소규모 수정. 순서: https://jules.google/ 접속 → 개인 Gmail 로그인 → 개인정보 안내 동의 → GitHub 연결은 저장소 1개만 → 작업 입력 → 계획 승인 → "Create branch" → GitHub에서 PR → CI → 운영자 병합. 하루 15건 이내. 설명용 채팅은 Copilot Free Chat. 한도 도달 시: 그날은 중단하고 24시간 뒤 재개(자동 전환 금지).
- 2단계 ($0, 설치 있음): 데스크톱 프로그램 개발용으로 Antigravity App/CLI 무료 또는 VS Code+Copilot Free 에이전트. CLI는 PowerShell 한 줄 설치 스크립트만 제공되므로 비개발자는 앱 설치 파일(https://antigravity.google/download)을 권장(의견). 설치 직후 학습·데이터 설정부터 끄고(Copilot은 Privacy 토글) 공식 클라이언트만 쓴다. 주간 한도가 소진되면 다음 리셋까지 보류하거나 1단계로 수동 이동. 큰 작업은 PR 단위로 잘게 쪼갤 것.
- 3단계 (소액, 무료 한도가 계속 막힐 때만): DeepSeek API 선불 $5 안팎+Aider 또는 Cline(월 약 $1~10, 내 계산, C절 조건 준수). 대안: Copilot Pro $10/월(신규 가입 일시 중단 공지가 있었고 현재 상태는 못 확인), ClinePass $9.99/월, Mistral Vibe Pro $14.99/월 [확인됨: https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/ · https://docs.cline.bot/getting-started/what-is-cline · https://mistral.ai/pricing].
- 로컬 모델: 코드 수정용으로는 권하지 않음. 알림·요약 실험(gemma4:e4b/12b)만, 사양 확인 후 선택.
- 한도에 닿았을 때 공통 규칙: 멈춤 → 다음 리셋 대기 → 수동으로 다른 도구 선택 → 그래도 급하면 3단계. 규칙(브랜치+PR+CI, T 등급)을 풀어서 해결하지 않는다.
- 운영자가 정할 것: (1) 월 소액($5~10) 허용 여부, (2) 개인 Google·GitHub 계정으로 Jules/Antigravity 연결 허용, (3) T2 검토에 쓸 "다른 회사 AI"(예: Copilot Free 채팅 또는 Gemini) 지정.

## 확인하지 못한 것
- Antigravity 무료 주간 한도 수치·한국 계정 이용 가능 여부·11-02 모델 제거 반영 여부. Jules 한국 이용·실제 사용 모델(문서는 Gemini 2.5 Pro)·테스트 실행. Copilot Free의 AI Credits 허용량·에이전트 한도·모델 목록 불일치. Cursor·Devin Free 수치.
- Gemini API 무료 모델별 RPM/RPD(AI Studio 로그인 화면에만 표시). Mistral·Cerebras·Groq 무료의 정확한 한도, NVIDIA 공식 수치, OpenCode 무료 모델의 가입 조건.
- ChatGPT Free·Codex의 데이터 학습 정책, Codex CLI 무료 여부(openai.com 403), Google AI Pro 가격(403).
- DeepSeek: 가입 무료 크레딧, 최소 충전액·결제수단, API 데이터의 학습 사용 여부, deepseek-chat 별칭의 실제 중단 여부, "Coder" 라인 공식 종료 문구.
- 로컬: Windows CPU 전용 속도, gpt-oss-20b·Gemma 4·ornith 등의 Aider/Cline 실제 편집 성공률, 한국어 품질 비교.
- 제3자(블로그·포럼·뉴스) 요금·한도 보도는 공식 페이지와 어긋날 수 있다.
