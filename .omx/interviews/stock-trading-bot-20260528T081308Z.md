# Deep Interview Transcript: Stock Trading Bot

- Profile: standard
- Context type: greenfield
- Final ambiguity: 12.9%
- Threshold: 20%
- Context snapshot: ``

## Rounds
1. Intent/risk posture → `검증 우선`: 백테스트·모의투자에서 먼저 증명.
2. Success criteria → `보수적 검증 패키지`: 백테스트, 워크포워드/기간분리, 모의투자, 손실한도 테스트.
3. Contrarian pressure / risk boundary → `중립적`: 초기 실거래 단계에서는 -10%~-20% 범위에 경고/축소/중지 로직 필요. 단, MVP 실거래 자동주문은 제외.
4. Non-goals → `실거래 자동주문 제외`, `레버리지/미수/공매도 제외`.
5. Decision boundaries → Agent may decide tech stack, data-source candidates, strategy candidates, validation metrics, project structure. User emphasized rigorous research and accuracy because real money may later be involved.
6. Market scope → `한국/미국 둘 다 후보 조사`: compare and recommend MVP market.

## Pressure-pass finding
The assumption that robust validation permits live trading was challenged: even after validation, live losses can occur. The spec therefore separates MVP validation from live auto-ordering and requires an explicit later approval gate.
