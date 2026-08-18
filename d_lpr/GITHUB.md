# GitHub 올리는 방법

저장소: https://github.com/omeccaProject/omecca_Project

내 모듈을 저장소 안 **`omeca-lpr/` 폴더**로 올린다. 팀원들 코드와 폴더 단위로
분리되어 있어 충돌이 거의 안 난다.

---

## 0단계 · 준비 (최초 1회만)

PowerShell을 열고 Git이 있는지 확인한다.

```powershell
git --version
```

없다고 나오면 설치한다.

```powershell
winget install Git.Git
```

설치 후 **PowerShell을 새로 열고** 이름·이메일을 등록한다 (커밋에 기록되는 정보).

```powershell
git config --global user.name "박지원"
git config --global user.email "hbcomlove1004@gmail.com"
```

---

## 1단계 · 저장소 내려받기

바탕화면에 저장소를 통째로 받는다.

```powershell
cd C:\Users\박지원\Desktop
git clone https://github.com/omeccaProject/omecca_Project.git
```

로그인 창이 뜨면 GitHub 계정으로 로그인한다.
(비밀번호를 물어보면 실패한다 → 아래 "로그인이 안 될 때" 참고)

`warning: You appear to have cloned an empty repository` 가 떠도 정상이다.
아직 아무도 안 올린 것뿐이다.

---

## 2단계 · 내 폴더 복사

```powershell
cd C:\Users\박지원\Desktop\omecca_Project

robocopy "C:\Users\박지원\Desktop\d\omeca-lpr" "omeca-lpr" /E /XD .venv64 __pycache__ .pytest_cache data output output_desktop realtest /XF *.db *.log
```

`/XD` 뒤가 **제외할 폴더**다. `.venv64`(1.5GB)를 빼는 게 핵심이다.

> robocopy는 성공해도 종료 코드가 1이라 빨간 글씨가 보일 수 있는데 정상이다.

복사됐는지 확인한다.

```powershell
dir omeca-lpr
```

`app`, `tests`, `README.md`, `try_lpr.py` 등이 보이면 성공이다.

---

## 3단계 · 올리기

```powershell
git add omeca-lpr
git status
```

`git status` 결과에 **`.venv64`나 `torch` 같은 게 보이면 멈추고** 다시 확인한다.
(정상이라면 51개 파일 정도만 보인다)

이상 없으면 커밋하고 올린다.

```powershell
git commit -m "번호판 인식(LPR) 및 차량 위반 감지 모듈 추가 - 박지원"
git push
```

`push` 에서 오류가 나면 저장소가 비어 있어서다. 아래를 실행한다.

```powershell
git branch -M main
git push -u origin main
```

---

## 4단계 · 확인

브라우저에서 https://github.com/omeccaProject/omecca_Project 를 열어
`omeca-lpr` 폴더가 보이면 끝이다. 안에 들어가면 README가 자동으로 표시된다.

---

## 다음부터 (수정한 걸 다시 올릴 때)

```powershell
cd C:\Users\박지원\Desktop\omecca_Project

# 팀원이 올린 것 먼저 받기
git pull

# 바뀐 내 코드 복사
robocopy "C:\Users\박지원\Desktop\d\omeca-lpr" "omeca-lpr" /E /XD .venv64 __pycache__ .pytest_cache data output output_desktop realtest /XF *.db *.log

git add omeca-lpr
git commit -m "무엇을 바꿨는지 한 줄로"
git push
```

**`git pull` 을 먼저 하는 습관을 들이면** 충돌이 거의 안 난다.

---

## 문제가 생겼을 때

### 로그인이 안 될 때

GitHub는 2021년부터 비밀번호 로그인을 막았다. 두 가지 방법이 있다.

**방법 A — GitHub Desktop 쓰기 (쉬움)**

https://desktop.github.com 에서 설치하고 로그인하면 인증이 자동으로 된다.
이후 PowerShell에서 `git push` 가 그냥 된다.

**방법 B — 토큰 만들기**

1. https://github.com/settings/tokens → *Generate new token (classic)*
2. `repo` 체크 → 생성 → **토큰 문자열 복사** (다시 못 봄)
3. `git push` 할 때 비밀번호 자리에 토큰을 붙여넣는다

### `push` 가 거부될 때 (rejected)

팀원이 먼저 올린 게 있는 경우다.

```powershell
git pull --rebase
git push
```

### 실수로 `.venv64` 를 올렸을 때

```powershell
git rm -r --cached omeca-lpr/.venv64
git commit -m "가상환경 제거"
git push
```

### 저장소에 접근 권한이 없다고 할 때

`omeccaProject` 조직에 초대받아야 한다. 팀장님(김관용)께 GitHub 아이디를
알려드리고 **Write 권한**으로 초대해달라고 요청한다.

---

## 팀원들에게 전달할 내용

> `omeca-lpr/` 에 번호판 인식(④)과 신호위반·불법유턴 감지(⑦) 모듈을 올렸습니다.
> 연동 방법은 `omeca-lpr/README.md` **2장 "팀 연동 규격"** 을 봐주세요.
>
> - 차량 탐지 결과를 `Detection(cam_id, track_id, cls, bbox, timestamp, frame_no)`
>   형태로 `ViolationEngine.process(det, frame)` 에 넣으면 됩니다.
> - 위반 이벤트는 `/ws` 구독 또는 `/api/violations` 로 받으시면 됩니다.
>
> 실행: `pip install -r requirements.txt` 후 `python run_demo.py --reset --serve`
>
> `.venv64`(가상환경)는 올리지 않았으니 각자 만드셔야 합니다.
