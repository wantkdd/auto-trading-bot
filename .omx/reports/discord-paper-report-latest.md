📊 자동매매 가정 일일 리포트 (NO-ORDER)
실거래/브로커/API주문 없음. 오늘 종가 기준으로 '매매했다면' 로그만 기록합니다.

**Champion 관찰**
- 전략: `AAPL_0.3_GLD_0.7`
- 관찰일: `9 / 12`
- 가상자산: `$9,327.75`
- 누적수익률: `-6.72%`
- 최대낙폭: `-6.72%`

**오늘 매매 가정**
- 판단: `would_rebalance`
- would buy/sell 통과: `0`건
- 거절: `0`건
- 가정 거래금액: `$0.00`

**장중 5분 로그 요약**
- 저장된 장중 체크: `18`회
- 최근 장중 상태: `ok`
- 판단 변화 합계: `64`
- 특이 움직임 합계: `78`
- 최근 체크 시각: `2026-06-11T19:40:38.982036+00:00`

**보정/튜닝 상태**
- 코드는 자동 자기수정하지 않음: 로그 기반 후보를 만들고 안전 게이트 통과 여부만 기록합니다.
- adaptive 후보 상태: `review`
- adaptive 중앙 초과수익: `5.40%`
- static 기준 중앙 초과수익: `8.53%`
- adaptive 최악 MDD: `-23.20%`
- 자동 교체/실거래 반영: `False`

**방대한 시장 데이터 게이트**
- 상태: `review`
- 사용 가능 자산: `153`개
- breadth coverage: `100.00%`
- regime: `conflicted`
- 권고: `review_only_market_signals_are_conflicted`
- 자동 전략/코드 반영: `False`

**브로커 API 연결 준비도**
- API preflight: `blocked`
- adapter ticket 수: `0`
- 남은 API 연결 blocker: `7`개
- 주문 생성/전송 시도: `False` / `False`

**시장 스캔 Challenger**
- 동적 universe: `150`종목 선정 / `297`종목 가격검증 / `536`개 원천심볼
- 우선 관찰 10종목: `SPY, QQQ, DIA, AAPL, GLD, MU, NVDA, TSLA, MSFT, AMD`
- 시장 top: `None`
- 추적 challenger: `None`
- challenger 관찰일: `0`
- challenger 가상자산: `unknown`
- challenger 수익률: `unknown`
- challenger MDD: `unknown`

**퀀트 paper 후보**
- 상태: `review`
- 후보: `quant_momentum_top5_defensive`
- regime: `conflicted`
- 비중: `SHY:35%, IEF:11%, AMD:9%, DELL:9%, FTNT:9%, HPE:9%`
- quant 관찰일: `4`
- quant 수익률: `1.48%`
- 자동 교체/실거래 반영: `False`

**안전 게이트**
- no-order gate: `pass`
- paper ready: `True`
- live authorized: `False`
- 남은 live blockers: `13`개