# 투자 전략 리포트 Streamlit 프론트엔드

실제 LangGraph 어댑터와 에이전트 없이 실행 가능한 Mock 어댑터를 제공합니다. 노드 목록과 실행 순서, 리포트 섹션은 `app/core/node_specs.yaml`에서 읽습니다.

## 설치 및 실행

백엔드 디렉터리에서 다음을 실행합니다.

```powershell
python -m pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Mock 노드 간 지연시간은 기본 0.45초이며 `KANGGAEMI_MOCK_DELAY_SECONDS` 환경변수로 바꿀 수 있습니다.

## 실제 에이전트 연결

사이드바의 `실제 에이전트 (LangGraph)`를 선택하면 백엔드의 `build_investment_report_graph`를 실행합니다. LangGraph의 `tasks` 스트림을 `node_start`, `node_complete`, `final`, `error` 이벤트로 변환합니다.

- `.env`에 유효한 `DATABASE_URL`과 `OPENAI_API_KEY`가 필요합니다.
- `DATABASE_URL`은 PostgresSaver를 사용할 수 있는 PostgreSQL URL이어야 합니다.
- 체크포인터 테이블을 아직 만들지 않았다면 최초 실행에만 `PostgresSaver 테이블 초기화`를 선택합니다.
- 실제 그래프에 아직 포함되지 않은 YAML 노드는 진행 표시만 Mock으로 보완합니다. 실제 그래프 오류나 인증 오류는 Mock으로 숨기지 않고 `error` 이벤트로 표시합니다.

기본 어댑터는 실제 LangGraph입니다. Mock을 기본값으로 사용하려면 다음을 설정합니다.

```powershell
$env:KANGGAEMI_AGENT_ADAPTER="mock"
python -m streamlit run frontend/app.py
```

## PDF용 한글 폰트

사내에서 사용 허가된 폰트를 기본 경로에 넣습니다. 폰트 파일은 Git에서 제외됩니다.

```text
frontend/assets/fonts/CompanyKoreanFont.ttf
```

파일명이나 패밀리가 다르면 실행 전에 설정합니다.

```powershell
$env:KANGGAEMI_PDF_FONT_FILE="CorpFont.otf"
$env:KANGGAEMI_PDF_FONT_FAMILY="Corp Font"
python -m streamlit run frontend/app.py
```

환경변수는 실행 중인 프로세스에 나중에 전달되지 않으므로 Streamlit 실행 전에 같은 PowerShell에서 설정해야 합니다. 폰트 디렉터리에 TTF/OTF 파일이 하나만 있으면 파일명 환경변수 없이도 자동 선택합니다.

상세 내용은 `frontend/assets/fonts/README.md`를 참고하세요. 폰트가 없으면 화면과 Markdown 리포트는 정상 동작하고, `PDF 생성`을 누를 때 필요한 경로가 포함된 오류를 보여줍니다.

## Windows의 WeasyPrint

WeasyPrint Python 패키지 외에 Pango 런타임이 필요할 수 있습니다. 공식 WeasyPrint Windows 안내에 따라 MSYS2와 Pango를 설치한 후, DLL을 찾지 못하면 해당 경로를 지정합니다.

```powershell
$env:WEASYPRINT_DLL_DIRECTORIES="C:\\msys64\\mingw64\\bin"
```

PDF는 리포트 실행 때 자동 생성하지 않습니다. `PDF 생성`을 클릭한 뒤 나타나는 `PDF 다운로드` 버튼으로 저장합니다.

## 어댑터 경계

`frontend.adapters.base.AgentEventAdapter`의 `stream(query, as_of_date)`가 UI가 의존하는 유일한 실행 경계입니다. `LangGraphAgentAdapter`와 `MockAgentAdapter`가 모두 같은 프로토콜을 구현합니다.
