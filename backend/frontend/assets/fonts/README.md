# PDF용 한글 폰트

사내에서 사용 허가된 TTF 또는 OTF 폰트를 이 디렉터리에 넣으세요. 폰트 파일 자체는 Git에 커밋하지 않습니다.

기본 설정은 다음 파일을 찾습니다.

```text
frontend/assets/fonts/CompanyKoreanFont.ttf
```

다른 파일명이나 폰트 패밀리를 사용할 때는 실행 전에 환경변수를 설정하세요.

```powershell
$env:KANGGAEMI_PDF_FONT_FILE="CorpFont.otf"
$env:KANGGAEMI_PDF_FONT_FAMILY="Corp Font"
```

폰트를 다른 디렉터리에 둘 경우 `KANGGAEMI_PDF_FONT_DIR`도 설정할 수 있습니다. 파일이 없거나 확장자가 `.ttf`/`.otf`가 아니면 PDF 생성 버튼을 눌렀을 때 필요한 경로를 포함한 오류가 표시됩니다.

환경변수를 사용하지 않은 상태에서 이 디렉터리에 TTF/OTF 파일이 정확히 하나만 있으면 해당 파일을 자동 선택합니다. 여러 폰트가 있으면 `KANGGAEMI_PDF_FONT_FILE`을 명시해야 합니다. 환경변수는 Streamlit을 실행하는 동일한 터미널에서 먼저 설정하고, 이미 서버가 실행 중이면 재시작해야 합니다.
