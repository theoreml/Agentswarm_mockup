import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

COMMUNITY_PROMPTS = {
    "mom": {
        "name": "맘카페",
        "system": """너는 육아·살림 맘카페(네이버 카페 스타일) 커뮤니티의 여러 회원들을 시뮬레이션하는 AI야.
각 회원은 30-45세 주부/엄마로, 가성비·안전성·추천 경험에 민감하다.
말투: 친근하고 공감 중심, 이모티콘 자주 씀(ㅠㅠ, ㅎㅎ, 😊, ~), 맞춤법 약간 틀려도 됨.
관심사: 세일/쿠폰, 올영/쿠팡 비교, 성분 안전성, 아이/가족 영향, 후기 공유.
자사몰보다 올리브영/쿠팡 선호 성향.""",
        "user_tmpl": """제품: {name} / 가격: {price}원 / {desc}

맘카페 대화 4명. 각 메시지는 30자 이내로 짧게.
JSON 배열만 출력 (마크다운 없이):
[{{"nick":"닉네임","text":"메시지(30자이내)","time":"오후 H:MM"}}]"""
    },
    "dc": {
        "name": "디시인사이드 뷰티갤",
        "system": """너는 디시인사이드 뷰티갤러리의 익명 유저들을 시뮬레이션하는 AI야.
말투: 직설적, 냉소적, 밈/인터넷 용어 사용(ㄹㅇ, ㅋㅋ, ㄷㄷ), 분석적.
익명 유저는 'ㅇㅇ (IP주소)' 형식, 갤로그 유저는 닉네임.
관심사: 성분 분석, 가성비 비교, 브랜드 마케팅 비판, 대안 제품 추천.
후기는 솔직하고 거침없음. 광고성 제품에 회의적.""",
        "user_tmpl": """제품: {name} / 가격: {price}원 / {desc}

디시 뷰티갤 댓글 4개. 각 댓글 30자 이내.
JSON 배열만 출력 (마크다운 없이):
[{{"nick":"닉","text":"댓글(30자이내)","rec":숫자,"blc":숫자,"no":"3847200"}}]"""
    },
    "fem": {
        "name": "펨코",
        "system": """너는 펨코(Female Community) 유저들을 시뮬레이션하는 AI야.
말투: 논리적, 비판적 소비, 직접적, 유머 있음.
레벨 시스템 있음 (Lv1-15).
관심사: 광고 피로도, 원가 분석, 합리적 소비, 카테고리 트렌드.
자사몰 전환에 부정적, 쿠폰/포인트 선호.""",
        "user_tmpl": """제품: {name} / 가격: {price}원 / {desc}

펨코 댓글 4개. 각 댓글 30자 이내.
JSON 배열만 출력 (마크다운 없이):
[{{"nick":"닉네임","lv":"Lv7","text":"댓글(30자이내)","up":숫자,"down":숫자,"reply":숫자}}]"""
    },
    "insta": {
        "name": "인스타그램",
        "system": """너는 인스타그램 뷰티/스킨케어 해시태그 생태계 분석 전문가야.
제품과 관련된 실제 인스타그램 해시태그 트렌드를 시뮬레이션한다.
각 해시태그는: 게시물 수(추정), 트렌드 방향(up/down/flat), 주요 감성(positive/negative/neutral/mixed), 해당 태그 안에서 실제로 어떤 맥락으로 쓰이는지 한 줄 요약.
브랜드 공식 태그, 성분 태그, 카테고리 태그, 경쟁 비교 태그 등 다양하게 포함.""",
        "user_tmpl": """제품: {name} / 가격: {price}원 / {desc}

아래 두 섹션을 JSON 객체 하나로 출력해줘. 마크다운 없이.

{{
  "hashtags": [  // 6개. 브랜드·성분·카테고리·경쟁비교·가격대·라이프스타일 태그 다양하게
    {{"tag":"#해시태그","posts":숫자,"trend":"up/down/flat","sentiment":"positive/negative/neutral/mixed","context":"20자이내"}}
  ],
  "reactions": [  // 5개. 실제 그 해시태그 피드 안에서 나올 법한 유저 간 상호작용. 멘션·답글·공감 흐름 포함
    {{"handle":"@핸들","text":"코멘트(이모지 포함, 30자이내)","hearts":숫자,"reply_to":"@핸들 또는 null"}}
  ]
}}"""
    }
}

class SimulateRequest(BaseModel):
    name: str
    price: str
    desc: str

def generate_community(community_key: str, name: str, price: str, desc: str):
    cfg = COMMUNITY_PROMPTS[community_key]
    prompt = cfg["user_tmpl"].format(name=name, price=price, desc=desc)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=cfg["system"],
        messages=[{"role": "user", "content": prompt}]
    )
    full_text = response.content[0].text

    # parse JSON — insta returns object {hashtags, reactions}, others return array
    # find outermost { } or [ ]
    clean = full_text.strip()
    obj_start = clean.find("{")
    arr_start = clean.find("[")

    # pick whichever comes first
    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        end = clean.rfind("}")
        clean = clean[obj_start:end+1] if end != -1 else clean[obj_start:]
    elif arr_start != -1:
        end = clean.rfind("]")
        clean = clean[arr_start:end+1] if end != -1 else clean[arr_start:]

    try:
        data = json.loads(clean)
    except Exception as e:
        print(f"JSON parse error for {community_key}: {e}\nRaw: {full_text[:300]}")
        data = [] if community_key != "insta" else {"hashtags": [], "reactions": []}

    return {"community": community_key, "data": data}

@app.post("/simulate")
async def simulate(req: SimulateRequest):
    loop = asyncio.get_event_loop()

    async def event_stream():
        for key in ["mom", "dc", "fem", "insta"]:
            result = await loop.run_in_executor(
                None, generate_community, key, req.name, req.price, req.desc
            )
            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/")
def root():
    return FileResponse(Path(__file__).parent / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
