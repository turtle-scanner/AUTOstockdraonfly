# -*- coding: utf-8 -*-
"""mojito 라이브러리를 활용해 한국투자증권 해외계좌 정보를 조회하고
외화예수금, 출금가능 외화금액, 출금가능 원화금액을 표시하는 예시 스크립트.

필수 패키지: mojito (pip install mojito)
"""

import os
import pprint

# ---------------------------------------------------------------------------
# mojito 라이브러리 임포트 (설치되지 않은 경우 안내)
# ---------------------------------------------------------------------------
try:
    import mojito
except ImportError as e:
    raise ImportError(
        "mojito 패키지가 설치되지 않았습니다. 'pip install mojito' 로 설치하세요."
    ) from e

# ---------------------------------------------------------------------------
# API 키 파일 경로 설정 (프로젝트 루트에 'koreainvestment.key' 가 있다고 가정)
# ---------------------------------------------------------------------------
key_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../koreainvestment.key")
)

if not os.path.exists(key_path):
    raise FileNotFoundError(f"키 파일을 찾을 수 없습니다: {key_path}")

with open(key_path, encoding="utf-8") as f:
    lines = f.readlines()

if len(lines) < 3:
    raise ValueError(
        "키 파일에 API key, secret, account number 가 모두 포함되어 있어야 합니다."
    )

api_key = lines[0].strip()
api_secret = lines[1].strip()
account_no = lines[2].strip()

# ---------------------------------------------------------------------------
# 한국투자증권 브로커 객체 생성 (미국 NASDAQ 거래소 지정)
# ---------------------------------------------------------------------------
broker = mojito.KoreaInvestment(
    api_key=api_key,
    api_secret=api_secret,
    acc_no=account_no,
    exchange="나스닥",  # 미국 NASDAQ
)

# ---------------------------------------------------------------------------
# 해외계좌 정보 파싱 헬퍼 함수
# ---------------------------------------------------------------------------
def display_overseas_account_info(resp: dict) -> None:
    """응답(resp)에서 외화예수금, 출금가능 외화금액, 출금가능 원화금액을 추출·출력한다.
    
    주요 필드:
    - 외화예수금 (USD 현금)      : output2['frcr_dncl_amt_2']
    - 출금가능 외화금액 (USD)    : output2['frcr_drwg_psbl_amt_1']
    - 출금가능 원화금액 (KRW)    : output3['wdrw_psbl_tot_amt']
    """
    foreign_cash = withdrawable_foreign = withdrawable_krw = 0.0

    if resp.get("rt_cd") == "0":
        # 외화 관련 정보는 output2에 존재
        out2 = resp.get("output2", [])
        if out2:
            data = out2[0]
            foreign_cash = float(data.get("frcr_dncl_amt_2", "0"))
            withdrawable_foreign = float(data.get("frcr_drwg_psbl_amt_1", "0"))
        # 원화 출금가능 금액은 output3에 존재
        out3 = resp.get("output3", {})
        withdrawable_krw = float(out3.get("wdrw_psbl_tot_amt", "0"))
    else:
        print("⚠️ API 응답 오류 또는 비정상 상태")

    print("\n▶ 해외계좌 상세 정보")
    print(f"  • 외화예수금 (USD 현금)      : {foreign_cash:,.2f} USD")
    print(f"  • 출금가능 외화금액 (USD)    : {withdrawable_foreign:,.2f} USD")
    print(f"  • 출금가능 원화금액 (KRW)    : {withdrawable_krw:,.0f} 원")

# ---------------------------------------------------------------------------
# 메인 실행부
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 전체 잔고 구조를 그대로 출력 (디버깅용)
    full_balance = broker.fetch_present_balance()
    print("▶ 해외계좌 전체 응답 결과")
    pprint.pprint(full_balance)

    # 원하는 핵심 정보만 정리해서 보여줌
    display_overseas_account_info(full_balance)
