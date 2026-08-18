// 3분할 관제 모드 - 지금 이 창(=1번 모니터, 평소의 통합 관제 대시보드 화면 그대로)은 그냥
// 놔두고, 새 창 2개만 열어 나머지 모니터 2대에 배치한다.
//   1번 모니터: (새로 열지 않음) 지금 이 창 그대로 - 이미 보고 있는 화면이 곧 1번 모니터다.
//   2번 모니터: CCTV 그리드 뷰어, 카메라 1~9, 화면 전체를 채움 (?view=monitor2)
//   3번 모니터: CCTV 그리드 뷰어, 카메라 10~18, 화면 전체를 채움 (?view=monitor3)
//
// "이 창을 저 모니터로 보내라"는 동작 자체는 표준 window.open()만으로는 할 수 없다 -
// Window Management API(window.getScreenDetails)가 있어야 실제 모니터별 좌표를 알 수
// 있는데, 이 API는 Chrome/Edge 계열에서만 지원되고 첫 호출 시 사용자의 권한 허용이
// 필요하다(반드시 클릭 등 사용자 제스처 안에서 호출해야 브라우저가 프롬프트를 띄운다).
// 지원하지 않는 브라우저이거나 권한이 거부되면, 그래도 창 2개는 띄우되 화면 왼쪽부터
// 나란히 배치만 해두고, 사용자가 각 창을 해당 모니터로 직접 드래그하도록 안내한다
// (한 번 옮겨두면 이후에는 대부분 OS/브라우저가 마지막 창 위치를 기억한다).

async function getSortedScreensIfSupported() {
  if (typeof window.getScreenDetails !== 'function') return null
  try {
    const details = await window.getScreenDetails()
    // left(가로 위치) 기준으로 정렬해서 "왼쪽부터 1/2/3번 모니터"로 다루기 쉽게 만든다.
    return [...details.screens].sort((a, b) => a.left - b.left)
  } catch (err) {
    // 권한 거부(NotAllowedError) 또는 사용자 제스처 밖에서 호출된 경우 등.
    console.warn('[SPLIT SCREEN] 다중 모니터 배치 권한을 사용할 수 없어 수동 배치로 대체합니다.', err)
    return null
  }
}

function openWindowAt(url, name, rect) {
  const features = [
    'noopener',
    'noreferrer',
    `left=${Math.round(rect.left)}`,
    `top=${Math.round(rect.top)}`,
    `width=${Math.round(rect.width)}`,
    `height=${Math.round(rect.height)}`,
  ].join(',')
  return window.open(url, name, features)
}

// 반환값: { placed: 실제 모니터 좌표에 정확히 배치됐는지, screenCount: 인식된 화면 수, opened: 실제로 열린 창 수 }
export async function openSplitScreenMode() {
  const base = `${window.location.origin}${window.location.pathname}`
  const monitors = [
    { name: 'omecca_monitor2', url: `${base}?view=monitor2`, label: '2번 모니터 (CCTV 1~9)' },
    { name: 'omecca_monitor3', url: `${base}?view=monitor3`, label: '3번 모니터 (CCTV 10~18)' },
  ]

  // [중요] 창은 반드시 여기서, 이 함수의 다른 어떤 await보다도 먼저 "동기적으로" 다 열어야
  // 한다. 브라우저의 팝업 차단 정책은 "사용자 클릭을 처리하는 바로 그 동기 실행 구간"에만
  // 관대하다 - 만약 window.getScreenDetails() 같은 비동기 권한 요청을 먼저 await한 뒤에
  // window.open()을 부르면, 첫 번째 창은 열려도 두 번째 창은 "사용자 제스처가 이미
  // 소비/만료됐다"는 이유로 팝업 차단기에 막힐 수 있다. 그래서 일단 대략적인(화면을
  // 절반씩 나눈) 위치로 둘 다 먼저 열고, 실제 모니터 좌표는 그 다음에(비동기로) 알아내서
  // 이미 열려 있는 창들을 moveTo/resizeTo로 재배치한다.
  const fallbackWidth = Math.round((window.screen.availWidth || 1920) / monitors.length)
  const fallbackHeight = window.screen.availHeight || 1080
  const handles = monitors.map((m, i) =>
    openWindowAt(m.url, m.name, { left: fallbackWidth * i, top: 0, width: fallbackWidth, height: fallbackHeight })
  )
  const openedCount = handles.filter(Boolean).length

  if (openedCount === 0) {
    // 팝업 차단기가 전부 막았다 - 자동 재시도는 의미가 없다(사용자가 팝업을 허용해야 함).
    return { placed: false, screenCount: 0, opened: 0, blocked: true }
  }

  const screens = await getSortedScreensIfSupported()
  if (!screens || screens.length < 2) {
    // 자동 배치 불가(권한 거부/미지원 브라우저/모니터 2대 미만 인식) - 창은 이미 화면 안에
    // 나란히 열려 있으니, 사용자가 각자 모니터로 드래그하면 된다.
    return { placed: false, screenCount: screens ? screens.length : 0, opened: openedCount }
  }

  // 지금 이 창(1번 모니터, 대시보드 화면)이 떠 있는 화면을 찾아서 "이미 쓰고 있는 화면"으로
  // 보고 후보에서 제외한다 - 그래야 남은 화면들을 2/3번 모니터에 순서대로 배정할 수 있다.
  // window.screenLeft/screenTop(구형은 screenX/screenY)로 이 창의 현재 위치를 읽는다.
  const currentLeft = window.screenLeft ?? window.screenX ?? 0
  const currentTop = window.screenTop ?? window.screenY ?? 0
  const currentScreen = screens.find(
    (s) => currentLeft >= s.left && currentLeft < s.left + s.width && currentTop >= s.top && currentTop < s.top + s.height
  )
  const otherScreens = currentScreen ? screens.filter((s) => s !== currentScreen) : screens

  if (otherScreens.length < monitors.length) {
    // 이 창이 있는 화면을 빼고 나면 2/3번 모니터에 배정할 화면이 부족하다(예: 실제로
    // 모니터가 2대뿐인 경우) - 수동 배치로 대체한다.
    return { placed: false, screenCount: screens.length, opened: openedCount }
  }

  handles.forEach((win, i) => {
    if (!win || win.closed) return
    const s = otherScreens[i]
    try {
      win.moveTo(s.left, s.top)
      win.resizeTo(s.width, s.height)
    } catch (err) {
      console.warn('[SPLIT SCREEN] 창 위치를 실제 모니터 좌표로 옮기지 못했습니다:', err)
    }
  })
  return { placed: true, screenCount: screens.length, opened: openedCount }
}
