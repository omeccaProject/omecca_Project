const apiKey = process.env.ITS_API_KEY;

if (!apiKey) {
  console.error("ITS_API_KEY가 설정되지 않았습니다.");
  process.exit(1);
}

const params = new URLSearchParams({
  apiKey,
  type: "its",
  cctvType: "1",
  minX: "126.70",
  maxX: "127.25",
  minY: "37.40",
  maxY: "37.75",
  getType: "json",
});

const url = `https://openapi.its.go.kr:9443/cctvInfo?${params}`;

console.log("ITS CCTV API 요청 시작");
console.log("서울 범위: 126.70~127.25 / 37.40~37.75");

try {
  const response = await fetch(url);

  console.log("HTTP 상태:", response.status);

  const text = await response.text();

  if (!response.ok) {
    console.error("API 요청 실패:");
    console.error(text);
    process.exit(1);
  }

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    console.log("JSON 파싱 실패. 원본 응답 일부:");
    console.log(text.slice(0, 3000));
    process.exit(0);
  }

  console.log("\n===== 응답 구조 =====");
  console.log(JSON.stringify(data, null, 2).slice(0, 10000));

} catch (error) {
  console.error("네트워크 오류:", error.message);
}